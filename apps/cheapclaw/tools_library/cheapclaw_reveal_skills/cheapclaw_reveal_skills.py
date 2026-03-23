#!/usr/bin/env python3
from pathlib import Path
from infiagent import infiagent
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import extend_task_visible_skills, load_panel, update_conversation_task
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawRevealSkillsTool(BaseTool):
    name = "cheapclaw_reveal_skills"
    def execute(self, task_id, parameters):
        target_task_id = str(Path(parameters.get("task_id") or "").expanduser().resolve())
        skill_names = parameters.get("skill_names") or []
        if not target_task_id or not isinstance(skill_names, list) or not skill_names:
            return {"status": "error", "output": "", "error": "task_id and non-empty skill_names are required"}
        payload = extend_task_visible_skills(target_task_id, skill_names)
        panel = load_panel()
        for channel_payload in panel.get("channels", {}).values():
            for conv in channel_payload.get("conversations", {}).values():
                for linked in conv.get("linked_tasks", []):
                    if linked.get("task_id") == target_task_id:
                        update_conversation_task(
                            str(conv.get("channel") or ""),
                            str(conv.get("conversation_id") or ""),
                            target_task_id,
                            {"default_exposed_skills": list(payload.get("visible_skills") or [])},
                            mark_dirty=False,
                        )
                        break
        result = {
            "status": "success",
            "output": f"visible skills updated: {len(payload['visible_skills'])}",
            "task_id": target_task_id,
            "visible_skills": list(payload.get("visible_skills") or []),
        }
        if bool(parameters.get("run_fresh", False)):
            agent = infiagent(user_data_root=str(Path(__import__('os').environ.get('MLA_USER_DATA_ROOT','~/mla_v3')).expanduser().resolve()))
            result["fresh"] = agent.fresh(task_id=target_task_id, reason="skills revealed")
        return result
