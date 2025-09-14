#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thinking Agent
专门用于任务进展分析的纯对话模型，不包含工具调用功能
"""

import sys
import os
from typing import List, Dict, Union

# 将项目根目录添加到Python路径中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.append(project_root)

from baseService.llm_client import LLMClient, ChatMessage, ModelType, normalize_model_name


class ThinkingAgent:
    """
    思考Agent类，专门用于分析任务进展，不调用任何工具
    """
    
    def __init__(self, model_type: Union[str, ModelType] = "claude-3-7-sonnet-20250219", max_retries: int = 3, retry_delay: float = 5.0):
        """
        初始化ThinkingAgent
        
        Args:
            model_type: 使用的LLM模型类型，支持字符串或ModelType枚举
            max_retries (int): 最大重试次数
            retry_delay (float): 重试延迟时间（秒）
        """
        self.model_type = normalize_model_name(model_type)  # 规范化为字符串
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 初始化LLM客户端（不配置工具，使用默认的 infiHelper 系统）
        # 智能选择是否使用custom APIs
        llm_config_path = os.path.join(project_root, 'config', 'run_env_config', 'llm_config.yaml')
        self.client = LLMClient(
            config_file=llm_config_path, 
            use_custom_apis=self._should_use_custom_apis(llm_config_path),
            agent_system_name="infiHelper"  # ThinkingAgent 使用默认的 infiHelper 系统
        )
        
        # 系统提示词
        self.system_prompt = """
You are a task progress analysis expert. Your responsibilities are:

1. Analyze the overall goal of the current task
2. Summarize the work that has been completed
3. Identify ongoing tasks
4. List the tasks that remain to be done
5. Assess the current progress status

Please provide your analysis in a clear and structured manner, including:
- Task overview
- Completed items
- Current status
- Remaining tasks
- Next steps
- Risk assessment (if any)

Always provide constructive and actionable insights.
"""
    
    def _should_use_custom_apis(self, llm_config_path: str) -> bool:
        """
        智能判断是否应该使用custom APIs
        
        Args:
            llm_config_path (str): LLM配置文件路径
            
        Returns:
            bool: 是否使用custom APIs
        """
        try:
            import yaml
            with open(llm_config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 检查是否有任何provider配置了有效的custom API
            providers = ["openai", "claude", "gemini"]
            
            for provider in providers:
                provider_config = config.get(provider, {})
                custom_config = provider_config.get("custom", {})
                
                # 如果有API密钥和base_url，认为配置了custom API
                if custom_config.get("api_key") and custom_config.get("base_url"):
                    return True
            
            # 没有找到任何custom API配置，使用官方API
            return False
            
        except Exception as e:
            print(f"⚠️ ThinkingAgent读取LLM配置文件失败，使用官方API: {e}")
            return False
    
    def _is_retryable_error(self, error_msg: str) -> bool:
        """判断错误是否可重试"""
        if not error_msg:
            return False
        
        error_msg_lower = error_msg.lower()
        
        # 可重试的错误模式
        retryable_patterns = [
            # 配额和速率限制
            "quota", "resource_exhausted", "rate limit", "too many requests",
            "429", "quota exceeded", "billing", "current quota",
            
            # 网络相关错误
            "timeout", "connection", "network", "socket", "dns",
            "502", "503", "504", "gateway", "service unavailable",
            
            # 服务器临时错误
            "internal server error", "500", "server error", "temporarily unavailable",
            "service temporarily unavailable", "overloaded",
            
            # 其他临时错误
            "try again", "retry", "temporary", "temporarily"
        ]
        
        # 检查是否包含可重试的错误模式
        for pattern in retryable_patterns:
            if pattern in error_msg_lower:
                return True
        
        return False
    
    def _call_llm_with_retry(self, history: List[ChatMessage], system_prompt: str):
        """带重试机制的LLM调用"""
        import time
        
        last_exception = None
        current_delay = self.retry_delay
        
        for attempt in range(self.max_retries + 1):
            try:
                print(f"[ThinkingAgent] 调用LLM进行任务分析 (尝试 {attempt + 1}/{self.max_retries + 1})")
                
                # 调用LLM
                response = self.client.chat(
                    history=history,
                    model=self.model_type,  # 现在是字符串
                    system_prompt=system_prompt,
                    tool_list=None,  # 不使用任何工具
                    tool_choice="none"  # 禁用工具调用
                )
                
                # 检查响应状态
                if response.status == "success":
                    if attempt > 0:
                        print(f"[ThinkingAgent] LLM调用在第{attempt + 1}次尝试后成功")
                    return response
                elif response.status == "error":
                    error_msg = response.error_information
                    
                    # 检查是否是可重试的错误
                    if self._is_retryable_error(error_msg):
                        if attempt < self.max_retries:
                            print(f"[ThinkingAgent] LLM调用失败，{current_delay:.1f}秒后重试: {error_msg}")
                            time.sleep(current_delay)
                            current_delay *= 1.5  # 指数退避
                            continue
                        else:
                            print(f"[ThinkingAgent] LLM调用重试次数耗尽: {error_msg}")
                            return response
                    else:
                        # 不可重试的错误，直接返回
                        print(f"[ThinkingAgent] LLM调用遇到不可重试错误: {error_msg}")
                        return response
                
            except Exception as e:
                last_exception = e
                error_msg = str(e)
                
                # 检查是否是可重试的异常
                if self._is_retryable_error(error_msg):
                    if attempt < self.max_retries:
                        print(f"[ThinkingAgent] LLM调用异常，{current_delay:.1f}秒后重试: {error_msg}")
                        time.sleep(current_delay)
                        current_delay *= 1.5  # 指数退避
                        continue
                    else:
                        print(f"[ThinkingAgent] LLM调用重试次数耗尽: {error_msg}")
                        raise e
                else:
                    # 不可重试的异常，直接抛出
                    print(f"[ThinkingAgent] LLM调用遇到不可重试异常: {error_msg}")
                    raise e
        
        # 理论上不应该到达这里
        if last_exception:
            raise last_exception
        else:
            raise Exception("LLM调用失败，原因未知")
    
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
        analysis_request = f"""The current task is: {task_description}

