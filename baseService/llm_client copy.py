#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM API 客户端
提供简单易用的接口来调用多种大语言模型
支持 OpenAI、Claude、Gemini 三大厂商的官方和自定义 API
"""

import json
import yaml
import os
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import traceback
from openai import OpenAI
from anthropic import Anthropic

# 导入 Google GenAI SDK
try:
    from google import genai
    from google.genai import types as genai_types
    HAS_GOOGLE_GENAI = True
except ImportError:
    HAS_GOOGLE_GENAI = False
    print("警告：未安装 google-genai 库，Gemini 原生 API 功能将不可用。请运行: pip install google-genai")

# 导入消息处理工具
try:
    from .message_utils import preprocess_messages_for_llm
    from .config_merger import ensure_merged_config
except ImportError:
    # 如果相对导入失败，尝试绝对导入
    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    from message_utils import preprocess_messages_for_llm
    from config_merger import ensure_merged_config

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

class LLMConfigManager:
    """LLM 配置管理器"""
    
    def __init__(self, config_file: str = None):
        if config_file is None:
            current_dir = Path(__file__).parent.parent
            config_file = str(current_dir / "config" / "run_env_config" / "llm_config.yaml")
        
        self.config_file = config_file
        self.config = self._load_config()
        self._load_env_variables()
    
    def _load_config(self) -> Dict:
        """加载配置文件"""
        try:
            config_path = Path(self.config_file)
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
            else:
                print(f"警告：配置文件 {self.config_file} 不存在，使用默认配置")
                return self._get_default_config()
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "default": {
                "force_tool_calling": True,
                "temperature": 0,
                "max_tokens": 10000
            },
            "openai": {"official": {}, "custom": {}},
            "claude": {"official": {}, "custom": {}},
            "gemini": {"official": {}, "custom": {}}
        }
    
    def _load_env_variables(self):
        """从环境变量加载 API 配置（环境变量优先级高于配置文件）"""
        # OpenAI 配置
        if os.getenv('OPENAI_API_KEY'):
            if not self.config['openai']['official'].get('api_key'):
                self.config['openai']['official']['api_key'] = os.getenv('OPENAI_API_KEY')
        if os.getenv('OPENAI_CUSTOM_API_KEY'):
            self.config['openai']['custom']['api_key'] = os.getenv('OPENAI_CUSTOM_API_KEY')
        if os.getenv('OPENAI_CUSTOM_BASE_URL'):
            self.config['openai']['custom']['base_url'] = os.getenv('OPENAI_CUSTOM_BASE_URL')
        if os.getenv('OPENAI_CUSTOM_MODELS'):
            self.config['openai']['custom']['models'] = os.getenv('OPENAI_CUSTOM_MODELS').split(',')
        
        # Claude 配置
        if os.getenv('ANTHROPIC_API_KEY'):
            if not self.config['claude']['official'].get('api_key'):
                self.config['claude']['official']['api_key'] = os.getenv('ANTHROPIC_API_KEY')
        if os.getenv('CLAUDE_CUSTOM_API_KEY'):
            self.config['claude']['custom']['api_key'] = os.getenv('CLAUDE_CUSTOM_API_KEY')
        if os.getenv('CLAUDE_CUSTOM_BASE_URL'):
            self.config['claude']['custom']['base_url'] = os.getenv('CLAUDE_CUSTOM_BASE_URL')
        if os.getenv('CLAUDE_CUSTOM_MODELS'):
            self.config['claude']['custom']['models'] = os.getenv('CLAUDE_CUSTOM_MODELS').split(',')
        
        # Gemini 配置
        if os.getenv('GEMINI_API_KEY'):
            if not self.config['gemini']['official'].get('api_key'):
                self.config['gemini']['official']['api_key'] = os.getenv('GEMINI_API_KEY')
        if os.getenv('GEMINI_CUSTOM_API_KEY'):
            self.config['gemini']['custom']['api_key'] = os.getenv('GEMINI_CUSTOM_API_KEY')
        if os.getenv('GEMINI_CUSTOM_BASE_URL'):
            self.config['gemini']['custom']['base_url'] = os.getenv('GEMINI_CUSTOM_BASE_URL')
        if os.getenv('GEMINI_CUSTOM_MODELS'):
            self.config['gemini']['custom']['models'] = os.getenv('GEMINI_CUSTOM_MODELS').split(',')
    
    def get_provider_config(self, provider: str, use_custom: bool = False) -> Dict:
        """获取提供商配置"""
        provider_config = self.config.get(provider, {})
        config_type = "custom" if use_custom else "official"
        return provider_config.get(config_type, {})
    
    def get_default_config(self) -> Dict:
        """获取默认配置"""
        return self.config.get("default", {})
    
    def get_config_status(self) -> Dict:
        """获取当前配置状态（用于调试）"""
        status = {}
        for provider in ["openai", "claude", "gemini"]:
            provider_config = self.config.get(provider, {})
            status[provider] = {
                "official": {
                    "has_api_key": bool(provider_config.get("official", {}).get("api_key")),
                    "base_url": provider_config.get("official", {}).get("base_url", ""),
                    "models_count": len(provider_config.get("official", {}).get("models", []))
                },
                "custom": {
                    "has_api_key": bool(provider_config.get("custom", {}).get("api_key")),
                    "base_url": provider_config.get("custom", {}).get("base_url", ""),
                    "models_count": len(provider_config.get("custom", {}).get("models", []))
                }
            }
        return status

class ToolManager:
    """工具管理器"""
    
    def __init__(self, config_file: str = "agent_configs.yaml"):
        self.config_file = config_file
        self.tools_config = self._load_tools_config()
    
    def _load_tools_config(self) -> Dict:
        """加载工具配置"""
        try:
            # 确保配置文件是最新的合并版本
            ensure_merged_config()
            
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
    
    def get_tool_definition_gemini(self, tool_name: str) -> Dict:
        """获取单个工具定义 (Gemini 格式)"""
        tool_config = self.tools_config.get("tools", {}).get(tool_name)
        if not tool_config:
            return None
        
        return {
            "name": tool_config["name"],
            "description": tool_config["description"],
            "parameters_json_schema": tool_config["parameters"]
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
    
    def get_tools_definitions_gemini(self, tool_list: List[str]) -> List[Dict]:
        """获取多个工具定义 (Gemini 格式)"""
        tools = []
        for tool_name in tool_list:
            tool_def = self.get_tool_definition_gemini(tool_name)
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
    
    def __init__(self, 
                 config_file: str = None, 
                 tools_config_file: str = None,
                 use_custom_apis: bool = False):
        """
        初始化 LLM 客户端
        
        Args:
            config_file: LLM 配置文件路径
            tools_config_file: 工具配置文件路径
            use_custom_apis: 是否优先使用自定义 API
        """
        # 初始化配置管理器
        self.config_manager = LLMConfigManager(config_file)
        self.use_custom_apis = use_custom_apis
        
        # 初始化工具管理器
        if tools_config_file is None:
            current_dir = Path(__file__).parent
            tools_config_file = str(current_dir / "agent_configs.yaml")
        self.tool_manager = ToolManager(tools_config_file)
        
        # 初始化各厂商客户端
        self._init_openai_client()
        self._init_anthropic_client()
        self._init_gemini_client()
    
    def _init_openai_client(self):
        """初始化 OpenAI 客户端"""
        self.openai_client = None
        self.openai_custom_client = None
        
        # 官方 API
        official_config = self.config_manager.get_provider_config("openai", False)
        if official_config.get("api_key"):
            self.openai_client = OpenAI(
                api_key=official_config["api_key"],
                base_url=official_config.get("base_url", "https://api.openai.com/v1")
            )
        
        # 自定义 API
        custom_config = self.config_manager.get_provider_config("openai", True)
        if custom_config.get("api_key") and custom_config.get("base_url"):
            self.openai_custom_client = OpenAI(
                api_key=custom_config["api_key"],
                base_url=custom_config["base_url"]
            )
    
    def _init_anthropic_client(self):
        """初始化 Anthropic 客户端"""
        self.anthropic_client = None
        self.anthropic_custom_client = None
        
        # 官方 API
        official_config = self.config_manager.get_provider_config("claude", False)
        if official_config.get("api_key"):
            self.anthropic_client = Anthropic(
                api_key=official_config["api_key"],
                base_url=official_config.get("base_url", "https://api.anthropic.com")
            )
        
        # 自定义 API
        custom_config = self.config_manager.get_provider_config("claude", True)
        if custom_config.get("api_key") and custom_config.get("base_url"):
            self.anthropic_custom_client = Anthropic(
                api_key=custom_config["api_key"],
                base_url=custom_config["base_url"]
            )
    
    def _init_gemini_client(self):
        """初始化 Gemini 客户端"""
        self.gemini_client = None
        self.gemini_custom_client = None
        
        if not HAS_GOOGLE_GENAI:
            return
        
        # 官方 API
        official_config = self.config_manager.get_provider_config("gemini", False)
        if official_config.get("api_key"):
            try:
                self.gemini_client = genai.Client(api_key=official_config["api_key"])
            except Exception as e:
                print(f"初始化 Gemini 官方客户端失败: {e}")
        
        # 自定义 API（通过 OpenAI 兼容接口）
        custom_config = self.config_manager.get_provider_config("gemini", True)
        if custom_config.get("api_key") and custom_config.get("base_url"):
            self.gemini_custom_client = OpenAI(
                api_key=custom_config["api_key"],
                base_url=custom_config["base_url"]
            )

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
    
    def _is_gemini_model(self, model: ModelType) -> bool:
        """判断是否为 Gemini 模型"""
        gemini_models = [
            ModelType.GEMINI_2_0_FLASH,
            ModelType.GEMINI_2_5_FLASH,
            ModelType.GEMINI_2_5_PRO,
            ModelType.GEMINI_2_5_PRO_PREVIEW
        ]
        return model in gemini_models
    
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
                           temperature: float = 0.0,
                           max_tokens: int = 10000,
                           tool_list: List[str] = None,
                           tool_choice: Union[str, Dict] = "any") -> LLMResponse:
        """使用 Anthropic 客户端进行调用"""
        # 选择客户端
        client = self.anthropic_custom_client if self.use_custom_apis and self.anthropic_custom_client else self.anthropic_client
        if not client:
            return LLMResponse(
                status="error",
                output="",
                error_information="Anthropic 客户端未初始化，请检查 API 密钥配置",
                model=model.value
            )
        
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
                "max_tokens": max_tokens or 10000,  # Anthropic 要求必须有 max_tokens
                "temperature": temperature  # 添加温度参数
            }
            
            # 添加系统提示
            if system_prompt:
                kwargs["system"] = system_prompt
            # 移除硬编码，使用传入的参数
            # 添加工具定义
            if tool_list:
                tools = self.tool_manager.get_tools_definitions_anthropic(tool_list)
                if tools:
                    kwargs["tools"] = tools
                    
                    # 处理工具选择策略
                    if tool_choice == "any":
                        kwargs["tool_choice"] = {"type": "any"}
                        print(f"🔧 强制 Claude 从 {len(tools)} 个工具中选择任意一个")
                    elif tool_choice == "required":
                        # OpenAI风格的"required"转换为Claude的"any"
                        kwargs["tool_choice"] = {"type": "any"}
                        print(f"🔧 强制 Claude 调用工具 (required->any)")
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
                    else:
                        # 未知的tool_choice，默认使用auto
                        kwargs["tool_choice"] = {"type": "auto"}
                        print(f"⚠️ 未知的tool_choice '{tool_choice}'，默认使用auto模式")
            
            # 发送请求
            response = client.messages.create(**kwargs)
            
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
                         temperature: float = 0.0,
                         max_tokens: int = 10000,
                         tool_list: List[str] = None,
                         tool_choice: Union[str, Dict] = "required",
                         parallel_tool_calls: bool = False) -> LLMResponse:
        """使用 OpenAI 客户端进行调用"""
        # 选择客户端
        client = self.openai_custom_client if self.use_custom_apis and self.openai_custom_client else self.openai_client
        if not client:
            return LLMResponse(
                status="error",
                output="",
                error_information="OpenAI 客户端未初始化，请检查 API 密钥配置",
                model=model.value
            )
        
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
            
            # OpenAI可以不设置max_tokens，让模型自然停止
            if max_tokens is not None and max_tokens > 0:
                kwargs["max_tokens"] = max_tokens
            
            # 添加工具定义
            if tool_list:
                tools = self.tool_manager.get_tools_definitions_openai(tool_list)
                
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = tool_choice
                    kwargs["parallel_tool_calls"] = parallel_tool_calls
            
            # 发送请求
            response = client.chat.completions.create(**kwargs)
            
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
    
    def _call_with_gemini_native(self,
                                history: List[ChatMessage],
                                model: ModelType,
                                system_prompt: str = None,
                                temperature: float = 0.0,
                                max_tokens: int = 10000,
                                tool_list: List[str] = None,
                                tool_choice: Union[str, Dict] = "any") -> LLMResponse:
        """使用原生 Gemini API 进行调用"""
        if not self.gemini_client:
            return LLMResponse(
                status="error",
                output="",
                error_information="Gemini 客户端未初始化，请检查 API 密钥配置",
                model=model.value
            )
        
        try:
            # 转换消息格式为 Gemini 格式
            contents = []
            
            for msg in history:
                if msg.role == "user":
                    contents.append(genai_types.UserContent(
                        parts=[genai_types.Part.from_text(text=msg.content)]
                    ))
                elif msg.role == "assistant":
                    contents.append(genai_types.ModelContent(
                        parts=[genai_types.Part.from_text(text=msg.content)]
                    ))
            
            # 构建配置
            config_kwargs = {
                "temperature": temperature,
            }
            
            if max_tokens:
                config_kwargs["max_output_tokens"] = max_tokens
            
            if system_prompt:
                config_kwargs["system_instruction"] = system_prompt
            
            # 添加工具定义
            tools = []
            if tool_list:
                tool_definitions = self.tool_manager.get_tools_definitions_gemini(tool_list)
                for tool_def in tool_definitions:
                    function_declaration = genai_types.FunctionDeclaration(
                        name=tool_def["name"],
                        description=tool_def["description"],
                        parameters_json_schema=tool_def["parameters_json_schema"]
                    )
                    tools.append(genai_types.Tool(function_declarations=[function_declaration]))
                
                if tools:
                    config_kwargs["tools"] = tools
                    # 默认强制调用工具
                    config_kwargs["tool_config"] = genai_types.ToolConfig(
                        function_calling_config=genai_types.FunctionCallingConfig(mode='ANY')
                    )
                    print(f"🔧 强制 Gemini 调用工具 (mode=ANY)")
            
            config = genai_types.GenerateContentConfig(**config_kwargs)
            
            # 发送请求
            response = self.gemini_client.models.generate_content(
                model=model.value,
                contents=contents,
                config=config
            )
            
            # 处理响应
            output_text = response.text or ""
            tool_calls = []
            
            # 处理工具调用
            if hasattr(response, 'function_calls') and response.function_calls:
                for func_call in response.function_calls:
                    tool_calls.append(ToolCall(
                        id=func_call.id if hasattr(func_call, 'id') else str(hash(func_call.name)),
                        name=func_call.name,
                        arguments=func_call.args if hasattr(func_call, 'args') else {}
                    ))
            
            # 处理使用情况
            usage = {}
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                usage = {
                    "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                    "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                    "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)
                }
            
            return LLMResponse(
                status="success",
                output=output_text,
                error_information="",
                model=model.value,
                usage=usage,
                finish_reason="stop",
                tool_calls=tool_calls if tool_calls else None
            )
            
        except Exception as e:
            error_msg = str(e)
            print(f"🚫 Gemini 原生 API 调用错误: {error_msg}")
            
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
            elif "unauthorized" in error_msg.lower() or "invalid_api_key" in error_msg.lower():
                return LLMResponse(
                    status="error",
                    output="",
                    error_information="Gemini API密钥无效或未授权",
                    model=model.value
                )
            else:
                return LLMResponse(
                    status="error",
                    output="",
                    error_information=f"Gemini API错误: {error_msg}",
                    model=model.value
                )
    
    def _call_with_gemini_openai_compatible(self,
                                          history: List[ChatMessage],
                                          model: ModelType,
                                          system_prompt: str = None,
                                          temperature: float = 0.0,
                                          max_tokens: int = 10000,
                                          tool_list: List[str] = None,
                                          tool_choice: Union[str, Dict] = "required",
                                          parallel_tool_calls: bool = False) -> LLMResponse:
        """使用 OpenAI 兼容的 Gemini API 进行调用"""
        if not self.gemini_custom_client:
            return LLMResponse(
                status="error",
                output="",
                error_information="Gemini 自定义客户端未初始化，请检查 API 密钥和 URL 配置",
                model=model.value
            )
        
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
            
            # Gemini也可以不设置max_tokens，让模型自然停止
            if max_tokens is not None and max_tokens > 0:
                kwargs["max_tokens"] = max_tokens
            
            # 添加工具定义 - Gemini 特殊处理
            if tool_list:
                tools = self.tool_manager.get_tools_definitions_openai(tool_list)
                
                if tools:
                    kwargs["tools"] = tools
                    
                    # Gemini 模型需要特殊的工具调用配置
                    if tool_choice == "any" or tool_choice == "required":
                        # 方案1: 使用标准的 tool_choice
                        kwargs["tool_choice"] = "required"
                        
                        # 方案2: 使用正确的 extra_body.google 格式
                        kwargs["extra_body"] = {
                            "google": {
                                "tool_config": {
                                    "function_calling_config": {
                                        "mode": "ANY"  # Gemini 的强制工具调用模式
                                    }
                                }
                            }
                        }
                        print(f"🔧 强制 Gemini 调用工具 (required + google.tool_config.mode=ANY)")
                        
                    elif tool_choice == "auto":
                        kwargs["tool_choice"] = "auto"
                        # Gemini auto 模式的原生配置
                        kwargs["extra_body"] = {
                            "google": {
                                "tool_config": {
                                    "function_calling_config": {
                                        "mode": "AUTO"
                                    }
                                }
                            }
                        }
                        print(f"🤖 允许 Gemini 自动决定是否使用工具")
                        
                    elif tool_choice == "none":
                        # 如果不使用工具，则移除工具定义
                        del kwargs["tools"]
                        kwargs["extra_body"] = {
                            "google": {
                                "tool_config": {
                                    "function_calling_config": {
                                        "mode": "NONE"
                                    }
                                }
                            }
                        }
                        print(f"🚫 禁止 Gemini 使用任何工具")
                        
                    elif isinstance(tool_choice, dict):
                        # 直接使用字典格式的tool_choice
                        kwargs["tool_choice"] = tool_choice
                        print(f"🔧 使用自定义工具选择策略: {tool_choice}")
                        
                    else:
                        # 默认使用强制模式
                        kwargs["tool_choice"] = "required"
                        kwargs["extra_body"] = {
                            "google": {
                                "tool_config": {
                                    "function_calling_config": {
                                        "mode": "ANY"
                                    }
                                }
                            }
                        }
                        print(f"⚠️ 未知的tool_choice '{tool_choice}'，默认使用google.tool_config.ANY模式")
                    
                    kwargs["parallel_tool_calls"] = parallel_tool_calls
            
            # 发送请求到 Gemini API
            response = self.gemini_custom_client.chat.completions.create(**kwargs)
            
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
            print(f"🚫 Gemini API 调用错误: {error_msg}")
            
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
            elif "unauthorized" in error_msg.lower() or "invalid_api_key" in error_msg.lower():
                return LLMResponse(
                    status="error",
                    output="",
                    error_information="Gemini API密钥无效或未授权",
                    model=model.value
                )
            else:
                return LLMResponse(
                    status="error",
                    output="",
                    error_information=f"Gemini API错误: {error_msg}",
                    model=model.value
                )
    
    def chat(self, 
             history: List[ChatMessage],
             model: ModelType = ModelType.GPT_4O_MINI,
             system_prompt: str = None,
             temperature: float = None,
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
        
        # 从配置文件获取默认值
        default_config = self.config_manager.get_default_config()
        if temperature is None:
            temperature = default_config.get("temperature", 0.0)
        if max_tokens is None:
            max_tokens = default_config.get("max_tokens", 0)
            # 如果配置文件中max_tokens为0，表示不限制，设为None
            if max_tokens == 0:
                max_tokens = None
        
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
        elif self._is_gemini_model(model):
            # 优先使用原生 Gemini API
            if self.gemini_client and not self.use_custom_apis:
                print(f"🤖 使用 Gemini 原生客户端调用 {model.value}")
                return self._call_with_gemini_native(
                    history=valid_history,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tool_list=tool_list,
                    tool_choice=tool_choice
                )
            else:
                print(f"🤖 使用 Gemini OpenAI 兼容客户端调用 {model.value}")
                return self._call_with_gemini_openai_compatible(
                    history=valid_history,
                    model=model,
                    system_prompt=system_prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tool_list=tool_list,
                    tool_choice=tool_choice,
                    parallel_tool_calls=parallel_tool_calls
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
        models = []
        
        # 从配置中获取模型列表
        for provider in ["openai", "claude", "gemini"]:
            official_config = self.config_manager.get_provider_config(provider, False)
            custom_config = self.config_manager.get_provider_config(provider, True)
            
            if official_config.get("models"):
                models.extend(official_config["models"])
            if custom_config.get("models"):
                models.extend(custom_config["models"])
        
        return list(set(models))  # 去重
    
    def debug_config(self):
        """打印当前配置状态（用于调试）"""
        print("🔍 当前 LLM 客户端配置状态:")
        print(f"  use_custom_apis: {self.use_custom_apis}")
        
        config_status = self.config_manager.get_config_status()
        for provider, status in config_status.items():
            print(f"\n📋 {provider.upper()}:")
            print(f"  官方 API: 密钥={'✅' if status['official']['has_api_key'] else '❌'}, "
                  f"URL={status['official']['base_url']}, "
                  f"模型数={status['official']['models_count']}")
            print(f"  自定义 API: 密钥={'✅' if status['custom']['has_api_key'] else '❌'}, "
                  f"URL={status['custom']['base_url']}, "
                  f"模型数={status['custom']['models_count']}")
        
        print("\n🤖 客户端初始化状态:")
        print(f"  OpenAI 官方: {'✅' if self.openai_client else '❌'}")
        print(f"  OpenAI 自定义: {'✅' if self.openai_custom_client else '❌'}")
        print(f"  Claude 官方: {'✅' if self.anthropic_client else '❌'}")
        print(f"  Claude 自定义: {'✅' if self.anthropic_custom_client else '❌'}")
        print(f"  Gemini 官方: {'✅' if self.gemini_client else '❌'}")
        print(f"  Gemini 自定义: {'✅' if self.gemini_custom_client else '❌'}")

# 使用示例
def main():
    """使用示例"""
    # 直接使用配置文件中的设置
    client = LLMClient()
    
    print("🚀 LLM客户端测试 (支持 OpenAI、Claude 和 Gemini)")
    
    # 显示配置状态
    client.debug_config()
    
    # 显示可用工具
    print("\n📋 可用工具:")
    available_tools = client.tool_manager.get_available_tools()
    for tool in available_tools[:5]:  # 只显示前5个
        print(f"  - {tool}")
    print(f"  ... 共 {len(available_tools)} 个工具")
    
    # 显示可用模型
    print("\n🤖 可用模型:")
    available_models = client.get_available_models()
    for model in available_models:
        print(f"  - {model}")
    
    # 测试配置的模型
    if client.gemini_client:
        print("\n🧪 测试 Gemini 原生 API")
        test_model = ModelType.GEMINI_2_5_FLASH
    elif client.anthropic_client:
        print("\n🧪 测试 Claude API")
        test_model = ModelType.CLAUDE_3_7_SONNET
    elif client.openai_client:
        print("\n🧪 测试 OpenAI API")
        test_model = ModelType.GPT_4O_MINI
    else:
        print("\n❌ 没有配置任何可用的 API")
        return
    
    test_history = [
        ChatMessage(role="user", content="你好，请介绍一下你自己")
    ]
    
    response = client.chat(
        history=test_history,
        model=test_model,
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