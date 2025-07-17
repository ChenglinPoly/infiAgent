from typing import Dict, List
from .tool_utils import execute_tool

def run(
    packages: List[str],
    task_id: str = "default_agent_task"
) -> Dict:
    """
    在任务的虚拟环境中安装Python包。

    Args:
        packages (List[str]): 要安装的包名列表。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "packages": packages,
    }
    return execute_tool(tool_name="pip_install", params=params, task_id=task_id) 