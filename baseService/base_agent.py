import sys
import os
import json
import importlib
import hashlib
from typing import List, Dict, Any, Optional, Union
import yaml
from datetime import datetime
# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.agent_class import Agent
from baseService.llm_client import LLMClient, ChatMessage, ModelType, normalize_model_name
from baseService.llm_client import ToolCall
from baseService.tool_utils import execute_tool
from baseService.config_merger import ensure_merged_config
from baseService.logger_service import AgentLogger
from baseService.thinking_agent import analyze_task_progress
from baseService.agent_hierarchy import get_cached_hierarchy_manager


def _check_and_clean_for_restart(task_id: str, task_input: str):
    """
    检查是否存在对应的对话文件，如果存在则清理栈和current状态，准备重新开始
    
    Args:
        task_id (str): 任务ID
        task_input (str): 任务输入
    """
    import hashlib
    
    # 生成基于task_id和task_input的hash
    content_for_hash = f"{task_id}|{task_input}"
    hash_object = hashlib.md5(content_for_hash.encode())
    file_hash = hash_object.hexdigest()[:12]
    
    # 检查对应的对话文件是否存在
    conversation_dir = os.path.join(project_root, 'conversations')
    conversation_pattern = f"{task_id}_{file_hash}"
    
    # 查找匹配的对话文件
    existing_conversations = []
    if os.path.exists(conversation_dir):
        for filename in os.listdir(conversation_dir):
            if filename.startswith(conversation_pattern) and filename.endswith('.json'):
                existing_conversations.append(filename)
    
    if existing_conversations:
        print(f"🔍 发现现有对话文件: {existing_conversations}")
        print(f"🧹 智能清理状态，保留已完成的Agent...")
        
        # 获取层级管理器
        hierarchy_manager = get_cached_hierarchy_manager(task_id)
        
        # 智能清理：保留已完成的Agent，删除等待中的Agent
        hierarchy_manager.smart_clean_for_restart()
        
        print(f"✅ 智能清理完成，将重新建立执行流程")


def get_available_tools(level: int, agent_system_name: str = None) -> List[str]:
    """
    从指定Agent系统的配置文件中获取工具配置
    
    Args:
        level (int): 工具级别
        agent_system_name (str): Agent系统名称
    """
    from baseService.config_merger import ensure_merged_config, get_agent_config_path
    
    # 确保配置文件是最新的合并版本
    ensure_merged_config(agent_system_name)
    
    agent_configs_path = get_agent_config_path(agent_system_name)
    available_tools = []
    with open(agent_configs_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f).get("tools", {})
        for key, value in config.items():
            if value.get("level") == level:
                available_tools.append(key)
        return available_tools

