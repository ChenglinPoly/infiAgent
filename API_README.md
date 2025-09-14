# Multi-Level Agent API 文档

## 概述

Multi-Level Agent API 提供了一个完整的多层级智能代理系统，支持任务创建、暂停、恢复、指令添加和历史查询等功能。系统采用层级化的Agent架构，支持动态的父子调用关系和实时状态管理。

<!-- API导入 - RESTful接口文档 -->

**服务器地址**：`http://localhost:5002`

## 核心概念

### 任务管理
- **task_id**：任务的唯一标识符
- **agent_system_name**：使用的Agent系统配置（如 `infiHelper-2`、`test_system`）
- **user_instructions**：用户指令列表，支持多条指令

### Agent层级
- **Level 0**：主控制Agent（如 `writing_agent`）
- **Level 1+**：子Agent（如 `experment_material_data_agent`、`judge_agent`）
- **栈管理**：动态维护Agent调用栈和父子关系

### 状态持久化
- **share_context.json**：任务的完整状态和层级关系
- **stack.json**：当前Agent调用栈
- **metadata.json**：任务元数据（用于恢复）

---

## API 端点

### 1. 健康检查

**GET** `/health`

检查API服务器状态和当前运行任务数量。

#### 请求
```bash
curl -X GET http://localhost:5002/health
```

#### 响应
```json
{
  "status": "healthy",
  "running_tasks": 1,
  "total_task_logs": 15,
  "timestamp": "2025-08-31T17:19:05.303205"
}
```

---

### 2. 创建任务

**POST** `/api/task/create`

创建并启动新的Agent任务。

#### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | ✅ | 任务唯一标识符 |
| user_input | string | ✅ | 用户指令内容 |
| agent_system_name | string | ❌ | Agent系统名称，默认 `infiHelper` |

#### 请求示例
```bash
curl -X POST http://localhost:5002/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "my_task_001",
    "agent_system_name": "infiHelper-2",
    "user_input": "生成一个Python计算器程序"
  }'
```

#### 响应
```json
{
  "status": "success",
  "message": "任务 my_task_001 已启动"
}
```

#### 错误响应
```json
{
  "status": "error",
  "message": "任务 my_task_001 已在运行中"
}
```

---

### 3. 暂停任务

**POST** `/api/task/pause`

暂停正在运行的任务，使用SIGINT信号终止进程树（类似Ctrl+C效果）。

#### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | ✅ | 要暂停的任务ID |

#### 请求示例
```bash
curl -X POST http://localhost:5002/api/task/pause \
  -H "Content-Type: application/json" \
  -d '{"task_id": "my_task_001"}'
```

#### 响应
```json
{
  "status": "success",
  "message": "任务 my_task_001 已暂停"
}
```

---

### 4. 恢复任务

**POST** `/api/task/resume`

恢复已暂停的任务，使用原始参数重新启动，程序会自动从状态文件恢复执行点。

#### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | ✅ | 要恢复的任务ID |
| agent_system_name | string | ❌ | Agent系统名称，默认使用原始系统 |

#### 请求示例
```bash
curl -X POST http://localhost:5002/api/task/resume \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "my_task_001",
    "agent_system_name": "infiHelper-2"
  }'
```

#### 响应
```json
{
  "status": "success",
  "message": "任务 my_task_001 已启动"
}
```

---

### 5. 添加指令

**POST** `/api/task/add_message`

向现有任务添加新指令，或创建新任务。系统会智能判断：
- 如果任务存在：暂停 → 添加指令到列表 → 重新启动
- 如果任务不存在：创建新任务

#### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | ✅ | 任务ID |
| message | string | ✅ | 新的用户指令 |
| agent_system_name | string | ❌ | Agent系统名称，默认 `infiHelper` |

#### 请求示例
```bash
curl -X POST http://localhost:5002/api/task/add_message \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "my_task_001",
    "message": "同时生成一个测试文件",
    "agent_system_name": "infiHelper-2"
  }'
```

#### 响应
```json
{
  "status": "success",
  "message": "消息已添加，添加指令并重新启动任务",
  "action": "添加指令并重新启动任务",
  "had_existing_task": true
}
```

---

### 6. 获取任务状态

**GET** `/api/task/status/<task_id>`

获取任务的详细状态，包括Agent层级关系、执行进度和历史记录。

#### 请求示例
```bash
curl -X GET http://localhost:5002/api/task/status/my_task_001
```

