const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const os = require('os');
const crypto = require('crypto');

let mainWindow;
let pythonProcess = null;

// ==================== Path Helpers ====================

// Python backend path (development vs packaged)
function getPythonBackendPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'python-backend');
  }
  return path.join(__dirname, '..', '..');
}

// User data root: ~/mla_v3/
function getUserDataRoot() {
  return path.join(os.homedir(), 'mla_v3');
}

function getUserConfigDir() {
  return path.join(getUserDataRoot(), 'config');
}

// LLM config file path
function getLlmConfigPath() {
  // Always store user-editable config under ~/mla_v3/config/
  return path.join(getUserConfigDir(), 'llm_config.yaml');
}

function ensureUserLlmConfigExists() {
  const userConfigDir = getUserConfigDir();
  fs.mkdirSync(userConfigDir, { recursive: true });
  const userConfigPath = getLlmConfigPath();
  if (fs.existsSync(userConfigPath)) return userConfigPath;

  // Bootstrap from bundled default (read-only is fine)
  const backendPath = getPythonBackendPath();
  const bundled = path.join(backendPath, 'config', 'run_env_config', 'llm_config.yaml');
  if (fs.existsSync(bundled)) {
    fs.copyFileSync(bundled, userConfigPath);
    return userConfigPath;
  }

  // Last resort: create minimal config
  fs.writeFileSync(
    userConfigPath,
    [
      'temperature: 0',
      'max_tokens: 0',
      'max_context_window: 200000',
      'base_url: ""',
      'api_key: ""',
      'models:',
      '- openai/gpt-4o-mini',
      'multimodal: false',
      'compressor_multimodal: false',
      ''
    ].join('\n'),
    'utf-8'
  );
  return userConfigPath;
}

// Skills library path: ~/mla_v3/skills_library/
function getSkillsLibraryPath() {
  return path.join(getUserDataRoot(), 'skills_library');
}

// Agent system library (user import): ~/mla_v3/agent_library/
function getUserAgentLibraryPath() {
  return path.join(getUserDataRoot(), 'agent_library');
}

// Conversations path: ~/mla_v3/conversations/
function getConversationsPath() {
  return path.join(getUserDataRoot(), 'conversations');
}

function safeReadJson(filePath) {
  try {
    const content = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(content);
  } catch (e) {
    return null;
  }
}

function pickPreviewFromShareContext(data) {
  // Prefer latest instruction in `current`, fallback to last `history`
  const currentInstructions = data?.current?.instructions;
  if (Array.isArray(currentInstructions) && currentInstructions.length > 0) {
    const last = currentInstructions[currentInstructions.length - 1];
    if (last?.instruction) return String(last.instruction);
  }
  const history = data?.history;
  if (Array.isArray(history) && history.length > 0) {
    const lastTurn = history[history.length - 1];
    const lastInst = Array.isArray(lastTurn?.instructions) ? lastTurn.instructions[lastTurn.instructions.length - 1] : null;
    if (lastInst?.instruction) return String(lastInst.instruction);
  }
  return '';
}

function computeTaskNameForConversation(taskId) {
  // Must match `core/hierarchy_manager.py`
  const taskHash = crypto.createHash('md5').update(String(taskId)).digest('hex').slice(0, 8);
  const taskFolder = path.basename(String(taskId));
  return `${taskHash}_${taskFolder}`;
}

function getStackFilePath(taskId) {
  const convDir = getConversationsPath();
  const taskName = computeTaskNameForConversation(taskId);
  return path.join(convDir, `${taskName}_stack.json`);
}

// ==================== Window ====================

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset', // macOS native look
    trafficLightPosition: { x: 16, y: 16 },
    backgroundColor: '#faf7f2',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'index.html'));
  
  // Open DevTools in development
  if (!app.isPackaged) {
    mainWindow.webContents.openDevTools();
  }
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  killPythonProcess();
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// ==================== IPC: Workspace ====================

// Select workspace folder
ipcMain.handle('select-folder', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory'],
    title: 'Select Workspace Folder'
  });
  if (result.canceled) return null;
  return result.filePaths[0];
});

