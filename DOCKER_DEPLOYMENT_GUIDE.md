# 🐳 Multi-Level Agent Framework Docker 部署指南

## 📋 概述

基于实际打包经验的Multi-Level Agent Framework Docker部署指南，包含完整的构建、启动和API使用说明。

## 🏗️ Docker镜像构建

### 1. 构建镜像
```bash
# 在项目根目录执行
docker build -t multi-level-agent-api:latest .
```

### 2. 验证构建
```bash
# 查看镜像信息
docker images multi-level-agent-api

# 预期输出：
# REPOSITORY              TAG       IMAGE ID       CREATED          SIZE
# multi-level-agent-api   latest    58dbc3871d8d   2 minutes ago    1.75GB
```

## 🚀 标准启动方法

### 推荐启动命令
```bash
docker run -d --name multi-agent-api -p 5003:5002 \
  -v $(pwd)/config/run_env_config:/app/config/run_env_config \
  -v $(pwd)/config/agent_library:/app/config/agent_library \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api:latest
```

### 启动参数说明
- `--name multi-agent-api` - 容器名称
- `-p 5003:5002` - 端口映射（宿主机5003 → 容器5002）
- `-v` 挂载必要的目录：
  - `config/run_env_config/` - LLM配置文件
  - `config/agent_library/` - Agent系统配置
  - `logs/` - 日志文件
  - `conversations/` - 对话历史文件

### 验证启动
```bash
# 检查容器状态
docker ps | grep multi-agent-api

# 测试健康检查
curl http://localhost:5003/health

# 预期响应：
# {
#   "status": "healthy",
#   "timestamp": "2025-09-14T22:15:30.123456",
#   "running_tasks": 0,
#   "total_task_logs": 0
# }
```

## 📡 完整API接口说明

### 1. 健康检查
```bash
GET /health
curl http://localhost:5003/health
```
**作用**: 检查服务器状态和运行统计

### 2. 创建任务
```bash
POST /api/task/create
curl -X POST http://localhost:5003/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "fibonacci_task",
    "agent_system_name": "infiHelper",
    "agent_name": "experment_material_data_agent",
    "user_input": "写一个输出斐波那契数列的Python代码"
  }'
```
**作用**: 创建并启动新的Agent任务
**参数**: 
- `task_id` - 任务唯一标识
- `agent_system_name` - Agent系统名称（默认"infiHelper"）
- `agent_name` - 启动的Agent名称（支持任意Agent）
- `user_input` - 用户任务描述

### 3. 暂停任务
```bash
POST /api/task/pause
curl -X POST http://localhost:5003/api/task/pause \
  -H "Content-Type: application/json" \
  -d '{"task_id": "fibonacci_task"}'
```
**作用**: 暂停正在运行的任务，保存当前状态

### 4. 恢复任务
```bash
POST /api/task/resume
curl -X POST http://localhost:5003/api/task/resume \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "fibonacci_task",
    "agent_system_name": "infiHelper"
  }'
```
**作用**: 从暂停点恢复任务执行，自动读取原始Agent配置

### 5. 添加消息
```bash add_meaasage自带暂停恢复逻辑，所以一般情况在无需使用暂停和恢复 api。
POST /api/task/add_message
curl -X POST http://localhost:5003/api/task/add_message \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "fibonacci_task",
    "agent_system_name": "infiHelper",
    "agent_name": "experment_material_data_agent",
    "message": "请优化代码并添加注释"
  }'
```
**作用**: 向现有任务添加新指令或询问

### 6. 获取任务元数据
```bash
GET /api/task/metadata/<task_id>
curl http://localhost:5003/api/task/metadata/fibonacci_task
```
**作用**: 获取任务的完整元数据信息
**返回**: 包含agent_name、user_instructions、创建时间等

### 7. 获取任务状态
```bash
GET /api/task/status/<task_id>
curl http://localhost:5003/api/task/status/fibonacci_task
```
**作用**: 获取任务当前运行状态和Agent层级信息

### 8. 获取对话历史
```bash
GET /api/task/conversation_history/<task_id>
curl http://localhost:5003/api/task/conversation_history/fibonacci_task
```
**作用**: 获取任务的完整对话历史记录

### 9. 获取任务日志
```bash
GET /api/task/logs/<task_id>
curl http://localhost:5003/api/task/logs/fibonacci_task
```
**作用**: 获取任务的控制台执行日志

### 10. 获取Agent系统列表
```bash
GET /api/systems/list
curl http://localhost:5003/api/systems/list
```
**作用**: 获取所有可用的Agent系统配置

## 🎯 实际使用流程

### 完整任务执行示例
```bash
# 1. 启动容器
docker run -d --name multi-agent-api -p 5003:5002 \
  -v $(pwd)/config/run_env_config:/app/config/run_env_config \
  -v $(pwd)/config/agent_library:/app/config/agent_library \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/conversations:/app/conversations \
  multi-level-agent-api:latest

# 2. 检查服务健康
curl http://localhost:5003/health

# 3. 创建斐波那契任务
curl -X POST http://localhost:5003/api/task/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "fibonacci_100",
    "agent_system_name": "infiHelper",
    "agent_name": "coding_task_agent",
    "user_input": "写一个能输出斐波那契数列前100项到txt文件的python代码，并运行"
  }'

# 4. 立即暂停（测试暂停功能）
curl -X POST http://localhost:5003/api/task/pause \
  -H "Content-Type: application/json" \
  -d '{"task_id": "fibonacci_100"}'

# 5. 查看任务元数据
curl http://localhost:5003/api/task/metadata/fibonacci_100

# 6. 恢复任务
curl -X POST http://localhost:5003/api/task/resume \
  -H "Content-Type: application/json" \
  -d '{"task_id": "fibonacci_100"}'

# 7. 添加新指令
curl -X POST http://localhost:5003/api/task/add_message \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "fibonacci_100",
    "agent_name": "coding_task_agent",
    "message": "请总结完成了什么任务，并检查结果文件"
  }'

# 8. 监控执行过程
curl http://localhost:5003/api/task/status/fibonacci_100
curl http://localhost:5003/api/task/conversation_history/fibonacci_100
```

## 🔧 容器管理

### 基本操作
```bash
# 查看容器日志
docker logs -f multi-agent-api

# 停止容器
docker stop multi-agent-api

# 删除容器
docker rm multi-agent-api

# 重启容器
docker restart multi-agent-api

# 进入容器调试
docker exec -it multi-agent-api /bin/bash
```

### 数据持久化
所有重要数据都通过volume挂载到宿主机：
- **配置文件** - `config/` 目录
- **对话历史** - `conversations/` 目录  
- **执行日志** - `logs/` 目录

## 🎯 支持的Agent类型

框架支持任意Agent名称，常用的包括：
- `writing_agent` - 写作和文档处理
- `experment_material_data_agent` - 实验数据收集
- `coding_task_agent` - 编程任务执行
- `research_agent` - 研究和分析
- `judge_agent` - 结果评判
- 以及配置文件中定义的任何其他Agent

## 🆕 新功能特性

### 微服务架构
- **6个独立服务包** - 完全解耦的功能模块
- **智能思考系统** - 首次规划 + 定期分析
- **上下文管理** - 自动压缩和智能构造
- **对话管理** - 完整的持久化和恢复

### API增强
- **任意Agent启动** - 不再限制Agent类型
- **完整元数据管理** - 包含agent_name的完整信息
- **智能任务恢复** - 保持原始Agent配置

---

*基于实际部署经验编写 - Multi-Level Agent Framework v2.0*
