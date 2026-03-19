# InfiAgent SDK Guide

适用版本：建议使用最新版 `infiagent`

这份文档按当前代码实现编写，目标是让你在 `pip install infiagent` 之后，只靠这份文档就能理解：

- `task_id` 到底是什么
- `user_data_root`、`skills_dir`、`tools_dir` 各自控制什么
- 默认目录里哪些内容会自动生成，哪些不会
- 怎么把默认配置复制到你自己的项目目录
- SDK 的同步 / 异步接口分别怎么用
- 怎么接入自己的动态工具（外挂 tool）

核心结论先说：

1. `infiagent(...)` 负责定义一个 SDK 实例的运行时默认配置。
2. 真正执行任务时，必须显式提供 `task_id`。
3. `task_id` 不是一个抽象字符串，它就是这个任务的工作目录绝对路径。
4. `user_data_root` 控制配置、agent system、运行状态、日志、share context 等目录。
5. `skills` 默认是全局目录 `~/.agent/skills`，不跟随 `user_data_root`，除非你显式覆盖。
6. `tools_library` 默认只会创建目录，不会像 `agent_library` 和 `skills` 那样自动复制内置工具进去。

参考代码：

- SDK 入口：`infiagent/sdk.py`
- 用户目录与默认资源：`utils/user_paths.py`
- 配置加载：`utils/config_loader.py`
- 后台任务启动 / fresh / resume：`utils/task_runtime.py`
- 动态工具注册：`tool_server_lite/registry.py`

## 1. 安装

推荐直接从 PyPI 安装：

```bash
python -m pip install -U infiagent
```

确认版本：

```bash
python - <<'PY'
import importlib.metadata
print(importlib.metadata.version("infiagent"))
PY
```

如果你有多个 Python 环境，请始终用实际运行 SDK 的那个解释器安装，例如：

```bash
/opt/anaconda3/bin/python -m pip install -U infiagent
```

## 2. 第一次启动应该做什么

安装完成后，最推荐做的一步不是直接跑任务，而是先让 SDK 打印运行时目录：

```python
from infiagent import infiagent

agent = infiagent()
runtime = agent.describe_runtime()
print(runtime)
```

这一步会做两件事：

1. 打印当前实例实际使用的路径。
2. 触发默认 runtime scaffold 的创建与内置资源的初始化。

注意：

- 仅仅执行 `agent = infiagent()` 构造函数，本身不会创建目录，也不会自动种资源。
- 真正触发目录初始化的是 `describe_runtime()`、`run()`、`add_message()` 这类进入 runtime scope 的方法。

## 3. 先分清两类目录

### 3.1 `user_data_root`：SDK 的运行时根目录

默认是：

```text
~/mla_v3
```

它下面通常会有：

```text
~/mla_v3/
├── config/
│   ├── llm_config.yaml
│   └── app_config.json
├── agent_library/
├── tools_library/
├── conversations/
├── logs/
└── runtime/
```

这些目录分别负责：

- `config/`：LLM 配置、app runtime 配置
- `agent_library/`：agent system YAML
- `tools_library/`：你的自定义动态工具目录
- `conversations/`：share context / stack / per-agent actions 持久化
- `logs/`：普通日志目录
- `runtime/`：后台任务、task events、运行态文件

### 3.2 `task_id`：单个任务的工作目录

`task_id` 不是逻辑 ID，不是 UUID，也不是数据库主键。

当前 SDK 语义里：

- `task_id` 就是任务工作目录的绝对路径
- 同一个 `task_id` 代表同一个任务身份
- 同一个 `task_id` 会复用同一份 workspace、share context、stack、历史动作和运行状态

例如：

```python
task_id="/path/to/my_agent_project/tasks/refactor_task"
```

那么：

- 这个目录本身是任务的工作空间
- 任务生成的文件一般写到这里
- `system-add.md` 放在这里
- 当前 task 加载的 skills 会部署到这里的 `.skills/`

