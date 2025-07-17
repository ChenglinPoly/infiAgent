from typing import Dict
from .tool_utils import execute_tool

def run(
    src_path: str,
    dest_path: str,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    移动或重命名文件或目录。

    Args:
        src_path (str): 源路径。
        dest_path (str): 目标路径。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "src_path": src_path,
        "dest_path": dest_path
    }
    return execute_tool(tool_name="file_move", params=params, task_id=task_id) 