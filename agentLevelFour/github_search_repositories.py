from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    query: str,
    sort: str = "stars",
    order: str = "desc",
    per_page: int = 10,
    page: int = 1,
    token: Optional[str] = None,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    搜索GitHub仓库。

    Args:
        query (str): 搜索关键词。
        sort (str, optional): 排序依据, 'stars', 'forks', 'updated'.
        order (str, optional): 排序顺序, 'desc', 'asc'.
        per_page (int, optional): 每页结果数量。
        page (int, optional): 页码。
        token (Optional[str], optional): GitHub Token。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "query": query,
        "sort": sort,
        "order": order,
        "per_page": per_page,
        "page": page,
    }
    if token:
        params["token"] = token
        
    return execute_tool(tool_name="github_search_repositories", params=params, task_id=task_id) 