### 3.3 `skills_dir`：全局 skills 源库

默认是：

```text
~/.agent/skills/
```

它和 `user_data_root` 是两套目录：

- `user_data_root` 管这个 SDK 实例的运行时
- `skills_dir` 管全局可发现的 skill 源库

默认情况下：

- 发现 skill：从 `~/.agent/skills/` 扫描
- 加载 skill：复制到 `<task_id>/.skills/<skill_name>/`

## 4. 默认会自动生成什么，不会自动生成什么

第一次真正进入 runtime scope 后，默认行为是：

### 4.1 会自动创建 / 补齐

- `~/mla_v3/config/llm_config.yaml`
- `~/mla_v3/config/app_config.json`
- `~/mla_v3/agent_library/`
- `~/mla_v3/tools_library/`
- `~/mla_v3/conversations/`
- `~/mla_v3/logs/`
- `~/mla_v3/runtime/`
- `~/.agent/skills/`

### 4.2 会自动种进去的内置资源

- `agent_library` 中的内置 agent systems
- `skills` 中的内置 skills
- `llm_config.yaml` 的默认样例
- `app_config.json` 的默认样例

### 4.3 不会自动种进去的内容

`tools_library` 默认只会创建空目录：

```text
~/mla_v3/tools_library/
```

不会自动复制内置 Python tool 文件进去。

也就是说，下面这件事经常是空操作：

```bash
cp -R ~/mla_v3/tools_library/. /path/to/my_agent_project/runtime/tools_library/
```

因为默认安装后的 `~/mla_v3/tools_library/` 往往本来就是空的。

## 5. `task_id` 的精确定义

这是最重要的一节。

### 5.1 `task_id` 是工作目录绝对路径

推荐始终传绝对路径：

```python
from infiagent import infiagent

agent = infiagent()
result = agent.run(
    "请分析这个目录并给出重构建议",
    task_id="/abs/path/to/tasks/refactor_task",
)
```

SDK 内部会对它做：

- `expanduser()`
- `resolve()`

但你仍然应该自己按“绝对路径工作目录”来理解和设计。

### 5.2 同一个 `task_id` 会复用什么

同一个 `task_id` 会复用：

- 同一个工作目录
- 同一份 `share_context`
- 同一份 `stack`
- 同一组 per-agent `actions`
- 同一段任务历史与 runtime metadata

所以：

- 同一 deliverable 的继续修改：优先复用旧 `task_id`
- 对同一任务补充新要求：优先 `add_message(...)`
- 已停止但仍是同一工作：可以 `start_background_task(task_id=旧 task_id, ...)`
- 全新 deliverable / 并行分支 / 完全不同工作：新建新的 `task_id`

### 5.3 `task_id` 对应的文件到底存在哪里

任务工作目录是：

```text
<task_id>/
```

而 runtime metadata 不直接写在 `<task_id>/`，而是写到：

```text
<user_data_root>/conversations/
```

文件命名不是固定的 `share_context.json`、`stack.json`、`actions.json`，而是带 task hash 的形式：

- `<hash>_<task-folder>_share_context.json`
- `<hash>_<task-folder>_stack.json`
- `<hash>_<task-folder>_<agent_id>_actions.json`

因此，最稳妥的定位方式不是猜文件名，而是用 SDK：

```python
paths = agent.task_share_context_path(task_id="/abs/path/to/tasks/refactor_task")
print(paths["share_context_path"])
print(paths["stack_path"])
```

### 5.4 `fresh()` 对停止任务的真实行为

文档里最容易被误解的一点是：

- 运行中的 task：`fresh()` 会发送 fresh 请求
- 未运行的 task：不是“必然后台 resume”

只有当这个 task 已经有：

- 可恢复的 `stack`
- 足够的 runtime metadata

时，`fresh()` 才能在后台 resume。

如果没有可恢复状态，`fresh()` 会返回错误，而不是自动创建一个新任务。

