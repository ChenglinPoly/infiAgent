# CheapClaw Guide

适用实现：
- 服务入口：[apps/cheapclaw/cheapclaw_service.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/apps/cheapclaw/cheapclaw_service.py)
- 面板辅助：[apps/cheapclaw/tool_runtime_helpers.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/apps/cheapclaw/tool_runtime_helpers.py)
- Supervisor 提示词：[apps/cheapclaw/assets/agent_library/CheapClawSupervisor/general_prompts.yaml](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/apps/cheapclaw/assets/agent_library/CheapClawSupervisor/general_prompts.yaml)
- Worker 提示词：[apps/cheapclaw/assets/agent_library/CheapClawWorkerGeneral/general_prompts.yaml](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/apps/cheapclaw/assets/agent_library/CheapClawWorkerGeneral/general_prompts.yaml)

## 1. 定位

CheapClaw 是基于 `infiagent` SDK 的独立应用层。

职责边界：
- CheapClaw 负责：社交消息入口、消息面板、消息与 task 绑定、主调度 agent、watchdog、计划任务、outbox 发送
- MLA/InfiAgent 负责：task runtime、agent system 装载、tool 调用、share/stack/history 持久化、fresh/resume/add_message

这意味着：
- CheapClaw 不需要嵌进框架内核
- CheapClaw 可以单独复制到另一个项目中使用
- 框架只需要暴露 SDK 和动态 `tools_dir`

## 2. 目录和状态

CheapClaw 运行在 `<user_data_root>/cheapclaw` 下，核心文件：

- `panel/panel.json`
- `panel/backups/*.json`
- `plans.json`
- `channels/<channel>/<conversation>/social_history.jsonl`
- `outbox/*.json`
- `task_skills/<task_slug>/...`
- `runtime/state.json`
- `tasks/<channel>/<conversation>/<task_slug>/...`

`panel.json` 是调度单一事实来源。conversation 记录至少包含：
- 渠道
- 联系人/群
- 最近消息摘要
- pending_events
- linked_tasks
- `message_task_bindings`
- `message_history_path`
- `share_context_path`
- `stack_path`
- `log_path`
- 最新 `thinking / final_output`
- watchdog 观测结果

## 3. 主 agent 决策语义

Supervisor 不自己做业务任务，只做路由和派工。

处理 dirty conversation 时必须按顺序判断：
1. 这次触发来自哪里：新消息、plan_tick、watchdog_tick、task_completed、系统状态变更
2. 是否可直接回复，无需 worker
3. 如果需要 worker，属于哪一类：
   - `append_to_running_task`
   - `continue_existing_task`
   - `fork_new_task`
   - `brand_new_task`
4. 把这次触发的 `message_id` 绑定到选定的 `task_id`
5. 发送用户回执
6. 更新面板，清理对应 dirty / pending_events

一个 `task_id` 可以绑定多条用户消息。
这表示“同一个工作在持续演进”，而不是每来一句话都要起新 task。

## 4. CheapClaw 自定义工具

Supervisor/Worker 通过动态 `tools_library` 使用 CheapClaw 工具，主要包括：
- `cheapclaw_read_panel`
- `cheapclaw_update_panel`
- `cheapclaw_read_social_history`
- `cheapclaw_send_message`
- `cheapclaw_send_file`
- `cheapclaw_start_task`
- `cheapclaw_add_task_message`
- `cheapclaw_get_task_status`
- `cheapclaw_list_agent_systems`
- `cheapclaw_schedule_plan`
- `cheapclaw_cancel_plan`
- `cheapclaw_reset_task`
- `cheapclaw_generate_task_id`
- `cheapclaw_list_conversation_tasks`
- `cheapclaw_list_global_skills`
- `cheapclaw_reveal_skills`

这些工具不再写进框架源码，也不靠 `template_assets.py` 生成。
它们就是真实存在的 Python 文件，位于：
- [apps/cheapclaw/tools_library](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/apps/cheapclaw/tools_library)

## 5. skills overlay 机制

CheapClaw 支持“主技能库 + task overlay skills”。

