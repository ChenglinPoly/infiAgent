#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM 包装器 - 统一处理原生和基于提示词的工具调用
支持两种模式：
1. 原生 tool call 能力的模型
2. 通过提示词模拟工具调用的模型
"""

import json
import re
from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass, field
from enum import Enum
import litellm
from litellm import completion

@dataclass
class ToolCall:
    """工具调用信息"""
    id: str
    name: str
    arguments: Dict

@dataclass
class LLMResponse:
    """LLM响应"""
    status: str  # "success" or "error"
    output: str  # 模型输出内容
    error_information: str  # 错误信息
    model: str = ""  # 使用的模型
    usage: Dict = field(default_factory=dict)  # token使用情况
    finish_reason: str = ""  # 完成原因
    tool_calls: Optional[List[ToolCall]] = None  # 工具调用列表

class LLMWrapper:
    """
    LLM 包装器类
    统一处理原生和基于提示词的工具调用
    """
    
    def __init__(self, 
                 timeout: int = 1000,
                 num_retries: int = 3,
                 suppress_debug: bool = True):
        """
        初始化 LLM 包装器
        
        Args:
            timeout: 请求超时时间（秒）
            num_retries: 重试次数
            suppress_debug: 是否抑制调试信息
        """
        # 配置 LiteLLM
        litellm.suppress_debug_info = suppress_debug
        litellm.telemetry = False
        litellm.request_timeout = timeout
        litellm.num_retries = num_retries
    
    def _generate_tool_prompt(self, tools: List[Dict], language: str = "zh") -> str:
        """
        生成工具调用的提示词
        
        Args:
            tools: 工具定义列表
            language: 提示词语言 ("zh" 或 "en")
            
        Returns:
            str: 工具调用提示词
        """
        if not tools:
            return ""
        
        if language == "en":
            prompt = """
You can use the following tools to complete tasks. You can only call one tool at a time.

Available tools:
"""
        else:
            prompt = """
你可以使用以下工具来完成任务。每次只能调用一个工具。

可用工具：
"""
        
        for tool in tools:
            func_info = tool.get("function", tool)
            name = func_info.get("name", "")
            description = func_info.get("description", "")
            parameters = func_info.get("parameters", {})
            
            if language == "en":
                prompt += f"\nTool Name: {name}\n"
                prompt += f"Description: {description}\n"
                prompt += "Parameters:\n"
            else:
                prompt += f"\n工具名称: {name}\n"
                prompt += f"功能描述: {description}\n"
                prompt += "参数说明:\n"
            
            properties = parameters.get("properties", {})
            required = parameters.get("required", [])
            
            for param_name, param_info in properties.items():
                param_type = param_info.get("type", "string")
                param_desc = param_info.get("description", "")
                is_required = param_name in required
                
                if language == "en":
                    req_text = "[Required]" if is_required else "[Optional]"
                else:
                    req_text = "[必需]" if is_required else "[可选]"
                
                prompt += f"  - {param_name} ({param_type}){req_text}: {param_desc}\n"
            
            prompt += "\n"
        
        if language == "en":
            prompt += """
Please strictly follow this format:
你必须使用工具，即使你认为无需调用工具，但是每次最多调用一个工具！
<tool_name>tool_name</tool_name>
<tool_use:param_name1>param_value1</tool_use:param_name1>
<tool_use:param_name2>param_value2</tool_use:param_name2>

Notes:
1. Only one tool can be called at a time
2. Parameter values must meet type requirements
3. Required parameters cannot be omitted
4. If no tool is needed, answer the question directly

"""
        else:
            prompt += """
如果你需要调用工具，请按照以下格式返回：

<tool_name>工具名称</tool_name>
<tool_use:参数名1>参数值1</tool_use:参数名1>
<tool_use:参数名2>参数值2</tool_use:参数名2>

注意：
1. 每次只能调用一个工具
2. 参数值必须符合参数类型要求
3. 必需参数不能省略

"""
        return prompt
    
    def _generate_strict_tool_prompt(self, tools: List[Dict], language: str = "zh", retry_count: int = 0) -> str:
        """
        生成加强版的工具调用提示词（用于重试）
        
        Args:
            tools: 工具定义列表
            language: 提示词语言
            retry_count: 重试次数
            
        Returns:
            str: 加强版工具调用提示词
        """
        if not tools:
            return ""
        
        # 根据重试次数增强语气
        if language == "en":
            if retry_count == 0:
                urgency = "IMPORTANT"
            elif retry_count == 1:
                urgency = "CRITICAL - MUST FOLLOW FORMAT"
            else:
                urgency = "FINAL WARNING - STRICT COMPLIANCE REQUIRED"
            
            prompt = f"""
{urgency}: You MUST call a tool using the EXACT format specified below. No exceptions!

