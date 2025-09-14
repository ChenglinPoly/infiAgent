#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任务运行器模块
将start.py的核心逻辑封装成可直接调用的方法，供API服务器使用

API导入 - 任务执行的核心模块
"""

import sys
import os
import json
from typing import List, Dict, Any

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.base_agent import run
from baseService.agent_hierarchy import get_cached_hierarchy_manager


def run_task_with_instructions(task_id: str, tool_name: str, user_history: List[str], agent_system_name: str = "infiHelper") -> Dict[str, Any]:
    """
    执行带有多条指令的任务
    
    Args:
        task_id (str): 任务ID
        tool_name (str): 工具名称（通常是"writing_agent"）
        user_history (List[str]): 用户指令历史列表
        agent_system_name (str): Agent系统名称
        
    Returns:
        Dict[str, Any]: 执行结果
    """
    if not user_history:
        return {"status": "error", "output": "user_history不能为空", "error_information": "缺少指令"}
    
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
    
    # 执行主要任务
    result = run(
        task_id=task_id,
        tool_name=tool_name,
        arguments={"task_input": main_instruction},
        agent_system_name=agent_system_name
    )
    
    return result


def run_single_task(task_id: str, user_input: str, agent_system_name: str = "infiHelper") -> Dict[str, Any]:
    """
    执行单个指令的任务
    
    Args:
        task_id (str): 任务ID
        user_input (str): 用户输入指令
        agent_system_name (str): Agent系统名称
        
    Returns:
        Dict[str, Any]: 执行结果
    """
    print(f"🎯 执行单个任务: {task_id}")
    print(f"🤖 Agent系统: {agent_system_name}")
    print(f"📝 用户指令: {user_input}")
    
    # 执行任务
    result = run(
        task_id=task_id,
        tool_name="writing_agent",
        arguments={"task_input": user_input},
        agent_system_name=agent_system_name
    )
    
    return result


def resume_task_from_stack(task_id: str, agent_system_name: str = "infiHelper") -> Dict[str, Any]:
    """
    从栈顶恢复任务执行
    
    Args:
        task_id (str): 任务ID
        agent_system_name (str): Agent系统名称
        
    Returns:
        Dict[str, Any]: 执行结果
    """
    print(f"🔄 恢复任务: {task_id}")
    print(f"🤖 Agent系统: {agent_system_name}")
    
    try:
        # 获取栈顶Agent信息进行恢复
        hierarchy_manager = get_cached_hierarchy_manager(task_id)
        
        # 先触发智能清理，模拟正常重启的行为
        print(f"🧹 恢复前清理任务状态...")
        hierarchy_manager.smart_clean_for_restart()
        
        # 获取栈顶Agent信息
        stack_top = hierarchy_manager.get_stack_top_agent()
        
        if not stack_top:
            print("❌ 栈为空，无法恢复")
            return {"status": "error", "output": "栈为空，无法恢复", "error_information": "栈为空"}
        
        print(f"📍 从栈顶恢复: {stack_top['agent_name']}")
        print(f"📝 原始输入: {stack_top['user_input']}")
        
        # 使用栈顶Agent的信息恢复执行
        result = run(
            task_id=task_id,
            tool_name=stack_top['agent_name'],
            arguments={"task_input": stack_top['user_input']},
            agent_system_name=agent_system_name
        )
        
        return result
        
    except Exception as e:
        error_msg = f"恢复任务失败: {str(e)}"
        print(f"❌ {error_msg}")
        return {"status": "error", "output": error_msg, "error_information": str(e)}


def add_instruction_to_task(task_id: str, new_instruction: str) -> Dict[str, Any]:
    """
    向现有任务添加新指令
    
    Args:
        task_id (str): 任务ID
        new_instruction (str): 新指令
        
    Returns:
        Dict[str, Any]: 操作结果
    """
    try:
        print(f"📝 向任务 {task_id} 添加新指令: {new_instruction}")
        
        # 使用hierarchy_manager添加新指令
        hierarchy_manager = get_cached_hierarchy_manager(task_id)
        
        # 添加新指令
        instruction_id = hierarchy_manager.start_new_instruction(new_instruction)
        
        print(f"✅ 指令已添加: {instruction_id}")
        
        return {
            "status": "success", 
            "output": f"指令已添加到任务 {task_id}",
            "instruction_id": instruction_id
        }
        
    except Exception as e:
        error_msg = f"添加指令失败: {str(e)}"
        print(f"❌ {error_msg}")
        return {
            "status": "error", 
            "output": error_msg,
            "error_information": str(e)
        }


if __name__ == '__main__':
    # 测试代码
    print("🧪 任务运行器模块测试")
    
    # 测试单个任务
    result = run_single_task("test_runner", "生成一个简单的hello world程序", "infiHelper-2")
    print("测试结果:", json.dumps(result, indent=2, ensure_ascii=False)) 