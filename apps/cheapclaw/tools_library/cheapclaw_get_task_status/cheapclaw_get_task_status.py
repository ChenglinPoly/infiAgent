#!/usr/bin/env python3
from pathlib import Path
from infiagent import infiagent
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import list_conversation_tasks, load_panel
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawGetTaskStatusTool(BaseTool):
    name = "cheapclaw_get_task_status"
    def execute(self, task_id, parameters):
        target_task_id = str(Path(parameters.get("task_id") or "").expanduser().resolve())
        if not target_task_id:
            return {"status": "error", "output": "", "error": "task_id is required"}
        agent = infiagent(user_data_root=str(Path(__import__('os').environ.get('MLA_USER_DATA_ROOT','~/mla_v3')).expanduser().resolve()))
        snapshot = agent.task_snapshot(task_id=target_task_id)
        log_path = ""
        panel = load_panel()
        for channel_payload in panel.get("channels", {}).values():
            for conv in channel_payload.get("conversations", {}).values():
                for item in conv.get("linked_tasks", []):
                    if item.get("task_id") == target_task_id:
                        log_path = item.get("log_path", "")
                        snapshot["conversation"] = {"channel": conv.get("channel", ""), "conversation_id": conv.get("conversation_id", ""), "display_name": conv.get("display_name", "")}
                        break
        snapshot["log_path"] = log_path
        return snapshot