// ==================== IPC: Agent Task ====================

// Start agent task (spawn Python subprocess with JSONL mode)
ipcMain.handle('start-task', async (event, { workspacePath, userInput, agentName, agentSystem }) => {
  if (pythonProcess) {
    return { error: 'A task is already running' };
  }

  const backendPath = getPythonBackendPath();
  const startScript = path.join(backendPath, 'start.py');
  const llmConfigPath = ensureUserLlmConfigExists();
  
  // Add timestamp to user input (consistent with CLI)
  const now = new Date();
  const timestamp = now.toISOString().slice(0, 19).replace('T', ' ');
  const userInputWithTimestamp = `${userInput} [时间: ${timestamp}]`;

  const args = [
    startScript,
    '--task_id', workspacePath,
    '--agent_name', agentName || 'alpha_agent',
    '--user_input', userInputWithTimestamp,
    '--agent_system', agentSystem || 'OpenCowork',
    '--jsonl',
    '--direct-tools'
  ];

  pythonProcess = spawn('python3', args, {
    cwd: backendPath,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      MLA_LLM_CONFIG_PATH: llmConfigPath,
      // Allow importing agent systems under ~/mla_v3/agent_library/
      MLA_AGENT_LIBRARY_DIR: getUserDataRoot()
    }
  });

  let buffer = '';

  pythonProcess.stdout.on('data', (data) => {
    buffer += data.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const evt = JSON.parse(line);
        mainWindow.webContents.send('agent-event', evt);
      } catch (e) {
        // Non-JSON output (debug prints, etc.)
        mainWindow.webContents.send('agent-log', line);
      }
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    mainWindow.webContents.send('agent-log', data.toString());
  });

  pythonProcess.on('close', (code) => {
    pythonProcess = null;
    mainWindow.webContents.send('agent-done', { code });
  });

  return { success: true };
});

// Human-in-loop respond (no-HTTP, via stdin JSONL to Python)
ipcMain.handle('hil-respond', async (event, { hil_id, response }) => {
  try {
    if (!pythonProcess || !pythonProcess.stdin) {
      return { error: 'No running task process' };
    }
    const hid = (hil_id || '').toString().trim();
    if (!hid) return { error: 'Missing hil_id' };
    const payload = { type: 'hil_response', hil_id: hid, response: (response ?? '').toString() };
    pythonProcess.stdin.write(JSON.stringify(payload) + '\n');
    return { success: true };
  } catch (e) {
    return { error: e.message || String(e) };
  }
});

// Check if there is an interrupted task that can be resumed (CLI-compatible: check stack file)
ipcMain.handle('check-resume', async (event, taskId) => {
  try {
    if (!taskId || typeof taskId !== 'string') return { found: false, message: 'Invalid task_id' };

    const stackFile = getStackFilePath(taskId);
    if (!fs.existsSync(stackFile)) {
      return { found: false, message: 'No interrupted task (stack file missing)' };
    }

    const data = safeReadJson(stackFile);
    const stack = Array.isArray(data?.stack) ? data.stack : [];
    if (stack.length === 0) {
      return { found: false, message: 'No interrupted task (stack empty)' };
    }

    const bottom = stack[0] || {};
    const agentName = bottom.agent_name || bottom.agentName || bottom.agent || null;
    const userInput = bottom.user_input || bottom.userInput || bottom.input || null;
    if (!agentName || !userInput) {
      return { found: false, message: 'Interrupted task data incomplete' };
    }

    return {
      found: true,
      agent_name: String(agentName),
      user_input: String(userInput),
      interrupted_at: bottom.start_time || bottom.startTime || '',
      stack_depth: stack.length
    };
  } catch (e) {
    return { found: false, message: String(e.message || e) };
  }
});

