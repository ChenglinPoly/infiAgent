from typing import Dict
from .tool_utils import execute_tool

def run(
    query: str,
    num_results: int = 50,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    执行Google搜索。

    Args:
        query (str): 搜索关键词。
        num_results (int, optional): 返回的结果数量。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "query": query,
        "num_results": num_results
    }
    return execute_tool(tool_name="google_search", params=params, task_id=task_id) 