const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');
const childProcess = require('child_process');
const os = require('os');
const crypto = require('crypto');
const AdmZip = require('adm-zip');

let mainWindow;
let pythonProcess = null;
let currentTaskLogger = null;

// ==================== Path Helpers ====================

// Python backend path (development vs packaged)
function getPythonBackendPath() {
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'python-backend');
  }
  return path.join(__dirname, '..', '..');
}

function getPackagedBackendArchDir() {
  // For universal app, we ship two PyInstaller backends and select at runtime.
  // Layout inside resources:
  //   resources/python-backend/darwin-arm64/mlav3-backend/mlav3-backend
  //   resources/python-backend/darwin-x64/mlav3-backend/mlav3-backend
  // Later we can extend for win32/linux similarly.
  if (process.platform === 'darwin') {
    if (process.arch === 'arm64') return 'darwin-arm64';
    if (process.arch === 'x64') return 'darwin-x64';
  }
  // Fallback: use platform-arch
  return `${process.platform}-${process.arch}`;
}

function getPackagedBackendExecutablePath() {
  const backendRoot = getPythonBackendPath();
  const archDir = getPackagedBackendArchDir();
  const exeName = process.platform === 'win32' ? 'mlav3-backend.exe' : 'mlav3-backend';
  // PyInstaller --onedir default: <dist>/<name>/<name>
  return path.join(backendRoot, archDir, 'mlav3-backend', exeName);
}

function getBackendLaunchSpecDev(userInput, workspacePath, agentName, agentSystem, appendTimestamp) {
  const backendPath = getPythonBackendPath();
  const startScript = path.join(backendPath, 'start.py');
  const now = new Date();
  const timestamp = now.toISOString().slice(0, 19).replace('T', ' ');
  const ui = appendTimestamp ? `${userInput} [时间: ${timestamp}]` : userInput;
  const args = [
    startScript,
    '--task_id', workspacePath,
    '--agent_name', agentName || 'alpha_agent',
    '--user_input', ui,
    '--agent_system', agentSystem || 'OpenCowork',
    '--jsonl',
    '--direct-tools'
  ];
  return { command: 'python3', args, cwd: backendPath };
}

function getBackendLaunchSpecPackaged(userInput, workspacePath, agentName, agentSystem, appendTimestamp) {
  const backendPath = getPythonBackendPath();
  const backendExe = getPackagedBackendExecutablePath();
  const now = new Date();
  const timestamp = now.toISOString().slice(0, 19).replace('T', ' ');
  const ui = appendTimestamp ? `${userInput} [时间: ${timestamp}]` : userInput;
  const args = [
    '--task_id', workspacePath,
    '--agent_name', agentName || 'alpha_agent',
    '--user_input', ui,
    '--agent_system', agentSystem || 'OpenCowork',
    '--jsonl',
    '--direct-tools'
  ];
  return { command: backendExe, args, cwd: backendPath };
}

// User data root: ~/mla_v3/
function getUserDataRoot() {
  return path.join(os.homedir(), 'mla_v3');
}

function getUserConfigDir() {
  return path.join(getUserDataRoot(), 'config');
}

function getAppConfigPath() {
  return path.join(getUserConfigDir(), 'app_config.json');
}

// LLM config file path
function getLlmConfigPath() {
  // Always store user-editable config under ~/mla_v3/config/
  return path.join(getUserConfigDir(), 'llm_config.yaml');
}

function defaultAppConfig() {
  return {
    env: {
      // system: use /usr/libexec/path_helper + common paths
      // zsh_login_interactive: use zsh -lic to get PATH (more terminal-like, may have side effects)
      shell_mode: 'system',
      // direct: run execute_command in backend process
      // system_terminal: macOS only, execute_command is proxied via Terminal.app
      command_mode: 'direct',
      extra_path: [],
      // additional env vars to inject into backend + execute_command
      extra_env: {}
    },
    market: {
      // Default marketplace (user can change in Settings → Environment)
      base_url: 'http://101.200.231.88'
    }
  };
}

