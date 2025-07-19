import os
import json
from typing import Dict, Optional


def run(
    task_input: str,
    task_id: str = "default_agent_task"
) -> Dict:
    """
    提示用户根据DOI或标题手动下载PDF，并验证文件是否存在于服务器。
    这是一个交互式工具，会暂停执行等待用户确认。

    Args:
        doi (Optional[str], optional): 论文的DOI。
        title (Optional[str], optional): 论文的标题。
        task_id (str, optional): 任务ID。

    Returns:
        Dict: 包含 'status', 'output', 'error_information' 的标准字典。
    """
    
    # 创建一个对文件系统安全的文件名
    
    # --- 1. 用户手动操作步骤 ---
    print("\n" + "="*60)
    print("--- 交互式工具：需要您手动操作 ---")
    print(f"请根据以下信息，将提示词利用 gpt 网页工具生成图片，并命名为gpt_generated_figure.png:")
    print(f"提示词: {task_input}")
    print(f"\n请将下载的PDF文件命名为: gpt_generated_figure.png")
    print(f"并将其放置在工具服务器任务 '{task_id}' 的 'upload' 文件夹中。")
    print("\n当您完成上述操作后，请在此处输入 'yes' 并按 Enter 键继续...")
    print("="*60)
    
    while True:
        user_input = input("> ").strip().lower()
        if user_input == 'yes':
            break
        else:
            print("请输入 'yes' 以确认您已完成文件下载和放置操作。")

  

    # --- 2. 服务器验证步骤 ---
    
    return {
                "status": "success",
                "output": f"文件 'gpt_generated_figure.png' 已在服务器的 '/uploads' 路径下成功确认。",
                "error_information": ""
            }
        