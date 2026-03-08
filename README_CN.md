<div align="center">
  <img src="assets/logo.png" alt="infiAgent Logo" width="200">

  <h1>MLA V3 / infiAgent</h1>

  <p>面向长任务研究与真实电脑工作的多智能体自动化框架。</p>

  <p>
    <img src="https://img.shields.io/badge/version-3.0.0-blue.svg" alt="Version">
    <img src="https://img.shields.io/badge/python-3.9%2B-green.svg" alt="Python">
    <img src="https://img.shields.io/badge/license-GPL-blue.svg" alt="License">
  </p>

  <p>
    <a href="README.md">English</a> | <a href="README_CN.md">简体中文</a>
  </p>
</div>

## 简介

`infiAgent`（也叫 `MLA V3`，Multi-Level Agent）是一个以 Python 为核心的长程智能体框架，面向不能在一两轮对话里结束的任务。它强调工作空间持久状态、可恢复执行、层级式智能体编排，以及基于文件系统的记忆，而不是单纯依赖不断膨胀的 prompt。

这个仓库现在已经不只是最初的 CLI 运行时：

- `Researcher`：内置的长程科研系统，采用多层级智能体编排。
- `OpenCowork`：更扁平的电脑工作助手，适合代码、文档、文件整理和工具密集型任务。
- `Desktop app`：Electron 客户端，支持打包 Python 后端、单任务日志、运行时设置、skills 导入、MCP 设置和 marketplace 集成。
- `Web UI`：浏览器端，支持 JSONL 流式输出、HIL、人机恢复、系统切换和任务文件浏览。
- `Python SDK`：可直接在 Python 里嵌入运行时，并配置步长、thinking 间隔、fresh 和 MCP servers。

## 当前能力