#### 响应数据结构
```json
{
  "status": "success",
  "task_id": "my_task_001",
  "is_running": false,
  "context_data": {
    "task_id": "my_task_001",
    "created_at": "2025-08-31T17:19:05.303205",
    "last_updated": "2025-08-31T17:19:07.177509",
    "current": {
      "instructions": [
        {
          "instruction": "生成一个Python计算器程序",
          "instruction_id": "instruction_abc123",
          "start_time": "2025-08-31T17:19:05.492902"
        }
      ],
      "hierarchy": {
        "writing_agent_abc123": {
          "parent": null,
          "children": ["experment_agent_def456"],
          "level": 0
        }
      },
      "agents_status": {
        "writing_agent_abc123": {
          "agent_name": "writing_agent",
          "status": "waiting",
          "progress": "正在等待子Agent返回结果...",
          "initial_input": "生成一个Python计算器程序",
          "start_time": "2025-08-31T17:19:05.493082",
          "end_time": null,
          "level": 0,
          "parent_id": null
        }
      }
    },
    "history": [],
    "agent_time_history": {
      "writing_agent_abc123": {
        "start_time": "2025-08-31T17:19:05.493079",
        "end_time": "2025-08-31T17:19:07.177320"
      }
    }
  },
  "log_info": {
    "log_file": "/path/to/logs/my_task_001_console.log",
    "status": "completed",
    "return_code": 0,
    "start_time": "2025-08-31T17:19:07.342490"
  }
}
```

#### 字段说明
- **current**：当前进行中的任务状态
- **history**：已完成的任务历史
- **agent_time_history**：所有Agent的时间记录
- **agents_status**：Agent详细状态
  - `status`: `"waiting"` | `"completed"`
  - `progress`: Agent当前进度描述
  - `level`: Agent层级（0, 1, 2, ...）

---

### 7. 获取历史对话

**GET** `/api/task/conversation_history/<task_id>`

获取任务的完整对话历史，按时间排序。

#### 请求示例
```bash
curl -X GET http://localhost:5002/api/task/conversation_history/my_task_001
```

#### 响应数据结构
```json
{
  "status": "success",
  "task_id": "my_task_001",
  "total_count": 4,
  "messages": [
    {
      "type": "user",
      "content": "生成一个Python计算器程序",
      "timestamp": "2025-08-31T17:19:05.492902",
      "instruction_id": "instruction_abc123"
    },
    {
      "type": "assistant",
      "content": "已成功生成Python计算器程序...",
      "progress": "已成功生成Python计算器程序...",
      "timestamp": "2025-08-31T17:19:07.177320",
      "agent_id": "writing_agent_abc123",
      "agent_name": "writing_agent",
      "status": "completed"
    }
  ]
}
```

#### 消息类型
- **用户消息**：
  - `type`: `"user"`
  - `content`: 用户指令内容
  - `instruction_id`: 指令唯一标识
  
- **Agent消息**：
  - `type`: `"assistant"`
  - `content`: Agent输出内容
  - `progress`: Agent进度详情（与content相同）
  - `agent_id`: Agent唯一标识
  - `agent_name`: Agent名称
  - `status`: `"completed"` | `"waiting"`

---

### 8. 获取任务日志

**GET** `/api/task/logs/<task_id>`

获取任务的控制台输出日志。

#### 请求示例
```bash
curl -X GET http://localhost:5002/api/task/logs/my_task_001
```

#### 响应
```json
{
  "status": "success",
  "log_info": {
    "log_file": "/path/to/logs/my_task_001_console.log",
    "status": "completed",
    "return_code": 0,
    "start_time": "2025-08-31T17:19:07.342490"
  },
  "log_content": "🚀 任务启动时间: 2025-08-31 17:19:05\n📋 任务ID: my_task_001\n..."
}
```

---

### 9. 获取Agent系统列表

**GET** `/api/systems/list`

获取所有可用的Agent系统配置。

#### 请求示例
```bash
curl -X GET http://localhost:5002/api/systems/list
```

#### 响应
```json
{
  "status": "success",
  "total_count": 3,
  "systems": [
    {
      "name": "infiHelper-2",
      "path": "/path/to/config/agent_library/infiHelper-2",
      "has_configs": true,
      "config_count": 6
    },
    {
      "name": "test_system",
      "path": "/path/to/config/agent_library/test_system",
      "has_configs": true,
      "config_count": 12
    }
  ]
}
```

---

### 10. 上传Agent系统

**POST** `/api/systems/upload`

上传ZIP格式的Agent系统配置包。

#### 请求参数
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| file | file | ✅ | ZIP格式的配置文件包 |
| system_name | string | ✅ | 新系统的名称 |

#### 请求示例
```bash
curl -X POST http://localhost:5002/api/systems/upload \
  -F "file=@/path/to/config.zip" \
  -F "system_name=my_custom_system"
```

#### 响应
```json
{
  "status": "success",
  "message": "Agent系统 'my_custom_system' 上传成功",
  "system_name": "my_custom_system",
  "file_count": 8,
  "extracted_files": [
    "level_0_tools.yaml",
    "level_1_agents.yaml",
    "general_prompts.yaml"
  ]
}
```

---

### 11. 获取LLM配置

**GET** `/api/config/llm`

获取当前的LLM配置信息。

#### 请求示例
```bash
curl -X GET http://localhost:5002/api/config/llm
```

#### 响应
```json
{
  "status": "success",
  "config": {
    "models": {
      "claude-3-sonnet": {
        "api_key": "sk-***",
        "base_url": "https://api.anthropic.com"
      }
    }
  }
}
```

