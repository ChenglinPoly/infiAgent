from typing import Dict
from .tool_utils import execute_tool

def run(
    file_path: str,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    删除文件或目录。

    Args:
        file_path (str): 要删除的文件或目录的路径。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "file_path": file_path,
    }
    return execute_tool(tool_name="file_delete", params=params, task_id=task_id) 