- 支持长任务执行，并可在中断后继续恢复。
- 支持通过 YAML 加载层级式或扁平式 agent system。
- 基于工作空间路径进行文件级记忆。
- 工具默认通过进程内 `direct-tools` 执行，不再依赖独立 tool server。
- 支持 [Agent Skills 标准](https://agentskills.io/)。
- 支持 `action_window_steps`、`thinking_interval` 和定时/手动 `fresh`。
- 支持动态发现并注入 MCP tools。
- 桌面端可配置 PATH 模式、额外环境变量、命令模式、skills 根目录和 marketplace 地址。
- 同时支持多模态和纯文本模型流。
- 提供 CLI、Web UI、Desktop、JSONL 流和 Python SDK 多种接入方式。

## 最近更新

- 2026-02-09：仓库 Releases 已发布打包好的 macOS 桌面版，可从 [Releases](https://github.com/ChenglinPoly/infiAgent/releases) 获取。
- 2026-02-07：`main` 已合入 Agent Skills、多供应商模型配置、Web UI 恢复/系统切换、多模态消息拆分等更新。
- 当前 `desktop-app` 工作进一步补上了打包后端构建脚本、Electron 运行时设置、单任务日志、marketplace server 集成、Python SDK 打包、MCP 运行时支持和可调执行节奏。

## 快速开始

### 方式 1：Desktop App

如果你希望直接使用打包客户端，可以从仓库 Releases 页面获取 macOS 版本。桌面端源码位于 [`desktop_app/`](desktop_app/)，打包后端构建脚本位于 [`backend_build/`](backend_build/)。

源码运行：

```bash
cd desktop_app
npm install
npm run start
```

从源码构建 mac 应用：

```bash
cd desktop_app
npm run build:mac
```

说明：

- 桌面端默认使用 `OpenCowork`。
- 运行时设置保存在 `~/mla_v3/config/app_config.json`。
- 用户可编辑的模型配置保存在 `~/mla_v3/config/llm_config.yaml`。

### 方式 2：Docker

```bash
docker pull chenglinhku/mlav3:latest
```

Web UI 模式：

```bash
cd /your/workspace
docker run -d --name mla \
  -e HOST_PWD=$(pwd) \
  -v $(pwd):/workspace$(pwd) \
  -v ~/.mla_v3:/root/mla_v3 \
  -v mla-config:/mla_config \
  -p 8002:8002 \
  -p 9641:9641 \
  -p 4242:4242 \
  -p 5002:5002 \
  chenglinhku/mlav3:latest webui && docker logs -f mla
```

然后打开：

- Web UI：`http://localhost:4242`
- 配置页：`http://localhost:9641`

CLI 模式：

```bash
cd /your/workspace
docker run -it --rm \
  -e HOST_PWD=$(pwd) \
  -v $(pwd):/workspace$(pwd) \
  -v ~/.mla_v3:/root/mla_v3 \
  -v mla-config:/mla_config \
  -p 8002:8002 \
  -p 9641:9641 \
  -p 5002:5002 \
  chenglinhku/mlav3:latest cli
```

### 方式 3：本地安装

支持 Python `3.9+`。如果需要通过打包依赖直接使用 MCP，建议使用 Python `3.10+`。

```bash
git clone https://github.com/ChenglinPoly/infiAgent.git
cd infiAgent
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

配置模型端点：

```bash
mla-agent --config-show
mla-agent --config-set api_key "your-api-key"
```

启动 CLI：

```bash
cd /your/workspace
mla-agent --cli
```

说明：

- CLI 和 Web UI 现在默认使用 `Researcher`。
- 首次运行会把 `llm_config.yaml` 复制到 `~/mla_v3/config/`。
- 内置 agent systems 和 bundled skills 在用户目录缺失时会自动播种。

## 工作方式

### Agent Systems

内置系统位于 [`config/agent_library/`](config/agent_library/)：

- `Researcher`：面向文献搜索、文档解析、代码、实验和论文写作的多层级系统。
- `OpenCowork`：面向通用电脑工作的扁平系统。

`ConfigLoader` 会优先读取用户数据目录中的配置，找不到时再回退到仓库内置配置。因此桌面端和 marketplace 可以导入新的 agent system，而不需要直接改仓库文件。

### 运行时模型

- `AgentExecutor` 保存短动作历史、完整事实历史、待执行工具和 thinking 摘要。
- `HierarchyManager` 保存调用树，保证子智能体拿到正确上下文。
- `ConversationStorage` 把状态持久化到工作空间，支持中断后恢复。
- 工具通过进程内 `direct-tools` 执行，旧的独立 tool server 路径不再是正常运行时的必需项。

### 运行时控制

运行时现在支持显式节奏和刷新控制：

- `action_window_steps`：短动作窗口保留多少次 tool call 后清空。
- `thinking_interval`：每隔多少次 tool call 触发一次新的 thinking。
- `fresh_enabled`：是否开启定时 fresh。
- `fresh_interval_sec`：定时刷新间隔。

这些值可以从以下位置设置：

- `~/mla_v3/config/app_config.json`
- 桌面端 Settings
- 环境变量，例如 `MLA_ACTION_WINDOW_STEPS`
- Python SDK 构造参数

### 用户数据目录

运行时统一把用户数据收敛到 `~/mla_v3` 和 `~/.agent`：

```text
~/mla_v3/
├── agent_library/
├── config/
│   ├── app_config.json
│   └── llm_config.yaml
├── conversations/
├── logs/
└── tools_library/

~/.agent/
└── skills/
```

这让 CLI、Web UI、Desktop 和打包后的 Python 后端可以共享导入的系统、skills、设置和任务历史。

## Skills、MCP 与 Marketplace

### Skills

- 仓库内置 skills 位于 [`skills/`](skills/)。
- 用户安装的 skills 位于 `~/.agent/skills/`。
- 运行时会发现 `SKILL.md` frontmatter，并可在任务执行时动态加载或卸载 skill。

### MCP

MCP servers 可通过以下方式配置：

- `~/mla_v3/config/app_config.json`
- 桌面端设置页
- `MLA_MCP_CONFIG_JSON`
- Python SDK 的 `mcp_servers=` 参数

支持的传输方式：

- `streamable_http`
- `sse`
- `stdio`

运行时会把发现到的 MCP tools 注入当前 agent 的可见工具集中，并在调用时通过 MCP client 路由执行。

### Marketplace

[`marketplace_server/`](marketplace_server/) 提供了一个很轻量的 FastAPI 服务，用于发布：

- skill zip 下载
- agent system zip 下载
- 轻量上传和管理接口

桌面端可以配置自定义 marketplace base URL，并从中安装 skills 或 agent systems。

## Python SDK

SDK 入口位于 [`infiagent/sdk.py`](infiagent/sdk.py)。

```python
from infiagent import infiagent

agent = infiagent(
    workspace="/path/to/workspace",
    default_agent_system="Researcher",
    default_agent_name="alpha_agent",
    action_window_steps=12,
    thinking_interval=6,
    fresh_enabled=True,
    fresh_interval_sec=300,
    mcp_servers=[
        {
            "name": "github",
            "transport": "streamable_http",
            "url": "https://example.com/mcp",
        }
    ],
)

result = agent.run("Analyze this repository and propose a refactor plan")
print(result["status"], result["output"])
```

异步包装：

```python
result = await agent.run_async("Write tests for this module")
```

## JSONL 集成

`mla-agent --jsonl` 会输出流式事件，适合编辑器、插件或自定义前端：

```bash
mla-agent \
  --task_id $(pwd) \
  --agent_system Researcher \
  --user_input "Optimize this code path" \
  --jsonl
```

常见事件类型：

- `start`
- `token`
- `progress`
- `result`
- `error`
- `end`

桌面端就是基于这条 JSONL 通道，再叠加 stdin 控制消息，完成 HIL 响应、工具确认和手动 fresh 请求。

## 仓库结构

```text
.
├── core/                    # 运行时编排
├── services/                # LLM 与 thinking 服务
├── tool_server_lite/tools/  # direct tool 实现
├── utils/                   # 配置、运行时、存储、skill 辅助
├── config/agent_library/    # 内置 agent systems
├── skills/                  # 内置 skills
├── infiagent/               # Python SDK package
├── desktop_app/             # Electron 桌面端
├── backend_build/           # 打包后端构建脚本与 spec
├── web_ui/                  # 浏览器客户端
├── marketplace_server/      # skills / agent-system 市场服务
└── docs/                    # CLI 与 Docker 指南
```

## 文档

- [`docs/CLI_GUIDE.md`](docs/CLI_GUIDE.md)
- [`docs/DOCKER_GUIDE.md`](docs/DOCKER_GUIDE.md)
- [`web_ui/README.md`](web_ui/README.md)
- [`marketplace_server/README.md`](marketplace_server/README.md)
- [`docs/EVENT_SCHEMA.md`](docs/EVENT_SCHEMA.md)

## Demo 输出

<p align="center">
  <img src="assets/paper_generation_demo_1.gif" alt="Paper Generation Demo 1" width="800">
</p>

<p align="center">
  <img src="assets/paper1.png" alt="Paper Output 1" width="800">
</p>

<p align="center">
  <img src="assets/paper2.png" alt="Paper Output 2" width="800">
</p>

## 论文

[InfiAgent: An Infinite-Horizon Framework for General-Purpose Autonomous Agents](https://arxiv.org/abs/2601.03204)

## 许可证

GPL。
