#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import read_social_history
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawReadSocialHistoryTool(BaseTool):
    name = "cheapclaw_read_social_history"
    def execute(self, task_id, parameters):
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        if not channel or not conversation_id:
            return {"status": "error", "output": "", "error": "channel and conversation_id are required"}
        items = read_social_history(
            channel=channel,
            conversation_id=conversation_id,
            limit=int(parameters.get("limit", 30) or 30),
            only_mentions_to_bot=bool(parameters.get("only_mentions_to_bot", False)),
            include_bot_replies=bool(parameters.get("include_bot_replies", True)),
            from_message_id=str(parameters.get("from_message_id") or ""),
            to_message_id=str(parameters.get("to_message_id") or ""),
            before_timestamp=str(parameters.get("before_timestamp") or ""),
            after_timestamp=str(parameters.get("after_timestamp") or ""),
        )
        return {"status": "success", "output": f"history_items={len(items)}", "messages": items}
