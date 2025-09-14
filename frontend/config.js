// Tool Server 前端配置文件
// 这个文件可以独立配置，无需修改核心代码

window.TOOL_SERVER_CONFIG = {
    // 默认API地址
    DEFAULT_API_URL: 'http://localhost:8001',
    
    // 自动刷新间隔（毫秒）
    REFRESH_INTERVALS: {
        HUMAN_TASKS: 5000,    // 人类任务每5秒刷新
        LOGS: 10000,          // 日志每10秒刷新
        TASKS: 3000         // 任务列表每30秒刷新
    },
    
    // 日志配置
    LOG_CONFIG: {
        MAX_LINES: 100,       // 最多显示100行日志
        FILE_NAMES: [         // 要读取的日志文件名模板
            'logs/{taskId}_process.log', 
        ]
    },
    
    // 文件上传配置
    UPLOAD_CONFIG: {
        MAX_FILE_SIZE: 10 * 1024 * 1024,  // 最大文件10MB
        ALLOWED_TYPES: [],    // 空数组表示允许所有类型
        DEFAULT_FOLDER: 'upload'
    },
    
    // UI配置
    UI_CONFIG: {
        TREE_INDENT: 20,      // 文件树缩进像素
        SHOW_FILE_SIZES: true, // 是否显示文件大小
        AUTO_EXPAND_ROOT: true // 是否自动展开根目录
    },
    
    // 调试配置
    DEBUG: {
        ENABLED: false,       // 是否启用调试模式
        LOG_API_CALLS: false, // 是否记录API调用
        VERBOSE: false        // 是否显示详细信息
    }
};

// 获取配置值的辅助函数
window.getConfig = function(path, defaultValue = null) {
    const parts = path.split('.');
    let current = window.TOOL_SERVER_CONFIG;
    
    for (const part of parts) {
        if (current && typeof current === 'object' && part in current) {
            current = current[part];
        } else {
            return defaultValue;
        }
    }
    
    return current;
};

// 设置配置值的辅助函数
window.setConfig = function(path, value) {
    const parts = path.split('.');
    let current = window.TOOL_SERVER_CONFIG;
    
    for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        if (!(part in current) || typeof current[part] !== 'object') {
            current[part] = {};
        }
        current = current[part];
    }
    
    current[parts[parts.length - 1]] = value;
}; 