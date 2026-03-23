// ==================== DOM Elements ====================
const selectFolderBtn = document.getElementById('select-folder-btn');
const workspaceLabel = document.getElementById('workspace-label');
const agentSystemSelect = document.getElementById('agent-system-select');
const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const statusText = document.getElementById('status-text');
const newChatBtn = document.getElementById('new-chat-btn');
const workspaceCurrent = document.getElementById('workspace-current');
const resumeBtn = document.getElementById('resume-btn');
const autoScrollBtn = document.getElementById('auto-scroll-btn');

// ==================== State ====================
let workspacePath = null;
let isRunning = false;
let autoScrollEnabled = true;
let lastLoadedSettingsConfig = {};

// Streaming state
let currentAgentBubble = null;
let currentAgentContentDiv = null;
let currentStreamText = '';

async function reloadAgentSystems(selectedValue = null) {
  const systemsResult = await window.api.getAgentSystems();
  if (!systemsResult?.success) return systemsResult;

  const systems = systemsResult.systems || [];
  const currentSidebarValue = selectedValue || agentSystemSelect.value || systems[0] || 'OpenCowork';

  const settingSelect = document.getElementById('setting-agent-system');
  if (settingSelect) settingSelect.innerHTML = '';
  agentSystemSelect.innerHTML = '';

  for (const sys of systems) {
    const opt1 = document.createElement('option');
    opt1.value = sys;
    opt1.textContent = sys;
    agentSystemSelect.appendChild(opt1);

    if (settingSelect) {
      const opt2 = document.createElement('option');
      opt2.value = sys;
      opt2.textContent = sys;
      settingSelect.appendChild(opt2);
    }
  }

  if (systems.includes(currentSidebarValue)) {
    agentSystemSelect.value = currentSidebarValue;
    if (settingSelect) settingSelect.value = currentSidebarValue;
  } else if (systems[0]) {
    agentSystemSelect.value = systems[0];
    if (settingSelect) settingSelect.value = systems[0];
  }

  return systemsResult;
}

// ==================== Markdown Render ====================

function renderMarkdownSafe(mdText) {
  try {
    const text = String(mdText ?? '');

    // marked + DOMPurify loaded via script tags in index.html
    if (window.marked && window.DOMPurify) {
      const html = window.marked.parse(text, {
        gfm: true,
        breaks: true
      });
      return window.DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
    }

    // Fallback: preserve newlines safely
    return escapeHtml(text).replace(/\n/g, '<br>');
  } catch (e) {
    return escapeHtml(String(mdText ?? ''));
  }
}

function setMarkdown(el, mdText) {
  if (!el) return;
  el.classList.add('markdown');
  el.innerHTML = renderMarkdownSafe(mdText);
}


// ==================== Workspace Selection ====================
selectFolderBtn.addEventListener('click', async () => {
  const folder = await window.api.selectFolder();
  if (folder) {
    workspacePath = folder;
    const folderName = folder.split('/').pop() || folder.split('\\').pop();
    // Keep button label stable, show current workspace separately
    if (workspaceCurrent) {
      workspaceCurrent.textContent = folder;
      workspaceCurrent.title = folder;
    }
    
    userInput.disabled = false;
    sendBtn.disabled = false;
    statusText.textContent = `Workspace: ${folderName}`;
    
    const welcome = messagesContainer.querySelector('.welcome-message');
    if (welcome) welcome.remove();

    await refreshResumeButton();
  }
});

// ==================== New Chat ====================
newChatBtn.addEventListener('click', () => {
  if (isRunning) return;
  // Clear messages
  messagesContainer.innerHTML = `
    <div class="welcome-message">
      <h2>Welcome to infiAgent</h2>
      <p>Select a workspace folder to begin. Your agent will work within that directory.</p>
      <div class="feature-cards">
        <div class="feature-card">
          <span class="feature-icon">🔄</span>
          <span class="feature-text">Days-long tasks with resume</span>
        </div>
        <div class="feature-card">
          <span class="feature-icon">🧠</span>
          <span class="feature-text">Persistent memory per workspace</span>
        </div>
        <div class="feature-card">
          <span class="feature-icon">⚡</span>
          <span class="feature-text">Agent Skills support</span>
        </div>
      </div>
    </div>
  `;
  finalizeCurrentStream();
  statusText.textContent = workspacePath 
    ? `Workspace: ${workspacePath.split('/').pop()}`
    : 'Select a workspace to start';
  statusText.style.color = '';
  refreshResumeButton();
});

// ==================== Resume (CLI-compatible) ====================

async function refreshResumeButton() {
  if (!resumeBtn) return;
  if (!workspacePath) {
    resumeBtn.style.display = 'none';
    return;
  }

  // If running, keep it visible but disabled
  if (isRunning) {
    resumeBtn.style.display = 'inline-flex';
    resumeBtn.disabled = true;
    resumeBtn.textContent = 'Resume';
    resumeBtn.title = 'Task is running. Resume is disabled.';
    return;
  }

  const info = await window.api.checkResume(workspacePath);
  if (!info || !info.found) {
    resumeBtn.style.display = 'none';
    return;
  }

  resumeBtn.style.display = 'inline-flex';
  resumeBtn.disabled = false;
  resumeBtn.textContent = 'Resume';
  resumeBtn.title = `Resume interrupted task (stack depth: ${info.stack_depth || '?'})`;
}

if (resumeBtn) {
  resumeBtn.addEventListener('click', async () => {
    if (!workspacePath || isRunning) return;
    const info = await window.api.checkResume(workspacePath);
    if (!info?.found) {
      addErrorMessage('No resumable task found for this workspace.');
      await refreshResumeButton();
      return;
    }

    isRunning = true;
    sendBtn.style.display = 'none';
    stopBtn.style.display = 'flex';
    userInput.disabled = true;
    statusText.textContent = 'Resuming...';
    await refreshResumeButton();

    showTypingIndicator();
    const result = await window.api.resumeTask({
      workspacePath,
      agentSystem: agentSystemSelect.value
    });
    if (result?.error) {
      removeTypingIndicator();
      addErrorMessage(result.error);
      resetState();
      await refreshResumeButton();
    }
  });
}

