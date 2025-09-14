// 配置 - 可以通过URL参数或localStorage配置
let API_BASE_URL = getAPIBaseURL();

function getAPIBaseURL() {
    // 1. 检查URL参数
    const urlParams = new URLSearchParams(window.location.search);
    const apiUrl = urlParams.get('api_url');
    if (apiUrl) {
        localStorage.setItem('api_base_url', apiUrl);
        return apiUrl;
    }
    
    // 2. 检查localStorage
    const savedUrl = localStorage.getItem('api_base_url');
    if (savedUrl) {
        return savedUrl;
    }
    
    // 3. 默认值
    return getConfig('DEFAULT_API_URL', 'http://localhost:8001');
}

function setAPIBaseURL(url) {
    API_BASE_URL = url;
    localStorage.setItem('api_base_url', url);
}

// 全局状态
let currentTaskId = null;
let humanTasksRefreshInterval = null;
let logsRefreshInterval = null;

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    updateApiUrlDisplay();
    loadTasks();
});

// 更新API URL显示
function updateApiUrlDisplay() {
    document.getElementById('apiUrlDisplay').textContent = `API: ${API_BASE_URL}`;
}

// 显示API配置
function showApiConfig() {
    document.getElementById('apiUrlInput').value = API_BASE_URL;
    document.getElementById('apiConfigModal').style.display = 'block';
}

// 关闭API配置
function closeApiConfig() {
    document.getElementById('apiConfigModal').style.display = 'none';
}

// 保存API配置
function saveApiConfig() {
    const newUrl = document.getElementById('apiUrlInput').value.trim();
    if (newUrl) {
        setAPIBaseURL(newUrl);
        updateApiUrlDisplay();
        closeApiConfig();
        // 重新加载任务列表
        loadTasks();
        alert('API配置已保存');
    } else {
        alert('请输入有效的API URL');
    }
}

