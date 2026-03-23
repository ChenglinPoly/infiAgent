#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import create_plan
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawSchedulePlanTool(BaseTool):
    name = "cheapclaw_schedule_plan"
    def execute(self, task_id, parameters):
        name = str(parameters.get("name") or "").strip()
        scope = str(parameters.get("scope") or "").strip()
        if not name or not scope:
            return {"status": "error", "output": "", "error": "name and scope are required"}
        plan = create_plan(
            name=name,
            scope=scope,
            task_id=str(parameters.get("task_id") or "").strip(),
            channel=str(parameters.get("channel") or "").strip(),
            conversation_id=str(parameters.get("conversation_id") or "").strip(),
            interval_sec=int(parameters.get("interval_sec") or 0),
            once_at=str(parameters.get("once_at") or "").strip(),
            schedule_type=str(parameters.get("schedule_type") or "").strip(),
            time_of_day=str(parameters.get("time_of_day") or "").strip(),
            days_of_week=parameters.get("days_of_week") or [],
            message=str(parameters.get("message") or "").strip(),
            enabled=bool(parameters.get("enabled", True)),
        )
        return {"status": "success", "output": f"created plan {plan['plan_id']}", "plan": plan}
