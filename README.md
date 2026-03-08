<div align="center">
  <img src="assets/logo.png" alt="infiAgent Logo" width="200">

  <h1>MLA V3 / infiAgent</h1>

  <p>Long-running multi-agent automation for research and real-world computer work.</p>

  <p>
    <img src="https://img.shields.io/badge/version-3.0.0-blue.svg" alt="Version">
    <img src="https://img.shields.io/badge/python-3.9%2B-green.svg" alt="Python">
    <img src="https://img.shields.io/badge/license-GPL-blue.svg" alt="License">
  </p>

  <p>
    <a href="README.md">English</a> | <a href="README_CN.md">简体中文</a>
  </p>
</div>

## Introduction

`infiAgent` (also called `MLA V3`, Multi-Level Agent) is a Python-first agent framework for tasks that do not finish in one short chat turn. It is built around persistent workspace state, resumable execution, hierarchical agent orchestration, and file-based memory rather than a single growing prompt.

The repository now ships more than the original CLI runtime:

- `Researcher`: the bundled long-horizon research system with multi-level agent orchestration.
- `OpenCowork`: a flatter workspace assistant for coding, document work, file operations, and tool-heavy tasks.
- `Desktop app`: Electron client with packaged Python backend support, per-task logs, runtime settings, skills import, MCP settings, and marketplace integration.
- `Web UI`: browser client with JSONL streaming, HIL handling, system selection, resume support, and task file browser.
- `Python SDK`: embed the runtime directly from Python with configurable action windows, thinking interval, fresh reload, and MCP servers.

## Current Capabilities