## 6. 如何查看当前实例实际在用哪些路径

```python
from infiagent import infiagent

agent = infiagent()
runtime = agent.describe_runtime()
print(runtime)
```

返回里最常用的字段有：

- `user_data_root`
- `config_dir`
- `llm_config_path`
- `app_config_path`
- `agent_library_dir`
- `tools_dir`
- `skills_dir`
- `conversations_dir`
- `logs_dir`
- `runtime_dir`
- `default_agent_system`
- `default_agent_name`
- `seed_builtin_resources`

如果你想看当前有哪些 agent system：

```python
systems = agent.list_agent_systems()
print(systems["agent_systems"])
```

注意返回字段名是：

```python
agent_systems
```

不是 `systems`。

## 7. 推荐的目录使用方式

不要直接长期在默认的 `~/mla_v3` 里开发你的项目逻辑。

更推荐的方式是：

1. 用默认用户目录拿到标准样例和内置系统
2. 复制到你自己的项目 runtime
3. 让你的应用显式绑定自己的 `user_data_root`

推荐项目结构：

```text
my_agent_project/
├── runtime/
│   ├── config/
│   │   ├── llm_config.yaml
│   │   └── app_config.json
│   ├── agent_library/
│   │   └── MyAgentSystem/
│   ├── tools_library/
│   │   └── echo_text/
│   │       └── echo_text.py
│   ├── conversations/
│   ├── logs/
│   └── runtime/
├── tasks/
│   ├── task_a/
│   └── task_b/
├── hooks/
│   └── my_hooks.py
└── main.py
```

好处：

- 配置和状态都跟你的项目一起管理
- 不污染全局 `~/mla_v3`
- 更容易迁移、打包、部署

## 8. 把默认配置复制到你自己的目录

### 8.1 先让默认资源种出来

```python
from infiagent import infiagent

agent = infiagent()
agent.describe_runtime()
```

### 8.2 创建你自己的 runtime

```bash
mkdir -p /path/to/my_agent_project/runtime/config
mkdir -p /path/to/my_agent_project/runtime/agent_library
mkdir -p /path/to/my_agent_project/runtime/tools_library
mkdir -p /path/to/my_agent_project/tasks
```

### 8.3 复制标准配置和你要用的 agent system

```bash
cp ~/mla_v3/config/llm_config.yaml /path/to/my_agent_project/runtime/config/
cp ~/mla_v3/config/app_config.json /path/to/my_agent_project/runtime/config/
cp -R ~/mla_v3/agent_library/OpenCowork /path/to/my_agent_project/runtime/agent_library/MyAgentSystem
```

说明：

- `tools_library` 不需要从 `~/mla_v3` 复制默认内容，因为默认情况下它本来就是空目录
- 你只要自己在 `/path/to/my_agent_project/runtime/tools_library/` 里新增工具即可

### 8.4 用你自己的 runtime 启动 SDK

```python
from infiagent import infiagent

agent = infiagent(
    user_data_root="/path/to/my_agent_project/runtime",
    default_agent_system="MyAgentSystem",
    default_agent_name="alpha_agent",
)
```

如果你的 runtime 已经包含：

- `config/llm_config.yaml`
- `config/app_config.json`
- `agent_library/...`
- `tools_library/...`

通常就不需要再额外传：

- `llm_config_path`
- `agent_library_dir`
- `tools_dir`

## 9. 参考配置文件样例

下面两份就是你最应该先准备好的配置。

### 9.1 `llm_config.yaml` 参考样例

这是一个和当前实现兼容的有效样例：

