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
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_root not in sys.path:
    sys.path.append(project_root)

# 延迟导入，避免循环依赖
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from baseService.llm_client import LLMClient, ChatMessage, ModelType, normalize_model_name


class ThinkingAgent:
    """
    思考Agent类，专门用于分析任务进展，不调用任何工具
    """
    
    def __init__(self, model_type = "claude-3-7-sonnet-20250219", max_retries: int = 3, retry_delay: float = 5.0):
        """
        初始化ThinkingAgent
        
        Args:
            model_type: 使用的LLM模型类型，支持字符串或ModelType枚举
            max_retries (int): 最大重试次数
            retry_delay (float): 重试延迟时间（秒）
        """
        # 延迟导入和初始化
        from baseService.llm_client import LLMClient, normalize_model_name
        
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
 你主要是监控另一个 agent 的任务进度或者分析未来计划！
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
并且一定不要输出 agent 无法使用的工具！
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
    
    def _call_llm_with_retry(self, history: List, system_prompt: str):
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
    
    def analyze_progress(self, task_description: str, conversation_history: List, agent_system_prompt: str = None, agent_name: str = None, is_first_thinking: bool = False, available_tools: List[str] = None, tools_descriptions: Dict[str, str] = None) -> str:
        """
        分析任务进展
        
        Args:
            task_description (str): 任务描述
            conversation_history (List[ChatMessage]): 对话历史
            agent_system_prompt (str, optional): 原执行Agent的系统提示词
            agent_name (str, optional): Agent名称，用于选择不同的thinking策略
            is_first_thinking (bool): 是否是首次thinking（行动前的规划）
            available_tools (List[str], optional): 可用工具列表
            tools_descriptions (Dict[str, str], optional): 工具描述字典
            
        Returns:
            str: 进展分析结果
        """
        # 确保最后一条不是用户消息为空的情况
        analysis_history = conversation_history.copy()
        
        # 检查最后一条消息是否是user角色
        if analysis_history and analysis_history[-1].role == "user":
            # 添加一个空的assistant消息
            from baseService.llm_client import ChatMessage
            analysis_history.append(ChatMessage(role="assistant", content="我来分析一下当前的任务进展。"))
        
        # 构建工具信息部分
        tools_info = ""
        if available_tools:
            tools_info = f"\n\n可用工具列表:\n"
            for tool in available_tools:
                tool_desc = tools_descriptions.get(tool, "无描述") if tools_descriptions else "无描述"
                tools_info += f"- {tool}: {tool_desc}\n"
        
        # 根据是否是首次thinking选择不同的分析请求
        if is_first_thinking:
            # 首次thinking：输出TODO清单和行动计划
            analysis_request = f"""The current task is: {task_description}

Agent名称: {agent_name if agent_name else 'Unknown Agent'}

下面是你需要分析的 agent 的提示词:
{agent_system_prompt if agent_system_prompt else '(No system prompt provided)'}

下面是这个agent 可以使用的工具列表，不要在计划中输出下面工具以外的工具！！：
**
{tools_info}
**
不要使用上面工具以外的工具加入到计划中！不要自己编工具类型！！！

这是Agent开始行动前的初始规划阶段，请分析并输出：
0. 罗列当前可以使用的工具列表。
1. **任务理解**：详细分析用户的需求和目标
2. **TODO清单**：列出完成此任务需要执行的具体步骤（按优先级排序）
3. **行动计划**：说明接下来的具体执行策略，主要是工具规划
4. **工具选择**：根据可用工具列表，即你第一步罗列出的列表，确定需要使用哪些工具及其使用顺序，不要使用外部工具！
（注意很多工具其实是其他 agent，具备很强的泛化能力，因此根据工具描述推测其包含的子能力来计划，其所有潜在能力都是可以调用的）
5. **预期产出**：说明完成后应该产生什么文件或结果
6. **注意事项**：特别需要注意的问题或限制

请使用中文输出，提供清晰的TODO清单和具体的行动计划。
不需要分析进度（因为还没开始行动）。
"""
        else:
            # 后续thinking：进展分析
            analysis_request = f"""The current task is: {task_description}

Agent名称: {agent_name if agent_name else 'Unknown Agent'}

下面是你需要分析的 agent 的提示词:
{agent_system_prompt if agent_system_prompt else '(No system prompt provided)'}

下面是这个agent 可以使用的工具列表，不要在计划中输出下面工具以外的工具！！：
**
{tools_info}
**
不要使用上面工具以外的工具加入到计划中！不要自己编工具类型！！！

这是Agent开始行动前的初始规划阶段，请分析并输出：
0. 罗列当前可以使用的工具列表。
1. **任务理解**：详细分析用户的需求和目标
2. **当前进度**：分析当前任务的进度，包括详细的已经完成的文件和文件地址和描述以及对于对应任务的作用是什么。
3. **行动计划**：说明接下来的具体执行策略，主要是工具规划
4. **工具选择**：根据可用工具列表，即你第一步罗列出的列表，确定需要使用哪些工具及其使用顺序，不要使用外部工具！
（注意很多工具其实是其他 agent，具备很强的泛化能力，因此根据工具描述推测其包含的子能力来计划，其所有潜在能力都是可以调用的）
5. **预期产出**：说明完成后应该产生什么文件或结果
6. **注意事项**：特别需要注意的问题或限制

请使用中文输出，提供清晰的TODO清单和具体的行动计划。
不需要分析进度（因为还没开始行动）。
"""
        
        from baseService.llm_client import ChatMessage
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
                         conversation_history: List,
                         agent_system_prompt: str = None,
                         agent_name: str = None,
                         is_first_thinking: bool = False,
                         available_tools: List[str] = None,
                         tools_descriptions: Dict[str, str] = None,
                         model_type = "claude-3-7-sonnet-20250219") -> str:
    """
    便捷函数：分析任务进展
    
    Args:
        task_description (str): 任务描述
        conversation_history (List[ChatMessage]): 对话历史
        agent_system_prompt (str, optional): 原执行Agent的系统提示词
        agent_name (str, optional): Agent名称
        is_first_thinking (bool): 是否是首次thinking
        model_type: 使用的模型类型，支持字符串或ModelType枚举
        
    Returns:
        str: 格式化的分析结果
    """
    thinking_agent = ThinkingAgent(model_type)
    analysis = thinking_agent.analyze_progress(task_description, conversation_history, agent_system_prompt, agent_name, is_first_thinking, available_tools, tools_descriptions)
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
