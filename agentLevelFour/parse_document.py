from typing import Dict
from .tool_utils import execute_tool

def run(
    file_path: str,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    解析文档内容，支持PDF, Word, PPT, Markdown。

    Args:
        file_path (str): 要解析的文档路径。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "file_path": file_path,
    }
    return execute_tool(tool_name="parse_document", params=params, task_id=task_id) 