// 加载任务列表
async function loadTasks() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/task/list`);
        const data = await response.json();
        
        if (data.success) {
            renderTaskList(data.data);
        } else {
            showError('加载任务列表失败: ' + data.error);
        }
    } catch (error) {
        showError('连接服务器失败: ' + error.message);
    }
}

// 渲染任务列表
function renderTaskList(tasks) {
    const taskList = document.getElementById('taskList');
    taskList.innerHTML = '';
    
    if (tasks.length === 0) {
        taskList.innerHTML = '<div class="task-item"><div class="task-name">暂无任务</div></div>';
        return;
    }
    
    tasks.forEach(task => {
        const taskItem = document.createElement('div');
        taskItem.className = 'task-item';
        taskItem.setAttribute('data-id', task.task_id);
        taskItem.onclick = () => selectTask(task.task_id);
        
        taskItem.innerHTML = `
            <div class="task-name">${task.task_name || '未命名任务'}</div>
            <div class="task-id">${task.task_id}</div>
            <div class="task-time">创建时间: ${formatDate(task.created_at)}</div>
        `;
        
        taskList.appendChild(taskItem);
    });
}

// 选择任务
function selectTask(taskId) {
    // 更新UI状态
    document.querySelectorAll('.task-item').forEach(item => {
        if (item.getAttribute('data-id') === taskId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    // 设置当前任务ID
    currentTaskId = taskId;
    document.getElementById('currentTaskTitle').textContent = `任务: ${taskId}`;
    
    // 停止之前的自动刷新
    stopAllAutoRefresh();
    
    // 加载任务数据
    loadLogs(taskId);
    loadHumanTasks(taskId);
    
    // 开始自动刷新
    startHumanTasksAutoRefresh(taskId);
    startLogsAutoRefresh(taskId);
}

// 刷新所有内容
function refreshAll() {
    if (currentTaskId) {
        loadLogs(currentTaskId);
        loadHumanTasks(currentTaskId);
    }
    loadTasks();
}

// 加载日志
async function loadLogs(taskId) {
    try {
        // 尝试读取多个可能的日志文件
        const logFiles = getConfig('LOG_CONFIG.FILE_NAMES', [
            'logs/{taskId}_detail.log', 
            'logs/{taskId}_process.log'
        ]);
        
        let allLogs = [];
        
        for (const logFile of logFiles) {
            const filePath = logFile.replace('{taskId}', taskId);
            try {
                const response = await fetch(`${API_BASE_URL}/api/tool/execute`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        tool_name: 'file_read',
                        task_id: taskId,
                        params: {
                            file_path: filePath,
                            silent: true
                        }
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    allLogs = allLogs.concat(data.data.content.split('\n'));
                }
            } catch (error) {
                console.log(`无法读取日志文件 ${filePath}: ${error.message}`);
            }
        }
        
        // 如果没有找到任何日志，尝试读取通用日志
        if (allLogs.length === 0) {
            try {
                const response = await fetch(`${API_BASE_URL}/api/tool/execute`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        tool_name: 'file_read',
                        task_id: taskId,
                        params: {
                            file_path: 'logs/tool_execution.log',
                            silent: true
                        }
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    allLogs = data.data.content.split('\n');
                }
            } catch (error) {
                console.log(`无法读取通用日志文件: ${error.message}`);
            }
        }
        
        // 渲染日志
        renderLogs(allLogs);
    } catch (error) {
        showError('加载日志失败: ' + error.message);
    }
}

// 渲染日志
function renderLogs(logs) {
    const logsContent = document.getElementById('logsContent');
    
    if (!logs || logs.length === 0) {
        logsContent.innerHTML = '<div class="log-line">暂无日志</div>';
        return;
    }
    
    // 只显示最后100行
    const maxLines = getConfig('LOG_CONFIG.MAX_LINES', 100);
    const recentLogs = logs.slice(-maxLines);
    
    logsContent.innerHTML = '';
    
    recentLogs.forEach(log => {
        if (!log.trim()) return;
        
        const logLine = document.createElement('div');
        logLine.className = 'log-line';
        
        // 根据日志级别添加颜色
        if (log.includes('[ERROR]') || log.includes('error')) {
            logLine.classList.add('error');
        } else if (log.includes('[WARNING]') || log.includes('warning')) {
            logLine.classList.add('warning');
        } else if (log.includes('[SUCCESS]') || log.includes('success')) {
            logLine.classList.add('success');
        } else {
            logLine.classList.add('info');
        }
        
        logLine.textContent = log;
        logsContent.appendChild(logLine);
    });
    
    // 滚动到底部
    logsContent.scrollTop = logsContent.scrollHeight;
}

// 加载人类任务
async function loadHumanTasks(taskId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/human-tasks/${taskId}`);
        const data = await response.json();
        
        if (data.success) {
            renderHumanTasks(data.data.human_tasks || [], taskId);
        } else {
            showError('加载人类任务失败: ' + data.error);
        }
    } catch (error) {
        showError('加载人类任务失败: ' + error.message);
    }
}

// 渲染人类任务
function renderHumanTasks(tasks, taskId) {
    const humanTasksContent = document.getElementById('humanTasksContent');
    
    if (!tasks || tasks.length === 0) {
        humanTasksContent.innerHTML = '<div style="padding: 20px; text-align: center; color: #7f8c8d;">暂无人类任务</div>';
        return;
    }
    
    // 排序：未完成的在上面，已完成的在下面，按创建时间降序排列
    const sortedTasks = [...tasks].sort((a, b) => {
        if (a.completed !== b.completed) {
            return a.completed ? 1 : -1; // 未完成的排在前面
        }
        // 相同完成状态下，按创建时间降序排列（新的在前）
        return new Date(b.created_at) - new Date(a.created_at);
    });
    
    humanTasksContent.innerHTML = '';
    
    sortedTasks.forEach(task => {
        const taskItem = document.createElement('div');
        taskItem.className = 'human-task-item';
        
        const statusClass = task.completed ? 'status-completed' : 'status-pending';
        const statusText = task.completed ? '已完成' : '待处理';
        const buttonDisabled = task.completed ? 'disabled' : '';
        
        taskItem.innerHTML = `
            <div class="human-task-info">
                <div class="human-task-desc">${task.human_task}</div>
                <div class="human-task-meta">
                    <span class="human-task-id">ID: ${task.human_task_id.substring(0, 8)}...</span>
                    <span class="human-task-status ${statusClass}">${statusText}</span>
                </div>
            </div>
            <button class="complete-btn" onclick="completeHumanTask('${taskId}', '${task.human_task_id}')" ${buttonDisabled}>
                完成任务
            </button>
        `;
        
        humanTasksContent.appendChild(taskItem);
    });
}

