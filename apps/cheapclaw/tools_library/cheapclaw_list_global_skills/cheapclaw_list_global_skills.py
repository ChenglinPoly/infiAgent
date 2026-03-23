#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from tool_runtime_helpers import list_global_skills
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawListGlobalSkillsTool(BaseTool):
    name = "cheapclaw_list_global_skills"
    def execute(self, task_id, parameters):
        skills = list_global_skills()
        return {"status": "success", "output": f"skills={len(skills)}", "skills": skills}