// Resume task: re-run start.py with SAME agent_name & user_input (do NOT append timestamp)
ipcMain.handle('resume-task', async (event, { workspacePath, agentSystem }) => {
  if (pythonProcess) {
    return { error: 'A task is already running' };
  }

  try {
    if (!workspacePath || typeof workspacePath !== 'string') return { error: 'Invalid workspacePath' };

    // Recompute interrupted info
    const stackFile = getStackFilePath(workspacePath);
    const data = safeReadJson(stackFile);
    const stack = Array.isArray(data?.stack) ? data.stack : [];
    if (stack.length === 0) return { error: 'No interrupted task to resume' };

    const bottom = stack[0] || {};
    const agentName = bottom.agent_name || bottom.agentName || bottom.agent || 'alpha_agent';
    const userInput = bottom.user_input || bottom.userInput || bottom.input || '';
    if (!userInput) return { error: 'No interrupted task input found' };

    const backendPath = getPythonBackendPath();
    const startScript = path.join(backendPath, 'start.py');
    const llmConfigPath = ensureUserLlmConfigExists();

    const args = [
      startScript,
      '--task_id', workspacePath,
      '--agent_name', String(agentName),
      '--user_input', String(userInput),
      '--agent_system', agentSystem || 'OpenCowork',
      '--jsonl',
      '--direct-tools'
    ];

    pythonProcess = spawn('python3', args, {
      cwd: backendPath,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        MLA_LLM_CONFIG_PATH: llmConfigPath,
        MLA_AGENT_LIBRARY_DIR: getUserDataRoot()
      }
    });

    let buffer = '';

    pythonProcess.stdout.on('data', (data) => {
      buffer += data.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const evt = JSON.parse(line);
          mainWindow.webContents.send('agent-event', evt);
        } catch (e) {
          mainWindow.webContents.send('agent-log', line);
        }
      }
    });

    pythonProcess.stderr.on('data', (data) => {
      mainWindow.webContents.send('agent-log', data.toString());
    });

    pythonProcess.on('close', (code) => {
      pythonProcess = null;
      mainWindow.webContents.send('agent-done', { code });
    });

    return { success: true };
  } catch (e) {
    pythonProcess = null;
    return { error: e.message || String(e) };
  }
});

// Stop running task
ipcMain.handle('stop-task', async () => {
  killPythonProcess();
  return { success: true };
});

function killPythonProcess() {
  if (pythonProcess) {
    try {
      process.kill(-pythonProcess.pid, 'SIGTERM');
    } catch (e) {
      try { pythonProcess.kill('SIGTERM'); } catch (e2) {}
    }
    pythonProcess = null;
  }
}

// ==================== IPC: Settings (llm_config.yaml) ====================

// Simple YAML parser for flat config (no nested objects)
function parseSimpleYaml(text) {
  const result = {};
  let currentKey = null;
  let currentList = null;
  
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trimEnd();
    
    // Skip empty lines and comments
    if (!line.trim() || line.trim().startsWith('#')) continue;
    
    // List item (- value)
    if (line.match(/^\s*-\s+/) && currentKey) {
      const val = line.replace(/^\s*-\s+/, '').trim();
      if (!currentList) currentList = [];
      currentList.push(val);
      result[currentKey] = currentList;
      continue;
    }
    
    // Key: value
    const match = line.match(/^(\w[\w_]*)\s*:\s*(.*)/);
    if (match) {
      // Save previous list
      currentList = null;
      currentKey = match[1];
      const val = match[2].trim();
      
      if (val === '') {
        // Could be list header
        result[currentKey] = [];
        currentList = [];
        result[currentKey] = currentList;
      } else if (val === 'true') {
        result[currentKey] = true;
      } else if (val === 'false') {
        result[currentKey] = false;
      } else if (!isNaN(Number(val)) && val !== '') {
        result[currentKey] = Number(val);
      } else {
        result[currentKey] = val;
      }
    }
  }
  
  return result;
}

// Simple YAML serializer for flat config
function serializeSimpleYaml(obj) {
  const lines = [];
  for (const [key, value] of Object.entries(obj)) {
    if (Array.isArray(value)) {
      lines.push(`${key}:`);
      for (const item of value) {
        lines.push(`- ${item}`);
      }
    } else if (typeof value === 'string' && value.includes('#')) {
      // Preserve inline comments - write value before comment
      lines.push(`${key}: ${value}`);
    } else {
      lines.push(`${key}: ${value}`);
    }
  }
  lines.push(''); // trailing newline
  return lines.join('\n');
}