- Long-running task execution with resume after interruption.
- Hierarchical or flat agent systems loaded from YAML.
- File-based memory scoped to the current workspace.
- Direct in-process tool execution. No standalone tool server is required.
- Agent Skills support via the [Agent Skills standard](https://agentskills.io/).
- Runtime tuning for `action_window_steps`, `thinking_interval`, and scheduled/manual `fresh`.
- Dynamic MCP tool discovery from configured MCP servers.
- Desktop-side environment controls: PATH mode, extra env vars, command mode, skills root, marketplace URL.
- Multimodal and text-only model flows.
- CLI, Web UI, Desktop app, JSONL streaming, and Python SDK integration.

## Recent Updates

- 2026-02-09: packaged macOS desktop release published on the repo [Releases](https://github.com/ChenglinPoly/infiAgent/releases).
- 2026-02-07: Agent Skills support, multi-provider model config, Web UI resume/system selector, and multimodal message split landed on `main`.
- Current `desktop-app` work adds packaged-backend build scripts, Electron runtime settings, per-task logs, marketplace server integration, Python SDK packaging, MCP runtime support, and configurable execution cadence.

## Quick Start

### Option 1: Desktop App

If you want a packaged client, use the macOS release from the repo Releases page. The desktop source lives in [`desktop_app/`](desktop_app/) and the packaged backend build scripts live in [`backend_build/`](backend_build/).

For source builds:

```bash
cd desktop_app
npm install
npm run start
```

To build a mac app bundle from source:

```bash
cd desktop_app
npm run build:mac
```

Notes:

- The desktop client defaults to `OpenCowork`.
- Runtime settings are stored under `~/mla_v3/config/app_config.json`.
- User-editable model config is stored at `~/mla_v3/config/llm_config.yaml`.

### Option 2: Docker

```bash
docker pull chenglinhku/mlav3:latest
```

Web UI mode:

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

Then open:

- Web UI: `http://localhost:4242`
- Config page: `http://localhost:9641`

CLI mode:

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

### Option 3: Local Installation

Python `3.9+` is supported. If you need MCP support through the packaged `mcp` dependency, use Python `3.10+`.

```bash
git clone https://github.com/ChenglinPoly/infiAgent.git
cd infiAgent
python -m venv .venv
source .venv/bin/activate
pip install -e .
playwright install chromium
```

Configure your model endpoint:

```bash
mla-agent --config-show
mla-agent --config-set api_key "your-api-key"
```

Start the CLI:

```bash
cd /your/workspace
mla-agent --cli
```

Notes:

- CLI and Web UI now default to `Researcher`.
- `llm_config.yaml` is copied into `~/mla_v3/config/` on first run.
- Built-in agent systems and bundled skills are seeded into the user directories if missing.

## How It Works

### Agent Systems

Bundled systems live under [`config/agent_library/`](config/agent_library/):

- `Researcher`: layered agents for literature search, document parsing, coding, experiments, and paper writing.
- `OpenCowork`: flatter workspace assistant for general computer work.

`ConfigLoader` first checks the user data root, then falls back to the repo copy. That lets the desktop client and marketplace import new agent systems without editing the repo.

### Runtime Model

- `AgentExecutor` keeps persistent action history, full fact history, pending tools, and thinking summaries.
- `HierarchyManager` stores the call tree so sub-agents can inherit the right context.
- `ConversationStorage` persists state under the workspace so interrupted runs can resume.
- Tools execute via the in-process `direct-tools` path; the old standalone tool server path is no longer required for normal runtime use.

### Runtime Controls

The runtime now supports explicit cadence and refresh controls:

- `action_window_steps`: how many tool calls stay visible before the short action window is cleared.
- `thinking_interval`: how often the runtime triggers a new thinking step.
- `fresh_enabled`: whether scheduled fresh is enabled.
- `fresh_interval_sec`: interval for scheduled refresh.

These values can be set from:

- `~/mla_v3/config/app_config.json`
- Desktop settings UI
- environment variables such as `MLA_ACTION_WINDOW_STEPS`
- the Python SDK constructor

### User Data Directories

The runtime standardizes user data under `~/mla_v3` and `~/.agent`:

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

This is what lets CLI, Web UI, Desktop, and packaged backends share the same imported systems, skills, settings, and task history.

## Skills, MCP, and Marketplace

### Skills

- Bundled skills live under [`skills/`](skills/).
- User-installed skills live under `~/.agent/skills/`.
- The runtime discovers `SKILL.md` frontmatter and can load or offload skills dynamically inside a task.

### MCP

MCP servers can be configured through:

- `~/mla_v3/config/app_config.json`
- the desktop settings screen
- `MLA_MCP_CONFIG_JSON`
- the Python SDK `mcp_servers=` argument

Supported transports:

- `streamable_http`
- `sse`
- `stdio`

Discovered MCP tools are exposed to the active agent as synthetic tool definitions and executed through the MCP client at runtime.

### Marketplace

[`marketplace_server/`](marketplace_server/) contains a small FastAPI service for publishing:

- skill zip downloads
- agent system zip downloads
- lightweight upload/admin endpoints

The desktop client can point to a custom marketplace base URL and install skills or agent systems from it.

## Python SDK

The packaged SDK entry point lives in [`infiagent/sdk.py`](infiagent/sdk.py).

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

Async wrapper:

```python
result = await agent.run_async("Write tests for this module")
```

## JSONL Integration

`mla-agent --jsonl` streams runtime events for editors, plugins, or custom frontends:

```bash
mla-agent \
  --task_id $(pwd) \
  --agent_system Researcher \
  --user_input "Optimize this code path" \
  --jsonl
```

Typical event types:

- `start`
- `token`
- `progress`
- `result`
- `error`
- `end`

The desktop client uses the same JSONL channel plus stdin control messages for HIL responses, tool confirmations, and manual fresh requests.

## Repository Layout

```text
.
├── core/                    # runtime orchestration
├── services/                # llm + thinking services
├── tool_server_lite/tools/  # direct tool implementations
├── utils/                   # config, runtime, storage, skill helpers
├── config/agent_library/    # bundled agent systems
├── skills/                  # bundled skills
├── infiagent/               # Python SDK package
├── desktop_app/             # Electron desktop client
├── backend_build/           # packaged backend build scripts/specs
├── web_ui/                  # browser client
├── marketplace_server/      # skills / agent-system market service
└── docs/                    # CLI and Docker guides
```

## Documentation

- [`docs/CLI_GUIDE.md`](docs/CLI_GUIDE.md)
- [`docs/DOCKER_GUIDE.md`](docs/DOCKER_GUIDE.md)
- [`web_ui/README.md`](web_ui/README.md)
- [`marketplace_server/README.md`](marketplace_server/README.md)
- [`docs/EVENT_SCHEMA.md`](docs/EVENT_SCHEMA.md)

## Demo Outputs

<p align="center">
  <img src="assets/paper_generation_demo_1.gif" alt="Paper Generation Demo 1" width="800">
</p>

<p align="center">
  <img src="assets/paper1.png" alt="Paper Output 1" width="800">
</p>

<p align="center">
  <img src="assets/paper2.png" alt="Paper Output 2" width="800">
</p>

## Paper

[InfiAgent: An Infinite-Horizon Framework for General-Purpose Autonomous Agents](https://arxiv.org/abs/2601.03204)

## License

GPL.
