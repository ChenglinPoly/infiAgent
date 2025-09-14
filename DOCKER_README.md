# Multi-Level Agent Docker 启动教程

## 概述

本教程介绍如何使用已构建的Multi-Level Agent Docker镜像，通过挂载配置文件和数据目录来启动API服务。

<!-- API导入 - Docker容器化部署教程 -->

## 🔒 安全设计

**重要**：Docker镜像**不包含任何配置文件**，所有配置必须通过挂载提供，确保API密钥等敏感信息安全。

## 📋 前置要求

- Docker 已安装并运行
- 已有 `multi-level-agent-api` Docker镜像
- 准备好配置文件目录

---

## 📁 目录结构准备

### 必需的目录结构
```
your_workspace/
├── config/
│   ├── run_env_config/
│   │   ├── tool_config.yaml      # 工具服务器配置
│   │   └── llm_config.yaml       # LLM API配置
│   └── agent_library/
│       ├── infiHelper/           # Agent系统配置
│       ├── infiHelper-2/
│       └── test_system/
├── logs/                         # 日志目录（可为空）
└── conversations/                # 对话历史（可为空）
```

**注意**：即使 `logs/` 和 `conversations/` 目录为空，也需要创建并挂载，系统会自动同步数据。

### 创建目录结构
```bash
# 创建工作目录
mkdir -p multi-agent-workspace
cd multi-agent-workspace

# 创建必需的目录（即使为空也要创建）
mkdir -p config/run_env_config
mkdir -p config/agent_library
mkdir -p logs
mkdir -p conversations
```

---

## ⚙️ 配置文件准备

### 1. 工具服务器配置 (`config/run_env_config/tool_config.yaml`)

```yaml
# 工具服务器配置（Docker环境使用宿主机IP）
tools_server: "http://192.168.31.211:8001/"

# 其他配置项
# timeout: 30
# max_retries: 3
```

**重要**：将 `192.168.31.211` 替换为您的实际宿主机IP地址。

### 2. LLM配置 (`config/run_env_config/llm_config.yaml`)

```yaml
# 基于 LiteLLM 的 LLM 配置文件
default:
  temperature: 0
  max_tokens: 0

environment_variables: {}

# 官方API配置
openai:
  official:
    api_key: "sk-your-openai-key"
    models:
      - "gpt-4o"
      - "gpt-4o-mini"

claude:
  official:
    api_key: "sk-ant-your-claude-key"
    models:
      - "claude-3-5-sonnet-20241022"

# Custom API 配置
custom:
  openai_format:
    api_key: "sk-REDACTED"
    base_url: "https://openrouter.ai/api/v1"
    models:
      - "google/gemini-2.5-flash"
```

### 3. Agent系统配置

将您的Agent系统配置放在 `config/agent_library/` 下，每个系统一个子目录。

---

## 🚀 启动容器

### 基础启动命令

```bash
docker run -d \
  --name multi-agent-api \
  -p 5003:5002 \
  -v $(pwd)/config/run_env_config:/app/config/run_env_config \
  -v $(pwd)/config/agent_library:/app/config/agent_library \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `-d` | 后台运行 |
| `--name multi-agent-api` | 容器名称 |
| `-p 5003:5002` | 端口映射：宿主机5003 → 容器5002 |
| `-v` | 目录挂载，格式：`宿主机路径:容器路径` |

### 挂载目录说明

| 宿主机目录 | 容器目录 | 必需 | 说明 |
|------------|----------|------|------|
| `./config/run_env_config` | `/app/config/run_env_config` | ✅ | LLM和工具配置 |
| `./config/agent_library` | `/app/config/agent_library` | ✅ | Agent系统配置 |
| `./logs` | `/app/logs` | ✅ | 日志和任务元数据（可为空目录） |
| `./conversations` | `/app/conversations` | ✅ | 对话历史和状态文件（可为空目录） |

**重要**：即使 `logs` 和 `conversations` 目录为空，也必须挂载，系统会自动创建和同步文件。

---

## ✅ 验证启动

### 1. 检查容器状态
```bash
docker ps | grep multi-agent-api
```

### 2. 检查API健康状态
```bash
curl -X GET http://localhost:5003/health
```

预期响应：
```json
{
  "status": "healthy",
  "running_tasks": 0,
  "total_task_logs": 0,
  "timestamp": "2025-08-31T17:56:31.684842"
}
```

### 3. 验证时区（北京时间）
```bash
docker exec multi-agent-api date
```

预期输出：`Sun Aug 31 17:56:40 CST 2025`

### 4. 检查Agent系统
```bash
curl -X GET http://localhost:5003/api/systems/list
```

---

## 🧪 快速测试

```bash
# 创建测试任务
curl -X POST http://localhost:5003/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "hello_test",
    "agent_system_name": "infiHelper",
    "user_input": "你好"
  }'