```yaml
temperature: 0
max_tokens: 0
max_context_window: 500000

base_url: https://openrouter.ai/api/v1
api_key: "YOUR_API_KEY"

timeout: 600
stream_timeout: 30
first_chunk_timeout: 30

tool_choice:
  execution: required
  thinking: none
  compressor: none
  image_generation: none
  read_figure: none

models:
  - name: openai/google/gemini-3-flash-preview
    default: true

figure_models:
  - google/gemini-3-pro-image-preview

compressor_models:
  - openai/google/gemini-3-flash-preview

thinking_models:
  - openai/google/gemini-3-flash-preview

read_figure_models:
  - openai/google/gemini-3-flash-preview

multimodal: true
compressor_multimodal: true
```

你也可以用对象格式按模型单独覆盖 `base_url`、`api_key`、`tool_choice`：

```yaml
models:
  - name: openai/qwen-plus
    default: true
    api_key: "YOUR_DASHSCOPE_KEY"
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    tool_choice: auto
```

当前实现支持的模型用途包括：

- `models`：执行模型
- `thinking_models`：thinking agent
- `compressor_models`：压缩模型
- `figure_models`：图像生成模型
- `read_figure_models`：读图模型

对应的 agent YAML 偏好字段包括：

- `execution_model`
- `thinking_model`
- `compressor_model`
- `image_generation_model`
- `read_figure_model`

### 9.2 `app_config.json` 参考样例

```json
{
  "runtime": {
    "action_window_steps": 10,
    "thinking_interval": 10,
    "fresh_enabled": false,
    "fresh_interval_sec": 0
  },
  "env": {
    "command_mode": "direct",
    "seed_builtin_resources": true
  },
  "context": {
    "user_history_compress_threshold_tokens": 1500,
    "structured_call_info_compress_threshold_agents": 10,
    "structured_call_info_compress_threshold_tokens": 2200
  }
}
```

这里最常改的是：

- `runtime.action_window_steps`
- `runtime.thinking_interval`
- `runtime.fresh_enabled`
- `runtime.fresh_interval_sec`

如果你是 SDK 嵌入式使用，`mcp_servers=[...]` 更推荐直接在构造参数里传，而不是先写 `app_config.json`。

## 10. 推荐的最小 agent system 改法

最简单的方式不是从零写一套 YAML，而是先复制一个现成 system，再逐步改。

例如基于 `OpenCowork`：

```bash
cp -R ~/mla_v3/agent_library/OpenCowork /path/to/my_agent_project/runtime/agent_library/MyAgentSystem
```

你最常改的是：

- `general_prompts.yaml`
- `level_0_tools.yaml`
- `level_3_agents.yaml`

### 10.1 `general_prompts.yaml`

通常只需要改：

- 系统角色
- 工作流程
- 输出要求

### 10.2 `level_0_tools.yaml`

这里定义工具的 schema，让 LLM 知道工具名、描述、参数。

### 10.3 `level_3_agents.yaml`

这里定义 LLM agent：

- agent 名称
- `available_tools`
- 模型偏好
- prompt 中注入的职责

## 11. SDK 初始化参数总览

最常用构造方式：

```python
from infiagent import infiagent

agent = infiagent(
    user_data_root="/path/to/my_agent_project/runtime",
    default_agent_system="MyAgentSystem",
    default_agent_name="alpha_agent",
    action_window_steps=20,
    thinking_interval=20,
)
```

主要参数如下：