// ==================== Send Message ====================
sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
});

async function sendMessage() {
  const text = userInput.value.trim();
  if (!text || !workspacePath || isRunning) return;
  
  addUserMessage(text);
  userInput.value = '';
  userInput.style.height = 'auto';
  
  isRunning = true;
  sendBtn.style.display = 'none';
  stopBtn.style.display = 'flex';
  userInput.disabled = true;
  statusText.textContent = 'Running...';
  
  showTypingIndicator();
  
  const result = await window.api.startTask({
    workspacePath,
    userInput: text,
    agentName: 'alpha_agent',
    agentSystem: agentSystemSelect.value
  });
  
  if (result.error) {
    removeTypingIndicator();
    addErrorMessage(result.error);
    resetState();
    await refreshResumeButton();
  }
}

// ==================== Stop Task ====================
stopBtn.addEventListener('click', async () => {
  await window.api.stopTask();
  statusText.textContent = 'Stopping...';
});

// ==================== Agent Events ====================
window.api.onAgentEvent((event) => {
  const type = event.type;
  
  switch (type) {
    case 'token':
      removeTypingIndicator();
      finalizeReasoningStream();
      streamToken(event.text || '');
      break;
      
    case 'reasoning_token':
      removeTypingIndicator();
      finalizeCurrentStream();
      streamReasoningToken(event.text || '');
      break;
      
    case 'thinking_token':
      removeTypingIndicator();
      finalizeCurrentStream();
      streamThinkingAgentToken(event.text || '');
      break;
      
    case 'tool_call':
      finalizeCurrentStream();
      removeTypingIndicator();
      addToolMessage(event.tool || event.name || 'unknown', 'running', event.arguments);
      showTypingIndicator();
      break;
      
    case 'tool_result':
      removeTypingIndicator();
      updateLastToolStatus(
        event.status === 'error' ? 'error' : 'success',
        event.output_preview
      );
      break;
      
    case 'agent_start':
      finalizeCurrentStream();
      removeTypingIndicator();
      addSystemMessage(`${event.agent || 'Agent'} started`);
      showTypingIndicator();
      break;
      
    case 'agent_end':
      finalizeCurrentStream();
      removeTypingIndicator();
      break;
      
    case 'thinking_start':
      finalizeCurrentStream();
      removeTypingIndicator();
      startThinkingAgentStream();
      break;
      
    case 'thinking_end':
      removeTypingIndicator();
      finalizeThinkingAgentStream();
      break;
      
    case 'error':
      finalizeCurrentStream();
      removeTypingIndicator();
      addErrorMessage(event.message || event.error || 'Unknown error');
      break;
      
    case 'result':
      finalizeCurrentStream();
      removeTypingIndicator();
      if (event.summary) {
        streamToken(event.summary);
        finalizeCurrentStream();
      }
      break;
      
    default:
      if (event.text) {
        removeTypingIndicator();
        streamToken(event.text);
      }
  }
  
  scrollToBottom();
});

window.api.onAgentLog((log) => {
  console.log('[Agent Log]', log);
});

window.api.onAgentDone((result) => {
  finalizeCurrentStream();
  removeTypingIndicator();
  
  if (result.code !== 0 && result.code !== null) {
    statusText.textContent = `Ended with code ${result.code}`;
    statusText.style.color = '#c75450';
  } else {
    statusText.textContent = 'Task completed';
    statusText.style.color = '#5a9a6a';
  }
  
  resetState();
  scrollToBottom();
  
  // Refresh conversation list after task ends
  loadConversations();
  refreshResumeButton();
});

// ==================== Message Builders ====================

function addUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'message-user';
  div.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  messagesContainer.appendChild(div);
  scrollToBottom();
}

function addSystemMessage(text) {
  const div = document.createElement('div');
  div.className = 'message-system';
  div.textContent = `— ${text} —`;
  messagesContainer.appendChild(div);
}

function addErrorMessage(text) {
  const div = document.createElement('div');
  div.className = 'message-error';
  div.innerHTML = `<div class="error-card">${escapeHtml(text)}</div>`;
  messagesContainer.appendChild(div);
}

function addToolMessage(toolName, status, args) {
  const div = document.createElement('div');
  div.className = 'message-tool';
  
  let argsHtml = '';
  if (args && typeof args === 'object' && Object.keys(args).length > 0) {
    const argsStr = JSON.stringify(args, null, 2);
    argsHtml = `
      <details class="tool-details">
        <summary class="tool-params-toggle">Parameters</summary>
        <pre class="tool-params-content">${escapeHtml(argsStr)}</pre>
      </details>
    `;
  }

  // Human-in-loop: inline response UI (seamless)
  let hilHtml = '';
  if (toolName === 'human_in_loop' && args && typeof args === 'object') {
    const hilId = args.hil_id || '';
    const instruction = args.instruction || '';
    if (hilId && instruction) {
      hilHtml = `
        <div class="hil-card">
          <div class="hil-title">Human-in-loop</div>
          <div class="hil-instruction">${escapeHtml(String(instruction))}</div>
          <div class="hil-actions">
            <textarea class="hil-input" rows="3" placeholder="在这里输入你的回复，然后发送…"></textarea>
            <button class="btn hil-send">Send</button>
          </div>
          <div class="hil-meta">hil_id: <code>${escapeHtml(String(hilId))}</code></div>
        </div>
      `;
    }
  }
  
  div.innerHTML = `
    <div class="tool-card tool-${status}">
      <div class="tool-header">
        <span class="tool-dot tool-dot-${status}"></span>
        <span class="tool-name">${escapeHtml(toolName)}</span>
        <span class="tool-status-label">${status === 'running' ? 'running...' : status}</span>
      </div>
      ${argsHtml}
      ${hilHtml}
      <div class="tool-result-area" style="display:none;"></div>
    </div>
  `;
  div.dataset.toolMessage = 'true';
  messagesContainer.appendChild(div);

  // Bind HIL send button if present
  if (toolName === 'human_in_loop' && args && typeof args === 'object') {
    const hilId = args.hil_id;
    const sendBtn = div.querySelector('.hil-send');
    const input = div.querySelector('.hil-input');
    if (sendBtn && input && hilId) {
      sendBtn.addEventListener('click', async () => {
        const text = (input.value || '').trim();
        if (!text) return;
        sendBtn.disabled = true;
        input.disabled = true;
        sendBtn.textContent = 'Sent';
        const r = await window.api.hilRespond({ hil_id: hilId, response: text });
        if (r && r.error) {
          sendBtn.disabled = false;
          input.disabled = false;
          sendBtn.textContent = 'Send';
          addErrorMessage(`HIL respond failed: ${r.error}`);
        } else {
          // show as a user message in chat for traceability
          addUserMessage(text);
        }
      });
    }
  }
  scrollToBottom();
}