# 等待几秒后查看结果
sleep 5
curl -X GET http://localhost:5003/api/task/conversation_history/hello_test
```

---

## 🔧 常用操作

### 查看容器日志
```bash
docker logs multi-agent-api
```

### 进入容器调试
```bash
docker exec -it multi-agent-api bash
```

### 停止和重启
```bash
# 停止容器
docker stop multi-agent-api

# 启动容器
docker start multi-agent-api

# 重启容器
docker restart multi-agent-api

# 删除容器
docker rm multi-agent-api
```

### 更新配置
修改宿主机的配置文件后，重启容器生效：
```bash
docker restart multi-agent-api
```

---

## 🛠️ 高级启动选项

### 使用宿主机网络（如果工具服务器在127.0.0.1）

```bash
docker run -d \
  --name multi-agent-api \
  --network host \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api
```

这样API将在 `http://localhost:5002` 可用，可以直接访问 `127.0.0.1:8001`。

### 资源限制
```bash
docker run -d \
  --name multi-agent-api \
  -p 5003:5002 \
  --memory=2g \
  --cpus=1.0 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api
```

### 环境变量覆盖
```bash
docker run -d \
  --name multi-agent-api \
  -p 5003:5002 \
  -e OPENAI_API_KEY="your-key" \
  -e CUSTOM_API_KEY="your-custom-key" \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api
```

---

## 🚨 故障排除

### 常见问题

#### 1. 无法访问工具服务器
**症状**：任务创建后失败，日志显示连接错误

**解决方案**：
- 检查 `tool_config.yaml` 中的IP地址
- 确认宿主机8001端口开放
- 尝试使用 `--network host` 模式

#### 2. 配置文件未找到
**症状**：容器启动失败或Agent系统列表为空

**解决方案**：
- 确保挂载了正确的配置目录
- 检查目录权限：`chmod -R 755 config/`

#### 3. 数据不同步
**症状**：宿主机看不到容器创建的任务

**解决方案**：
- 确保 `logs` 和 `conversations` 目录已挂载
- 检查目录权限：`chmod -R 755 logs conversations`

### 调试命令

```bash
# 检查挂载是否成功
docker exec multi-agent-api ls -la /app/config/run_env_config/

# 检查Agent系统配置
docker exec multi-agent-api ls -la /app/config/agent_library/

# 测试网络连接
docker exec multi-agent-api curl -I http://192.168.31.211:8001/

# 查看实时日志
docker logs -f multi-agent-api
```

---

## 🎯 完整启动示例

假设您有以下文件结构：

```
my_agent_workspace/
├── config/
│   ├── run_env_config/
│   │   ├── tool_config.yaml
│   │   └── llm_config.yaml
│   └── agent_library/
│       ├── infiHelper/
│       └── custom_system/
├── logs/                    # 可能有历史日志，也可能为空
└── conversations/           # 可能有历史对话，也可能为空
```

### 启动命令

```bash
cd my_agent_workspace

# 启动容器
docker run -d \
  --name multi-agent-api \
  -p 5003:5002 \
  -v $(pwd)/config/run_env_config:/app/config/run_env_config \
  -v $(pwd)/config/agent_library:/app/config/agent_library \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api

# 验证启动
sleep 3
curl -X GET http://localhost:5003/health
```

### 如果目录为空

即使 `logs/` 和 `conversations/` 为空，也必须创建并挂载：

```bash
# 创建空目录
mkdir -p logs conversations

# 正常启动（系统会自动创建文件）
docker run -d \
  --name multi-agent-api \
  -p 5003:5002 \
  -v $(pwd)/config/run_env_config:/app/config/run_env_config \
  -v $(pwd)/config/agent_library:/app/config/agent_library \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api
```

