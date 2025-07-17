from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    full_name: str,
    token: Optional[str] = None,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    获取指定GitHub仓库的详细信息。

    Args:
        full_name (str): 仓库全名，格式为`owner/repo`。
        token (Optional[str], optional): GitHub Token。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "full_name": full_name,
    }
    if token:
        params["token"] = token
        
    return execute_tool(tool_name="github_get_repository_info", params=params, task_id=task_id) 