// Read LLM config
ipcMain.handle('get-settings', async () => {
  try {
    ensureUserLlmConfigExists();
    const configPath = getLlmConfigPath();
    if (!fs.existsSync(configPath)) {
      return { error: 'Config file not found', path: configPath };
    }
    const content = fs.readFileSync(configPath, 'utf-8');
    const config = parseSimpleYaml(content);
    return { success: true, config, raw_yaml: content, path: configPath };
  } catch (e) {
    return { error: e.message };
  }
});

// Save LLM config
ipcMain.handle('save-settings', async (event, config) => {
  try {
    ensureUserLlmConfigExists();
    const configPath = getLlmConfigPath();
    // Accept either a config object (simple form) or raw YAML string (full fidelity)
    if (typeof config === 'string') {
      fs.writeFileSync(configPath, config, 'utf-8');
    } else {
      const yaml = serializeSimpleYaml(config);
      fs.writeFileSync(configPath, yaml, 'utf-8');
    }
    return { success: true };
  } catch (e) {
    return { error: e.message };
  }
});

// List available agent systems (scan config/agent_library/)
ipcMain.handle('get-agent-systems', async () => {
  try {
    const systems = new Set();

    // Bundled systems (read-only)
    const backendPath = getPythonBackendPath();
    const bundledAgentLibDir = path.join(backendPath, 'config', 'agent_library');
    if (fs.existsSync(bundledAgentLibDir)) {
      const entries = fs.readdirSync(bundledAgentLibDir, { withFileTypes: true });
      for (const e of entries) {
        if (e.isDirectory() && !e.name.startsWith('.')) systems.add(e.name);
      }
    }

    // User imported systems under ~/mla_v3/agent_library/<System>/
    const userAgentLibRoot = getUserAgentLibraryPath();
    if (fs.existsSync(userAgentLibRoot)) {
      const entries = fs.readdirSync(userAgentLibRoot, { withFileTypes: true });
      for (const e of entries) {
        if (e.isDirectory() && !e.name.startsWith('.')) systems.add(e.name);
      }
    }

    return { success: true, systems: Array.from(systems).sort() };
  } catch (e) {
    return { error: e.message };
  }
});

// Import Agent System folder into ~/mla_v3/agent_library/
ipcMain.handle('import-agent-system-folder', async () => {
  try {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory'],
      title: 'Select Agent System Folder to Import'
    });
    if (result.canceled) return { canceled: true };

    const srcDir = result.filePaths[0];
    const systemName = path.basename(srcDir);
    const destRoot = getUserAgentLibraryPath();
    const destDir = path.join(destRoot, systemName);
    fs.mkdirSync(destRoot, { recursive: true });
    copyDirSync(srcDir, destDir);
    return { success: true, name: systemName, path: destDir };
  } catch (e) {
    return { error: e.message };
  }
});

// ==================== IPC: Skills Library ====================

// Select skill folder and copy to ~/mla_v3/skills_library/
ipcMain.handle('import-skill-folder', async () => {
  try {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory'],
      title: 'Select Skill Folder to Import'
    });
    if (result.canceled) return { canceled: true };
    
    const srcDir = result.filePaths[0];
    const folderName = path.basename(srcDir);
    const destDir = path.join(getSkillsLibraryPath(), folderName);
    
    // Ensure skills_library exists
    fs.mkdirSync(getSkillsLibraryPath(), { recursive: true });
    
    // Copy recursively
    copyDirSync(srcDir, destDir);
    
    return { success: true, name: folderName, path: destDir };
  } catch (e) {
    return { error: e.message };
  }
});