| 参数 | 作用 | 备注 |
| --- | --- | --- |
| `user_data_root` | 这套实例的 runtime 根目录 | 最推荐使用 |
| `llm_config_path` | 指定 `llm_config.yaml` 路径 | 可覆盖 `user_data_root/config/llm_config.yaml` |
| `library_dir` / `agent_library_dir` | 指向包含 `agent_library/` 的根目录 | 兼容旧参数，推荐优先用 `user_data_root` |
| `skills_dir` | 指定 skills 源库目录 | 默认 `~/.agent/skills` |
| `tools_dir` | 指定动态工具根目录 | 默认 `<user_data_root>/tools_library` |
| `default_agent_system` | 默认 agent system 名称 | 默认 `OpenCowork` |
| `default_agent_name` | 默认入口 agent 名称 | 默认 `alpha_agent` |
| `action_window_steps` | 行动窗口步数 | 同时可从 `app_config.json` / 环境变量读取 |
| `thinking_interval` | thinking 间隔 | 同上 |
| `fresh_enabled` | 是否启用定时 fresh | 可选 |
| `fresh_interval_sec` | fresh 周期秒数 | 可选 |
| `mcp_servers` | 直接注入 MCP 配置 | SDK 嵌入场景推荐 |
| `tool_hooks` | 工具调用 hook | 见后文 |
| `context_hooks` | 上下文构建 hook | 见后文 |
| `seed_builtin_resources` | 是否自动种内置 agent systems / skills | 默认 `True` |
| `direct_tools` | 是否使用进程内 direct tools | 默认 `True`，保持默认即可 |
| `workspace` | 旧参数兼容保留 | 新语义下不要依赖它，显式传 `task_id` |

## 12. 公共同步 API

下面这些都是当前 SDK 已公开的方法。

### 12.1 `run(...)`

同步前台执行一个任务：

```python
result = agent.run(
    "请分析这个目录并给出重构建议",
    task_id="/path/to/my_agent_project/tasks/refactor_task",
)
print(result)
```

要点：

- `task_id` 必填
- `agent_system`、`agent_name` 可覆盖实例默认值
- `force_new=True` 会清空当前 task 的 current state 和 stack 后重新开始
- 如果这个 task 已在运行，会返回 `status="busy"`，而不是强行并发重入

### 12.2 `fresh(...)`

```python
agent.fresh(
    task_id="/path/to/my_agent_project/tasks/refactor_task",
    reason="reload runtime config",
)
```

行为：

- task 正在运行：发送定向 fresh 请求
- task 未运行但可恢复：重载配置后后台 resume
- task 未运行且不可恢复：返回 error

### 12.3 `add_message(...)`

```python
agent.add_message(
    "补充要求：保留原目录结构，只允许做增量修改。",
    task_id="/path/to/my_agent_project/tasks/refactor_task",
    source="user",
    resume_if_needed=True,
)
```

适合：

- 对同一任务追加需求
- 给运行中的 task 插入新消息
- 已停止 task 先追加消息，再视情况后台恢复

### 12.4 `start_background_task(...)`

```python
agent.start_background_task(
    task_id="/path/to/my_agent_project/tasks/task_b",
    user_input="后台整理日志并生成总结",
    agent_system="MyAgentSystem",
    agent_name="alpha_agent",
    force_new=True,
)
```

特点：

- 启动独立后台 Python 进程
- `task_id` 对应的目录不存在时会自动创建
- 日志写到 `<user_data_root>/runtime/launched_tasks/`

`config=` 还支持在后台启动时临时覆盖运行时参数，常见键包括：

- `llm_config_path`
- `user_data_root`
- `agent_library_dir` / `library_dir`
- `skills_dir`
- `tools_dir`
- `action_window_steps`
- `thinking_interval`
- `fresh_enabled`
- `fresh_interval_sec`
- `mcp_servers`
- `tool_hooks`
- `context_hooks`
- `visible_skills`
- `auto_mode`
- `force_new`
- `direct_tools`
- `seed_builtin_resources`

### 12.5 `task_share_context_path(...)`

```python
paths = agent.task_share_context_path(
    task_id="/path/to/my_agent_project/tasks/refactor_task"
)
print(paths["share_context_path"])
print(paths["stack_path"])
```

用来精确定位 runtime metadata 文件路径。

### 12.6 `list_task_ids(...)`

```python
tasks = agent.list_task_ids()
running_only = agent.list_task_ids(only_running=True)
print(tasks["tasks"])
```

返回当前 `user_data_root/conversations` 下已知的任务列表。

### 12.7 `describe_runtime(...)`

```python
runtime = agent.describe_runtime()
print(runtime)
```

这是最推荐的 runtime 自省入口。

### 12.8 `list_agent_systems(...)`