Here is the system prompt and work plan of the Agent whose progress you are supervising:
{agent_system_prompt if agent_system_prompt else '(No system prompt provided)'}

Based on the above conversation history and the Agent's work plan, please analyze:
0. 最重要的是检查是否完成了职责外的事情，警告 agent立即停止指责外的任务和无效操作！让其交给工具完成！
1. How far has the task progressed so far?
2. If there is no task list, summarize the task list; if there is, summarize which tasks have been completed.
3. What tasks still need to be completed?
4. What is the current execution status?
5. Is the Agent following its system prompt correctly? For example, if the prompt requires using specific tools to complete the task, but the Agent did not do so.
6. What should be the next step? Note: you should only suggest the next step for the current Agent!
7. Are there any current notes or reminders, such as missing any steps in the workflow?
8. Please list all possible file paths and descriptions that the Agent may use in the future to prevent omissions.
使用中文输出，最关键的是进度必须精准，例如 coding任务必须输出已经实现多少功能完成多少文件，文本处理功能必须输出已经修改了什么文件的多少行，第几行！
Please provide a concise but comprehensive analysis.
当你发现 agent 陷入死循环后，应该用严格严厉语气中英文警告 agent立即执行之后的工作，明确下一步的任务！
如果发现历史对话因为以外故障退出，你应该指出已经完成了什么工作，对应文件是什么，还有什么没完成，没完成的原因是什么。
"""
        
        analysis_history.append(ChatMessage(role="user", content=analysis_request))
        
        # 调用LLM进行分析（不使用工具）
        response = self._call_llm_with_retry(
            history=analysis_history,
            system_prompt=self.system_prompt
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
                         model_type: Union[str, ModelType] = "claude-3-7-sonnet-20250219") -> str:
    """
    便捷函数：分析任务进展
    
    Args:
        task_description (str): 任务描述
        conversation_history (List[ChatMessage]): 对话历史
        agent_system_prompt (str, optional): 原执行Agent的系统提示词
        model_type: 使用的模型类型，支持字符串或ModelType枚举
        
    Returns:
        str: 格式化的分析结果
    """
    thinking_agent = ThinkingAgent(model_type)
    analysis = thinking_agent.analyze_progress(task_description, conversation_history, agent_system_prompt)
    return thinking_agent.format_analysis_message(analysis)


if __name__ == "__main__":
    # 测试示例
    from baseService.llm_client import ChatMessage, get_model_from_config
    
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
    You are a Python project development assistant. Your tasks are:
    1. Create a clear project structure
    2. Implement file read/write functionality
    3. Implement data processing functionality
    4. Write test code
    5. Provide complete documentation
    
    Please follow best practices for development to ensure code quality and maintainability.
    """
    
    # 从配置文件获取可用模型
    available_model = get_model_from_config()
    print(f"使用模型: {available_model}")
    
    result = analyze_task_progress(
        task_description="Create a Python project with file read/write and data processing functionality",
        conversation_history=test_history,
        agent_system_prompt=test_system_prompt,
        model_type=available_model  # 直接使用字符串
    )
    
    print("分析结果：")
    print(result)