function updateLastToolStatus(status, outputPreview) {
  const tools = messagesContainer.querySelectorAll('[data-tool-message]');
  if (tools.length > 0) {
    const last = tools[tools.length - 1];
    const card = last.querySelector('.tool-card');
    const dot = last.querySelector('.tool-dot');
    const label = last.querySelector('.tool-status-label');
    if (card) card.className = `tool-card tool-${status}`;
    if (dot) dot.className = `tool-dot tool-dot-${status}`;
    if (label) label.textContent = status === 'success' ? 'done' : status;
    
    if (outputPreview) {
      const resultArea = last.querySelector('.tool-result-area');
      if (resultArea) {
        resultArea.style.display = 'block';
        resultArea.innerHTML = `
          <details class="tool-details">
            <summary class="tool-params-toggle">Result</summary>
            <pre class="tool-params-content">${escapeHtml(outputPreview)}</pre>
          </details>
        `;
      }
    }
  }
}

// ==================== Streaming ====================

function streamToken(text) {
  if (!currentAgentBubble) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-agent';
    
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    
    const label = document.createElement('div');
    label.className = 'agent-label';
    label.textContent = 'Agent';
    
    const content = document.createElement('div');
    content.className = 'agent-content';
    
    bubble.appendChild(label);
    bubble.appendChild(content);
    wrapper.appendChild(bubble);
    messagesContainer.appendChild(wrapper);
    
    currentAgentBubble = wrapper;
    currentAgentContentDiv = content;
    currentStreamText = '';
  }
  
  currentStreamText += text;
  currentAgentContentDiv.innerText = currentStreamText;
  scrollToBottom();
}

function finalizeCurrentStream() {
  // Convert the just-streamed text to Markdown on finalize
  if (currentAgentContentDiv && currentStreamText) {
    setMarkdown(currentAgentContentDiv, currentStreamText);
  }
  currentAgentBubble = null;
  currentAgentContentDiv = null;
  currentStreamText = '';
}

// ==================== Reasoning Stream ====================

let reasoningBubble = null;
let reasoningContentDiv = null;
let reasoningStreamText = '';

function streamReasoningToken(text) {
  if (!reasoningBubble) {
    const div = document.createElement('div');
    div.className = 'message-thinking';
    div.innerHTML = `
      <div class="thinking-card">
        <details open>
          <summary>Model Reasoning</summary>
          <div class="thinking-content"></div>
        </details>
      </div>
    `;
    messagesContainer.appendChild(div);
    reasoningBubble = div;
    reasoningContentDiv = div.querySelector('.thinking-content');
    reasoningStreamText = '';
  }
  
  reasoningStreamText += text;
  reasoningContentDiv.innerText = reasoningStreamText;
  scrollToBottom();
}

function finalizeReasoningStream() {
  if (reasoningBubble) {
    const details = reasoningBubble.querySelector('details');
    if (details) {
      details.open = false;
      const summary = details.querySelector('summary');
      if (summary) summary.textContent = 'Model Reasoning (click to expand)';
    }
  }
  // Convert reasoning to Markdown before finalize
  if (reasoningContentDiv && reasoningStreamText) {
    setMarkdown(reasoningContentDiv, reasoningStreamText);
  }
  reasoningBubble = null;
  reasoningContentDiv = null;
  reasoningStreamText = '';
}

// ==================== Thinking Agent Stream ====================

let thinkingAgentBubble = null;
let thinkingAgentContentDiv = null;
let thinkingAgentText = '';

function startThinkingAgentStream() {
  const div = document.createElement('div');
  div.className = 'message-thinking';
  div.innerHTML = `
    <div class="thinking-card">
      <details open>
        <summary>Thinking...</summary>
        <div class="thinking-content"></div>
      </details>
    </div>
  `;
  messagesContainer.appendChild(div);
  thinkingAgentBubble = div;
  thinkingAgentContentDiv = div.querySelector('.thinking-content');
  thinkingAgentText = '';
  scrollToBottom();
}

function streamThinkingAgentToken(text) {
  if (!thinkingAgentBubble) startThinkingAgentStream();
  thinkingAgentText += text;
  thinkingAgentContentDiv.innerText = thinkingAgentText;
  scrollToBottom();
}

function finalizeThinkingAgentStream() {
  if (thinkingAgentBubble) {
    const details = thinkingAgentBubble.querySelector('details');
    if (details) {
      details.open = false;
      const summary = details.querySelector('summary');
      if (summary) summary.textContent = 'Thinking (click to expand)';
    }
  }
  // Convert thinking to Markdown before finalize
  if (thinkingAgentContentDiv && thinkingAgentText) {
    setMarkdown(thinkingAgentContentDiv, thinkingAgentText);
  }
  thinkingAgentBubble = null;
  thinkingAgentContentDiv = null;
  thinkingAgentText = '';
}

// ==================== UI Helpers ====================

function showTypingIndicator() {
  if (messagesContainer.querySelector('.typing-indicator')) return;
  const div = document.createElement('div');
  div.className = 'typing-indicator';
  div.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
  messagesContainer.appendChild(div);
  scrollToBottom();
}

function removeTypingIndicator() {
  const indicator = messagesContainer.querySelector('.typing-indicator');
  if (indicator) indicator.remove();
}

function resetState() {
  isRunning = false;
  sendBtn.style.display = 'flex';
  stopBtn.style.display = 'none';
  userInput.disabled = false;
  userInput.focus();
  refreshResumeButton();
}

