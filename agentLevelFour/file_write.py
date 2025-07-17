from typing import Dict
from .tool_utils import execute_tool

def run(
    file_path: str,
    content: str,
    mode: str = "overwrite",
    is_base64: bool = False,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    向指定文件写入内容。
    
    Args:
        file_path (str): 要写入的文件的路径。
        content (str): 要写入的内容。
        mode (str, optional): 写入模式, 'overwrite' (默认) 或 'append'.
        is_base64 (bool, optional): 内容是否为Base64编码.
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "file_path": file_path,
        "content": content,
        "mode": mode,
        "is_base64": is_base64
    }
    return execute_tool(tool_name="file_write", params=params, task_id=task_id) 