function safeReadJsonFile(filePath) {
  try {
    if (!fs.existsSync(filePath)) return null;
    const content = fs.readFileSync(filePath, 'utf-8');
    return JSON.parse(content);
  } catch (_) {
    return null;
  }
}

function ensureUserAppConfigExists() {
  ensureUserDataRootScaffold();
  const p = getAppConfigPath();
  if (fs.existsSync(p)) return p;
  fs.writeFileSync(p, JSON.stringify(defaultAppConfig(), null, 2) + '\n', 'utf-8');
  return p;
}

function readAppConfig() {
  ensureUserAppConfigExists();
  const raw = safeReadJsonFile(getAppConfigPath());
  if (!raw || typeof raw !== 'object') return defaultAppConfig();
  const base = defaultAppConfig();
  // shallow merge
  const out = { ...base, ...raw };
  out.env = { ...base.env, ...(raw.env || {}) };
  out.market = { ...base.market, ...(raw.market || {}) };
  // normalize types
  if (!Array.isArray(out.env.extra_path)) out.env.extra_path = [];
  if (!out.env.extra_env || typeof out.env.extra_env !== 'object') out.env.extra_env = {};
  if (typeof out.env.command_mode !== 'string' || !out.env.command_mode.trim()) out.env.command_mode = 'direct';
  if (typeof out.market.base_url !== 'string') out.market.base_url = '';
  return out;
}

function stripApiKeysFromYaml(yamlText) {
  // Best-effort sanitizer: blank any `api_key:` values (including nested model entries).
  // Keep file otherwise unchanged to preserve advanced YAML structures.
  if (typeof yamlText !== 'string') return '';
  return yamlText.replace(/^(\s*api_key\s*:\s*).*/gm, '$1""');
}

function _parsePathFromPathHelperOutput(text) {
  // path_helper -s output example:
  //   PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"; export PATH;
  if (!text) return null;
  const m = String(text).match(/PATH="([^"]*)"/);
  if (!m) return null;
  return m[1];
}

function getSystemPathFromPathHelper() {
  try {
    const out = childProcess.execFileSync('/usr/libexec/path_helper', ['-s'], {
      encoding: 'utf-8',
      timeout: 1500
    });
    return _parsePathFromPathHelperOutput(out);
  } catch (_) {
    return null;
  }
}

function getZshLoginInteractivePath() {
  try {
    // zsh -lic: reads login + interactive configs (closest to user's terminal env)
    const out = childProcess.execFileSync('/bin/zsh', ['-lic', 'echo -n "$PATH"'], {
      encoding: 'utf-8',
      timeout: 4000
    });
    const p = String(out || '').trim();
    return p || null;
  } catch (_) {
    return null;
  }
}

function computeEffectivePath(appCfg) {
  const mode = appCfg?.env?.shell_mode || 'system';

  let basePath = null;
  if (mode === 'zsh_login_interactive') {
    basePath = getZshLoginInteractivePath();
  }
  if (!basePath) {
    basePath = getSystemPathFromPathHelper() || process.env.PATH || '';
  }

  const baseParts = basePath.split(':').filter(Boolean);
  const extraParts = Array.isArray(appCfg?.env?.extra_path) ? appCfg.env.extra_path : [];

  // Common user tool locations (best-effort; harmless if missing)
  const common = [
    '/opt/homebrew/bin',
    '/opt/homebrew/sbin',
    '/usr/local/bin',
    '/usr/local/sbin',
    '/opt/anaconda3/bin',
    '/opt/anaconda3/condabin'
  ];

  const all = [...common, ...baseParts, ...extraParts].map(s => String(s || '').trim()).filter(Boolean);
  const seen = new Set();
  const dedup = [];
  for (const p of all) {
    if (seen.has(p)) continue;
    seen.add(p);
    dedup.push(p);
  }
  return dedup.join(':');
}