function scrollToBottom() {
  if (!autoScrollEnabled) return;
  requestAnimationFrame(() => {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  });
}

function forceScrollToBottom() {
  requestAnimationFrame(() => {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ==================== Auto Scroll Toggle ====================
function updateAutoScrollBtn() {
  if (!autoScrollBtn) return;
  autoScrollBtn.textContent = autoScrollEnabled ? 'Auto Scroll: On' : 'Auto Scroll: Off';
  autoScrollBtn.classList.toggle('off', !autoScrollEnabled);
}

if (autoScrollBtn) {
  autoScrollBtn.addEventListener('click', () => {
    autoScrollEnabled = !autoScrollEnabled;
    updateAutoScrollBtn();
    if (autoScrollEnabled) forceScrollToBottom();
  });
  updateAutoScrollBtn();
}

// Keep chat scroll usable even when nested <pre>/<thinking> areas exist.
// If inner scroll area can't continue scrolling in current direction,
// route wheel delta to the main messages container.
if (messagesContainer) {
  const INNER_SCROLL_SELECTOR = '.tool-params-content, .thinking-content';
  messagesContainer.addEventListener('wheel', (e) => {
    let node = e.target;
    while (node && node !== messagesContainer) {
      if (node.matches && node.matches(INNER_SCROLL_SELECTOR)) {
        const canScrollUp = node.scrollTop > 0;
        const canScrollDown = node.scrollTop + node.clientHeight < node.scrollHeight - 1;
        if ((e.deltaY < 0 && canScrollUp) || (e.deltaY > 0 && canScrollDown)) {
          return; // Let inner panel consume wheel
        }
        break; // Inner panel at edge -> fall through to main container
      }
      node = node.parentElement;
    }
    e.preventDefault();
    messagesContainer.scrollTop += e.deltaY;
  }, { passive: false });
}

// ==================== Settings Modal ====================

const settingsModal = document.getElementById('settings-modal');
const settingsBtn = document.getElementById('settings-btn');
const settingsCloseBtn = document.getElementById('settings-close-btn');
const settingsSaveBtn = document.getElementById('settings-save-btn');
const settingsStatus = document.getElementById('settings-status');
const toggleApiKeyBtn = document.getElementById('toggle-api-key');
const importAgentSystemBtn = document.getElementById('import-agent-system-btn');
const deleteAgentSystemBtn = document.getElementById('delete-agent-system-btn');
const rawYamlTextarea = document.getElementById('setting-raw-yaml');
const freshRuntimeBtn = document.getElementById('fresh-runtime-btn');

// Open settings
settingsBtn.addEventListener('click', async () => {
  settingsModal.style.display = 'flex';
  await loadSettings();
});

// Close settings
settingsCloseBtn.addEventListener('click', () => {
  settingsModal.style.display = 'none';
});

settingsModal.addEventListener('click', (e) => {
  if (e.target === settingsModal) settingsModal.style.display = 'none';
});

// Tab switching
document.querySelectorAll('.modal-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.modal-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add('active');
  });
});

// Toggle API key visibility
toggleApiKeyBtn.addEventListener('click', () => {
  const input = document.getElementById('setting-api-key');
  input.type = input.type === 'password' ? 'text' : 'password';
});

// Load settings from backend
async function loadSettings() {
  const result = await window.api.getSettings();
  if (result.error) {
    settingsStatus.textContent = `Error: ${result.error}`;
    settingsStatus.style.color = '#c75450';
    return;
  }
  
  const c = result.config;
  lastLoadedSettingsConfig = (c && typeof c === 'object') ? c : {};
  document.getElementById('setting-base-url').value = c.base_url || '';
  document.getElementById('setting-api-key').value = c.api_key || '';
  document.getElementById('setting-timeout').value = c.timeout || 600;
  document.getElementById('setting-stream-timeout').value = c.stream_timeout || 30;
  document.getElementById('setting-first-chunk-timeout').value = c.first_chunk_timeout || 30;
  document.getElementById('setting-temperature').value = c.temperature ?? 0;
  document.getElementById('setting-max-tokens').value = c.max_tokens ?? 0;
  document.getElementById('setting-max-context').value = c.max_context_window || 500000;
  document.getElementById('setting-multimodal').checked = c.multimodal !== false;
  document.getElementById('setting-compressor-multimodal').checked = c.compressor_multimodal !== false;
  
  // Models (array → newline-separated)
  document.getElementById('setting-models').value = formatModelEntries(c.models || []);
  document.getElementById('setting-figure-models').value = formatModelEntries(c.figure_models || []);
  document.getElementById('setting-compressor-models').value = formatModelEntries(c.compressor_models || []);
  document.getElementById('setting-read-figure-models').value = formatModelEntries(c.read_figure_models || []);
  document.getElementById('setting-thinking-models').value = formatModelEntries(c.thinking_models || []);

  // Raw yaml
  if (rawYamlTextarea) rawYamlTextarea.value = result.raw_yaml || '';
  
  // Config path display
  document.getElementById('config-path-display').textContent = result.path || '—';
  
  // Load agent systems for both sidebar + settings
  await reloadAgentSystems(agentSystemSelect.value);

  // Load app config (env + market)
  const appCfgRes = await window.api.getAppConfig();
  if (appCfgRes?.success) {
    const cfg = appCfgRes.config || {};
    const env = cfg.env || {};
    const runtime = cfg.runtime || {};
    const context = cfg.context || {};
    const mcp = cfg.mcp || {};
    const market = cfg.market || {};
    const pathModeEl = document.getElementById('setting-path-mode');
    const commandModeEl = document.getElementById('setting-command-mode');
    const extraPathEl = document.getElementById('setting-extra-path');
    const extraEnvEl = document.getElementById('setting-extra-env');
    const marketUrlEl = document.getElementById('setting-market-url');
    if (pathModeEl) pathModeEl.value = env.shell_mode || 'system';
    if (commandModeEl) commandModeEl.value = env.command_mode || 'direct';
    if (extraPathEl) extraPathEl.value = Array.isArray(env.extra_path) ? env.extra_path.join('\n') : '';
    if (extraEnvEl) {
      const extraEnv = env.extra_env || {};
      const lines = Object.entries(extraEnv).map(([k, v]) => `${k}=${v ?? ''}`);
      extraEnvEl.value = lines.join('\n');
    }
    if (marketUrlEl) marketUrlEl.value = market.base_url || '';
    const actionWindowEl = document.getElementById('setting-action-window-steps');
    const thinkingIntervalEl = document.getElementById('setting-thinking-interval');
    const maxTurnsEl = document.getElementById('setting-max-turns');
    const freshEnabledEl = document.getElementById('setting-fresh-enabled');
    const freshIntervalEl = document.getElementById('setting-fresh-interval-sec');
    const userHistoryThresholdEl = document.getElementById('setting-user-history-threshold');
    const structuredAgentThresholdEl = document.getElementById('setting-structured-call-agent-threshold');
    const structuredTokenThresholdEl = document.getElementById('setting-structured-call-token-threshold');
    const mcpServersEl = document.getElementById('setting-mcp-servers');
    if (actionWindowEl) actionWindowEl.value = runtime.action_window_steps ?? 30;
    if (thinkingIntervalEl) thinkingIntervalEl.value = runtime.thinking_interval ?? runtime.action_window_steps ?? 30;
    if (maxTurnsEl) maxTurnsEl.value = runtime.max_turns ?? 100000;
    if (freshEnabledEl) freshEnabledEl.checked = !!runtime.fresh_enabled;
    if (freshIntervalEl) freshIntervalEl.value = runtime.fresh_interval_sec ?? 0;
    if (userHistoryThresholdEl) userHistoryThresholdEl.value = context.user_history_compress_threshold_tokens ?? 1500;
    if (structuredAgentThresholdEl) structuredAgentThresholdEl.value = context.structured_call_info_compress_threshold_agents ?? 10;
    if (structuredTokenThresholdEl) structuredTokenThresholdEl.value = context.structured_call_info_compress_threshold_tokens ?? 2200;
    if (mcpServersEl) {
      const lines = Array.isArray(mcp.servers) ? mcp.servers.map(item => JSON.stringify(item)) : [];
      mcpServersEl.value = lines.join('\n');
    }
  }
  
  settingsStatus.textContent = '';
}

