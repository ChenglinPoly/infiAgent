#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thinking Agent
专门用于任务进展分析的纯对话模型，不包含工具调用功能
"""

import sys
import os
from typing import List, Dict

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.llm_client import LLMClient, ChatMessage, ModelType


class ThinkingAgent:
    """
    思考Agent类，专门用于分析任务进展，不调用任何工具
    """
    
    def __init__(self, model_type: ModelType = ModelType.CLAUDE_3_7_SONNET):
        """
        初始化ThinkingAgent
        
        Args:
            model_type (ModelType): 使用的LLM模型类型
        """
        self.model_type = model_type
        
        # 初始化LLM客户端（不配置工具）
        self.client = LLMClient()
        
        # 系统提示词
        self.system_prompt = """
你是一个任务进展分析专家。你的职责是：

1. 分析当前任务的整体目标
2. 总结已完成的工作
3. 识别正在进行的任务
4. 列出待完成的任务
5. 评估当前进展状态

请以清晰、结构化的方式提供分析，包括：
- 任务概览
- 已完成项目
- 当前状态
- 待办事项
- 下一步建议

你的分析应该简洁明了，帮助执行Agent更好地理解当前进展。
"""
    
    def analyze_progress(self, task_description: str, conversation_history: List[ChatMessage], agent_system_prompt: str = None) -> str:
        """
        分析任务进展
        
        Args:
            task_description (str): 任务描述
            conversation_history (List[ChatMessage]): 对话历史
            agent_system_prompt (str, optional): 原执行Agent的系统提示词
            
        Returns:
            str: 进展分析结果
        """
        # 确保最后一条不是用户消息为空的情况
        analysis_history = conversation_history.copy()
        
        # 检查最后一条消息是否是user角色
        if analysis_history and analysis_history[-1].role == "user":
            # 添加一个空的assistant消息
            analysis_history.append(ChatMessage(role="assistant", content="我来分析一下当前的任务进展。"))
        
        # 构建分析请求，包含原agent的系统提示词
        analysis_request = f"""当前的任务是：{task_description}

你要监督进度的Agent的系统提示词和工作计划：
{agent_system_prompt if agent_system_prompt else '(未提供系统提示词)'}

请基于以上对话历史和Agent的工作计划，分析：
1. 目前任务已经进展到何种地步？
2. 任务列表如果不存在则总结任务列表，如果存在则总结已经完成了什么任务
3. 还需要完成的任务是什么？
4. 当前执行状态如何？
5. Agent是否按照其系统提示词正确执行？例如提示词要求使用专用工具完成任务，而他没有。
6. 下一步应该怎么做？注意你只应该提示当前 agent 的下一步的任务！
7. 当前的注意事项，比如是否遗漏了自己工作过程中的某个步骤？
8. 你应该为 agent 罗列一下之后所有可能用到的文件的地址和说明，防止其遗忘。

请提供简洁但全面的分析。"""
        
        analysis_history.append(ChatMessage(role="user", content=analysis_request))
        
        # 调用LLM进行分析（不使用工具）
        response = self.client.chat(
            history=analysis_history,
            model=self.model_type,
            system_prompt=self.system_prompt,
            tool_list=None,  # 不使用任何工具
            tool_choice="none"  # 禁用工具调用
        )
        
        if response.status == "success":
            return response.output
        else:
            return f"分析失败: {response.error_information}"
    
    def format_analysis_message(self, analysis_result: str) -> str:
        """
        格式化分析结果为消息
        
        Args:
            analysis_result (str): 分析结果
            
        Returns:
            str: 格式化后的消息
        """
        return f"""📊 **任务进展分析** (第5N轮总结)

{analysis_result}

---
*此分析由ThinkingAgent生成，用于帮助理解当前任务进展*"""


def analyze_task_progress(task_description: str, 
                         conversation_history: List[ChatMessage],
                         agent_system_prompt: str = None,
                         model_type: ModelType = ModelType.CLAUDE_3_7_SONNET) -> str:
    """
    便捷函数：分析任务进展
    
    Args:
        task_description (str): 任务描述
        conversation_history (List[ChatMessage]): 对话历史
        agent_system_prompt (str, optional): 原执行Agent的系统提示词
        model_type (ModelType): 使用的模型类型
        
    Returns:
        str: 格式化的分析结果
    """
    thinking_agent = ThinkingAgent(model_type)
    analysis = thinking_agent.analyze_progress(task_description, conversation_history, agent_system_prompt)
    return thinking_agent.format_analysis_message(analysis)


if __name__ == "__main__":
    # 测试示例
    from baseService.llm_client import ChatMessage, ModelType
    
    # 模拟对话历史
    test_history = [
        ChatMessage(role="user", content="请帮我创建一个Python项目，包含文件读写和数据处理功能"),
        ChatMessage(role="assistant", content="我来帮您创建项目。首先创建项目目录结构。"),
        ChatMessage(role="user", content="工具调用结果：已创建项目目录"),
        ChatMessage(role="assistant", content="接下来创建主要的Python文件。"),
        ChatMessage(role="user", content="工具调用结果：已创建main.py文件"),
    ]
    
    # 测试分析功能
    test_system_prompt = """
    你是一个Python项目开发助手。你的任务是：
    1. 创建清晰的项目结构
    2. 实现文件读写功能
    3. 实现数据处理功能
    4. 编写测试代码
    5. 提供完整的文档
    
    请按照最佳实践进行开发，确保代码质量和可维护性。
    """
    
    result = analyze_task_progress(
        task_description="创建一个Python项目，包含文件读写和数据处理功能",
        conversation_history=test_history,
        agent_system_prompt=test_system_prompt
    )
    
    print("分析结果：")
    print(result)