function buildRuntimeEnv() {
  const appCfg = readAppConfig();
  const env = { ...process.env };
  env.PATH = computeEffectivePath(appCfg);
  env.MLA_EXECUTE_COMMAND_MODE = (appCfg?.env?.command_mode === 'system_terminal') ? 'system_terminal' : 'direct';

  // Encourage consistent unicode behavior
  env.LANG = env.LANG || 'en_US.UTF-8';
  env.LC_ALL = env.LC_ALL || 'en_US.UTF-8';

  // Inject extra env
  const extraEnv = appCfg?.env?.extra_env || {};
  for (const [k, v] of Object.entries(extraEnv)) {
    const key = String(k || '').trim();
    if (!key) continue;
    env[key] = String(v ?? '');
  }

  return env;
}

function ensureUserDataRootScaffold() {
  // Create user-writable dirs under ~/mla_v3 (do not overwrite user files).
  fs.mkdirSync(getUserDataRoot(), { recursive: true });
  fs.mkdirSync(getUserConfigDir(), { recursive: true });
  fs.mkdirSync(getSkillsLibraryPath(), { recursive: true });
  fs.mkdirSync(getUserAgentLibraryPath(), { recursive: true });
  fs.mkdirSync(getConversationsPath(), { recursive: true });
  fs.mkdirSync(getLogsPath(), { recursive: true });

  // Seed default bundled skills (best-effort; never overwrite existing ones)
  try {
    const bundledSkillsDir = path.join(getPythonBackendPath(), 'skills');
    if (fs.existsSync(bundledSkillsDir)) {
      const entries = fs.readdirSync(bundledSkillsDir, { withFileTypes: true });
      for (const e of entries) {
        if (!e.isDirectory() || e.name.startsWith('.')) continue;
        const src = path.join(bundledSkillsDir, e.name);
        const dst = path.join(getSkillsLibraryPath(), e.name);
        if (fs.existsSync(dst)) continue; // do not overwrite user skill
        copyDirSync(src, dst);
      }
    }
  } catch (_) {
    // Seeding skills should never block app startup
  }

  // Seed bundled agent systems into ~/mla_v3/agent_library (best-effort; never overwrite existing ones)
  try {
    const backendPath = getPythonBackendPath();
    const bundledAgentLibDir = path.join(backendPath, 'config', 'agent_library');
    if (fs.existsSync(bundledAgentLibDir)) {
      const destRoot = getUserAgentLibraryPath();
      fs.mkdirSync(destRoot, { recursive: true });
      const entries = fs.readdirSync(bundledAgentLibDir, { withFileTypes: true });
      for (const e of entries) {
        if (!e.isDirectory() || e.name.startsWith('.')) continue;
        const src = path.join(bundledAgentLibDir, e.name);
        const dst = path.join(destRoot, e.name);
        if (fs.existsSync(dst)) continue; // do not overwrite user system
        copyDirSync(src, dst);
      }
    }
  } catch (_) {
    // Seeding agent systems should never block app startup
  }
}

