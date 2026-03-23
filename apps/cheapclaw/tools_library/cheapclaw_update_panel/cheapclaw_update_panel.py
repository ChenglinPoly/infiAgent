#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import (
    bind_messages_to_task,
    clear_conversation_dirty,
    ensure_conversation,
    mutate_panel,
    now_iso,
    update_conversation_task,
)
from tool_server_lite.tools.file_tools import BaseTool


class CheapClawUpdatePanelTool(BaseTool):
    name = "cheapclaw_update_panel"

    def execute(self, task_id, parameters):
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        if not channel or not conversation_id:
            return {"status": "error", "output": "", "error": "channel and conversation_id are required"}

        operations = []
        if parameters.get("clear_dirty"):
            clear_conversation_dirty(channel, conversation_id)
            operations.append("clear_dirty")
        else:
            def _mutate(panel):
                conv = ensure_conversation(panel, channel=channel, conversation_id=conversation_id)
                if parameters.get("set_dirty") is not None:
                    conv["dirty"] = bool(parameters.get("set_dirty"))
                    panel.setdefault("service_state", {})["main_agent_dirty"] = bool(parameters.get("set_dirty"))
                    operations.append("set_dirty")
                conversation_patch = parameters.get("conversation_patch") or {}
                if isinstance(conversation_patch, dict):
                    conv.update(conversation_patch)
                    operations.append("conversation_patch")
                pending_event = parameters.get("append_pending_event")
                if isinstance(pending_event, dict):
                    conv.setdefault("pending_events", []).append(pending_event)
                    operations.append("append_pending_event")
                conv["unread_event_count"] = len(conv.get("pending_events", []))
                conv["updated_at"] = now_iso()
                return panel
            mutate_panel(_mutate)

        target_task_id = str(parameters.get("task_id") or "").strip()
        task_patch = parameters.get("task_patch") or {}
        if target_task_id and isinstance(task_patch, dict):
            update_conversation_task(channel, conversation_id, target_task_id, task_patch, mark_dirty=bool(parameters.get("set_dirty", False)))
            operations.append("task_patch")

        bind_message_ids = parameters.get("bind_message_ids") or []
        if target_task_id and isinstance(bind_message_ids, list) and bind_message_ids:
            bind_messages_to_task(
                channel,
                conversation_id,
                target_task_id,
                bind_message_ids,
                note=str(parameters.get("binding_note") or "manual panel binding"),
                binding_type=str(parameters.get("binding_type") or "task"),
            )
            operations.append("bind_messages")

        return {
            "status": "success",
            "output": "ok",
            "channel": channel,
            "conversation_id": conversation_id,
            "task_id": target_task_id,
            "operations": operations,
        }