// Import agent system folder
if (importAgentSystemBtn) {
  importAgentSystemBtn.addEventListener('click', async () => {
    const result = await window.api.importAgentSystemFolder();
    if (result?.canceled) return;
    if (result?.error) {
      settingsStatus.textContent = `Error: ${result.error}`;
      settingsStatus.style.color = '#c75450';
      return;
    }
    settingsStatus.textContent = `Imported Agent System: ${result.name}`;
    settingsStatus.style.color = '#5a9a6a';

    await reloadAgentSystems(result?.name || null);

    setTimeout(() => { settingsStatus.textContent = ''; }, 3000);
  });
}

// Delete selected agent system (user library only)
if (deleteAgentSystemBtn) {
  deleteAgentSystemBtn.addEventListener('click', async () => {
    const select = document.getElementById('setting-agent-system');
    const sys = select?.value;
    if (!sys) return;
    if (!confirm(`Delete Agent System "${sys}" from ~/mla_v3/agent_library/? (Bundled copy inside app is untouched)`)) return;
    const res = await window.api.deleteAgentSystem(sys);
    if (res?.error) {
      settingsStatus.textContent = `Error: ${res.error}`;
      settingsStatus.style.color = '#c75450';
      return;
    }
    settingsStatus.textContent = `Deleted Agent System: ${sys}`;
    settingsStatus.style.color = '#5a9a6a';
    await reloadAgentSystems();
    setTimeout(() => { settingsStatus.textContent = ''; }, 3000);
  });
}

if (freshRuntimeBtn) {
  freshRuntimeBtn.addEventListener('click', async () => {
    const res = await window.api.freshRuntime({ reason: 'manual fresh from desktop settings' });
    if (res?.error) {
      settingsStatus.textContent = `Error: ${res.error}`;
      settingsStatus.style.color = '#c75450';
      return;
    }
    await reloadAgentSystems(agentSystemSelect.value);
    settingsStatus.textContent = res?.running
      ? 'Fresh request sent to running task'
      : 'Runtime config updated. New tasks will use fresh settings';
    settingsStatus.style.color = '#5a9a6a';
    setTimeout(() => { settingsStatus.textContent = ''; }, 3000);
  });
}