// 完成人类任务
async function completeHumanTask(taskId, humanTaskId) {
    try {
        const response = await fetch(`${API_BASE_URL}/api/human-tasks/${taskId}/${humanTaskId}?completed=true`, {
            method: 'PUT'
        });
        
        const data = await response.json();
        
        if (data.success) {
            // 重新加载人类任务列表
            loadHumanTasks(taskId);
        } else {
            showError('更新任务状态失败: ' + data.error);
        }
    } catch (error) {
        showError('更新任务状态失败: ' + error.message);
    }
}

// 显示上传文件模态框
function showUploadModal() {
    if (!currentTaskId) {
        alert('请先选择一个任务');
        return;
    }
    
    document.getElementById('uploadModal').style.display = 'block';
}

// 关闭上传文件模态框
function closeUploadModal() {
    document.getElementById('uploadModal').style.display = 'none';
    document.getElementById('fileInput').value = '';
}

// 上传文件
async function uploadFile() {
    if (!currentTaskId) {
        alert('请先选择一个任务');
        return;
    }
    
    const fileInput = document.getElementById('fileInput');
    const files = fileInput.files;
    
    if (files.length === 0) {
        alert('请选择要上传的文件');
        return;
    }
    
    // 准备文件数据数组
    const fileDataArray = [];
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        try {
            const base64Content = await fileToBase64(file);
            fileDataArray.push({
                filename: file.name,
                content: base64Content,
                is_base64: true
            });
        } catch (error) {
            showError(`处理文件 ${file.name} 失败: ${error.message}`);
            return;
        }
    }
    
    // 一次性上传所有文件
    try {
        const response = await fetch(`${API_BASE_URL}/api/tool/execute`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tool_name: 'file_upload',
                task_id: currentTaskId,
                params: {
                    files: fileDataArray,
                    target_path: 'upload'
                }
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`成功上传 ${fileDataArray.length} 个文件到 upload 文件夹`);
        } else {
            showError(`上传文件失败: ${data.error}`);
        }
    } catch (error) {
        showError(`上传文件失败: ${error.message}`);
    }
    
    alert('文件上传完成');
    closeUploadModal();
}

// 将文件转换为Base64
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
            // 移除 "data:image/jpeg;base64," 前缀
            const base64 = reader.result.split(',')[1];
            resolve(base64);
        };
        reader.onerror = error => reject(error);
    });
}

// 自动刷新人类任务
function startHumanTasksAutoRefresh(taskId) {
    stopHumanTasksAutoRefresh();
    const interval = getConfig('REFRESH_INTERVALS.HUMAN_TASKS', 5000);
    humanTasksRefreshInterval = setInterval(() => {
        loadHumanTasks(taskId);
    }, interval);
}

// 停止自动刷新人类任务
function stopHumanTasksAutoRefresh() {
    if (humanTasksRefreshInterval) {
        clearInterval(humanTasksRefreshInterval);
        humanTasksRefreshInterval = null;
    }
}

// 自动刷新日志
function startLogsAutoRefresh(taskId) {
    stopLogsAutoRefresh();
    const interval = getConfig('REFRESH_INTERVALS.LOGS', 10000);
    logsRefreshInterval = setInterval(() => {
        loadLogs(taskId);
    }, interval);
}

// 停止自动刷新日志
function stopLogsAutoRefresh() {
    if (logsRefreshInterval) {
        clearInterval(logsRefreshInterval);
        logsRefreshInterval = null;
    }
}

// 停止所有自动刷新
function stopAllAutoRefresh() {
    stopHumanTasksAutoRefresh();
    stopLogsAutoRefresh();
}

// 格式化日期
function formatDate(dateString) {
    if (!dateString) return '未知';
    
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// 显示错误提示
function showError(message) {
    console.error(message);
    const errorToast = document.getElementById('errorToast');
    errorToast.textContent = message;
    errorToast.style.display = 'block';
    
    setTimeout(() => {
        errorToast.style.display = 'none';
    }, 5000);
}

// 从配置中获取值
function getConfig(path, defaultValue) {
    if (!window.TOOL_SERVER_CONFIG) {
        return defaultValue;
    }
    
    const parts = path.split('.');
    let value = window.TOOL_SERVER_CONFIG;
    
    for (const part of parts) {
        if (value && typeof value === 'object' && part in value) {
            value = value[part];
        } else {
            return defaultValue;
        }
    }
    
    return value !== undefined ? value : defaultValue;
} 