规则：
- 全局主技能库仍默认来自 SDK runtime 的 `skills_dir`
- Supervisor 可以用 `cheapclaw_reveal_skills` 把某些 skills 暴露给某个 task
- 每个 task 的 overlay skills 存在 `task_skills/<task_slug>/`
- Worker 只默认看到 overlay 中允许的 skills
- 如果 worker 发现技能不够，可以：
  1. `cheapclaw_list_global_skills`
  2. `cheapclaw_reveal_skills`
  3. `fresh` 当前 task

## 6. 渠道接入

### Telegram
当前实现：轮询 `getUpdates`。

需要：
- `bot_token`
- 可选 `allowed_chats`

群聊规则：
- 只处理提到了 bot 的消息
- 私聊默认直接接收
- 识别 mention 时会同时检查：
  - 文本里的 `@bot_username`
  - Telegram `entities/caption_entities`
  - `text_mention`
  - 回复 bot 消息
- 如果群里仍然收不到 `@bot` 消息，优先检查 BotFather 的隐私模式是否已关闭：`/setprivacy -> Disable`

### Feishu
当前实现：webhook 接收 `im.message.receive_v1`，发送走开放平台消息接口。

需要：
- `app_id`
- `app_secret`
- `verify_token`
- 可选 `encrypt_key`

### WhatsApp Cloud API
当前实现：webhook 接收 + Graph API 发送文本。

需要：
- `access_token`
- `phone_number_id`
- `verify_token`
- 可选 `api_version`

## 7. 运行命令

初始化：
```bash
python apps/cheapclaw/cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --bootstrap
```

查看面板：
```bash
python apps/cheapclaw/cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --show-panel
```

单次执行：
```bash
python apps/cheapclaw/cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --run-once
```

常驻轮询：
```bash
python apps/cheapclaw/cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --run-loop
```

Webhook：
```bash
python apps/cheapclaw/cheapclaw_service.py \
  --user-data-root /abs/path/to/user_root \
  --llm-config-path /abs/path/to/llm_config.yaml \
  --serve-webhooks --host 0.0.0.0 --port 8787
```

看板：
- 启动 HTTP 服务后，浏览器打开 `http://127.0.0.1:8787/dashboard`
- 面板 JSON API：`http://127.0.0.1:8787/api/panel`

## 8. Panel 同步与 watchdog

CheapClaw 不默认依赖 `final_output` hook 更新 panel。

当前同步机制：
1. 每个 cycle 读取 task snapshot
2. `task_snapshot()` 同时读取：
   - `share_context.current.agents_status`
   - `share_context.history[*].agents_status`
   - 进程级 running 状态
3. 把 `last_thinking / last_final_output / pid_alive / share_context_path / stack_path / log_path` 回填到 panel
4. 若发现 task 新完成，会向 conversation 添加 `task_completed` 事件并重新标记 `dirty`

结果：
- 即使 worker 结束后 `current` 被清空，只要 `history` 中有完成态，panel 仍能回填
- CheapClaw 不只看 share 文件，也看进程级运行状态
- watchdog 主要负责“可疑状态观测”，不是唯一的 panel 同步来源

默认 watchdog 周期：
- `10800` 秒，也就是 3 小时

## 9. 外移到独立项目

如果要把 CheapClaw 放到一个独立项目：
1. 安装你的 MLA 包
2. 复制 `cheapclaw/` 文件夹
3. 保留以下内容：
   - `cheapclaw_service.py`
   - `tool_runtime_helpers.py`
   - `assets/`
   - `tools_library/`
   - `skills/`
4. 用独立项目自己的 `user_data_root` 运行

当前实现已经把导入方式改成“本目录自举”，不会依赖仓库内 `apps.cheapclaw` 包路径。

## 10. 验证

当前已覆盖：
- 面板初始化
- 社交消息入面板
- `message_id -> task_id` 绑定
- 动态 `tools_library` 注册
- skills overlay
- 后台 task 启动
- `add_message` 时间戳追加
- `reset_task`
- 独立目录导入 `cheapclaw_service.py`
- 独立目录导入 CheapClaw custom tool

对应测试文件：
- [tests/test_cheapclaw_service.py](/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/tests/test_cheapclaw_service.py)