---

### 12. 更新LLM配置

**PUT** `/api/config/llm`

更新LLM配置信息。

#### 请求参数
```json
{
  "config": {
    "models": {
      "gpt-4": {
        "api_key": "sk-new-key",
        "base_url": "https://api.openai.com"
      }
    }
  }
}
```

#### 请求示例
```bash
curl -X PUT http://localhost:5002/api/config/llm \
  -H "Content-Type: application/json" \
  -d '{"config": {"models": {"gpt-4": {"api_key": "sk-new"}}}}'
```

---

### 13. 获取Agent配置

**GET** `/api/config/agent/<config_type>`

获取特定类型的Agent配置。

#### 路径参数
- `config_type`: 配置类型（如 `level_0_tools`、`general_prompts`）

#### 请求示例
```bash
curl -X GET http://localhost:5002/api/config/agent/level_0_tools
```

---

### 14. 更新Agent配置

**PUT** `/api/config/agent/<config_type>`

更新特定类型的Agent配置。

#### 请求示例
```bash
curl -X PUT http://localhost:5002/api/config/agent/level_0_tools \
  -H "Content-Type: application/json" \
  -d '{"tools": {"new_tool": {"description": "新工具"}}}'
```

---

## 使用流程示例

### 基本任务流程

```bash
# 1. 创建任务
curl -X POST http://localhost:5002/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "demo_task",
    "agent_system_name": "infiHelper-2",
    "user_input": "写一个Python爬虫程序"
  }'

# 2. 查看任务状态
curl -X GET http://localhost:5002/api/task/status/demo_task

# 3. 添加新指令（任务运行中）
curl -X POST http://localhost:5002/api/task/add_message \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "demo_task",
    "message": "同时添加错误处理功能"
  }'

# 4. 暂停任务
curl -X POST http://localhost:5002/api/task/pause \
  -H "Content-Type: application/json" \
  -d '{"task_id": "demo_task"}'

# 5. 恢复任务
curl -X POST http://localhost:5002/api/task/resume \
  -H "Content-Type: application/json" \
  -d '{"task_id": "demo_task"}'

# 6. 查看历史对话
curl -X GET http://localhost:5002/api/task/conversation_history/demo_task
```

### Agent系统管理

```bash
# 1. 查看可用系统
curl -X GET http://localhost:5002/api/systems/list

# 2. 上传新系统
curl -X POST http://localhost:5002/api/systems/upload \
  -F "file=@/path/to/my_agents.zip" \
  -F "system_name=custom_system"

# 3. 使用新系统创建任务
curl -X POST http://localhost:5002/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "custom_task",
    "agent_system_name": "custom_system",
    "user_input": "测试新系统功能"
  }'
```

---

## 错误处理

### 常见错误码

| HTTP状态码 | 错误类型 | 说明 |
|------------|----------|------|
| 400 | Bad Request | 请求参数错误或缺失 |
| 404 | Not Found | 任务或资源不存在 |
| 500 | Internal Server Error | 服务器内部错误 |

### 错误响应格式
```json
{
  "status": "error",
  "message": "具体错误信息"
}
```

---

## 数据结构详解

### Agent状态对象
```json
{
  "agent_name": "writing_agent",
  "status": "waiting",
  "progress": "正在处理任务...",
  "initial_input": "用户原始输入",
  "start_time": "2025-08-31T17:19:05.493082",
  "end_time": null,
  "level": 0,
  "parent_id": null,
  "waiting_for": "等待描述"
}
```

### 层级关系对象
```json
{
  "agent_id": {
    "parent": "parent_agent_id",
    "children": ["child1_id", "child2_id"],
    "level": 1
  }
}
```

### 指令对象
```json
{
  "instruction": "用户指令内容",
  "instruction_id": "instruction_abc123",
  "start_time": "2025-08-31T17:19:05.492902"
}
```

---

## 注意事项

### 任务生命周期
1. **创建**：任务开始执行，创建状态文件
2. **运行**：Agent层级调用，实时更新状态
3. **暂停**：SIGINT信号终止，保持状态文件
4. **恢复**：重新启动，自动从状态文件恢复
5. **完成**：所有Agent完成，状态移至历史

### 文件管理
- **状态文件**：`{task_id}_share_context.json`、`{task_id}_stack.json`
- **元数据文件**：`logs/api_state/{task_id}_metadata.json`
- **日志文件**：`logs/api_state/{task_id}_console.log`
- **对话历史**：保存在 `share_context.json` 中

### 性能考虑
- 使用subprocess管理任务进程，支持真正的暂停/恢复
- 状态文件实时更新，确保数据一致性
- 智能消息压缩，处理长对话历史
- 元数据文件确保任务参数持久化

---

## 开发者信息

**版本**：v3.0  
**端口**：5002  
**开发模式**：支持热重载  
**日志级别**：DEBUG  

如有问题，请查看服务器控制台输出或任务日志文件。 