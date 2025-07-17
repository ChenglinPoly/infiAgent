from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    command: str,
    workdir: Optional[str] = None,
    timeout: int = 60,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    在任务的工作目录中执行Shell命令。

    Args:
        command (str): 要执行的Shell命令。
        workdir (Optional[str], optional): 执行命令的工作目录，默认为`code_run/`。
        timeout (int, optional): 超时时间（秒）。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "command": command,
        "timeout": timeout
    }
    if workdir is not None:
        params["workdir"] = workdir
        
    return execute_tool(tool_name="execute_shell", params=params, task_id=task_id) 