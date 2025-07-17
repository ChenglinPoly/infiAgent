from typing import Dict
from .tool_utils import execute_tool

def run(
    file_path: str,
    timeout: int = 300,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    在任务的独立虚拟环境中执行Python脚本。

    Args:
        file_path (str): 要执行的Python脚本路径。
        timeout (int, optional): 执行超时时间（秒）。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "file_path": file_path,
        "timeout": timeout
    }
    return execute_tool(tool_name="execute_code", params=params, task_id=task_id) 