```python
systems = agent.list_agent_systems()
for item in systems["agent_systems"]:
    print(item["name"], item["agent_names"])
```

返回：

- system 名称
- 路径
- 是否包含 `general_prompts.yaml`
- 是否包含 `level_0_tools.yaml`
- 该 system 下识别出的 agent 名称

### 12.9 `task_snapshot(...)`

```python
snapshot = agent.task_snapshot(
    task_id="/path/to/my_agent_project/tasks/refactor_task"
)
print(snapshot)
```

适合做 dashboard / watchdog / 外部调度：

- 是否还在运行
- 最新 instruction
- 最新 thinking
- 最近 final output
- share_context / stack 路径

### 12.10 `reset_task(...)`

```python
agent.reset_task(
    task_id="/path/to/my_agent_project/tasks/refactor_task",
    reason="clear broken loop",
    preserve_history=True,
    kill_background_processes=True,
)
```

适合：

- 清理损坏的 current state
- 保留或丢弃旧 history
- 停掉关联后台进程

## 13. 异步 API：和同步版是否一致，会不会有坑

当前 SDK 为所有主要同步方法都提供了 `_async` 版本：

- `run_async`
- `fresh_async`
- `add_message_async`
- `start_background_task_async`
- `task_share_context_path_async`
- `list_task_ids_async`
- `describe_runtime_async`
- `list_agent_systems_async`
- `task_snapshot_async`
- `reset_task_async`

### 13.1 语义是否一致

一致。

这些 async 方法不是另一套独立实现，而是用 `asyncio.to_thread(...)` 包装同步方法，所以：

- 参数语义一致
- 返回结构一致
- 报错条件一致
- 业务行为一致

例如：

```python
runtime = await agent.describe_runtime_async()
tasks = await agent.list_task_ids_async()
result = await agent.run_async(
    "分析这个目录",
    task_id="/path/to/my_agent_project/tasks/async_task",
)
```

### 13.2 async 版本的真实定位

它的定位是：

- 方便你在 `asyncio` 应用里调用 SDK
- 避免在 event loop 里直接阻塞

它不是：

- 一套“天然支持高并发并行隔离”的运行时
- 一套线程安全的多实例并发调度框架

### 13.3 当前 async 版本的并发注意事项

这点非常重要。

SDK 内部会通过 `runtime_env_scope(...)` 临时切换环境变量来隔离：

- `MLA_USER_DATA_ROOT`
- `MLA_LLM_CONFIG_PATH`
- `MLA_SKILLS_LIBRARY_DIR`
- `MLA_TOOLS_LIBRARY_DIR`
- hooks / MCP / runtime 参数等

这些环境变量是进程级全局状态，不是线程局部状态。

所以当前建议是：

- 可以在 `asyncio` 项目里使用 `_async` 方法
- 但不要在同一个 Python 进程里，让多个 SDK 调用无控制地并发重叠运行
- 特别是不同 `user_data_root`、不同 `tools_dir`、不同 hooks 的实例，更不要并发重叠调用

最稳的用法：

1. 同一进程里串行调用 SDK
2. 或者自己加一个 `asyncio.Lock()`
3. 真要强隔离并发，就做进程隔离

一个安全写法示例：

```python
import asyncio
from infiagent import infiagent

agent = infiagent(user_data_root="/path/to/my_agent_project/runtime")
sdk_lock = asyncio.Lock()

async def safe_run(prompt: str, task_id: str):
    async with sdk_lock:
        return await agent.run_async(prompt, task_id=task_id)
```

## 14. 如何外挂自己的动态工具

这是 `tools_library` 最重要的用法。

### 14.1 动态工具目录规则

默认动态工具根目录是：

```text
<user_data_root>/tools_library/
```

也可以显式覆盖：

```python
agent = infiagent(
    user_data_root="/path/to/my_agent_project/runtime",
    tools_dir="/path/to/my_agent_project/runtime/tools_library",
)
```