// Save settings
settingsSaveBtn.addEventListener('click', async () => {
  // If Raw YAML tab is active, save raw YAML as-is
  const activeTab = document.querySelector('.modal-tab.active')?.dataset?.tab;
  if (activeTab === 'yaml') {
    const yamlText = (rawYamlTextarea?.value || '').trimEnd() + '\n';
    const result = await window.api.saveSettings(yamlText);
    if (result.success) {
      settingsStatus.textContent = 'YAML saved successfully';
      settingsStatus.style.color = '#5a9a6a';
    } else {
      settingsStatus.textContent = `Error: ${result.error}`;
      settingsStatus.style.color = '#c75450';
    }
    setTimeout(() => { settingsStatus.textContent = ''; }, 3000);
    return;
  }

  // Environment tab saves app_config.json
  if (activeTab === 'env') {
    const mode = document.getElementById('setting-path-mode')?.value || 'system';
    const commandMode = document.getElementById('setting-command-mode')?.value || 'direct';
    const extraPathText = document.getElementById('setting-extra-path')?.value || '';
    const extraEnvText = document.getElementById('setting-extra-env')?.value || '';
    const marketUrl = document.getElementById('setting-market-url')?.value || '';

    const extra_path = extraPathText.split('\n').map(s => s.trim()).filter(Boolean);
    const extra_env = {};
    for (const line of extraEnvText.split('\n')) {
      const t = line.trim();
      if (!t || t.startsWith('#')) continue;
      const idx = t.indexOf('=');
      if (idx <= 0) continue;
      const k = t.slice(0, idx).trim();
      const v = t.slice(idx + 1).trim();
      if (k) extra_env[k] = v;
    }

    const mcpServersText = document.getElementById('setting-mcp-servers')?.value || '';
    const mcpServers = [];
    for (const rawLine of mcpServersText.split('\n')) {
      const line = rawLine.trim();
      if (!line || line.startsWith('#')) continue;
      if (line.startsWith('{')) {
        try {
          const parsed = JSON.parse(line);
          if (parsed && typeof parsed === 'object') mcpServers.push(parsed);
        } catch (_) {}
        continue;
      }
      const idx = line.indexOf('=');
      if (idx > 0) {
        const name = line.slice(0, idx).trim();
        const url = line.slice(idx + 1).trim();
        if (name && url) mcpServers.push({ name, transport: 'streamable_http', url });
      } else {
        mcpServers.push({ transport: 'streamable_http', url: line });
      }
    }

    const appCfg = {
      env: { shell_mode: mode, command_mode: commandMode, extra_path, extra_env },
      runtime: {
        action_window_steps: readPositiveNumber(document.getElementById('setting-action-window-steps')?.value, 30),
        thinking_interval: readPositiveNumber(document.getElementById('setting-thinking-interval')?.value, 30),
        max_turns: readPositiveNumber(document.getElementById('setting-max-turns')?.value, 100000),
        fresh_enabled: !!document.getElementById('setting-fresh-enabled')?.checked,
        fresh_interval_sec: Number(document.getElementById('setting-fresh-interval-sec')?.value) || 0
      },
      context: {
        user_history_compress_threshold_tokens: readNonNegativeNumber(document.getElementById('setting-user-history-threshold')?.value, 1500),
        structured_call_info_compress_threshold_agents: readPositiveNumber(document.getElementById('setting-structured-call-agent-threshold')?.value, 10),
        structured_call_info_compress_threshold_tokens: readNonNegativeNumber(document.getElementById('setting-structured-call-token-threshold')?.value, 2200)
      },
      mcp: { servers: mcpServers },
      market: { base_url: String(marketUrl || '').trim() }
    };

    const res = await window.api.saveAppConfig(appCfg);
    if (res?.success) {
      settingsStatus.textContent = 'Environment settings saved';
      settingsStatus.style.color = '#5a9a6a';
    } else {
      settingsStatus.textContent = `Error: ${res?.error || 'Failed to save'}`;
      settingsStatus.style.color = '#c75450';
    }
    setTimeout(() => { settingsStatus.textContent = ''; }, 3000);
    return;
  }

  const modelsText = document.getElementById('setting-models').value.trim();
  const figureModelsText = document.getElementById('setting-figure-models').value.trim();
  const compressorModelsText = document.getElementById('setting-compressor-models').value.trim();
  const readFigureModelsText = document.getElementById('setting-read-figure-models').value.trim();
  const thinkingModelsText = document.getElementById('setting-thinking-models').value.trim();
  
  const config = {
    ...lastLoadedSettingsConfig,
    temperature: Number(document.getElementById('setting-temperature').value) || 0,
    max_tokens: Number(document.getElementById('setting-max-tokens').value) || 0,
    max_context_window: Number(document.getElementById('setting-max-context').value) || 500000,
    base_url: document.getElementById('setting-base-url').value.trim(),
    api_key: document.getElementById('setting-api-key').value.trim(),
    timeout: Number(document.getElementById('setting-timeout').value) || 600,
    stream_timeout: Number(document.getElementById('setting-stream-timeout').value) || 30,
    first_chunk_timeout: Number(document.getElementById('setting-first-chunk-timeout').value) || 30,
    models: parseModelEntries(modelsText),
    figure_models: parseModelEntries(figureModelsText),
    compressor_models: parseModelEntries(compressorModelsText),
    read_figure_models: parseModelEntries(readFigureModelsText),
    thinking_models: parseModelEntries(thinkingModelsText),
    multimodal: document.getElementById('setting-multimodal').checked,
    compressor_multimodal: document.getElementById('setting-compressor-multimodal').checked
  };
  
  const result = await window.api.saveSettings(config);
  if (result.success) {
    settingsStatus.textContent = 'Settings saved successfully';
    settingsStatus.style.color = '#5a9a6a';
    
    // Sync agent system select in sidebar
    const agentSys = document.getElementById('setting-agent-system').value;
    if (agentSys) {
      // Update sidebar select if the option exists
      const opt = agentSystemSelect.querySelector(`option[value="${agentSys}"]`);
      if (opt) agentSystemSelect.value = agentSys;
    }
  } else {
    settingsStatus.textContent = `Error: ${result.error}`;
    settingsStatus.style.color = '#c75450';
  }
  
  setTimeout(() => { settingsStatus.textContent = ''; }, 3000);
});

// ==================== Marketplace Modal ====================

const marketModal = document.getElementById('market-modal');
const marketBtn = document.getElementById('market-btn');
const marketCloseBtn = document.getElementById('market-close-btn');
const marketRefreshBtn = document.getElementById('market-refresh-btn');
const marketSearch = document.getElementById('market-search');
const marketList = document.getElementById('market-list');
const marketStatus = document.getElementById('market-status');
const marketTabSkills = document.getElementById('market-tab-skills');
const marketTabSystems = document.getElementById('market-tab-systems');

let marketIndexCache = null;
let marketActiveKind = 'skill'; // 'skill' | 'agent_system'

function setMarketStatus(text, isError = false) {
  if (!marketStatus) return;
  marketStatus.textContent = text || '';
  marketStatus.style.color = isError ? '#c75450' : '#5a9a6a';
}

function formatModelEntries(value) {
  if (!Array.isArray(value)) return '';
  return value.map(item => {
    if (typeof item === 'string') return item;
    try {
      return JSON.stringify(item);
    } catch (_) {
      return String(item ?? '');
    }
  }).join('\n');
}

function parseModelEntries(text) {
  return String(text || '')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => {
      if (line.startsWith('{') || line.startsWith('[')) {
        try {
          return JSON.parse(line);
        } catch (_) {
          return line;
        }
      }
      return line;
    });
}

function readPositiveNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function readNonNegativeNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
}

