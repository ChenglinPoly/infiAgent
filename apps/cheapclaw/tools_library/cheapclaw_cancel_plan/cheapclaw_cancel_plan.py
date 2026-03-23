#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import cancel_plan
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawCancelPlanTool(BaseTool):
    name = "cheapclaw_cancel_plan"
    def execute(self, task_id, parameters):
        plan_id = str(parameters.get("plan_id") or "").strip()
        if not plan_id:
            return {"status": "error", "output": "", "error": "plan_id is required"}
        ok = cancel_plan(plan_id)
        if not ok:
            return {"status": "error", "output": "", "error": f"plan not found: {plan_id}"}
        return {"status": "success", "output": f"cancelled {plan_id}"}
