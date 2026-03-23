#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import generate_task_id
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawGenerateTaskIdTool(BaseTool):
    name = "cheapclaw_generate_task_id"
    def execute(self, task_id, parameters):
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        task_name = str(parameters.get("task_name") or "").strip()
        if not channel or not conversation_id or not task_name:
            return {"status": "error", "output": "", "error": "channel, conversation_id and task_name are required"}
        value = generate_task_id(channel, conversation_id, task_name)
        return {"status": "success", "output": value, "task_id": value}
