#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import queue_outbound_message
from tool_server_lite.tools.file_tools import BaseTool


def _get_active_service():
    main_mod = sys.modules.get("__main__")
    active_service = getattr(main_mod, "ACTIVE_SERVICE", None) if main_mod is not None else None
    if active_service is not None:
        return active_service
    try:
        import cheapclaw_service as _cheapclaw_service
        return getattr(_cheapclaw_service, "ACTIVE_SERVICE", None)
    except Exception:
        return None


class CheapClawSendMessageTool(BaseTool):
    name = "cheapclaw_send_message"
    def execute(self, task_id, parameters):
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        message = str(parameters.get("message") or "").strip()
        if not channel or not conversation_id or not message:
            return {"status": "error", "output": "", "error": "channel, conversation_id and message are required"}
        active_service = _get_active_service()
        if active_service is not None:
            result = active_service.send_message_now(
                channel=channel,
                conversation_id=conversation_id,
                message=message,
                attachments=parameters.get("attachments") or [],
            )
            if result.get("status") == "success":
                return result
        payload = queue_outbound_message(
            channel=channel,
            conversation_id=conversation_id,
            message=message,
            attachments=parameters.get("attachments") or [],
            metadata={"requested_by_task": str(task_id or "")},
        )
        return {"status": "success", "output": f"queued outbound message {payload['event_id']}", **payload}