// List imported skills
ipcMain.handle('get-skills', async () => {
  try {
    const skillsDir = getSkillsLibraryPath();
    if (!fs.existsSync(skillsDir)) {
      fs.mkdirSync(skillsDir, { recursive: true });
      return { success: true, skills: [] };
    }
    
    const entries = fs.readdirSync(skillsDir, { withFileTypes: true });
    const skills = [];
    
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith('.')) continue;
      
      const skillMd = path.join(skillsDir, entry.name, 'SKILL.md');
      let description = '';
      
      if (fs.existsSync(skillMd)) {
        // Parse frontmatter for description
        const content = fs.readFileSync(skillMd, 'utf-8');
        const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
        if (fmMatch) {
          const descMatch = fmMatch[1].match(/description:\s*(.+)/);
          if (descMatch) description = descMatch[1].trim();
        }
      }
      
      skills.push({
        name: entry.name,
        description,
        path: path.join(skillsDir, entry.name),
        hasSkillMd: fs.existsSync(skillMd)
      });
    }
    
    return { success: true, skills };
  } catch (e) {
    return { error: e.message };
  }
});

// Delete a skill
ipcMain.handle('delete-skill', async (event, skillName) => {
  try {
    const skillDir = path.join(getSkillsLibraryPath(), skillName);
    if (fs.existsSync(skillDir)) {
      fs.rmSync(skillDir, { recursive: true, force: true });
    }
    return { success: true };
  } catch (e) {
    return { error: e.message };
  }
});

// Recursive copy helper
function copyDirSync(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  const entries = fs.readdirSync(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      copyDirSync(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

// ==================== IPC: Conversation History ====================

// List all conversations from ~/mla_v3/conversations/
ipcMain.handle('get-conversations', async () => {
  try {
    const convDir = getConversationsPath();
    if (!fs.existsSync(convDir)) {
      fs.mkdirSync(convDir, { recursive: true });
      return { success: true, conversations: [] };
    }
    
    // Only scan share context JSONs to avoid duplicates
    const files = fs
      .readdirSync(convDir)
      .filter(f => f.endsWith('.json') && f.includes('share'));

    const byTaskId = new Map(); // taskId -> conversation item (keep latest)

    for (const file of files) {
      const filePath = path.join(convDir, file);
      const stat = fs.statSync(filePath);
      const data = safeReadJson(filePath);
      if (!data || !data.task_id) continue;

      const taskId = String(data.task_id || '');
      const workspaceName = path.basename(taskId) || taskId;

      const rawPreview = pickPreviewFromShareContext(data);
      const preview = rawPreview.length > 60 ? rawPreview.substring(0, 60) + '...' : rawPreview;

      const item = {
        id: file.replace('.json', ''),
        file: file,
        taskId,
        workspaceName,
        preview,
        // turns = number of completed user instructions in history
        turns: Array.isArray(data.history) ? data.history.length : 0,
        lastUpdated: data.last_updated || stat.mtime.toISOString(),
        mtime: stat.mtime.getTime()
      };

      const prev = byTaskId.get(taskId);
      if (!prev || item.mtime > prev.mtime) {
        byTaskId.set(taskId, item);
      }
    }

    const conversations = Array.from(byTaskId.values()).sort((a, b) => b.mtime - a.mtime);
    return { success: true, conversations };
  } catch (e) {
    return { error: e.message };
  }
});

// Read a share_context.json by filename
ipcMain.handle('get-conversation-detail', async (event, fileName) => {
  try {
    if (!fileName || typeof fileName !== 'string') return { error: 'Invalid file name' };
    const base = path.basename(fileName);
    // Restrict to share json files only
    if (!base.endsWith('.json') || !base.includes('share')) return { error: 'Not a share context file' };

    const filePath = path.join(getConversationsPath(), base);
    if (!fs.existsSync(filePath)) return { error: 'File not found' };

    const data = safeReadJson(filePath);
    if (!data) return { error: 'Failed to parse JSON' };
    return { success: true, data };
  } catch (e) {
    return { error: e.message };
  }
});

// Delete a conversation file
ipcMain.handle('delete-conversation', async (event, fileName) => {
  try {
    const filePath = path.join(getConversationsPath(), fileName);
    if (fs.existsSync(filePath)) {
      fs.unlinkSync(filePath);
    }
    return { success: true };
  } catch (e) {
    return { error: e.message };
  }
});

// Open conversations folder in Finder
ipcMain.handle('open-conversations-folder', async () => {
  const convDir = getConversationsPath();
  fs.mkdirSync(convDir, { recursive: true });
  shell.openPath(convDir);
  return { success: true };
});