def get_general_prompts(agent_system_name: str = None) -> Dict:
    """
    从指定Agent系统的配置文件中获取通用提示词
    
    Args:
        agent_system_name (str): Agent系统名称
    """
    from baseService.config_merger import ensure_merged_config, get_agent_config_path
    
    # 确保配置文件是最新的合并版本
    ensure_merged_config(agent_system_name)
    
    agent_prompts_path = get_agent_config_path(agent_system_name)
    with open(agent_prompts_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        return config.get("general_prompts", {})

'''修改'''
def create_agent(
    agent_name:str = "default_agent",
    task_id:str = "default_agent_task",
    level:int = 4,
    type:str = "llm_call_agent",
    available_tools:List[str] = [],
    max_turns: int = 100,
    model_type: Union[str, ModelType] = "claude-3-7-sonnet-20250219",
    prompts: Dict = {},
    agent_system_name: str = None,
    **kwargs
    ) -> Agent:

    """
    创建一个 修改 Agent实例。
    
    Args:
        max_turns (int): 最大轮次
        model_type: 模型类型，支持字符串或ModelType枚举
        
    Returns:
        Agent: 配置好的 修改 Agent实例
    """
    if agent_name == "judge_agent":
        system_prompt = prompts.get("system_prompt", "")
        system_prompt += "\n" + f"现在时刻是{datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}"
        available_tools = ['file_read','dir_list','final_output','parse_document','execute_code']
    else:
        general_prompts = get_general_prompts(agent_system_name)
        agent_workflow = prompts.pop("agent_workflow", "")
        agent_responsibility = prompts.pop("agent_responsibility", "")
        format_dict = {}
        for key,value in prompts.items():
            if f'{{{key}}}' in agent_workflow:
                format_dict[key] = value
        if format_dict:
            agent_workflow = agent_workflow.format(**format_dict)
        system_prompt = general_prompts.get("agent_system_prompt", "") + \
            general_prompts.get("agent_warning_prompt", "") + \
            general_prompts.get("agent_workflow_prompt", "") + \
            general_prompts.get("agent_output_format_prompt", "")
        system_prompt = system_prompt.format(agent_name=agent_name,agent_responsibility=agent_responsibility,task_id=task_id,agent_workflow=agent_workflow)
    
    # 规范化模型名称，支持字符串和枚举
    normalized_model_name = normalize_model_name(model_type)
    
    # 创建Agent实例
    agent = Agent(
        agent_name=agent_name,
        system_prompt=system_prompt,
        available_tools=available_tools,
        max_turns=max_turns,
        model_type=normalized_model_name,  # 直接传入字符串
        agent_system_name=agent_system_name
    )
    # print(system_prompt)
    # print(available_tools)
    
    return agent


def get_tool_config(tool_name: str, agent_system_name: str = None) -> Dict:
    """
    从指定Agent系统的配置文件中获取工具配置
    
    Args:
        tool_name (str): 工具名称
        agent_system_name (str): Agent系统名称
    """
    from baseService.config_merger import ensure_merged_config, get_agent_config_path
    
    # 确保配置文件是最新的合并版本
    ensure_merged_config(agent_system_name)
    
    tools_config_path = get_agent_config_path(agent_system_name)
    with open(tools_config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        return config.get("tools", {}).get(tool_name, {})

def run(
    task_id: str,
    tool_name: str,
    arguments: Dict = {},
    max_history_turns: int=40,
    max_history_tokens: int=80000,
    agent_system_name: str = None,
) -> Dict:
    print("Running tool ", tool_name)
    
    # 如果是从start.py启动的Agent，检查并清理状态
    if arguments.get("from_start_py", False) and "task_input" in arguments:
        task_input = arguments.get("task_input", "")
        print(f"🧹 检测到从start.py启动的Agent: {tool_name}，执行智能清理...")
        _check_and_clean_for_restart(task_id, task_input)
    
    tool_config = get_tool_config(tool_name, agent_system_name)
    if tool_config.get("type") == "llm_call_agent":
        task_input = arguments.get("task_input", "")
        print(f"⚖️  启动{tool_name}，审查任务: {task_id} ⚖️")
        
        # 获取层级管理器，更新当前Agent状态为等待子Agent返回结果
        hierarchy_manager = get_cached_hierarchy_manager(task_id)
        current_agent_id = hierarchy_manager.get_current_agent_id()
        if current_agent_id:
            hierarchy_manager.update_agent_progress(current_agent_id, f"正在等待子Agent {tool_name} 返回结果...", "waiting")
        
        # 创建Agent实例
        agent = create_agent(
            agent_name=tool_name,
            task_id=task_id,
            max_history_turns=max_history_turns,
            max_history_tokens=max_history_tokens,
            agent_system_name=agent_system_name,
            **tool_config
        )
        
        # 运行子Agent
        agent_result = agent.run(task_id, task_input)
        
        # 子Agent完成后，更新父Agent的进度
        if current_agent_id:
            result_summary = agent_result.get("output", "子任务已完成")[:100]  # 截取前100字符作为摘要
            hierarchy_manager.update_agent_progress(current_agent_id, f"子Agent {tool_name} 已完成: {result_summary}", "general")
        
        return agent_result, tool_config.get("level", 0)
    elif tool_config.get("type") == "tool_call_agent":
        params = arguments
        return execute_tool(tool_name=tool_name, params=params, task_id=task_id), tool_config.get("level", 0)


if __name__ == '__main__':
    # --- 使用示例 ---
    # 模拟一个场景：一个Agent被要求创建一个文件，并声称它成功了。
    
    # 1. 原始指令
    mock_instruction = "upload/AAAI_adv.pdf中有没有明确的作者？"

   

    # 3. 启动 Judge Agent 进行审查
    final_judgement = run(
        task_id="recovery_test",
        tool_name="answer_from_one_paper",
        arguments={"task_input":mock_instruction},
    )

    print("\n" + "="*20 + " 最终审查结果 " + "="*20)
    print(json.dumps(final_judgement, indent=2, ensure_ascii=False))
    print("="*55) 