Available tools:
"""
        else:
            if retry_count == 0:
                urgency = "重要"
            elif retry_count == 1:
                urgency = "关键 - 必须遵循格式"
            else:
                urgency = "最后警告 - 严格遵守格式"
            
            prompt = f"""
{urgency}：你必须调用工具，严格按照下面指定的格式！绝无例外！

可用工具：
"""
        
        # 添加工具定义（简化版）
        for tool in tools:
            func_info = tool.get("function", tool)
            name = func_info.get("name", "")
            description = func_info.get("description", "")
            
            if language == "en":
                prompt += f"\n- {name}: {description}\n"
            else:
                prompt += f"\n- {name}: {description}\n"
        
        if language == "en":
            prompt += f"""
MANDATORY FORMAT (attempt {retry_count + 1}/{3}):
<tool_name>EXACT_TOOL_NAME</tool_name>
<tool_use:param_name>param_value</tool_use:param_name>

YOU MUST RESPOND WITH THIS XML FORMAT ONLY!
NO OTHER TEXT IS ALLOWED!
"""
        else:
            prompt += f"""
强制格式要求（第 {retry_count + 1}/{3} 次尝试）：
<tool_name>确切的工具名称</tool_name>
<tool_use:参数名>参数值</tool_use:参数名>

你必须只返回这种XML格式！
不允许其他任何文字！
"""
        
        return prompt
    
    def _parse_tool_call_from_text(self, text: str, tools: List[Dict]) -> Optional[ToolCall]:
        """
        从文本中解析工具调用
        
        Args:
            text: 模型输出的文本
            tools: 工具定义列表
            
        Returns:
            ToolCall: 解析出的工具调用，如果没有则返回None
        """
        if not text or not tools:
            return None
        
        # 提取工具名称
        tool_name_match = re.search(r'<tool_name>(.*?)</tool_name>', text, re.DOTALL)
        if not tool_name_match:
            return None
        
        tool_name = tool_name_match.group(1).strip()
        
        # 查找对应的工具定义
        tool_def = None
        for tool in tools:
            func_info = tool.get("function", tool)
            if func_info.get("name") == tool_name:
                tool_def = tool
                break
        
        if not tool_def:
            return None
        
        # 提取参数
        arguments = {}
        func_info = tool_def.get("function", tool_def)
        properties = func_info.get("parameters", {}).get("properties", {})
        
        # 查找所有参数
        param_pattern = r'<tool_use:([^>]+)>(.*?)</tool_use:\1>'
        param_matches = re.findall(param_pattern, text, re.DOTALL)
        
        for param_name, param_value in param_matches:
            param_name = param_name.strip()
            param_value = param_value.strip()
            
            if param_name in properties:
                param_type = properties[param_name].get("type", "string")
                
                # 根据参数类型转换值
                try:
                    if param_type == "integer":
                        arguments[param_name] = int(param_value)
                    elif param_type == "number":
                        arguments[param_name] = float(param_value)
                    elif param_type == "boolean":
                        arguments[param_name] = param_value.lower() in ("true", "1", "yes", "是", "真")
                    elif param_type == "array":
                        # 尝试解析为JSON数组
                        try:
                            arguments[param_name] = json.loads(param_value)
                        except:
                            # 如果JSON解析失败，尝试按逗号分割
                            arguments[param_name] = [item.strip() for item in param_value.split(",")]
                    elif param_type == "object":
                        # 尝试解析为JSON对象
                        try:
                            arguments[param_name] = json.loads(param_value)
                        except:
                            arguments[param_name] = param_value
                    else:
                        arguments[param_name] = param_value
                except (ValueError, TypeError):
                    # 如果转换失败，保持为字符串
                    arguments[param_name] = param_value
            else:
                # 如果参数不在定义中，也保留它
                arguments[param_name] = param_value
        
        # 生成工具调用ID
        tool_id = f"tool_{tool_name}_{abs(hash(text)) % 10000}"
        
        return ToolCall(
            id=tool_id,
            name=tool_name,
            arguments=arguments
        )
    
    def _normalize_model_name(self, model: str, api_base: str = None) -> str:
        """
        规范化模型名称，为 LiteLLM 添加适当的前缀
        
        Args:
            model: 原始模型名称
            api_base: API 基础 URL
            
        Returns:
            str: 规范化后的模型名称
        """
        # 如果提供了 custom API base URL，说明是 custom API
        # 所有 custom API 都是 OpenAI 格式，统一添加 openai/ 前缀
        if api_base and api_base != "https://api.openai.com/v1":
            # 所有 custom API 模型都添加 openai/ 前缀
            return f"openai/{model}"
        
        # 官方 API 的处理
        if api_base is None or "openai.com" in api_base:
            # OpenAI 官方 API 不需要前缀
            return model
        
        # 如果没有 api_base，根据模型名称判断提供商（用于官方 API）
        model_lower = model.lower()
        if any(x in model_lower for x in ["gpt", "o1", "o3", "chatgpt"]):
            return model  # OpenAI 模型不需要前缀
        elif "claude" in model_lower:
            return f"anthropic/{model}"
        elif "gemini" in model_lower:
            return f"gemini/{model}"
        elif "deepseek" in model_lower:
            return f"deepseek/{model}"
        elif "qwen" in model_lower:
            return f"qwen/{model}"
        else:
            # 默认返回原始名称
            return model
    
    def chat(self,
             messages: List[Dict],
             model: str,
             api_key: str = None,
             api_base: str = None,
             temperature: float = 0.0,
             max_tokens: int = None,
             tools: List[Dict] = None,
             tool_choice: str = "auto",
             tool_call_capability: bool = True,
             prompt_language: str = "zh",
             parallel_tool_calls: bool = False,
             max_retries: int = 3) -> LLMResponse:
        """
        发送聊天消息，支持原生和基于提示词的工具调用
        
        Args:
            messages: 消息列表
            model: 模型名称（不需要添加前缀，直接使用）
            api_key: API密钥
            api_base: API基础URL
            temperature: 温度参数
            max_tokens: 最大token数
            tools: 工具列表
            tool_choice: 工具选择策略
            tool_call_capability: 是否支持原生工具调用
            prompt_language: 提示词语言 ("zh" 或 "en")
            parallel_tool_calls: 是否允许并行工具调用
            max_retries: 提示词模式下的最大重试次数
            
        Returns:
            LLMResponse: 统一格式的响应
        """
        # 规范化模型名称
        normalized_model = self._normalize_model_name(model, api_base)
        
        # 基本请求参数
        base_kwargs = {
            "model": normalized_model,
            "temperature": temperature
        }
        
        if api_key:
            base_kwargs["api_key"] = api_key
        if api_base:
            base_kwargs["api_base"] = api_base
        if max_tokens and max_tokens > 0:
            base_kwargs["max_tokens"] = max_tokens
        
        # 处理工具调用
        is_tool_required = tool_choice in ["required", "any"] and tools and len(tools) > 0
        
        if tools and len(tools) > 0 and tool_call_capability:
            # 原生工具调用模式 - 直接调用，不需要重试
            return self._call_with_native_tools(base_kwargs, messages, tools, tool_choice, parallel_tool_calls)
        elif tools and len(tools) > 0 and not tool_call_capability:
            # 基于提示词的工具调用模式 - 可能需要重试
            return self._call_with_prompt_tools(base_kwargs, messages, tools, tool_choice, prompt_language, is_tool_required, max_retries)
        else:
            # 无工具调用
            return self._call_without_tools(base_kwargs, messages)
    
    def _call_with_native_tools(self, base_kwargs: Dict, messages: List[Dict], tools: List[Dict], 
                               tool_choice: str, parallel_tool_calls: bool) -> LLMResponse:
        """使用原生工具调用"""
        try:
            kwargs = base_kwargs.copy()
            kwargs["messages"] = messages.copy()
            kwargs["tools"] = tools
            
            if tool_choice == "any":
                kwargs["tool_choice"] = "required"
            else:
                kwargs["tool_choice"] = tool_choice
            
            if parallel_tool_calls:
                kwargs["parallel_tool_calls"] = True
            
            # 调试信息（可选）
            # print(f"🔧 发送给 LiteLLM 的参数:")
            # print(f"   model: {kwargs.get('model')}")
            # print(f"   tools: {len(kwargs.get('tools', []))} 个工具")
            # print(f"   tool_choice: {kwargs.get('tool_choice')}")
            # print(f"   messages: {len(kwargs.get('messages', []))} 条消息")
            
            # 调用 LiteLLM
            response = completion(**kwargs)
            return self._process_response(response, tools, True, base_kwargs["model"])
            
        except Exception as e:
            return self._handle_error(e, model)
    
    def _call_with_prompt_tools(self, base_kwargs: Dict, messages: List[Dict], tools: List[Dict],
                               tool_choice: str, prompt_language: str, is_tool_required: bool, max_retries: int) -> LLMResponse:
        """使用基于提示词的工具调用，支持重试"""
        
        # 准备初始消息（添加工具提示词）
        initial_messages = messages.copy()
        tool_prompt = self._generate_tool_prompt(tools, prompt_language)
        
        # 将工具提示词添加到系统消息或第一条消息
        if initial_messages and initial_messages[0].get("role") == "system":
            initial_messages[0]["content"] += "\n\n" + tool_prompt
        else:
            initial_messages.insert(0, {
                "role": "system",
                "content": tool_prompt
            })
        
        # 当前对话历史（会在重试中累积）
        current_messages = initial_messages.copy()
        
        for retry_count in range(max_retries + 1):
            try:
                kwargs = base_kwargs.copy()
                kwargs["messages"] = current_messages.copy()
                
                if retry_count > 0:
                    print(f"🔄 重试第 {retry_count} 次，添加强制要求")
                
                # 调试信息
                print(f"🔧 发送给 LiteLLM 的参数:")
                print(f"   model: {kwargs.get('model')}")
                print(f"   tools: {len(kwargs.get('tools', []))} 个工具")
                print(f"   tool_choice: {kwargs.get('tool_choice')}")
                print(f"   messages: {len(kwargs.get('messages', []))} 条消息")
                
                # 调用 LiteLLM
                response = completion(**kwargs)
                
                # 处理响应
                if response.choices and len(response.choices) > 0:
                    choice = response.choices[0]
                    message = choice.message
                    output_text = message.content or ""
                    
                    # 尝试解析工具调用
                    parsed_tool_call = self._parse_tool_call_from_text(output_text, tools)
                    
                    # 如果需要工具调用但没有解析出来，且还有重试机会
                    if is_tool_required and not parsed_tool_call and retry_count < max_retries:
                        print(f"⚠️ 未解析出工具调用，准备重试 (尝试 {retry_count + 1}/{max_retries + 1})")
                        
                        # 将模型的错误回复添加到历史中（仅用于重试，不影响最终返回）
                        current_messages.append({
                            "role": "assistant", 
                            "content": output_text
                        })
                        
                        # 生成强制要求的用户消息（仅用于重试）
                        if prompt_language == "en":
                            if retry_count == 0:
                                force_message = "You did not call the tool as required. You MUST call a tool using the exact XML format: <tool_name>tool_name</tool_name><tool_use:param>value</tool_use:param>"
                            elif retry_count == 1:
                                force_message = "CRITICAL: You are still not following the tool calling format! You MUST respond with ONLY the XML format. No other text allowed!"
                            else:
                                force_message = "FINAL WARNING: Use the exact XML format NOW: <tool_name>tool_name</tool_name><tool_use:param>value</tool_use:param>. Nothing else!不允许其他内容！并且不要要求我提供任何额外信息！！"
                        else:
                            if retry_count == 0:
                                force_message = "你没有按要求调用工具。你必须使用确切的XML格式调用工具：<tool_name>工具名</tool_name><tool_use:参数>值</tool_use:参数>"
                            elif retry_count == 1:
                                force_message = "输出工具调用的xml 格式信息，注意你的提示词!!"
                            else:
                                force_message = "最后警告：立即使用确切的XML格式：<tool_name>工具名</tool_name><tool_use:参数>值</tool_use:参数>。不允许其他内容！即使你不知道应该干什么，也直接选出一个大概率可行的工具进行输出！！而不是输出其他任何内容！"
                        
                        # 添加强制要求的用户消息（仅用于重试）
                        current_messages.append({
                            "role": "user",
                            "content": force_message
                        })


                        
                        continue
                    
                    # 构建最终响应 - 重要：只返回最后一次成功的输出，不包含重试过程
                    tool_calls = [parsed_tool_call] if parsed_tool_call else None
                    
                    # 如果解析出了工具调用，清空输出文本，避免返回XML格式
                    if parsed_tool_call:
                        final_output = ""  # 工具调用时不返回原始XML文本
                    else:
                        final_output = output_text  # 没有工具调用时返回原始文本
                    
                    return self._process_response(response, tools, False, base_kwargs["model"], tool_calls, final_output)
                else:
                    if retry_count < max_retries:
                        print(f"⚠️ 响应格式异常，准备重试")
                        continue
                    else:
                        return LLMResponse(
                            status="error",
                            output="",
                            error_information="响应格式异常：缺少choices字段",
                            model=base_kwargs["model"]
                        )
                        
            except Exception as e:
                if retry_count < max_retries:
                    print(f"⚠️ 调用出错，准备重试: {str(e)}")
                    continue
                else:
                    return self._handle_error(e, base_kwargs["model"])
        
        # 如果所有重试都失败了
        return LLMResponse(
            status="error",
            output="",
            error_information="所有重试都失败了",
            model=base_kwargs["model"]
        )
    
    def _call_without_tools(self, base_kwargs: Dict, messages: List[Dict]) -> LLMResponse:
        """无工具调用的简单聊天"""
        try:
            kwargs = base_kwargs.copy()
            kwargs["messages"] = messages.copy()
            
            response = completion(**kwargs)
            return self._process_response(response, None, False, base_kwargs["model"])
            
        except Exception as e:
            return self._handle_error(e, base_kwargs["model"])
    
    def _process_response(self, response, tools: List[Dict] = None, is_native_tools: bool = False, 
                         model: str = "", tool_calls: List[ToolCall] = None, output_text: str = None) -> LLMResponse:
        """处理 LiteLLM 响应"""
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            message = choice.message
            
            if output_text is None:
                output_text = message.content or ""
            
            # 处理工具调用
            if tool_calls is None:
                tool_calls = []
                if tools and is_native_tools:
                    # 原生工具调用解析
                    if hasattr(message, 'tool_calls') and message.tool_calls:
                        for tool_call in message.tool_calls:
                            try:
                                arguments = json.loads(tool_call.function.arguments)
                            except (json.JSONDecodeError, AttributeError):
                                arguments = {}
                            
                            tool_calls.append(ToolCall(
                                id=tool_call.id,
                                name=tool_call.function.name,
                                arguments=arguments
                            ))
            
            # 处理使用情况
            usage = {}
            if hasattr(response, 'usage') and response.usage:
                usage = {
                    "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                    "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
                    "total_tokens": getattr(response.usage, 'total_tokens', 0)
                }
            
            return LLMResponse(
                status="success",
                output=output_text,
                error_information="",
                model=response.model or model,
                usage=usage,
                finish_reason=choice.finish_reason or "unknown",
                tool_calls=tool_calls if tool_calls else None
            )
        else:
            return LLMResponse(
                status="error",
                output="",
                error_information="响应格式异常：缺少choices字段",
                model=model
            )
    
    def _handle_error(self, e: Exception, model: str) -> LLMResponse:
        """处理错误"""
        error_msg = str(e)
        
        # 分类错误类型
        if "timeout" in error_msg.lower():
            error_info = "请求超时"
        elif "connection" in error_msg.lower():
            error_info = "网络连接错误"
        elif "unauthorized" in error_msg.lower() or "invalid_api_key" in error_msg.lower():
            error_info = "API密钥无效或未授权"
        elif "rate_limit" in error_msg.lower():
            error_info = "超出速率限制"
        else:
            error_info = f"未知错误: {error_msg}"
        
        return LLMResponse(
            status="error",
            output="",
            error_information=error_info,
            model=model
        )
    
    def get_supported_models(self) -> Dict[str, List[str]]:
        """
        获取支持的模型列表
        
        Returns:
            Dict: 按提供商分类的模型列表
        """
        return {
            "openai": [
                "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo",
                "o1", "o1-mini", "o1-preview", "o3-mini", "o4-mini",
                "chatgpt-4o-latest"
            ],
            "anthropic": [
                "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022",
                "claude-3-7-sonnet-20250219", "claude-4-sonnet-20250514",
                "claude-4-opus-20250514"
            ],
            "google": [
                "gemini-2.0-flash", "gemini-2.5-flash", "gemini-2.5-pro",
                "gemini-2.5-pro-preview-03-25"
            ],
            "deepseek": [
                "deepseek-r1", "deepseek-v3", "deepseek-r1-250120",
                "deepseek-r1-250528", "deepseek-v3-250324"
            ],
            "qwen": [
                "qwen-max-latest", "qwen-plus-latest", "qwen-turbo-latest",
                "qwen3-235b-a22b", "qwen3-32b"
            ]
        }
    
    def is_model_supports_native_tools(self, model: str) -> bool:
        """
        检查模型是否支持原生工具调用
        
        Args:
            model: 模型名称
            
        Returns:
            bool: 是否支持原生工具调用
        """
        # 大部分现代模型都支持原生工具调用
        # 这里可以根据实际情况调整
        unsupported_patterns = [
            "text-", "davinci", "curie", "babbage", "ada",  # OpenAI 旧模型
            "claude-1", "claude-2",  # Claude 旧版本
        ]
        
        model_lower = model.lower()
        for pattern in unsupported_patterns:
            if pattern in model_lower:
                return False
        
        return True
