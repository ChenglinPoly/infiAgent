from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    repo_url: str,
    target_dir: Optional[str] = None,
    branch: Optional[str] = None,
    token: Optional[str] = None,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    克隆一个Git仓库到`upload/`目录。

    Args:
        repo_url (str): 仓库的URL。
        target_dir (Optional[str], optional): 克隆到的子目录名。
        branch (Optional[str], optional): 要克隆的特定分支。
        token (Optional[str], optional): 用于私有仓库的GitHub Token。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "repo_url": repo_url,
    }
    if target_dir:
        params["target_dir"] = target_dir
    if branch:
        params["branch"] = branch
    if token:
        params["token"] = token
        
    return execute_tool(tool_name="git_clone", params=params, task_id=task_id) 