function filterMarketItems(items, q) {
  const query = String(q || '').trim().toLowerCase();
  if (!query) return items;
  return items.filter(it => {
    const name = String(it?.name || '').toLowerCase();
    const desc = String(it?.description || '').toLowerCase();
    return name.includes(query) || desc.includes(query);
  });
}

function renderMarketList() {
  if (!marketList) return;
  const q = marketSearch?.value || '';
  const idx = marketIndexCache?.index || marketIndexCache;
  if (!idx) {
    marketList.innerHTML = '<div class="empty-state">No data. Click refresh.</div>';
    return;
  }
  const items = (marketActiveKind === 'skill') ? (idx.skills || []) : (idx.agent_systems || []);
  const filtered = filterMarketItems(items, q);
  if (filtered.length === 0) {
    marketList.innerHTML = '<div class="empty-state">No matches.</div>';
    return;
  }
  marketList.innerHTML = filtered.map(it => `
    <div class="skill-item">
      <div class="skill-info">
        <div class="skill-name">${escapeHtml(it.name || '')}</div>
        ${(() => {
          const d = String(it.description || '');
          const truncated = d.length > 120;
          const safe = escapeHtml(d);
          return `
            <div class="skill-desc">
              <span class="desc-text ${truncated ? 'truncated' : ''}">${safe}</span>
              ${truncated ? '<span class="desc-toggle" data-action="toggle">More</span>' : ''}
            </div>
          `;
        })()}
      </div>
      <button class="btn-secondary market-install-btn" data-name="${escapeHtml(it.name || '')}">Install</button>
    </div>
  `).join('');

  marketList.querySelectorAll('.market-install-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      await installFromMarket(marketActiveKind, name);
    });
  });

  // Expand / collapse descriptions (event delegation)
  marketList.querySelectorAll('.desc-toggle').forEach(t => {
    t.addEventListener('click', () => {
      const row = t.closest('.skill-item');
      const text = row?.querySelector('.desc-text');
      if (!text) return;
      const isExpanded = text.classList.toggle('expanded');
      if (isExpanded) {
        text.classList.remove('truncated');
        t.textContent = 'Less';
      } else {
        text.classList.add('truncated');
        t.textContent = 'More';
      }
    });
  });
}

async function loadMarketIndex() {
  setMarketStatus('Loading...', false);
  const res = await window.api.marketGetIndex();
  if (res?.error) {
    marketIndexCache = null;
    setMarketStatus(res.error, true);
    renderMarketList();
    return;
  }
  marketIndexCache = res;
  setMarketStatus(`Loaded from ${res.base_url}`, false);
  renderMarketList();
}

async function installFromMarket(kind, name) {
  setMarketStatus(`Installing ${name}...`, false);
  const res1 = await window.api.marketInstall({ kind: kind === 'skill' ? 'skill' : 'agent_system', name });
  if (res1?.conflict) {
    const overwrite = confirm(`"${name}" already exists. Click OK to overwrite, Cancel to keep both.`);
    const strategy = overwrite ? 'overwrite' : 'keep_both';
    const res2 = await window.api.marketInstall({ kind: kind === 'skill' ? 'skill' : 'agent_system', name, strategy });
    if (res2?.success) {
      setMarketStatus(`Installed: ${res2.installed_name}`, false);
      // refresh agent systems if installed
      if (kind !== 'skill') await reloadAgentSystems();
      return;
    }
    setMarketStatus(res2?.error || 'Install failed', true);
    return;
  }
  if (res1?.success) {
    setMarketStatus(`Installed: ${res1.installed_name}`, false);
    if (kind !== 'skill') await reloadAgentSystems();
    return;
  }
  setMarketStatus(res1?.error || 'Install failed', true);
}

if (marketBtn) {
  marketBtn.addEventListener('click', async () => {
    marketModal.style.display = 'flex';
    marketActiveKind = 'skill';
    await loadMarketIndex();
  });
}
if (marketCloseBtn) {
  marketCloseBtn.addEventListener('click', () => { marketModal.style.display = 'none'; });
}
if (marketModal) {
  marketModal.addEventListener('click', (e) => {
    if (e.target === marketModal) marketModal.style.display = 'none';
  });
}
if (marketRefreshBtn) marketRefreshBtn.addEventListener('click', loadMarketIndex);
if (marketSearch) marketSearch.addEventListener('input', renderMarketList);
if (marketTabSkills) marketTabSkills.addEventListener('click', () => { marketActiveKind = 'skill'; renderMarketList(); });
if (marketTabSystems) marketTabSystems.addEventListener('click', () => { marketActiveKind = 'agent_system'; renderMarketList(); });

// ==================== Skills Modal ====================

const skillsModal = document.getElementById('skills-modal');
const skillsBtn = document.getElementById('skills-btn');
const skillsCloseBtn = document.getElementById('skills-close-btn');
const importSkillBtn = document.getElementById('import-skill-btn');
const refreshSkillsBtn = document.getElementById('refresh-skills-btn');
const skillsList = document.getElementById('skills-list');

// Open skills modal
skillsBtn.addEventListener('click', async () => {
  skillsModal.style.display = 'flex';
  await loadSkills();
});

// Close skills modal
skillsCloseBtn.addEventListener('click', () => {
  skillsModal.style.display = 'none';
});

skillsModal.addEventListener('click', (e) => {
  if (e.target === skillsModal) skillsModal.style.display = 'none';
});

// Initial sidebar agent-system refresh on app startup, even before opening Settings.
reloadAgentSystems().catch(() => {});

// Import skill folder
importSkillBtn.addEventListener('click', async () => {
  const result = await window.api.importSkillFolder();
  if (result.canceled) return;
  if (result.error) {
    alert(`Import failed: ${result.error}`);
    return;
  }
  await loadSkills();
});

// Refresh skills
refreshSkillsBtn.addEventListener('click', loadSkills);

