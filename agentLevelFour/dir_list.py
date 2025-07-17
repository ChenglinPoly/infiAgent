from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    dir_path: Optional[str] = None,
    recursive: bool = False,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    列出目录内容。

    Args:
        dir_path (Optional[str], optional): 要列出的目录路径，默认为任务根目录。
        recursive (bool, optional): 是否递归列出所有子目录内容。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "recursive": recursive,
    }
    if dir_path is not None:
        params["dir_path"] = dir_path
        
    return execute_tool(tool_name="dir_list", params=params, task_id=task_id) 