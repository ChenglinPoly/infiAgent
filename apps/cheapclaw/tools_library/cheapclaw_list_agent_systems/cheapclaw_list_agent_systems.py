#!/usr/bin/env python3
from pathlib import Path
from infiagent import infiagent
from tool_server_lite.tools.file_tools import BaseTool

class CheapClawListAgentSystemsTool(BaseTool):
    name = "cheapclaw_list_agent_systems"
    def execute(self, task_id, parameters):
        agent = infiagent(user_data_root=str(Path(__import__('os').environ.get('MLA_USER_DATA_ROOT','~/mla_v3')).expanduser().resolve()))
        payload = agent.list_agent_systems()
        payload["recommended_defaults"] = {
            "CheapClawSupervisor": "supervisor_agent",
            "CheapClawWorkerGeneral": "worker_agent",
        }
        return payload
