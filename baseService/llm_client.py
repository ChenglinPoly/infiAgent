#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM API 客户端
提供简单易用的接口来调用多种大语言模型
"""

import json
import yaml
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import traceback
from openai import OpenAI
from anthropic import Anthropic

# 导入消息处理工具
try:
    from .message_utils import preprocess_messages_for_llm
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    from message_utils import preprocess_messages_for_llm

class ModelType(Enum):
    """模型类型枚举"""
    # OpenAI 模型
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_3_5_TURBO = "gpt-3.5-turbo"
    O1 = "o1"
    o3="o3"
    O1_MINI = "o1-mini"
    O1_PREVIEW = "o1-preview"
    O3_MINI = "o3-mini"
    O4_MINI = "o4-mini"
    CHATGPT_4O_LATEST = "chatgpt-4o-latest"
    GPT_4_5_PREVIEW = "gpt-4.5-preview"
    GPT_4_1 = "gpt-4.1"
    GPT_4_1_MINI = "gpt-4.1-mini"
    GPT_4_1_NANO = "gpt-4.1-nano"
    
    # Claude 模型
    CLAUDE_3_5_SONNET = "claude-3-5-sonnet-20241022"
    CLAUDE_3_5_HAIKU = "claude-3-5-haiku-20241022"
    CLAUDE_3_7_SONNET = "claude-3-7-sonnet-20250219"
    CLAUDE_4_SONNET = "claude-sonnet-4-20250514"
    CLAUDE_4_OPUS = "claude-opus-4-20250514"
    
    # DeepSeek 模型
    DEEPSEEK_R1 = "deepseek-r1"
    DEEPSEEK_V3 = "deepseek-v3"
    DEEPSEEK_R1_250120 = "deepseek-r1-250120"
    DEEPSEEK_R1_250528 = "deepseek-r1-250528"
    DEEPSEEK_V3_250324 = "deepseek-v3-250324"
    
    # Gemini 模型
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_PRO_PREVIEW = "gemini-2.5-pro-preview-03-25"
    
    # 通义千问模型
    QWEN_MAX = "qwen-max-latest"
    QWEN_PLUS = "qwen-plus-latest"
    QWEN_TURBO = "qwen-turbo-latest"
    QWEN3_235B = "qwen3-235b-a22b"
    QWEN3_32B = "qwen3-32b"
    
    # 其他模型
    DOUBAO_1_5_PRO = "doubao-1-5-pro-256k-250115"
    DOUBAO_1_5_THINKING = "doubao-1-5-thinking-pro-250415"
    GROK_3 = "grok-3"
    GROK_3_MINI = "grok-3-mini"
    GROK_4 = "grok-4"

@dataclass
class ChatMessage:
    """聊天消息"""
    role: str  # "user", "assistant", "system"
    content: str

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
    usage: Dict = None  # token使用情况
    finish_reason: str = ""  # 完成原因
    tool_calls: List[ToolCall] = None  # 工具调用列表

class ToolManager:
    """工具管理器"""
    
    def __init__(self, config_file: str = "tools_config.yaml"):
        self.config_file = config_file
        self.tools_config = self._load_tools_config()
    
    def _load_tools_config(self) -> Dict:
        """加载工具配置"""
        try:
            config_path = Path(self.config_file)
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            else:
                return {"tools": {}}
        except Exception as e:
            print(f"加载工具配置失败: {e}")
            return {"tools": {}}
    
    def get_tool_definition_openai(self, tool_name: str) -> Dict:
        """获取单个工具定义 (OpenAI 格式)"""
        tool_config = self.tools_config.get("tools", {}).get(tool_name)
        if not tool_config:
            return None
        
        return {
            "type": "function",
            "function": {
                "name": tool_config["name"],
                "description": tool_config["description"],
                "parameters": tool_config["parameters"]
            }
        }
    
    def get_tool_definition_anthropic(self, tool_name: str) -> Dict:
        """获取单个工具定义 (Anthropic 格式)"""
        tool_config = self.tools_config.get("tools", {}).get(tool_name)
        if not tool_config:
            return None
        
        return {
            "name": tool_config["name"],
            "description": tool_config["description"],
            "input_schema": tool_config["parameters"]
        }
    
    def get_tools_definitions_openai(self, tool_list: List[str]) -> List[Dict]:
        """获取多个工具定义 (OpenAI 格式)"""
        tools = []
        for tool_name in tool_list:
            tool_def = self.get_tool_definition_openai(tool_name)
            if tool_def:
                tools.append(tool_def)
            else:
                print(f"警告: 工具 '{tool_name}' 未找到")
        return tools
    
    def get_tools_definitions_anthropic(self, tool_list: List[str]) -> List[Dict]:
        """获取多个工具定义 (Anthropic 格式)"""
        tools = []
        for tool_name in tool_list:
            tool_def = self.get_tool_definition_anthropic(tool_name)
            if tool_def:
                tools.append(tool_def)
            else:
                print(f"警告: 工具 '{tool_name}' 未找到")
        return tools
    
    def get_available_tools(self) -> List[str]:
        """获取所有可用工具名称"""
        return list(self.tools_config.get("tools", {}).keys())

class LLMClient:
    """LLM API 客户端"""
    
    def __init__(self, api_key: str = None, base_url: str = None, tools_config_file: str = None):
        self.api_key = api_key or "sk-REDACTED"
        self.base_url = base_url or "https://api2.road2all.com"
        
        # 初始化 OpenAI 客户端
        self.openai_client = OpenAI(
            api_key=self.api_key,
            base_url=f"{self.base_url}/v1"
        )
        
        # 初始化 Anthropic 客户端
        self.anthropic_client = Anthropic(
            api_key=self.api_key,
            base_url=f"{self.base_url}/"
        )
        
        # 设置默认工具配置文件路径
        if tools_config_file is None:
            # 获取当前文件所在目录
            current_dir = Path(__file__).parent
            tools_config_file = str(current_dir / "tools_config.yaml")
        
        self.tool_manager = ToolManager(tools_config_file)
    
    def _is_claude_model(self, model: ModelType) -> bool:
        """判断是否为 Claude 模型"""
        claude_models = [
            ModelType.CLAUDE_3_5_SONNET,
            ModelType.CLAUDE_3_5_HAIKU, 
            ModelType.CLAUDE_3_7_SONNET,
            ModelType.CLAUDE_4_SONNET,
            ModelType.CLAUDE_4_OPUS
        ]
        return model in claude_models
    
    def _convert_anthropic_to_standard_usage(self, usage) -> Dict:
        """将 Anthropic usage 格式转换为标准格式"""
        if not usage:
            return {}
        
        return {
            "prompt_tokens": getattr(usage, 'input_tokens', 0),
            "completion_tokens": getattr(usage, 'output_tokens', 0),
            "total_tokens": getattr(usage, 'input_tokens', 0) + getattr(usage, 'output_tokens', 0)
        }
    
    def _preprocess_history(self, history: List[ChatMessage]) -> List[Dict[str, str]]:
        """预处理对话历史"""
        # 转换为字典格式
        message_dicts = []
        for msg in history:
            message_dicts.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 使用消息处理工具预处理
        processed_messages = preprocess_messages_for_llm(
            message_dicts, 
            clean_tool_calls=True, 
            ensure_alternating=True
        )
        
        return processed_messages
    
    def _call_with_anthropic(self, 
                           history: List[ChatMessage],
                           model: ModelType,
                           system_prompt: str = None,
                           temperature: float = 0.7,
                           max_tokens: int = None,
                           tool_list: List[str] = None,
                           tool_choice: Union[str, Dict] = "any") -> LLMResponse:
        """使用 Anthropic 客户端进行调用"""
        try:
            # 预处理消息历史
            processed_messages = self._preprocess_history(history)
            
            messages = []
            # Anthropic 不支持 system 消息在 messages 中，需要单独处理
            for msg in processed_messages:
                if msg["role"] != "system":  # 跳过 system 消息，它们会在 system 参数中处理
                    messages.append({"role": msg["role"], "content": msg["content"]})
            
            f=open('messages.json','w', encoding='utf-8')
            f.write(json.dumps(messages, ensure_ascii=False, indent=2))
            f.close()
            
            # 构建请求参数
            kwargs = {
                "model": model.value,
                "messages": messages,
                "max_tokens": max_tokens or 10000  # Anthropic 要求必须有 max_tokens
            }
            
            # 添加系统提示
            if system_prompt:
                kwargs["system"] = system_prompt
            tool_choice="any"
            # 添加工具定义
            if tool_list:
                tools = self.tool_manager.get_tools_definitions_anthropic(tool_list)
                if tools:
                    kwargs["tools"] = tools
                    
                    # 处理工具选择策略
                    if tool_choice == "any":
                        kwargs["tool_choice"] = {"type": "any"}
                        print(f"🔧 强制 Claude 从 {len(tools)} 个工具中选择任意一个")
                    elif tool_choice == "auto":
                        kwargs["tool_choice"] = {"type": "auto"}
                        print(f"🤖 允许 Claude 自动决定是否使用工具")
                    elif tool_choice == "none":
                        # 如果不使用工具，则移除工具定义
                        del kwargs["tools"]
                        print(f"🚫 禁止 Claude 使用任何工具")
                    elif isinstance(tool_choice, dict) and "name" in tool_choice:
                        # 强制使用特定工具
                        kwargs["tool_choice"] = {"type": "tool", "name": tool_choice["name"]}
                        print(f"🎯 强制 Claude 使用工具: {tool_choice['name']}")
                    elif isinstance(tool_choice, dict):
                        # 直接使用字典格式的tool_choice
                        kwargs["tool_choice"] = tool_choice
                        print(f"🔧 使用自定义工具选择策略: {tool_choice}")
            
            # 发送请求
            response = self.anthropic_client.messages.create(**kwargs)
            
            # 处理响应
            output_text = ""
            tool_calls = []

            print(response.content,'这次的回复')
            
            if response.content:
                for content_block in response.content:
                    if content_block.type == 'text':
                        output_text += content_block.text
                    elif content_block.type == 'tool_use':
                        tool_calls.append(ToolCall(
                            id=content_block.id,
                            name=content_block.name,
                            arguments=content_block.input
                        ))
            
            return LLMResponse(
                status="success",
                output=output_text,
                error_information="",
                model=response.model,
                usage=self._convert_anthropic_to_standard_usage(response.usage),
                finish_reason=response.stop_reason or "unknown",
                tool_calls=tool_calls if tool_calls else None
            )
            
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return LLMResponse(
                    status="error",
                    output="",
                    error_information="请求超时",
                    model=model.value
                )
            elif "connection" in error_msg.lower():
                return LLMResponse(
                    status="error",
                    output="",
                    error_information="网络连接错误",
                    model=model.value
                )
            else:
                return LLMResponse(
                    status="error",
                    output="",
                    error_information=f"未知错误: {error_msg}",
                    model=model.value
                )
    
    def _call_with_openai(self,
                         history: List[ChatMessage],
                         model: ModelType,
                         system_prompt: str = None,
                         temperature: float = 0.7,
                         max_tokens: int = None,
                         tool_list: List[str] = None,
                         tool_choice: Union[str, Dict] = "required",
                         parallel_tool_calls: bool = False) -> LLMResponse:
        """使用 OpenAI 客户端进行调用"""
        try:
            # 预处理消息历史
            processed_messages = self._preprocess_history(history)
            
            messages = []
            
            # 添加系统提示
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # 添加预处理后的对话历史
            for msg in processed_messages:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # 构建请求参数
            kwargs = {
                "model": model.value,
                "messages": messages,
                "temperature": temperature
            }
            
            # 仅在设置了max_tokens时才添加该参数
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            
            # 添加工具定义
            if tool_list:
                tools = self.tool_manager.get_tools_definitions_openai(tool_list)
                
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice
                    kwargs["parallel_tool_calls"] = parallel_tool_calls
            
            # 发送请求
            response = self.openai_client.chat.completions.create(**kwargs)
            
            # 处理响应
            if response.choices and len(response.choices) > 0:
                choice = response.choices[0]
                message = choice.message
                
                # 处理工具调用
                tool_calls = []
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_calls.append(ToolCall(
                            id=tool_call.id,
                            name=tool_call.function.name,
                            arguments=json.loads(tool_call.function.arguments)
                        ))
                
                return LLMResponse(
                    status="success",
                    output=message.content or "",
                    error_information="",
                    model=response.model,
                    usage=response.usage.model_dump() if response.usage else {},
                    finish_reason=choice.finish_reason or "unknown",
                    tool_calls=tool_calls if tool_calls else None
                )
            else:
                return LLMResponse(
                    status="error",
                    output="",
                    error_information="响应格式异常：缺少choices字段",
                    model=model.value
                )
                
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return LLMResponse(
                    status="error",
                    output="",
                    error_information="请求超时",
                    model=model.value
                )
            elif "connection" in error_msg.lower():
                return LLMResponse(
                    status="error",
                    output="",
                    error_information="网络连接错误",
                    model=model.value
                )
            else:
                return LLMResponse(
                    status="error",
                    output="",
                    error_information=f"未知错误: {error_msg}",
                    model=model.value
                )
    
    def chat(self, 
             history: List[ChatMessage],
             model: ModelType = ModelType.GPT_4O_MINI,
             system_prompt: str = None,
             temperature: float = 0.7,
             max_tokens: int = None,
             tool_list: List[str] = None,
             tool_choice: Union[str, Dict] = "any",
             parallel_tool_calls: bool = False) -> LLMResponse:
        """
        发送聊天消息
        
        Args:
            history: 对话历史，最后一个消息应该是用户的最新输入
            model: 使用的模型
            system_prompt: 系统提示
            temperature: 温度参数
            max_tokens: 最大token数（可选，不设置则自然停止）
            tool_list: 工具列表，工具名称列表
            tool_choice: 工具选择策略 ("auto", "none", 或 {"type": "function", "function": {"name": "工具名"}})
            parallel_tool_calls: 是否允许并行工具调用，False表示每次最多调用一个工具
        
        Returns:
            LLMResponse: 统一格式的响应
        """
        if not history:
            return LLMResponse(
                status="error",
                output="",
                error_information="对话历史不能为空",
                model=model.value
            )
        
        # 基本验证将在预处理中完成，这里只做基础检查
        valid_history = [msg for msg in history if msg.content and msg.content.strip()]
        if not valid_history:
            return LLMResponse(
                status="error",
                output="",
                error_information="对话历史中没有有效消息",
                model=model.value
            )
        
        # 根据模型类型选择不同的客户端
        if self._is_claude_model(model):
            print(f"🎭 使用 Anthropic 客户端调用 {model.value}")
            return self._call_with_anthropic(
                history=valid_history,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                tool_list=tool_list,
                tool_choice=tool_choice
            )
        else:
            if tool_choice == "any":
                tool_choice = "required"
            print(f"🤖 使用 OpenAI 客户端调用 {model.value}")
            return self._call_with_openai(
                history=valid_history,
                model=model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                tool_list=tool_list,
                tool_choice=tool_choice,
                parallel_tool_calls=parallel_tool_calls
            )
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        try:
            # 尝试从 OpenAI 客户端获取
            models = self.openai_client.models.list()
            return [model.id for model in models.data]
        except Exception:
            return []

# 使用示例
def main():
    """使用示例"""
    client = LLMClient()
    
    print("🚀 LLM客户端测试 (支持 OpenAI 和 Anthropic)")
    
    # 显示可用工具
    print("\n📋 可用工具:")
    available_tools = client.tool_manager.get_available_tools()
    for tool in available_tools:
        print(f"  - {tool}")
    
    # 测试消息预处理功能
    print("\n🧪 测试消息预处理功能")
    
    # 模拟连续用户消息的情况
    problematic_history = [
        ChatMessage(role="user", content="创建一个图"),
        ChatMessage(role="user", content="继续,注意不要在内容中调用工具"),
        ChatMessage(role="assistant", content='{"tool_calls": [{"id": "123", "name": "test"}]}'),
        ChatMessage(role="user", content="请继续"),
    ]
    
    response = client.chat(
        history=problematic_history,
        model=ModelType.GPT_4O_MINI,
        tool_list=["file_write"]
    )
    
    print(f"状态: {response.status}")
    print(f"模型: {response.model}")
    print(f"输出: {response.output}")
    if response.tool_calls:
        print("🛠️ 工具调用:")
        for tool_call in response.tool_calls:
            print(f"  - 工具: {tool_call.name}")
            print(f"  - 参数: {tool_call.arguments}")

if __name__ == "__main__":
    main()