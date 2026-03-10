# InfiAgent Python SDK Guide

适用实现：
- SDK: [infiagent/sdk.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/infiagent/sdk.py)
- 用户目录路径: [utils/user_paths.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/utils/user_paths.py)
- Task 运行时辅助: [utils/task_runtime.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/utils/task_runtime.py)

## 1. 设计原则

当前 SDK 采用“实例描述运行时，方法绑定具体 task”的模型：

1. `infiagent(...)` 负责定义 runtime 配置
2. `run(..., task_id=...)` 和其他 task 方法负责操作具体任务

因此：
- 不再建议把 `workspace` 作为实例级主参数
- `task_id` 才是任务主键，语义上就是任务工作目录绝对路径
- `run()` 必须显式提供 `task_id`

## 2. `user_data_root` 规则

如果指定了 `user_data_root`，下面这些目录都会一起切换：
- `<user_data_root>/config`
- `<user_data_root>/agent_library`
- `<user_data_root>/tools_library`
- `<user_data_root>/conversations`
- `<user_data_root>/logs`
- `<user_data_root>/runtime`

其中：
- `share_context.json`、`stack.json`、`actions.json` 都在 `<user_data_root>/conversations`
- running task / fresh request 状态都在 `<user_data_root>/runtime`

例外：
- `skills` 默认仍然走 `~/.agent/skills`
- 只有显式传 `skills_dir` 才覆盖

## 3. 何时不需要再传路径参数

如果 `user_data_root` 里已经有完整内容：
- `config/llm_config.yaml`
- `config/app_config.json`
- `agent_library/...`
- `tools_library/...`

通常不需要再传：
- `llm_config_path`
- `agent_library_dir`
- `tools_dir`

最小实例：
```python
from infiagent import infiagent

agent = infiagent(
    user_data_root="/abs/path/to/my_root",
    default_agent_system="OpenCowork",
    default_agent_name="alpha_agent",
)
```

## 4. 常用初始化参数

```python
agent = infiagent(
    user_data_root="/abs/path/to/my_root",
    llm_config_path="/abs/path/to/llm_config.yaml",
    agent_library_dir="/abs/path/to/agent_library",
    tools_dir="/abs/path/to/tools_library",
    skills_dir="/abs/path/to/skills",
    default_agent_system="OpenCowork",
    default_agent_name="alpha_agent",
    action_window_steps=12,
    thinking_interval=12,
    fresh_enabled=True,
    fresh_interval_sec=300,
    direct_tools=True,
)
```

参数语义：
- `user_data_root`: 当前实例主数据根目录
- `llm_config_path`: 覆盖模型配置
- `agent_library_dir`: 覆盖 agent system 配置目录
- `tools_dir`: 覆盖动态工具目录
- `skills_dir`: 覆盖 skills 根目录
- `default_agent_system`: 默认 agent system
- `default_agent_name`: 默认根 agent 名称
- `action_window_steps`: 动作窗口大小
- `thinking_interval`: thinking 插入间隔
- `fresh_enabled` / `fresh_interval_sec`: 定时 fresh 参数
- `direct_tools`: 是否启用进程内 direct tools

## 5. 基本运行

```python
from infiagent import infiagent

agent = infiagent(
    user_data_root="/abs/path/to/my_root",
    default_agent_system="OpenCowork",
    default_agent_name="alpha_agent",
)

result = agent.run(
    "请分析这个目录并给出重构建议",
    task_id="/abs/path/to/tasks/project_a",
)
```

关键点：
- `task_id` 必填
- `run()` 会先按 `start.py` 语义清理/归档必要状态
- 然后注册本次用户输入并在当前进程运行 executor

如果要明确重开任务：
```python
agent.run(
    "重新开始这个任务",
    task_id="/abs/path/to/tasks/project_a",
    force_new=True,
)
```

## 6. Task 管理接口

### 6.1 `fresh`

```python
agent.fresh(
    task_id="/abs/path/to/tasks/project_a",
    reason="reload runtime config",
)
```

行为：
- task 正在运行：发定向 fresh 请求
- task 未运行：重载配置后后台 resume

### 6.2 `add_message`

```python
agent.add_message(
    "补充需求：保留已有结果，只做增量修改。",
    task_id="/abs/path/to/tasks/project_a",
    source="user",
    resume_if_needed=True,
)
```

行为：
- 追加到同一 task 的 `current.instructions`
- 不会当成新任务
- 运行中的 task 会在下一轮上下文重建时看到它
- 未运行 task 可按需后台恢复

### 6.3 `start_background_task`

```python
agent.start_background_task(
    task_id="/abs/path/to/tasks/sub_task",
    user_input="后台整理日志并生成总结",
    force_new=True,
)
```

行为：
- 启动新的后台 Python 进程运行 `start.py`
- 日志写到 `<user_data_root>/runtime/launched_tasks`

### 6.4 `task_share_context_path`

