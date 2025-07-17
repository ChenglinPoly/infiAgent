from typing import Dict
from .tool_utils import execute_tool

def run(
    file_path: str,
    start_line: int,
    end_line: int,
    new_content: str,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    替换文件中的指定行范围。

    Args:
        file_path (str): 要修改的文件的路径。
        start_line (int): 替换的起始行号。
        end_line (int): 替换的结束行号。
        new_content (str): 用于替换的新内容。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "new_content": new_content
    }
    return execute_tool(tool_name="file_replace_lines", params=params, task_id=task_id) 