#!/usr/bin/env python3
from datetime import datetime
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from infiagent import infiagent
from tool_runtime_helpers import bind_messages_to_task
from tool_server_lite.tools.file_tools import BaseTool


class CheapClawAddTaskMessageTool(BaseTool):
    name = "cheapclaw_add_task_message"

    def execute(self, task_id, parameters):
        target_task_id = str(Path(parameters.get("task_id") or "").expanduser().resolve())
        message = str(parameters.get("message") or "").strip()
        if not target_task_id or not message:
            return {"status": "error", "output": "", "error": "task_id and message are required"}

        user_root = str(Path(__import__("os").environ.get("MLA_USER_DATA_ROOT", "~/mla_v3")).expanduser().resolve())
        tools_root = str(Path(__file__).resolve().parents[1])
        agent = infiagent(user_data_root=user_root, tools_dir=tools_root)
        timestamped = f"{message}\n\n[message_appended_at {datetime.now().astimezone().isoformat(timespec='seconds')}]"
        result = agent.add_message(
            timestamped,
            task_id=target_task_id,
            source=str(parameters.get("source") or "agent"),
            resume_if_needed=bool(parameters.get("resume_if_needed", False)),
            agent_system=str(parameters.get("agent_system") or "") or None,
        )
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        source_message_ids = parameters.get("source_message_ids") or []
        if result.get("status") == "success" and channel and conversation_id and isinstance(source_message_ids, list) and source_message_ids:
            bind_messages_to_task(channel, conversation_id, target_task_id, source_message_ids, note="message appended to existing task")
        return result