function ensureUserLlmConfigExists() {
  ensureUserDataRootScaffold();
  const userConfigPath = getLlmConfigPath();
  if (fs.existsSync(userConfigPath)) return userConfigPath;

  // Bootstrap from bundled example (always no key, safe to copy)
  const backendPath = getPythonBackendPath();
  const bundled = path.join(backendPath, 'config', 'run_env_config', 'llm_config.example.yaml');
  if (fs.existsSync(bundled)) {
    const example = fs.readFileSync(bundled, 'utf-8');
    fs.writeFileSync(userConfigPath, stripApiKeysFromYaml(example), 'utf-8');
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

function getLogsPath() {
  return path.join(getUserDataRoot(), 'logs');
}

function sanitizeFilenamePart(input) {
  const s = String(input || '').trim();
  if (!s) return 'unknown';
  return s.replace(/[^\w.-]+/g, '_').slice(0, 80) || 'unknown';
}

function createTaskLogger({ workspacePath, agentName, agentSystem, mode, launchSpec }) {
  try {
    fs.mkdirSync(getLogsPath(), { recursive: true });
    const now = new Date();
    const ts = now.toISOString().replace(/[-:]/g, '').replace(/\..+/, '').replace('T', '_');
    const workspaceName = sanitizeFilenamePart(path.basename(String(workspacePath || 'workspace')));
    const runHash = crypto.createHash('md5')
      .update(`${workspacePath}|${agentName}|${agentSystem}|${now.toISOString()}`)
      .digest('hex')
      .slice(0, 8);
    const fileName = `${ts}_${workspaceName}_${runHash}_${mode}.log`;
    const filePath = path.join(getLogsPath(), fileName);
    const stream = fs.createWriteStream(filePath, { flags: 'a', encoding: 'utf-8' });

    const write = (line) => {
      try {
        stream.write(`${new Date().toISOString()} ${line}\n`);
      } catch (_) {}
    };

    write('[TASK_START]');
    write(`[META] mode=${mode} workspace="${workspacePath}" agent="${agentName}" system="${agentSystem}"`);
    if (launchSpec && launchSpec.command) {
      const args = Array.isArray(launchSpec.args) ? launchSpec.args.join(' ') : '';
      write(`[LAUNCH] ${launchSpec.command} ${args}`);
    }

    return {
      filePath,
      write,
      close(exitCode) {
        try {
          write(`[TASK_END] exit_code=${exitCode}`);
          stream.end();
        } catch (_) {}
      }
    };
  } catch (_) {
    return null;
  }
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

  const llmConfigPath = ensureUserLlmConfigExists();
  
  const spec = app.isPackaged
    ? getBackendLaunchSpecPackaged(userInput, workspacePath, agentName, agentSystem, true)
    : getBackendLaunchSpecDev(userInput, workspacePath, agentName, agentSystem, true);

  currentTaskLogger = createTaskLogger({
    workspacePath,
    agentName: agentName || 'alpha_agent',
    agentSystem: agentSystem || 'OpenCowork',
    mode: 'start',
    launchSpec: spec
  });

  pythonProcess = spawn(spec.command, spec.args, {
    cwd: spec.cwd,
    env: {
      ...buildRuntimeEnv(),
      PYTHONUNBUFFERED: '1',
      MLA_LLM_CONFIG_PATH: llmConfigPath,
      // Allow importing agent systems under ~/mla_v3/agent_library/
      MLA_AGENT_LIBRARY_DIR: getUserDataRoot(),
      // Packaged app: force Playwright to use bundled browsers under
      //   <bundle>/_internal/playwright/driver/package/.local-browsers
      // (installed at build time via PLAYWRIGHT_BROWSERS_PATH=0).
      ...(app.isPackaged ? { PLAYWRIGHT_BROWSERS_PATH: '0' } : {})
    }
  });

  let buffer = '';
  let errBuffer = '';

  pythonProcess.stdout.on('data', (data) => {
    if (currentTaskLogger) currentTaskLogger.write(`[STDOUT_CHUNK] ${JSON.stringify(data.toString())}`);
    buffer += data.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    
    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const evt = JSON.parse(line);
        if (currentTaskLogger) currentTaskLogger.write(`[EVENT] ${line}`);
        mainWindow.webContents.send('agent-event', evt);
      } catch (e) {
        // Non-JSON output (debug prints, etc.)
        if (currentTaskLogger) currentTaskLogger.write(`[LOG] ${line}`);
        mainWindow.webContents.send('agent-log', line);
      }
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    if (currentTaskLogger) currentTaskLogger.write(`[STDERR_CHUNK] ${JSON.stringify(data.toString())}`);
    errBuffer += data.toString();
    const lines = errBuffer.split('\n');
    errBuffer = lines.pop() || '';
    for (const line of lines) {
      if (!line.trim()) continue;
      if (currentTaskLogger) currentTaskLogger.write(`[ERR] ${line}`);
      mainWindow.webContents.send('agent-log', line);
    }
  });

  pythonProcess.on('close', (code) => {
    pythonProcess = null;
    if (currentTaskLogger) {
      currentTaskLogger.close(code);
      currentTaskLogger = null;
    }
    mainWindow.webContents.send('agent-done', { code });
  });

  return { success: true, log_file: currentTaskLogger?.filePath || null };
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

    const llmConfigPath = ensureUserLlmConfigExists();
    const spec = app.isPackaged
      ? getBackendLaunchSpecPackaged(String(userInput), workspacePath, String(agentName), agentSystem, false)
      : getBackendLaunchSpecDev(String(userInput), workspacePath, String(agentName), agentSystem, false);

    currentTaskLogger = createTaskLogger({
      workspacePath,
      agentName: String(agentName),
      agentSystem: agentSystem || 'OpenCowork',
      mode: 'resume',
      launchSpec: spec
    });

    pythonProcess = spawn(spec.command, spec.args, {
      cwd: spec.cwd,
      env: {
        ...buildRuntimeEnv(),
        PYTHONUNBUFFERED: '1',
        MLA_LLM_CONFIG_PATH: llmConfigPath,
        MLA_AGENT_LIBRARY_DIR: getUserDataRoot(),
        ...(app.isPackaged ? { PLAYWRIGHT_BROWSERS_PATH: '0' } : {})
      }
    });

    let buffer = '';
    let errBuffer = '';

    pythonProcess.stdout.on('data', (data) => {
      if (currentTaskLogger) currentTaskLogger.write(`[STDOUT_CHUNK] ${JSON.stringify(data.toString())}`);
      buffer += data.toString();
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const evt = JSON.parse(line);
          if (currentTaskLogger) currentTaskLogger.write(`[EVENT] ${line}`);
          mainWindow.webContents.send('agent-event', evt);
        } catch (e) {
          if (currentTaskLogger) currentTaskLogger.write(`[LOG] ${line}`);
          mainWindow.webContents.send('agent-log', line);
        }
      }
    });

    pythonProcess.stderr.on('data', (data) => {
      if (currentTaskLogger) currentTaskLogger.write(`[STDERR_CHUNK] ${JSON.stringify(data.toString())}`);
      errBuffer += data.toString();
      const lines = errBuffer.split('\n');
      errBuffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.trim()) continue;
        if (currentTaskLogger) currentTaskLogger.write(`[ERR] ${line}`);
        mainWindow.webContents.send('agent-log', line);
      }
    });

    pythonProcess.on('close', (code) => {
      pythonProcess = null;
      if (currentTaskLogger) {
        currentTaskLogger.close(code);
        currentTaskLogger = null;
      }
      mainWindow.webContents.send('agent-done', { code });
    });

    return { success: true, log_file: currentTaskLogger?.filePath || null };
  } catch (e) {
    pythonProcess = null;
    if (currentTaskLogger) {
      currentTaskLogger.close(-1);
      currentTaskLogger = null;
    }
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
    if (currentTaskLogger) {
      currentTaskLogger.write('[STOP_REQUESTED] task stopped by user');
    }
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

// Delete an imported/seeded agent system under ~/mla_v3/agent_library/<System>/
ipcMain.handle('delete-agent-system', async (event, systemName) => {
  try {
    const name = String(systemName || '').trim();
    if (!name) return { error: 'Invalid system name' };
    const userRoot = getUserAgentLibraryPath();
    const target = path.join(userRoot, name);
    if (!fs.existsSync(target)) {
      return { success: true, deleted: false };
    }
    fs.rmSync(target, { recursive: true, force: true });
    return { success: true, deleted: true };
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

// ==================== IPC: App Config (app_config.json) ====================

ipcMain.handle('get-app-config', async () => {
  try {
    const cfg = readAppConfig();
    return { success: true, config: cfg, path: getAppConfigPath() };
  } catch (e) {
    return { error: e.message };
  }
});

ipcMain.handle('save-app-config', async (event, config) => {
  try {
    ensureUserAppConfigExists();
    const base = defaultAppConfig();
    const raw = (config && typeof config === 'object') ? config : {};
    const out = { ...base, ...raw };
    out.env = { ...base.env, ...(raw.env || {}) };
    out.market = { ...base.market, ...(raw.market || {}) };
    fs.writeFileSync(getAppConfigPath(), JSON.stringify(out, null, 2) + '\n', 'utf-8');
    return { success: true };
  } catch (e) {
    return { error: e.message };
  }
});

// ==================== IPC: Marketplace ====================

function normalizeMarketBaseUrl(url) {
  const u = String(url || '').trim();
  if (!u) return '';
  return u.replace(/\/+$/, '');
}

async function fetchJson(url) {
  const res = await fetch(url, { method: 'GET' });
  if (!res.ok) {
    const t = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${t.slice(0, 300)}`);
  }
  return await res.json();
}

async function fetchBuffer(url) {
  const res = await fetch(url, { method: 'GET' });
  if (!res.ok) {
    const t = await res.text().catch(() => '');
    throw new Error(`HTTP ${res.status}: ${t.slice(0, 300)}`);
  }
  const ab = await res.arrayBuffer();
  return Buffer.from(ab);
}

function resolveUniqueName(rootDir, baseName) {
  let name = baseName;
  if (!fs.existsSync(path.join(rootDir, name))) return name;
  for (let i = 2; i < 1000; i++) {
    const candidate = `${baseName}__${i}`;
    if (!fs.existsSync(path.join(rootDir, candidate))) return candidate;
  }
  // fallback
  return `${baseName}__${Date.now()}`;
}

function extractSingleTopFolderFromZip(zipBuffer, tempDir) {
  fs.mkdirSync(tempDir, { recursive: true });
  const zip = new AdmZip(zipBuffer);
  zip.extractAllTo(tempDir, true);
  const entries = fs.readdirSync(tempDir, { withFileTypes: true }).filter(e => !e.name.startsWith('.'));
  const dirs = entries.filter(e => e.isDirectory());
  if (dirs.length === 1) {
    return path.join(tempDir, dirs[0].name);
  }
  // If zip doesn't have a single top folder, treat tempDir as root
  return tempDir;
}

ipcMain.handle('market-get-index', async () => {
  try {
    const appCfg = readAppConfig();
    const base = normalizeMarketBaseUrl(appCfg?.market?.base_url);
    if (!base) return { error: 'Market base_url is empty. Set it in Settings → Environment / Marketplace.' };
    const index = await fetchJson(`${base}/api/v1/index`);
    return { success: true, base_url: base, index };
  } catch (e) {
    return { error: e.message || String(e) };
  }
});

ipcMain.handle('market-install', async (event, { kind, name, strategy }) => {
  try {
    const k = String(kind || '').trim(); // 'skill' | 'agent_system'
    const n = String(name || '').trim();
    const s = String(strategy || '').trim(); // 'overwrite' | 'keep_both'
    if (!n) return { error: 'Missing name' };
    if (k !== 'skill' && k !== 'agent_system') return { error: 'Invalid kind' };

    const appCfg = readAppConfig();
    const base = normalizeMarketBaseUrl(appCfg?.market?.base_url);
    if (!base) return { error: 'Market base_url is empty' };

    const dlUrl = (k === 'skill')
      ? `${base}/api/v1/skills/${encodeURIComponent(n)}/download`
      : `${base}/api/v1/agent-systems/${encodeURIComponent(n)}/download`;

    const buf = await fetchBuffer(dlUrl);
    const tempRoot = path.join(getUserDataRoot(), 'tmp', 'market');
    const tempDir = path.join(tempRoot, `${k}_${Date.now()}_${Math.random().toString(16).slice(2)}`);
    const extractedRoot = extractSingleTopFolderFromZip(buf, tempDir);

    const destRoot = (k === 'skill') ? getSkillsLibraryPath() : getUserAgentLibraryPath();
    fs.mkdirSync(destRoot, { recursive: true });

    // Determine installed folder name
    let installName = path.basename(extractedRoot);
    if (!installName || installName === '.' || installName === '..') installName = n;

    let destDir = path.join(destRoot, installName);
    if (fs.existsSync(destDir)) {
      if (!s) {
        return { success: false, conflict: true, existing: installName };
      }
      if (s === 'overwrite') {
        fs.rmSync(destDir, { recursive: true, force: true });
      } else if (s === 'keep_both') {
        const uniq = resolveUniqueName(destRoot, installName);
        installName = uniq;
        destDir = path.join(destRoot, installName);
      } else {
        return { error: `Unknown strategy: ${s}` };
      }
    }

    copyDirSync(extractedRoot, destDir);
    try { fs.rmSync(tempDir, { recursive: true, force: true }); } catch (_) {}

    return { success: true, installed_name: installName, path: destDir };
  } catch (e) {
    return { error: e.message || String(e) };
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
