# CheapClaw Implementation Plan

本文件是 CheapClaw 的实现前设计文档。

目标：
- 基于当前 `infiagent` SDK 和 task runtime，构建一个独立的社交消息编排服务
- 主 agent 只做调度，不做具体业务任务
- 主服务负责事件接入、面板状态、串行触发、后台任务守护、计划任务和容错

约束：
- 尽量把 CheapClaw 实现为一个独立应用，不强耦合当前框架目录
- 优先复用现有 SDK、task runtime、skills、custom tools
- 只有在必须时才做小范围框架改动，如 skills 遮掩

## 1. 外部参考与结论

参考 OpenClaw 官方文档，确认以下模式可借鉴：

- 单一长生命周期 Gateway 统一接入多个消息渠道
- 群消息默认按 mention 触发，而不是吃掉所有群消息
- group / DM 使用不同 session 键
- 多渠道共用统一事件层和状态层

参考链接：
- [OpenClaw Gateway Architecture](https://docs.openclaw.ai/architecture)
- [OpenClaw Integrations](https://docs.openclaw.ai/)
- [OpenClaw Groups](https://docs.openclaw.ai/channels/groups)
- [OpenClaw Group Messages](https://docs.openclaw.ai/group-messages)
- [OpenClaw Feishu](https://docs.openclaw.ai/channels/feishu)

从这些资料推导出的结论：
- CheapClaw 的核心不应是“再造一个 agent”
- 应该是“消息网关 + 面板状态机 + 主服务 + 主 agent + worker tasks”
- 主 agent 不常驻，常驻的是主服务

## 2. 当前仓库已有能力

当前仓库已经具备的关键能力：

1. 基于 `task_id` 启动和恢复任务
2. 判断某个 `task_id` 是否正在运行
3. 对已有任务 `fresh`
4. 对已有任务 `add_message`
5. 启动后台任务
6. 获取 `share_context` / `stack` 路径
7. SDK 已支持：
   - `run`
   - `fresh`
   - `add_message`
   - `start_background_task`
   - `task_share_context_path`
   - `list_task_ids`
8. `user_data_root` 已统一控制 `conversation/share/stack/runtime`
9. 自定义工具可以放在 `tools_library` 中，不必改框架 builtin registry
10. `skills_dir` 可通过 SDK / runtime env 指向任意目录

关键位置：
- [infiagent/sdk.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/infiagent/sdk.py)
- [utils/task_runtime.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/utils/task_runtime.py)
- [utils/runtime_control.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/utils/runtime_control.py)
- [core/hierarchy_manager.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/core/hierarchy_manager.py)
- [tool_server_lite/registry.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/tool_server_lite/registry.py)
- [utils/skill_loader.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/utils/skill_loader.py)
- [tool_server_lite/tools/skill_tools.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/tool_server_lite/tools/skill_tools.py)

## 3. 当前仓库缺失能力

CheapClaw 还缺这些核心模块：

1. 多社交渠道 gateway 层
2. 消息面板状态层
3. 主服务调度器
4. 主 agent 专用工具集
5. 计划任务 / watchdog 层
6. `reset_task` 类工具
7. worker task 完成后的统一回流机制

## 4. 顶层架构

建议拆成 4 层：

1. `Channel Gateway`
2. `CheapClaw Service`
3. `Main Agent`
4. `Worker Tasks`

### 4.1 Channel Gateway

职责：
- 接入 WhatsApp / Telegram / 飞书
- 统一事件格式
- 群聊 mention 过滤
- 消息发送
- 附件下载与发送
- 去重

不做：
- 任务理解
- task 路由决策
- agent 调度

### 4.2 CheapClaw Service

职责：
- 接收 gateway 事件
- 更新消息面板
- 保证主 agent 串行运行
- 触发主 agent
- 接收 worker task 完成事件
- 定时巡检和 watchdog
- 守护进程自恢复

这是系统核心。

### 4.3 Main Agent

主 agent 是调度者，不是执行者。

只负责：
- 理解新消息
- 判断直接回复 / 新建任务 / 续任务 / 追加消息 / resume / fresh / reset
- 发送回执
- 更新消息面板

不负责：
- 直接长时间做任务
- 直接产出业务文件
- 长期占用运行资源

### 4.4 Worker Tasks

Worker task 继续复用当前 `task_id` 体系：
- 独立 workspace
- 独立 `share_context`
- 独立 `stack`
- 独立 `actions`
- 可选择不同 `agent_system`
- 可选择不同 `skills_dir`

## 5. 消息面板状态层

消息面板应成为 CheapClaw 的单一事实来源。

建议位置：
- `<cheapclaw_root>/panel/panel.json`
- `<cheapclaw_root>/panel/backups/*.json`

其中 `cheapclaw_root` 建议为：
- `<user_data_root>/cheapclaw`

### 5.1 面板必须包含的字段

你本轮补充后的最终字段，建议如下：

```json
{
  "version": 1,
  "channels": {
    "telegram": {
      "conversations": {
        "group_123": {
          "channel": "telegram",
          "conversation_id": "group_123",
          "conversation_type": "group",
          "display_name": "ML Group",
          "trigger_policy": {
            "require_mention": true
          },
          "message_history_path": "/abs/path/to/social_history.jsonl",
          "messages": [],
          "linked_tasks": [
            {
              "task_id": "/abs/path/to/task",
              "agent_system": "OpenCowork",
              "agent_name": "alpha_agent",
              "status": "running",
              "share_context_path": "/abs/path/to/share_context.json",
              "stack_path": "/abs/path/to/stack.json",
              "log_path": "/abs/path/to/runtime/launched_tasks/xxx.log",
              "skills_dir": "/abs/path/to/task_skills",
              "last_thinking": "",
              "last_thinking_at": "",
              "last_final_output": "",
              "last_final_output_at": "",
              "last_action_at": "",
              "last_log_at": "",
              "fresh_retry_count": 0,
              "last_watchdog_note": ""
            }
          ],
          "pending_events": [],
          "dirty": false,
          "last_snapshot_path": "/abs/path/to/panel/backups/xxx.json",
          "updated_at": ""
        }
      }
    }
  },
  "service_state": {
    "main_agent_task_id": "/abs/path/to/cheapclaw/supervisor_task",
    "main_agent_running": false,
    "main_agent_run_id": "",
    "main_agent_last_started_at": "",
    "main_agent_last_finished_at": "",
    "main_agent_dirty": false,
    "watchdog_last_run_at": "",
    "last_backup_path": ""
  }
}
```

### 5.2 还需要的派生字段

为了减少主 agent 重复计算，建议面板还维护这些派生字段：

- `running_task_count`
- `has_stale_running_tasks`
- `latest_user_message_at`
- `latest_bot_message_at`
- `unread_event_count`
- `last_reply_summary`
- `conversation_tags`

这些不是事实字段，但有利于主 agent 快速判断。

### 5.3 share 文件地址

你补的这个字段必须保留，而且不止一个：

- `share_context_path`
- `stack_path`
- `message_history_path`
- `log_path`

这样主 agent 不需要自己推导文件位置。

## 6. 主 agent 的动态输入策略

### 6.1 消息面板内容不要固化进 system prompt

结论：
- 不建议把完整消息面板直接固化到 system prompt
- 应把“面板 schema / 角色边界 / 决策原则”固化进 system prompt
- 动态面板内容应在每次触发时作为任务输入的一部分提供

原因：

1. 面板变化频繁
2. system prompt 过大容易污染所有轮次
3. 面板是状态数据，不是长期规则
4. 未来需要按 dirty conversations 局部注入，而不是全量注入

### 6.2 推荐注入方式

主 agent 每次触发时，任务输入中包含：

1. 本次触发原因
2. dirty conversation 列表
3. 每个 conversation 的摘要
4. 面板路径
5. 若需要，最近一版 snapshot 路径

建议格式：

```text
触发类型: social_message_update
当前时区: Asia/Shanghai
面板路径: /abs/path/to/panel.json
本次 dirty conversations:
- telegram/group_123
- feishu/ou_xxx

请先读取面板，再对每个 dirty conversation 判断：
1. 直接聊天回复
2. 在已有 task_id 上追加消息
3. 恢复已有 task
4. 在已有 task_id 上新建连续任务
5. 新建 task_id
6. 仅回执，不启动任务
```

## 7. 主 agent 专用工具

主 agent 需要专用工具，但这些工具不必都加到框架 builtin。
绝大多数可以做成 `tools_library` 自定义工具，然后仅暴露给 CheapClaw 专用 agent system。

建议工具集合：

### 7.1 必需工具

1. `cheapclaw_read_panel`
- 读消息面板
- 支持：
  - `only_dirty`
  - `channel`
  - `conversation_id`

2. `cheapclaw_update_panel`
- 更新 conversation 状态
- 能做：
  - 标记 dirty / clear dirty
  - 写 `last_thinking`
  - 写 `last_final_output`
  - 绑定 task
  - 更新 task status
  - 写 `share_context_path`
  - 写 `log_path`

3. `cheapclaw_read_social_history`
- 读某个 conversation 的社交历史
- 默认最近 30 或 50 条
- 支持：
  - `limit`
  - `only_mentions_to_bot`
  - `from_message_id`
  - `before_timestamp`
  - `after_timestamp`

4. `cheapclaw_send_message`
- 发送消息到社交平台
- 参数：
  - `channel`
  - `conversation_id`
  - `message`
  - `attachments`

5. `cheapclaw_start_task`
- 主 agent 专用任务启动工具
- 包装现有 `start_background_task`
- 但要把 conversation 绑定一起做掉，防止遗漏

6. `cheapclaw_add_task_message`
- 包装现有 `add_message`
- 自动附加当前时区时间

7. `cheapclaw_get_task_status`
- 聚合：
  - running
  - share_context_path
  - stack_path
  - log_path
  - latest_thinking
  - latest_action_at
  - latest_log_at

8. `cheapclaw_list_agent_systems`
- 查询当前可用 agent_system 列表

9. `cheapclaw_schedule_plan`
- 设置计划任务

10. `cheapclaw_cancel_plan`
- 取消计划任务

11. `cheapclaw_reset_task`
- 重置 task 状态

### 7.2 可选工具

1. `cheapclaw_generate_task_id`
- 按规则生成新 task_id

2. `cheapclaw_list_conversation_tasks`
- 查询某个 conversation 已关联 task

3. `cheapclaw_reveal_skills`
- 为某个 task 暴露新的 skill 到 task 专属 skills overlay

4. `cheapclaw_list_global_skills`
- 看全局 skill 库，供主 agent 选择允许给某个 task 的 skills

## 8. `start_background_task` 是否够用

现有工具已经有基础：
- [tool_server_lite/tools/task_tools.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/tool_server_lite/tools/task_tools.py)

但参数不够贴合 CheapClaw 业务。

现有问题：

1. 不带 `channel / conversation_id / display_name`
2. 不会自动绑定 panel 中的 linked task
3. 不会自动写 `share_context_path / log_path`
4. 不会自动生成规范 task_id
5. 不会附带 task 专属 `skills_dir`

结论：
- 不直接给主 agent 用 `start_background_task`
- 应新增 `cheapclaw_start_task`
- 这个工具内部可以复用现有 SDK `start_background_task`

## 9. task_id 设计

### 9.1 不建议把原始群名直接写入路径

建议路径：

```text
<cheapclaw_root>/tasks/<channel>/<conversation_key>/<task_slug>
```

例如：

```text
/root/cheapclaw/tasks/telegram/group_123/report_revision
/root/cheapclaw/tasks/feishu/ou_xxx/slides_update
```

### 9.2 conversation_key 与 display_name 分离

建议：
- `conversation_key` 用稳定 ID
- `display_name` 只放面板里展示

否则群改名会导致路径漂移。

### 9.3 连续任务与新任务的判断

主 agent 在决定任务时，不只是判断“新 task 还是旧 task 恢复”。

应区分为 3 类：

1. `append_to_running_task`
- 同一工作正在进行
- 只需给运行中的 task 追加消息

2. `continue_existing_task`
- 同一工作，但当前未运行
- 恢复已有 task_id

3. `fork_new_task`
- 与历史 task 有关，但应独立新建 task_id
- 例如：
  - 不同 deliverable
  - 不同 agent_system
  - 风险隔离
  - 长实验分支

因此主 agent 的决策集合应为：

- 直接聊天回复
- 在已有运行中 task 上追加消息
- 恢复已有 task
- 在已有工作上下文旁边新建一个新 task_id
- 全新 task_id
- 仅回执

## 10. 主 agent 串行运行

你提到“主 agent 只有一个，为什么会有同一？”

这里的“同一主 agent 同时只有一个 run”指的是：

- 虽然主 agent 的 task_id 固定只有一个
- 但可能会被多个事件同时触发
  - 新社交消息
  - worker task 完成
  - watchdog tick
  - 计划任务 tick

如果不加串行锁，主服务可能在前一个主 agent run 还没结束时又拉起一个新的同 task_id run。

因此必须有：

- `main_agent_running` 锁
- `main_agent_dirty` 合并标记

策略：
- 如果主 agent 正在运行，新事件只写面板并标 dirty
- 当前 run 结束后，如果 dirty 仍为 true，立刻再跑一次

## 11. 群历史消息读取

这里不应该把全量历史都塞给主 agent。

建议工具：
- `cheapclaw_read_social_history`

默认策略：
- 默认最近 30 条
- 群聊默认只取与 bot 相关的 30 条
- 可配置 `limit=50`

支持参数：

- `limit`
- `only_mentions_to_bot`
- `include_bot_replies`
- `before_timestamp`
- `after_timestamp`
- `from_message_id`
- `to_message_id`

这比让主 agent 直接扫全 JSON 历史更稳。

## 12. task 专属 skills 库

### 12.1 可以做到，而且第一版不必改框架

现有框架已经支持：
- 通过 SDK / env 指定 `skills_dir`
- `SkillLoader` 从当前 `skills_dir` 扫描 `<available_skills>`
- `load_skill` 从当前 `skills_dir` 复制 skill 到 task workspace

因此可以做：

1. 保留全局 skill 主库，例如 `~/.agent/skills`
2. 为每个 task 创建一个 overlay skills 目录，例如：

```text
<cheapclaw_root>/task_skills/<task_hash>/
```

3. 这个 overlay 初始只包含被主 agent 允许的 skills
4. 启动 task 时，把 `skills_dir` 指向这个 overlay

这样：
- 子 agent 在 prompt 中只会看到被允许的 skills
- `load_skill` 也只会从该 overlay 中加载

### 12.2 “遮掩再揭开”怎么做

如果你希望子 agent 知道还有更多 skill，但默认被遮住，不建议直接让它浏览全局根目录。

更稳的方案：

新增两个 CheapClaw 工具：

1. `cheapclaw_list_global_skills`
- 查看主库中的全部 skill 元数据

2. `cheapclaw_reveal_skills`
- 把指定 skill 从全局库复制或软链到该 task 的 overlay 中

这样实现“遮掩再揭开”，而不需要放开对全局目录的任意探索。

### 12.3 是否需要框架改动

第一版不需要。

因为：
- `skills_dir` 已可通过 SDK 配置
- 每个 worker task 启动时可传不同 `skills_dir`

只有当你要求：
- 同一个正在运行的 task 进程里，动态切换 `skills_dir`
- 并让 `<available_skills>` 自动刷新

这时才需要配合 `fresh` 或扩展 runtime 接口。

## 13. Watchdog 策略

### 13.1 不做“规则直接执行处置”

你这轮修正是合理的：
- watchdog 不应自己直接决定 `fresh` / `reset`
- watchdog 负责提供观察结果和风险信号
- 主 agent 使用 watchdog skill / 工具进行探索，再决定怎么处置

这是比硬编码阈值更稳的策略。

### 13.2 Watchdog 的输出

建议 watchdog 每次 tick 更新面板中的观测字段：

- `running`
- `pid_alive`
- `last_thinking_at`
- `last_action_at`
- `last_log_at`
- `last_panel_update_at`
- `watchdog_observation`
- `watchdog_suspected_state`

其中 `watchdog_suspected_state` 不是最终裁决，只是提示：

- `healthy`
- `quiet_but_alive`
- `possibly_stalled`
- `process_dead`
- `loop_suspected`

### 13.3 主 agent 如何使用 watchdog

建议把 watchdog 逻辑封装为 skill 或专用工具：
- 定时触发时，主 agent 收到一个 `watchdog_tick`
- 读取面板上的运行观测
- 若需要，再调用：
  - task 状态读取工具
  - 日志路径工具
  - `file_read` 看日志尾部
  - `task_share_context_path`
  - `fresh`
  - `reset_task`

### 13.4 thinking 停滞不要直接等同卡死

这是重要原则。

不能写死：
- 1 小时没更新 thinking 就等于卡死

因为可能：
- 长时间跑实验
- 阻塞型工具在工作
- 外部命令无输出但正常

因此：
- watchdog 只更新观测数据和怀疑等级
- 决策留给主 agent

## 14. task 状态重置

当前框架没有正式的 `reset_task` 工具。

第一版必须补。

建议语义：

```json
{
  "task_id": "/abs/path/to/task",
  "preserve_history": true,
  "kill_background_processes": true,
  "reason": "watchdog/manual/main-agent-decision"
}
```

行为：
- 清空 current
- 清空 stack
- 可选保留 history
- 可选终止当前 task 关联后台命令
- 写 reset 元数据到 share_context 或 panel

## 15. 主 agent 专用 agent_system

主 agent 必须单独写一个 agent system。

建议：
- `CheapClawSupervisor`

特点：
- 只给 orchestration 工具
- 不给或默认不暴露：
  - `human_in_loop`
  - 业务重工具
  - 可能阻塞的命令工具

### 15.1 主 agent 不需要等待长工具

主 agent 应遵循：
- 立即派工
- 立即回执
- 由 worker task 继续做任务

因此主 agent 只应调用：
- 面板工具
- 消息发送工具
- 启任务工具
- 续任务工具
- 计划工具
- task 状态工具

### 15.2 worker agent system 也应单独配置

CheapClaw 后台 worker 至少需要独立 agent systems：

1. `CheapClawSupervisor`
2. `CheapClawWorkerGeneral`
3. 后续按需求扩展：
   - `CheapClawResearchWorker`
   - `CheapClawOpsWorker`
   - `CheapClawWriterWorker`

## 16. 可以放在 `tools_library` 吗

结论：
- 可以，而且应该优先这样做

现有框架支持：
- 从 `tools_library/<tool_name>/<tool_file>.py` 加载自定义工具

因此 CheapClaw 大多数新工具：
- 不需要加进框架 builtin
- 直接实现为自定义工具即可

只需要：
- 把工具放到 CheapClaw 自己的 `tools_library`
- 在 CheapClaw 专用 agent_system 里配置暴露哪些工具

## 17. 是否能基于当前 SDK 独立写出 CheapClaw

结论：
- 可以，大部分能力已经足够
- CheapClaw 应尽量作为“基于 SDK 的独立应用”

已经足够的部分：
- 启动 task
- 追加消息
- fresh / resume
- 指定 `agent_system`
- 指定 `skills_dir`
- 指定 `user_data_root`

可能需要的小范围框架改动：

1. 更方便读取和聚合 task 运行时摘要
2. 更标准地获取 `latest_thinking / final_output / log_path`
3. 增加 `reset_task`
4. 如有需要，开放“上下文重建/状态摘要”接口供 CheapClaw 直接调用

但第一版不需要大改 framework。

## 18. 主服务应该放在哪里

最终目标：
- CheapClaw 可以在 `pip install mla-agent` 后，作为独立应用运行

所以开发期也建议按独立应用组织。

第一版建议在当前仓库先放一个单独入口：

- `apps/cheapclaw/cheapclaw_service.py`

如果你坚持单文件实现，第一版可以这样做。

但这只是入口单文件，不表示所有逻辑都永远不拆。

建议后续允许拆出：
- `panel_store.py`
- `gateway_adapters.py`
- `scheduler.py`
- `main_agent_runner.py`

## 19. 实现阶段计划

### Phase 1: 设计与状态层

产出：
- 消息面板 schema
- plans schema
- task 绑定规则
- CheapClaw root 布局

实现：
- `apps/cheapclaw/cheapclaw_service.py`
- 先只实现 panel 读写、备份、锁

### Phase 2: 主 agent 专用工具

实现：
- `cheapclaw_read_panel`
- `cheapclaw_update_panel`
- `cheapclaw_read_social_history`
- `cheapclaw_send_message`
- `cheapclaw_start_task`
- `cheapclaw_add_task_message`
- `cheapclaw_get_task_status`
- `cheapclaw_list_agent_systems`
- `cheapclaw_schedule_plan`
- `cheapclaw_cancel_plan`
- `cheapclaw_reset_task`

这些优先做成自定义工具。

### Phase 3: 主 agent system

实现：
- `CheapClawSupervisor` agent_system
- supervisor 专用 prompt
- 仅暴露 orchestration 工具

### Phase 4: 主服务触发器

实现：
- dirty conversation 合并
- 主 agent 串行锁
- 事件到主 agent 的触发
- worker 完成回流触发

### Phase 5: task-specific skills

实现：
- overlay skills 目录
- 启动 task 时传 `skills_dir`
- `cheapclaw_list_global_skills`
- `cheapclaw_reveal_skills`

### Phase 6: watchdog 与 scheduler

实现：
- main-agent tick
- task tick
- watchdog 观测写入 panel
- 主 agent 使用 watchdog skill 判断是否处置

### Phase 7: 渠道接入

建议先做顺序：

1. Telegram
2. 飞书
3. WhatsApp

原因：
- Telegram 和飞书开发/调试成本更低
- WhatsApp 风险更高，登录会话更脆弱

## 20. 当前明确采纳的设计决策

根据你本轮意见，以下内容确定采纳：

1. 面板中增加 `share_context_path`
2. task 绑定工具要能一起写 panel，避免遗漏
3. 群历史读取支持截断，默认只读最近有限条
4. 主 agent 决定是：
   - 旧 task 追加
   - 旧 task 恢复
   - 旧工作分叉出新 task
   - 全新 task
5. 追加消息时应附带当前时区时间
6. watchdog 不直接硬编码处置，而是提供观测给主 agent
7. 主 agent 与 worker 使用单独 agent_system
8. 新工具优先做在 `tools_library`
9. CheapClaw 优先作为基于 SDK 的独立应用

## 21. 当前仍需确认的问题

这些问题不阻碍 Phase 1 开始，但在接入渠道前要定：

1. CheapClaw 首发先接哪个渠道
2. 附件发送是否为 MVP 必须能力
3. 是否允许主 agent 自动 `reset_task`
4. 任务命名中的 `task_slug` 是否需要中文保留
5. panel 是否采用单文件 JSON 还是 conversation 分片 JSONL

当前建议：
- MVP 用单文件 `panel.json` + backups
- 后续量大再拆分片存储

## 22. 推荐的下一步

后续实现顺序建议严格按这个文档推进：

1. 先做 panel store 和 CheapClaw root
2. 再做主 agent 专用工具
3. 再做 `CheapClawSupervisor` agent_system
4. 再做主服务触发串行逻辑
5. 最后才接具体社交渠道

不要反过来先接消息平台，否则会在状态层未定型时把问题放大。