async function loadSkills() {
  const result = await window.api.getSkills();
  if (result.error) {
    skillsList.innerHTML = `<div class="empty-state">Error: ${escapeHtml(result.error)}</div>`;
    return;
  }
  
  if (result.skills.length === 0) {
    skillsList.innerHTML = '<div class="empty-state">No skills imported yet. Click "Import Skill Folder" to add one.</div>';
    return;
  }
  
  skillsList.innerHTML = result.skills.map(skill => `
    <div class="skill-item">
      <div class="skill-info">
        <div class="skill-name">${escapeHtml(skill.name)}</div>
        <div class="skill-desc">${escapeHtml(skill.description || 'No description')}</div>
        ${skill.hasSkillMd ? '<span class="skill-badge">SKILL.md ✓</span>' : '<span class="skill-badge warn">No SKILL.md</span>'}
      </div>
      <button class="skill-delete-btn" data-skill="${escapeHtml(skill.name)}" title="Delete">✕</button>
    </div>
  `).join('');
  
  // Attach delete handlers
  skillsList.querySelectorAll('.skill-delete-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.skill;
      if (confirm(`Delete skill "${name}"?`)) {
        await window.api.deleteSkill(name);
        await loadSkills();
      }
    });
  });
}

// ==================== Conversation History ====================

const conversationsContainer = document.getElementById('conversations');
const refreshConversationsBtn = document.getElementById('refresh-conversations-btn');

refreshConversationsBtn.addEventListener('click', loadConversations);

async function loadConversations() {
  const result = await window.api.getConversations();
  if (result.error) {
    conversationsContainer.innerHTML = `<div class="empty-state">Error loading</div>`;
    return;
  }
  
  if (result.conversations.length === 0) {
    conversationsContainer.innerHTML = '<div class="empty-state">No conversations yet</div>';
    return;
  }
  
  conversationsContainer.innerHTML = result.conversations.map(conv => {
    const date = new Date(conv.lastUpdated);
    const timeStr = formatRelativeTime(date);
    
    return `
      <div class="conversation-item" data-task-id="${escapeHtml(conv.taskId)}" data-file="${escapeHtml(conv.file)}" title="${escapeHtml(conv.taskId)}">
        <div class="conv-main">
          <div class="conv-workspace">${escapeHtml(conv.workspaceName)}</div>
          <div class="conv-preview">${escapeHtml(conv.preview)}</div>
        </div>
        <div class="conv-meta">
          <span class="conv-time">${timeStr}</span>
          <span class="conv-turns">${conv.turns || 0} turns</span>
        </div>
        <button class="conv-delete-btn" data-file="${escapeHtml(conv.file)}" title="Delete">✕</button>
      </div>
    `;
  }).join('');
  
  // Click to load workspace
  conversationsContainer.querySelectorAll('.conversation-item').forEach(item => {
    item.addEventListener('click', async (e) => {
      // Don't trigger on delete button
      if (e.target.closest('.conv-delete-btn')) return;
      
      const taskId = item.dataset.taskId;
      const file = item.dataset.file;
      if (taskId && !isRunning) {
        workspacePath = taskId;
        const folderName = taskId.split('/').pop() || taskId.split('\\').pop();
        if (workspaceCurrent) {
          workspaceCurrent.textContent = taskId;
          workspaceCurrent.title = taskId;
        }
        userInput.disabled = false;
        sendBtn.disabled = false;
        statusText.textContent = `Workspace: ${folderName}`;
        
        const welcome = messagesContainer.querySelector('.welcome-message');
        if (welcome) welcome.remove();

        if (file) {
          await loadConversationDetail(file);
        }
        await refreshResumeButton();
        
        // Highlight selected
        conversationsContainer.querySelectorAll('.conversation-item').forEach(i => i.classList.remove('active'));
        item.classList.add('active');
      }
    });
  });
  
  // Delete handlers
  conversationsContainer.querySelectorAll('.conv-delete-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const fileName = btn.dataset.file;
      if (confirm('Delete this conversation history?')) {
        await window.api.deleteConversation(fileName);
        await loadConversations();
      }
    });
  });
}

function formatRelativeTime(date) {
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

async function loadConversationDetail(fileName) {
  const res = await window.api.getConversationDetail(fileName);
  if (res?.error) {
    addErrorMessage(`Failed to load conversation: ${res.error}`);
    return;
  }
  const data = res?.data;
  if (!data) return;

  // Clear chat area and render share_context content
  messagesContainer.innerHTML = '';
  finalizeCurrentStream();
  finalizeReasoningStream();
  finalizeThinkingAgentStream();

  renderShareContext(data);
  scrollToBottom();
}

function renderShareContext(data) {
  const turns = Array.isArray(data.history) ? data.history : [];
  for (const turn of turns) {
    const instructions = Array.isArray(turn?.instructions) ? turn.instructions : [];
    for (const inst of instructions) {
      if (inst?.instruction) addUserMessage(String(inst.instruction));
    }

    const agentsStatus = turn?.agents_status && typeof turn.agents_status === 'object' ? Object.values(turn.agents_status) : [];
    const topLevel = agentsStatus.filter(a => a && a.final_output && (a.parent_id === null || a.parent_id === undefined) && (a.level === 0 || a.level === undefined));
    const picked = topLevel.length > 0 ? topLevel : agentsStatus.filter(a => a && a.final_output);

    for (const a of picked) {
      addAgentMessage(String(a.agent_name || 'Agent'), String(a.final_output || ''));
    }
  }
}

function addAgentMessage(label, text) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message-agent';

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  const l = document.createElement('div');
  l.className = 'agent-label';
  l.textContent = label;

  const content = document.createElement('div');
  content.className = 'agent-content markdown';
  setMarkdown(content, text);

  bubble.appendChild(l);
  bubble.appendChild(content);
  wrapper.appendChild(bubble);
  messagesContainer.appendChild(wrapper);
}

// ==================== Keyboard Shortcuts ====================

document.addEventListener('keydown', (e) => {
  // Escape to close modals
  if (e.key === 'Escape') {
    settingsModal.style.display = 'none';
    skillsModal.style.display = 'none';
  }
  
  // Cmd+, to open settings
  if ((e.metaKey || e.ctrlKey) && e.key === ',') {
    e.preventDefault();
    settingsBtn.click();
  }
  
  // Cmd+N for new chat
  if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
    e.preventDefault();
    newChatBtn.click();
  }
});

// ==================== Init ====================

// Load conversations on startup
loadConversations();
