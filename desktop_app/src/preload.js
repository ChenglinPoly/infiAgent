const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // Workspace
  selectFolder: () => ipcRenderer.invoke('select-folder'),
  
  // Agent
  startTask: (params) => ipcRenderer.invoke('start-task', params),
  stopTask: () => ipcRenderer.invoke('stop-task'),
  hilRespond: (params) => ipcRenderer.invoke('hil-respond', params),
  
  // Events from main process
  onAgentEvent: (callback) => ipcRenderer.on('agent-event', (_, event) => callback(event)),
  onAgentLog: (callback) => ipcRenderer.on('agent-log', (_, log) => callback(log)),
  onAgentDone: (callback) => ipcRenderer.on('agent-done', (_, result) => callback(result)),
  
  // Settings (llm_config.yaml)
  getSettings: () => ipcRenderer.invoke('get-settings'),
  saveSettings: (config) => ipcRenderer.invoke('save-settings', config),
  getAgentSystems: () => ipcRenderer.invoke('get-agent-systems'),
  importAgentSystemFolder: () => ipcRenderer.invoke('import-agent-system-folder'),
  deleteAgentSystem: (name) => ipcRenderer.invoke('delete-agent-system', name),

  // App config (app_config.json)
  getAppConfig: () => ipcRenderer.invoke('get-app-config'),
  saveAppConfig: (config) => ipcRenderer.invoke('save-app-config', config),

  // Marketplace
  marketGetIndex: () => ipcRenderer.invoke('market-get-index'),
  marketInstall: (params) => ipcRenderer.invoke('market-install', params),
  
  // Skills library
  importSkillFolder: () => ipcRenderer.invoke('import-skill-folder'),
  getSkills: () => ipcRenderer.invoke('get-skills'),
  deleteSkill: (name) => ipcRenderer.invoke('delete-skill', name),
  
  // Conversation history
  getConversations: () => ipcRenderer.invoke('get-conversations'),
  getConversationDetail: (fileName) => ipcRenderer.invoke('get-conversation-detail', fileName),
  deleteConversation: (fileName) => ipcRenderer.invoke('delete-conversation', fileName),
  openConversationsFolder: () => ipcRenderer.invoke('open-conversations-folder'),

  // Resume (CLI-compatible)
  checkResume: (taskId) => ipcRenderer.invoke('check-resume', taskId),
  resumeTask: (params) => ipcRenderer.invoke('resume-task', params),
  
  // Remove listeners
  removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel)
});
