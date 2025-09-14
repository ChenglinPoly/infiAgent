#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import json
import argparse

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.base_agent import run
from baseService.agent_hierarchy import get_cached_hierarchy_manager

# 导入task_runner中的函数
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from task_runner import resume_task_from_stack


def run_with_multiple_instructions(task_id: str, tool_name: str, user_history: list, agent_system_name: str = "infiHelper", from_start_py: bool = True):
    """
    支持多条指令的Agent运行函数
    
    Args:
        task_id (str): 任务ID
        tool_name (str): Agent名称（可以是任何Agent，不限于writing_agent）
        user_history (list): 用户指令历史列表
        agent_system_name (str): Agent系统名称，默认为"infiHelper"
        from_start_py (bool): 标记是否从start.py启动，用于清理判断
        
    Returns:
        tuple: (result, level) 执行结果和工具级别
    """
    if not user_history:
        raise ValueError("user_history不能为空")
    
    # 第一条指令作为主要任务
    main_instruction = user_history[0]
    additional_instructions = user_history[1:] if len(user_history) > 1 else []
    
    print(f"🚀 开始执行任务: {task_id}")
    print(f"📝 主要指令: {main_instruction[:60]}...")
    if additional_instructions:
        print(f"📋 附加指令数量: {len(additional_instructions)}")
        for i, instr in enumerate(additional_instructions):
            print(f"   {i+1}. {instr[:60]}...")
    
    # 如果有附加指令，在任务开始前添加到共享上下文中
    if additional_instructions:
        print(f"\n📝 预先添加附加指令到共享上下文...")
        hierarchy_manager = get_cached_hierarchy_manager(task_id)
        
        # 添加每条附加指令
        for instruction in additional_instructions:
            instruction_id = hierarchy_manager.start_new_instruction(instruction)
            print(f"✅ 已添加指令: {instruction_id} -> {instruction[:50]}...")
    
    # 执行主要任务，传递from_start_py标记
    result = run(
        task_id=task_id,
        tool_name=tool_name,
        arguments={"task_input": main_instruction, "from_start_py": from_start_py},
        agent_system_name=agent_system_name
    )
    
    return result


if __name__ == '__main__':
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Multi-Level Agent Task Runner')
    parser.add_argument('--task_id', type=str, help='任务ID')
    parser.add_argument('--agent_system_name', type=str, default='infiHelper', help='Agent系统名称')
    parser.add_argument('--agent_name', type=str, default='writing_agent', help='启动的Agent名称')
    parser.add_argument('--user_instructions', nargs='*', help='用户指令列表')

    
    args = parser.parse_args()
    
    # 如果提供了命令行参数，使用命令行参数
    if args.task_id:
        # 统一启动模式（程序会自动检测和恢复状态）
        user_instructions = args.user_instructions or []
        print(f"🚀 启动任务: {args.task_id}")
        print(f"📝 指令列表: {user_instructions}")
        
        result = run_with_multiple_instructions(
            task_id=args.task_id,
            tool_name=args.agent_name,  # 使用命令行参数指定的Agent名称
            user_history=user_instructions,
            agent_system_name=args.agent_system_name
        )
    else:
        # 默认测试
        print("📋 使用默认配置运行...")
        user_history = ['''执行 code_run下draw_star.py 代码，并检查结果''']
        
        # 默认使用writing_agent，但也可以通过环境变量修改
        default_agent_name = os.getenv("DEFAULT_AGENT_NAME", "writing_agent")
        
        result = run_with_multiple_instructions(
            task_id="example_test",
            tool_name="experment_material_data_agent", 
            user_history=user_history,
            agent_system_name="infiHelper"
        )

    print("\n" + "="*20 + " Final Review Result " + "="*20)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    print("="*55) 