当前加载规则是：

1. `tools_library/` 下每个一级子目录代表一个工具
2. 每个工具目录顶层必须且只能有一个 `.py` 文件作为主工具文件
3. 这个 `.py` 文件里必须只有一个公开工具类候选
4. 这个类需要实现 `execute(...)` 或 `execute_async(...)`
5. 推荐继承 `BaseTool`，但加载器当前真正强制的是“公开类 + execute/execute_async”
6. 工具名优先取类属性 `name`，没有则回退到文件名
7. 工具名不能和内置工具重名

推荐目录结构：

```text
/path/to/my_agent_project/runtime/tools_library/
└── echo_text/
    └── echo_text.py
```

注意：

- 工具目录顶层有多个 `.py` 文件会加载失败
- 其他资源文件可以放进去
- 辅助代码更推荐放在子目录里，避免顶层多个 `.py`

### 14.2 一个最小外挂 tool 示例

文件：

```text
/path/to/my_agent_project/runtime/tools_library/echo_text/echo_text.py
```

内容：

```python
from pathlib import Path
from tool_server_lite.tools.file_tools import BaseTool, get_abs_path


class EchoTextTool(BaseTool):
    name = "echo_text"

    def execute(self, task_id: str, parameters: dict) -> dict:
        text = str(parameters.get("text") or "")
        output_path = str(parameters.get("output_path") or "").strip()

        if output_path:
            abs_path = get_abs_path(task_id, output_path)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(text, encoding="utf-8")

        return {
            "status": "success",
            "output": text,
            "error": ""
        }
```

这里要点是：

- `task_id` 就是当前 task 的 workspace 根目录
- 相对路径应通过 `get_abs_path(task_id, relative_path)` 转成绝对路径

### 14.3 只把 `.py` 放进去还不够，还要在 agent system 里声明

动态工具被 runtime registry 扫描到之后，还要在你的 agent system YAML 里把它声明出来，LLM 才知道这个工具存在。

#### 在 `level_0_tools.yaml` 中声明工具 schema

```yaml
tools:
  echo_text:
    level: 0
    type: tool_call_agent
    name: "echo_text"
    description: "回显文本，并可选写入当前 task 工作目录中的文件。"
    parameters:
      type: "object"
      properties:
        text:
          type: "string"
          description: "要输出的文本。"
        output_path:
          type: "string"
          description: "可选。相对于当前 task 工作目录的输出文件路径。"
      required: ["text"]
```

#### 在 `level_3_agents.yaml` 中让 agent 看见它

如果你的 agent 使用显式 `available_tools`：

```yaml
tools:
  alpha_agent:
    level: 3
    type: llm_call_agent
    name: "alpha_agent"
    available_tools:
      - file_read
      - file_write
      - echo_text
      - final_output
    prompts:
      agent_responsibility: |
        你是一个通用 AI 助手。
      agent_workflow: |
        阅读任务后，选择合适工具完成工作。
```

如果你的 agent 用的是 `available_tool_level` 自动收集对应 level 的工具，那么只要：

- 你的工具在 `level_0_tools.yaml` 中是 `level: 0`
- 这个 agent 会自动包含 level 0 工具

就不需要在 `available_tools` 里逐个列。

### 14.4 新增外挂 tool 之后如何让运行中的任务看到它

你新增工具之后：

- 对新启动的 task：通常直接可见
- 对已经在运行中的 task：需要 `fresh()`

例如：

```python
agent.fresh(
    task_id="/path/to/my_agent_project/tasks/refactor_task",
    reason="installed new custom tool echo_text",
)
```

### 14.5 最容易踩的坑

如果你发现工具“写了但调用不到”，优先检查：

1. 工具目录顶层是否只有一个 `.py`
2. 工具类是否是公开类，且实现了 `execute` 或 `execute_async`
3. 工具 `name` 是否和 YAML 里的 `name` / tool key 对得上
4. 目标 agent 是否真的能看到这个工具
5. 运行中的 task 是否已经 `fresh()`