```python
agent.task_share_context_path(task_id="/abs/path/to/tasks/project_a")
```

返回：
- `share_context_path`
- `stack_path`

### 6.5 `list_task_ids`

```python
agent.list_task_ids()
agent.list_task_ids(only_running=True)
```

返回当前 `user_data_root` 下已知 task 列表。

### 6.6 `task_snapshot`

```python
snapshot = agent.task_snapshot(task_id="/abs/path/to/tasks/project_a")
```

返回：
- `running`
- `share_context_path`
- `stack_path`
- `instruction_count`
- `latest_instruction`
- `history_count`
- `last_updated`
- `latest_thinking`
- `latest_thinking_at`
- `last_final_output`
- `last_final_output_at`

这个接口适合外部应用做面板和轻量 watchdog。

### 6.7 `reset_task`

```python
agent.reset_task(
    task_id="/abs/path/to/tasks/project_a",
    reason="clear broken loop",
    preserve_history=True,
    kill_background_processes=True,
)
```

行为：
- 清空当前 `current`
- 清空 stack
- 可选归档到 history
- 可选尝试终止当前后台进程
- 删除该 task 对应的 `*_actions.json`

## 7. 运行时自省接口

### 7.1 `describe_runtime`

```python
runtime = agent.describe_runtime()
print(runtime["user_data_root"])
print(runtime["agent_library_dir"])
print(runtime["tools_dir"])
print(runtime["skills_dir"])
```

关键字段：
- `user_data_root`
- `config_dir`
- `llm_config_path`
- `agent_library_dir`
- `tools_dir`
- `skills_dir`
- `conversations_dir`
- `logs_dir`
- `runtime_dir`

### 7.2 `list_agent_systems`

```python
systems = agent.list_agent_systems()
for item in systems["agent_systems"]:
    print(item["name"], item["path"])
```

适合外部调度应用决定使用哪个 agent system。

## 8. Tool Hooks

SDK 现在支持对任意工具调用注册前置/后置 hook。

适用场景：
- 记录工具审计日志
- 只监听 `final_output`
- 监听某些自定义工具的参数或结果
- 在工具调用前后触发外部状态同步

示例：
```python
from infiagent import infiagent

agent = infiagent(
    user_data_root="/abs/path/to/my_root",
    tool_hooks=[
        {
            "name": "final-output-audit",
            "callback": "/abs/path/to/hooks.py:on_tool_event",
            "when": "after",
            "tool_names": ["final_output"],
            "include_arguments": True,
            "include_result": True,
            "argument_filters": ["status"],
            "result_filters": ["output", "status"],
        }
    ],
)
```

hook 字段：
- `name`
- `callback`: `module:function` 或 `/abs/path.py:function`
- `when`: `before` / `after` / `both`
- `tool_names`
- `include_arguments`
- `include_result`
- `argument_filters`
- `result_filters`

callback 接收的 payload 至少包含：
- `hook_name`
- `when`
- `tool_name`
- `task_id`
- `agent_id`
- `agent_name`
- `agent_level`

注意：
- hook 是 runtime 级能力，不是 CheapClaw 专属能力
- 如果系统存在子 agent，直接监听所有 `final_output` 可能会误触发；应结合 `agent_level == 0` 或更严格的工具/参数过滤自行约束
- CheapClaw 当前默认不依赖 hook 更新 panel，而是依赖 task reconcile

## 9. 异步接口

这些接口都有 async 包装：
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

示例：
```python
result = await agent.add_message_async(
    "补充一条要求",
    task_id="/abs/path/to/tasks/project_a",
)
```

## 10. 面向独立应用的建议

如果你要在独立项目里写 CheapClaw 这类应用，优先只依赖公开 SDK：
- `infiagent(...)`
- `describe_runtime()`
- `list_agent_systems()`
- `run()`
- `start_background_task()`
- `add_message()`
- `fresh()`
- `task_snapshot()`
- `reset_task()`
- `tool_hooks`

然后把应用层自己的：
- panel store
- social gateway
- scheduler
- watchdog
- supervisor service
- custom tools

都放在外部项目里。

## 11. 当前验证

已补充测试：
- [tests/test_sdk_runtime_paths.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/tests/test_sdk_runtime_paths.py)
- [tests/test_cheapclaw_service.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/tests/test_cheapclaw_service.py)

覆盖：
1. `user_data_root` 切换后路径是否统一
2. SDK 和原始 task 工具是否共享同一根目录语义
3. `agent_library` / `tools_library` 在自定义根目录下是否仍然可加载
4. 不同 SDK 实例是否互不串用
5. 后台任务日志是否落到 `<user_data_root>/runtime/launched_tasks`
6. CheapClaw 是否可以用公开 SDK 和动态工具目录独立运行
7. `task_snapshot()` 是否能从 `share_context.history` 回填完成态
8. tool hook 是否能在 `final_output` 后触发 callback
