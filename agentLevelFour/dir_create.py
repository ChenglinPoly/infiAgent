from typing import Dict
from .tool_utils import execute_tool

def run(
    dir_path: str,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    创建目录，支持递归创建。

    Args:
        dir_path (str): 要创建的目录路径。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "dir_path": dir_path,
    }
    return execute_tool(tool_name="dir_create", params=params, task_id=task_id) 