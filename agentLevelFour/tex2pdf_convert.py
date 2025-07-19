from typing import Dict, Optional
from .tool_utils import execute_tool

def run(
    input_path: str,
    output_path: Optional[str] = None,
    engine: str = "pdflatex",
    clean_aux: bool = True,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    将包含LaTeX源文件的目录编译为PDF。

    Args:
        input_path (str): 包含`.tex`文件的目录路径。
        output_path (Optional[str], optional): PDF输出目录。
        engine (str, optional): LaTeX引擎, 'pdflatex', 'xelatex', 'lualatex'.
        clean_aux (bool, optional): 是否清理编译辅助文件。
        task_id (str, optional): 任务ID.

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    params = {
        "input_path": input_path,
        "engine": engine,
        "clean_aux": clean_aux
    }
    if output_path:
        params["output_path"] = output_path
        
    return execute_tool(tool_name="tex2pdf_convert", params=params, task_id=task_id)

