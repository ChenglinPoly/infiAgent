#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import list_conversation_tasks, load_panel
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawListConversationTasksTool(BaseTool):
    name = "cheapclaw_list_conversation_tasks"
    def execute(self, task_id, parameters):
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        if not channel or not conversation_id:
            return {"status": "error", "output": "", "error": "channel and conversation_id are required"}
        tasks = list_conversation_tasks(channel, conversation_id)
        panel = load_panel()
        conv = panel.get("channels", {}).get(channel, {}).get("conversations", {}).get(conversation_id, {})
        bindings = list(conv.get("message_task_bindings", []))
        bindings.sort(key=lambda item: str(item.get("bound_at") or ""), reverse=True)

        recommended_task_id = ""
        recommended_reason = ""
        recommended_action = ""

        for binding in bindings:
            candidate = str(binding.get("task_id") or "").strip()
            if candidate and any(item.get("task_id") == candidate for item in tasks):
                recommended_task_id = candidate
                recommended_reason = "latest_message_binding"
                break

        if not recommended_task_id and tasks:
            recommended_task_id = str(tasks[0].get("task_id") or "")
            recommended_reason = "most_recent_task_activity"

        if recommended_task_id:
            target = next((item for item in tasks if item.get("task_id") == recommended_task_id), {})
            recommended_action = "append_to_running_task" if target.get("status") == "running" else "continue_existing_task"

        latest_binding = bindings[0] if bindings else {}
        running_task_ids = [str(item.get("task_id") or "") for item in tasks if item.get("status") == "running" and str(item.get("task_id") or "")]
        recent_task_ids = [str(item.get("task_id") or "") for item in tasks if str(item.get("task_id") or "")]

        return {
            "status": "success",
            "output": f"tasks={len(tasks)}",
            "tasks": tasks,
            "latest_bound_task_id": str(latest_binding.get("task_id") or ""),
            "latest_bound_message_id": str(latest_binding.get("message_id") or ""),
            "running_task_ids": running_task_ids,
            "recent_task_ids": recent_task_ids,
            "recommended_task_id": recommended_task_id,
            "recommended_reason": recommended_reason,
            "recommended_action": recommended_action,
            "heuristic_note": "recommended_* is only a heuristic hint derived from latest bindings and recent task activity. The supervisor must decide by reading panel history, social history, and task states.",
        }
