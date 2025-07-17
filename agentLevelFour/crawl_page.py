from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    url: str,
    output_dir: Optional[str] = None,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    爬取指定URL的网页内容并保存为Markdown。

    Args:
        url (str): 要爬取的网页URL。
        output_dir (Optional[str], optional): 保存Markdown文件的目录。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "url": url,
    }
    if output_dir:
        params["output_dir"] = output_dir
        
    return execute_tool(tool_name="crawl_page", params=params, task_id=task_id) 