from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    读取指定文件的内容。

    Args:
        file_path (str): 要读取的文件的路径。
        start_line (Optional[int], optional): 读取的起始行号（从1开始）。Defaults to None.
        end_line (Optional[int], optional): 读取的结束行号。Defaults to None.
        task_id (str, optional): 任务ID. Defaults to "default_agent_task".

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "file_path": file_path,
    }
    if start_line is not None:
        params["start_line"] = start_line
    if end_line is not None:
        params["end_line"] = end_line
        
    return execute_tool(tool_name="file_read", params=params, task_id=task_id) 