## 15. Skills 的用法

默认 skills 主库：

```text
~/.agent/skills/
```

SDK 会先把可见 skills 作为 `<available_skills>` 注入 system prompt。

真正使用 skill 时：

1. LLM 调用 `load_skill`
2. skill 从 `skills_dir` 复制到 `<task_id>/.skills/<skill_name>/`
3. `SKILL.md` 的内容注入当前上下文

所以要区分两件事：

- “当前 task 看得见哪些 skill”
- “当前 task 已经加载了哪些 skill”

如果你想改 skill 源库目录：

```python
agent = infiagent(
    user_data_root="/path/to/my_agent_project/runtime",
    skills_dir="/path/to/my_agent_project/skills",
)
```

## 16. Hooks：如何在 SDK 外层做集成

### 16.1 Tool Hooks

你可以在工具调用前后挂钩：

```python
agent = infiagent(
    user_data_root="/path/to/my_agent_project/runtime",
    tool_hooks=[
        {
            "name": "observe-final-output",
            "callback": "/abs/path/to/my_hooks.py:on_tool_event",
            "when": "after",
            "tool_names": ["final_output"],
            "include_arguments": False,
            "include_result": True,
            "result_filters": {"status": "success"}
        }
    ],
)
```

当前支持的主要字段：

- `name`
- `callback`
- `when`: `before` / `after` / `both`
- `tool_names`
- `include_arguments`
- `include_result`
- `argument_filters`
- `result_filters`

`callback` 可以是：

- `"/abs/path/to/file.py:function_name"`
- `"python.module:function_name"`

### 16.2 Context Hooks

你也可以在上下文构建后改写最终 prompt：

```python
agent = infiagent(
    user_data_root="/path/to/my_agent_project/runtime",
    context_hooks=[
        {
            "name": "rewrite-context",
            "callback": "/abs/path/to/my_hooks.py:on_context",
            "when": "after_build"
        }
    ],
)
```

当前 callback 可以返回：

- 一个字符串：直接替换 `context_text`
- 一个 dict：例如 `{"context_text": "..."}`

## 17. 一个完整起步示例

```python
from infiagent import infiagent


agent = infiagent(
    user_data_root="/path/to/my_agent_project/runtime",
    default_agent_system="MyAgentSystem",
    default_agent_name="alpha_agent",
    action_window_steps=20,
    thinking_interval=20,
)


task_id = "/path/to/my_agent_project/tasks/plan_task"

result = agent.run(
    "先阅读项目，再生成一份改造计划",
    task_id=task_id,
)
print(result)

snapshot = agent.task_snapshot(task_id=task_id)
print(snapshot["latest_thinking"])

agent.add_message(
    "补充要求：优先保留现有目录结构。",
    task_id=task_id,
    source="user",
    resume_if_needed=True,
)
```

## 18. 最后几条建议

1. 不要直接修改 `site-packages/infiagent/...`

- 升级后会丢
- 也不利于迁移和复用

2. 不要把所有长期实验都堆在默认 `~/mla_v3`

- 先用默认目录拿样例
- 再复制到自己的 `runtime/`
- 让项目代码显式绑定自己的 `user_data_root`

3. 如果你是 SDK 嵌入式使用者，优先把“项目目录”和“task workspace”分开设计

- `runtime/` 管框架配置和状态
- `tasks/<task_name>/` 管单个任务的工作文件

4. 如果你要在生产代码里使用 async 版本，请把它当作“async 友好的同步封装”，而不是并发隔离框架

- 需要并发时，优先自己加锁
- 真正强隔离时，优先进程隔离

5. 如果安装后发现 `~/mla_v3/tools_library/` 是空的，这是正常现象

- 默认不会自动复制内置 Python tool 到这里
- 这个目录本来就是留给你放自定义动态工具的
