from typing import Dict, List, Optional
from .tool_utils import execute_tool

def run(
    files: List[Dict],
    target_path: Optional[str] = None,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    上传一个或多个文件的内容到任务工作空间。

    Args:
        files (List[Dict]): 文件列表，每个字典包含:
            - filename (str): 包含相对路径的文件名。
            - content (str): 文件内容，可以是文本或Base64编码的二进制数据。
            - is_base64 (bool): 指示内容是否为Base64编码。
        target_path (Optional[str], optional): 上传到的目标子目录。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "files": files,
    }
    if target_path:
        params["target_path"] = target_path
        
    return execute_tool(tool_name="file_upload", params=params, task_id=task_id) 