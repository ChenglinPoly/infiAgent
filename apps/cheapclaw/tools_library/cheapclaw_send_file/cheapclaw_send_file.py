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


class CheapClawSendFileTool(BaseTool):
    name = "cheapclaw_send_file"

    def execute(self, task_id, parameters):
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        local_path = str(parameters.get("local_path") or "").strip()
        if not channel or not conversation_id or not local_path:
            return {"status": "error", "output": "", "error": "channel, conversation_id and local_path are required"}

        file_path = Path(local_path).expanduser().resolve()
        if not file_path.exists() or not file_path.is_file():
            return {"status": "error", "output": "", "error": f"file not found: {file_path}"}

        attachment = {
            "local_path": str(file_path),
            "filename": str(parameters.get("filename") or file_path.name),
            "mime_type": str(parameters.get("mime_type") or "").strip(),
            "kind": str(parameters.get("kind") or "auto").strip(),
            "caption": str(parameters.get("caption") or "").strip(),
        }
        active_service = _get_active_service()
        if active_service is not None:
            result = active_service.send_message_now(
                channel=channel,
                conversation_id=conversation_id,
                message=str(parameters.get("message") or "").strip(),
                attachments=[attachment],
            )
            if result.get("status") == "success":
                return result
        payload = queue_outbound_message(
            channel=channel,
            conversation_id=conversation_id,
            message=str(parameters.get("message") or "").strip(),
            attachments=[attachment],
            metadata={"requested_by_task": str(task_id or ""), "mode": "send_file"},
        )
        return {"status": "success", "output": f"queued outbound file {payload['event_id']}", **payload}
