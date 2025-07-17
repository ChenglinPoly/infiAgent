from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    query: str,
    output_dir: Optional[str] = None,
    pages: int = 1,
    year_low: Optional[int] = None,
    year_high: Optional[int] = None,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    执行Google Scholar搜索。

    Args:
        query (str): 搜索关键词。
        output_dir (Optional[str], optional): 保存结果的目录。
        pages (int, optional): 爬取的页数。
        year_low (Optional[int], optional): 起始年份。
        year_high (Optional[int], optional): 结束年份。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "query": query,
        "pages": pages,
    }
    if output_dir:
        params["output_dir"] = output_dir
    if year_low:
        params["year_low"] = year_low
    if year_high:
        params["year_high"] = year_high
        
    return execute_tool(tool_name="google_scholar_search", params=params, task_id=task_id) 