---

## 🔧 日常操作

### 查看运行状态
```bash
# 检查容器状态
docker ps | grep multi-agent-api

# 检查API健康
curl -X GET http://localhost:5003/health
```

### 查看日志
```bash
# 容器日志
docker logs multi-agent-api

# 任务日志（会自动同步到宿主机）
ls -la logs/api_state/
```

### 停止和重启
```bash
# 停止
docker stop multi-agent-api

# 重启
docker start multi-agent-api

# 删除（数据保留在宿主机）
docker rm multi-agent-api
```

---

## 🌐 网络配置

### 配置工具服务器地址

编辑 `config/run_env_config/tool_config.yaml`：

```yaml
# 工具服务器配置
tools_server: "http://192.168.31.211:8001/"
```

**将 `192.168.31.211` 替换为您的实际宿主机IP地址。**

### 如果工具服务器在本地

如果工具服务器运行在 `127.0.0.1:8001`，使用宿主机网络模式：

```bash
docker run -d \
  --name multi-agent-api \
  --network host \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api
```

这样API将在 `http://localhost:5002` 可用。

---

## 📊 数据同步说明

### 自动同步
- ✅ **任务日志**：容器内创建的任务日志自动保存到 `logs/api_state/`
- ✅ **对话历史**：所有对话和状态文件自动保存到 `conversations/`
- ✅ **元数据**：任务元数据文件自动同步
- ✅ **双向同步**：宿主机和容器的数据完全同步

### 历史数据恢复
如果您有历史的 `logs/` 和 `conversations/` 数据：
- ✅ 直接挂载即可，容器会自动识别和加载
- ✅ 历史任务状态完全保留
- ✅ 可以继续之前未完成的任务

---

## 🔐 安全注意事项

### 配置文件安全
- ✅ **永远不要**将包含API密钥的配置文件打包到镜像
- ✅ 配置文件仅通过挂载提供
- ✅ 设置适当的文件权限：`chmod 600 config/run_env_config/*.yaml`

### 数据安全
- ✅ 定期备份 `logs/` 和 `conversations/` 目录
- ✅ 监控日志文件大小，防止磁盘空间不足

---

## 🆘 故障排除

### 启动失败
```bash
# 查看启动日志
docker logs multi-agent-api

# 检查配置文件是否存在
docker exec multi-agent-api ls -la /app/config/run_env_config/

# 检查Agent系统配置
docker exec multi-agent-api ls -la /app/config/agent_library/
```

### 网络问题
```bash
# 测试工具服务器连接
docker exec multi-agent-api curl -I http://192.168.31.211:8001/

# 检查容器网络
docker exec multi-agent-api ip addr show
```

### 权限问题
```bash
# 修改宿主机目录权限
chmod -R 755 logs conversations config

# 检查容器内权限
docker exec multi-agent-api ls -la /app/
```

---

## 📖 版本信息

- **镜像名称**：`multi-level-agent-api:latest`
- **API端口**：5002（容器内）
- **时区**：Asia/Shanghai（北京时间）
- **Python版本**：3.12

---

## 🎯 完整启动流程

```bash
# 1. 准备工作目录
mkdir -p my_agent_deployment
cd my_agent_deployment

# 2. 创建目录结构
mkdir -p config/run_env_config config/agent_library logs conversations

# 3. 准备配置文件
# 将您的配置文件复制到 config/ 目录

# 4. 启动容器
docker run -d \
  --name multi-agent-api \
  -p 5003:5002 \
  -v $(pwd)/config/run_env_config:/app/config/run_env_config \
  -v $(pwd)/config/agent_library:/app/config/agent_library \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api

# 5. 验证启动
sleep 3
curl -X GET http://localhost:5003/health

# 6. 测试功能
curl -X POST http://localhost:5003/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test",
    "agent_system_name": "infiHelper",
    "user_input": "你好"
  }'
```

---

**🎉 启动完成！您的Multi-Level Agent API系统现在运行在Docker容器中，所有数据与宿主机完全同步！**

**API访问地址**：`http://localhost:5003`
