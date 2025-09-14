#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于 LiteLLM 的简化 LLM API 客户端
提供统一接口调用多种大语言模型，大幅简化原有复杂实现
完全兼容原有 LLMClient 接口
"""

import json
import yaml
import os
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import traceback

# 导入新的 LLM Service
try:
    import sys
    import os
    current_dir = Path(__file__).parent.parent
    if str(current_dir) not in sys.path:
        sys.path.append(str(current_dir))
    
    from Services.llm_service import LLMWrapper
    from Services.llm_service.config import LLMServiceConfig
    HAS_LLM_SERVICE = True
except ImportError as e:
    HAS_LLM_SERVICE = False
    print(f"错误：无法导入 LLM Service: {e}")

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
    """模型类型枚举 - 保持向后兼容性，但推荐直接使用字符串"""
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
    CLAUDE_4_SONNET = "claude-4-sonnet-20250514"
    CLAUDE_4_OPUS = "claude-4-opus-20250514"
    
    # DeepSeek 模型
    DEEPSEEK_R1 = "deepseek/deepseek-r1"
    DEEPSEEK_V3 = "deepseek/deepseek-v3"
    DEEPSEEK_R1_250120 = "deepseek/deepseek-r1-250120"
    DEEPSEEK_R1_250528 = "deepseek/deepseek-r1-250528"
    DEEPSEEK_V3_250324 = "deepseek/deepseek-v3-250324"
    
    # Gemini 官方模型（注意：配置文件中没有gemini/前缀！）
    GEMINI_2_0_FLASH = "gemini-2.0-flash"
    GEMINI_2_5_FLASH = "gemini-2.5-flash"
    GEMINI_2_5_PRO = "gemini-2.5-pro"
    GEMINI_2_5_PRO_PREVIEW = "gemini-2.5-pro-preview-03-25"
    # Custom API 中的模型（代理服务器实际支持的名称）
    CUSTOM_GEMINI_FLASH = "gemini-2.5-flash"
    CUSTOM_GEMINI_PRO = "gemini-2.5-pro"
    
    # 通义千问模型
    QWEN_MAX = "qwen/qwen-max-latest"
    QWEN_PLUS = "qwen/qwen-plus-latest"
    QWEN_TURBO = "qwen/qwen-turbo-latest"
    QWEN3_235B = "qwen/qwen3-235b-a22b"
    QWEN3_32B = "qwen/qwen3-32b"
    
    # 其他模型
    DOUBAO_1_5_PRO = "doubao/doubao-1-5-pro-256k-250115"
    DOUBAO_1_5_THINKING = "doubao/doubao-1-5-thinking-pro-250415"
    GROK_3 = "xai/grok-3"
    GROK_3_MINI = "xai/grok-3-mini"
    GROK_4 = "xai/grok-4"

# 新增工具函数，用于规范化模型名称
def normalize_model_name(model: Union[str, ModelType]) -> str:
    """
    规范化模型名称，支持字符串和枚举类型
    
    Args:
        model: 模型名称（字符串）或ModelType枚举
        
    Returns:
        str: 规范化后的模型名称
    """
    if isinstance(model, ModelType):
        return model.value
    elif isinstance(model, str):
        return model
    else:
        raise ValueError(f"不支持的模型类型: {type(model)}")

def validate_model_name(model_name: str, available_models: List[str]) -> bool:
    """
    验证模型名称是否在可用列表中
    
    Args:
        model_name: 模型名称
        available_models: 可用模型列表
        
    Returns:
        bool: 模型是否可用
    """
    return model_name in available_models

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
    """LLM 配置管理器 - 兼容原有接口"""
    
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
        # 从配置文件设置环境变量
        if "environment_variables" in self.config:
            for key, value in self.config["environment_variables"].items():
                if not os.getenv(key):  # 只有在环境变量不存在时才设置
                    os.environ[key] = str(value)
        
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
    
    def get_models_no_tool_call(self) -> List[str]:
        """获取不支持原生工具调用的模型列表"""
        models_no_tool_call = []
        
        # 从 custom 配置中获取
        custom_config = self.config.get("custom", {})
        for format_type in ["openai_format", "gemini_format", "claude_format"]:
            format_config = custom_config.get(format_type, {})
            no_tool_call_models = format_config.get("models_no_tool_call", [])
            if no_tool_call_models:  # 确保不是 None
                models_no_tool_call.extend(no_tool_call_models)
        
        return models_no_tool_call
    
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
    
    def __init__(self, config_file: str = None, agent_system_name: str = None):
        if config_file is None:
            # 默认使用 infiHelper 系统的配置
            from .config_merger import get_agent_config_path
            config_file = get_agent_config_path(agent_system_name or "infiHelper")
        self.config_file = config_file
        self.agent_system_name = agent_system_name or "infiHelper"
        self.tools_config = self._load_tools_config()
    
    def _load_tools_config(self) -> Dict:
        """加载工具配置"""
        try:
            # 确保配置文件是最新的合并版本
            ensure_merged_config(self.agent_system_name)
            
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
    """基于 LiteLLM 的简化客户端 - 完全兼容原有接口"""
    
    def __init__(self, 
                 config_file: str = None, 
                 tools_config_file: str = None,
                 use_custom_apis: bool = False,
                 agent_system_name: str = None):
        """
        初始化 LLM 客户端
        
        Args:
            config_file: LLM 配置文件路径
            tools_config_file: 工具配置文件路径
            use_custom_apis: 是否优先使用自定义 API（为兼容性保留，LiteLLM会自动处理）
            agent_system_name: Agent系统名称，用于选择对应的工具配置
        """
        if not HAS_LLM_SERVICE:
            raise ImportError("LLM Service 未安装或导入失败")
        
        # 初始化配置管理器
        self.config_manager = LLMConfigManager(config_file)
        self.use_custom_apis = use_custom_apis  # 保留参数以兼容原有接口
        
        # 初始化工具管理器
        if tools_config_file is None:
            # 根据 agent_system_name 选择配置文件
            from .config_merger import get_agent_config_path
            tools_config_file = get_agent_config_path(agent_system_name)
        self.tool_manager = ToolManager(tools_config_file, agent_system_name)
        
        # 初始化新的 LLM Wrapper
        self.llm_wrapper = LLMWrapper()
        
        # 为兼容性添加客户端属性
        self._init_client_attributes()
    
    
    def _init_client_attributes(self):
        """初始化客户端属性（为兼容性）"""
        # 这些属性在原有代码中可能被检查，保留以确保兼容性
        self.openai_client = True if os.getenv("OPENAI_API_KEY") else None
        self.anthropic_client = True if os.getenv("ANTHROPIC_API_KEY") else None
        self.gemini_client = True if os.getenv("GEMINI_API_KEY") else None
        self.openai_custom_client = None
        self.anthropic_custom_client = None
        self.gemini_custom_client = None
    
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
    
    def _convert_tool_choice(self, tool_choice: Union[str, Dict], model: str) -> Union[str, Dict]:
        """转换工具选择策略以适配不同模型"""
        if tool_choice == "any":
            # LiteLLM 中 "any" 对应 "required"
            return "required"
        elif tool_choice == "required":
            return "required" 
        elif tool_choice == "auto":
            return "auto"
        elif tool_choice == "none":
            return "none"
        else:
            return tool_choice
    
    def _check_model_tool_call_capability(self, model: str) -> bool:
        """
        检查模型是否支持原生工具调用
        
        Args:
            model: 模型名称
            
        Returns:
            bool: 是否支持原生工具调用
        """
        # 获取不支持原生工具调用的模型列表
        models_no_tool_call = self.config_manager.get_models_no_tool_call()
        
        # 检查模型是否在不支持列表中
        return model not in models_no_tool_call
    
    def _is_model_actually_available(self, model: Union[str, ModelType]) -> bool:
        """检查模型是否真正可用（严格按照配置文件）"""
        model_name = normalize_model_name(model)
        available_models = self.get_available_models()
        return validate_model_name(model_name, available_models)
    
    def _is_using_custom_api(self, model: Union[str, ModelType]) -> bool:
        """检查模型是否通过custom API调用"""
        model_name = normalize_model_name(model)
        
        # 检查新的custom配置结构
        custom_config = self.config_manager.config.get("custom", {})
        
        # 检查三种custom格式
        for format_type in ["openai_format", "gemini_format", "claude_format"]:
            format_config = custom_config.get(format_type, {})
            models_list = format_config.get("models", []) or []
            models_no_tool_call_list = format_config.get("models_no_tool_call", []) or []
            if model_name in models_list or model_name in models_no_tool_call_list:
                return True
        
        return False
    
    def _get_custom_api_config(self, model: Union[str, ModelType]) -> tuple:
        """获取custom API的配置信息"""
        model_name = normalize_model_name(model)
        custom_config = self.config_manager.config.get("custom", {})
        
        # 检查三种custom格式，返回对应的配置
        for format_type in ["openai_format", "gemini_format", "claude_format"]:
            format_config = custom_config.get(format_type, {})
            models_list = format_config.get("models", []) or []
            models_no_tool_call_list = format_config.get("models_no_tool_call", []) or []
            if model_name in models_list or model_name in models_no_tool_call_list:
                return format_config.get("api_key"), format_config.get("base_url"), format_type
        
        return None, None, None
    
    def _get_fallback_model(self, requested_model: Union[str, ModelType], allow_fallback: bool = True) -> str:
        """
        获取可用的模型名称，支持禁用自动回退
        
        Args:
            requested_model: 请求的模型
            allow_fallback: 是否允许自动回退到其他模型
            
        Returns:
            str: 最终使用的模型名称
            
        Raises:
            ValueError: 当模型不可用且不允许回退时
        """
        model_name = normalize_model_name(requested_model)
        available_models = self.get_available_models()
        
        # 检查请求的模型是否真正可用（有API密钥）
        if validate_model_name(model_name, available_models):
            return model_name
        
        if not allow_fallback:
            raise ValueError(f"模型 {model_name} 不可用，且禁用了自动回退")
        
        # 如果不可用，寻找真正可用的模型
        print(f"⚠️ {model_name}模型未配置API密钥，寻找可用模型...")
        
        if available_models:
            # 如果优先使用custom，按custom优先级排序
            if self.use_custom_apis:
                # 优先选择custom配置的模型
                custom_models = []
                official_models = []
                
                for model_str in available_models:
                    # 检查是否是custom模型
                    found_in_custom = False
                    custom_config = self.config_manager.config.get("custom", {})
                    for format_type in ["openai_format", "gemini_format", "claude_format"]:
                        format_config = custom_config.get(format_type, {})
                        if model_str in format_config.get("models", []):
                            custom_models.append(model_str)
                            found_in_custom = True
                            break
                    
                    if not found_in_custom:
                        official_models.append(model_str)
                
                # 优先使用custom模型
                priority_model_strings = custom_models + official_models
            else:
                # 默认优先级
                priority_model_strings = available_models
            
            # 返回第一个可用的模型
            if priority_model_strings:
                fallback_model = priority_model_strings[0]
                print(f"⚠️ {model_name}模型未配置，默认使用当前 available 模型：{fallback_model}")
                return fallback_model
                
        # 如果都没有找到，使用默认模型
        default_model = "gpt-4o-mini"
        print(f"⚠️ 没有找到可用模型，使用默认模型：{default_model}")
        return default_model

    def chat(self, 
             history: List[ChatMessage],
             model: Union[str, ModelType] = ModelType.GPT_4O_MINI,
             system_prompt: str = None,
             temperature: float = None,
             max_tokens: int = None,
             tool_list: List[str] = None,
             tool_choice: Union[str, Dict] = "any",
             parallel_tool_calls: bool = False,
             allow_model_fallback: bool = True,
             tool_call_capability: bool = None) -> LLMResponse:
        """
        发送聊天消息
        
        Args:
            history: 对话历史，最后一个消息应该是用户的最新输入
            model: 使用的模型（支持字符串或ModelType枚举）
            system_prompt: 系统提示
            temperature: 温度参数
            max_tokens: 最大token数（可选，不设置则自然停止）
            tool_list: 工具列表，工具名称列表
            tool_choice: 工具选择策略 ("auto", "none", 或 {"type": "function", "function": {"name": "工具名"}})
            parallel_tool_calls: 是否允许并行工具调用，False表示每次最多调用一个工具
            allow_model_fallback: 是否允许模型自动回退（默认True保持兼容性）
            tool_call_capability: 是否支持原生工具调用，None表示自动检测
        
        Returns:
            LLMResponse: 统一格式的响应
        """
        if not history:
            return LLMResponse(
                status="error",
                output="",
                error_information="对话历史不能为空",
                model=normalize_model_name(model)
            )
        
        # 检查并获取可用模型
        try:
            actual_model_name = self._get_fallback_model(model, allow_model_fallback)
        except ValueError as e:
            return LLMResponse(
                status="error",
                output="",
                error_information=str(e),
                model=normalize_model_name(model)
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
                model=actual_model_name
            )
        
        try:
            # 预处理消息历史
            processed_messages = self._preprocess_history(valid_history)
            
            messages = []
            
            # 添加系统提示
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            # 添加预处理后的对话历史
            messages.extend(processed_messages)
            
            # 获取API配置
            api_key = None
            api_base = None
            
            if self._is_using_custom_api(actual_model_name):
                # Custom API配置
                api_key, api_base, format_type = self._get_custom_api_config(actual_model_name)
            else:
                # 官方API配置
                model_lower = actual_model_name.lower()
                if "gemini" in model_lower:
                    gemini_config = self.config_manager.get_provider_config("gemini", False)
                    api_key = gemini_config.get("api_key")
                elif "claude" in model_lower:
                    claude_config = self.config_manager.get_provider_config("claude", False)
                    api_key = claude_config.get("api_key")
                elif any(x in model_lower for x in ["gpt", "o1", "o3", "chatgpt"]):
                    openai_config = self.config_manager.get_provider_config("openai", False)
                    api_key = openai_config.get("api_key")
            
            # 准备工具定义
            tools = None
            if tool_list:
                tools = self.tool_manager.get_tools_definitions_openai(tool_list)
                if tools:
                    print(f"🔧 使用工具: {[tool['function']['name'] for tool in tools]}")
                    print(f"🎯 工具选择策略: {tool_choice}")
            
            # 根据配置文件决定工具调用能力
            if tool_call_capability is None:
                tool_call_capability = self._check_model_tool_call_capability(actual_model_name)
            
            print(f"🔧 工具调用模式: {'原生' if tool_call_capability else '提示词'} (模型: {actual_model_name})")
            
            # 调用新的 LLM Wrapper
            print(f"🤖 调用模型: {actual_model_name}")
            response = self.llm_wrapper.chat(
                messages=messages,
                model=actual_model_name,
                api_key=api_key,
                api_base=api_base,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                tool_call_capability=tool_call_capability,
                parallel_tool_calls=parallel_tool_calls,
                max_retries=3  # 提示词模式下的重试次数
            )
            
            return response
        
        except Exception as e:
            error_msg = str(e)
            print(f"❌ LLM 调用错误: {error_msg}")
            
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
                model=normalize_model_name(model)
            )
    
    def get_available_models(self) -> List[str]:
        """获取可用模型列表 - 严格按照配置文件"""
        models = []
        
        # 检查官方API配置
        for provider in ["openai", "claude", "gemini"]:
            official_config = self.config_manager.get_provider_config(provider, False)
            
            # 检查是否有对应的API密钥
            has_official_key = False
            if provider == "openai":
                has_official_key = bool(os.getenv("OPENAI_API_KEY") or official_config.get("api_key"))
            elif provider == "claude":
                has_official_key = bool(os.getenv("ANTHROPIC_API_KEY") or official_config.get("api_key"))
            elif provider == "gemini":
                has_official_key = bool(os.getenv("GEMINI_API_KEY") or official_config.get("api_key"))
            
            if has_official_key and official_config.get("models"):
                models.extend(official_config["models"])
        
        # 检查Custom API配置
        custom_config = self.config_manager.config.get("custom", {})
        
        # OpenAI格式的Custom API
        openai_custom = custom_config.get("openai_format", {})
        if openai_custom.get("api_key"):
            # 添加常规模型
            regular_models = openai_custom.get("models", [])
            if regular_models:
                models.extend(regular_models)
            # 添加不支持原生工具调用的模型
            no_tool_call_models = openai_custom.get("models_no_tool_call", [])
            if no_tool_call_models:
                models.extend(no_tool_call_models)
        
        # Gemini格式的Custom API
        gemini_custom = custom_config.get("gemini_format", {})
        if gemini_custom.get("api_key"):
            regular_models = gemini_custom.get("models", [])
            if regular_models:
                models.extend(regular_models)
            no_tool_call_models = gemini_custom.get("models_no_tool_call", [])
            if no_tool_call_models:
                models.extend(no_tool_call_models)
        
        # Claude格式的Custom API
        claude_custom = custom_config.get("claude_format", {})
        if claude_custom.get("api_key"):
            regular_models = claude_custom.get("models", [])
            if regular_models:
                models.extend(regular_models)
            no_tool_call_models = claude_custom.get("models_no_tool_call", [])
            if no_tool_call_models:
                models.extend(no_tool_call_models)
        
        # 去重但保持顺序
        seen = set()
        unique_models = []
        for model in models:
            if model not in seen:
                seen.add(model)
                unique_models.append(model)
        
        return unique_models
    
    def debug_config(self):
        """打印当前配置状态（用于调试）"""
        print("🔍 当前 LLM 客户端配置状态:")
        print(f"  use_custom_apis: {self.use_custom_apis}")
        print(f"  配置文件: {self.config_manager.config_file}")
        
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

def get_model_from_config(config_file: str = None, prefer_custom: bool = True) -> str:
    """
    从配置文件中获取第一个可用的模型名称
    
    Args:
        config_file: 配置文件路径
        prefer_custom: 是否优先选择custom API中的模型
        
    Returns:
        str: 第一个可用的模型名称
    """
    try:
        config_manager = LLMConfigManager(config_file)
        
        # 获取所有可用模型
        available_models = []
        custom_models = []
        official_models = []
        
        # 检查custom配置
        custom_config = config_manager.config.get("custom", {})
        for format_type in ["openai_format", "gemini_format", "claude_format"]:
            format_config = custom_config.get(format_type, {})
            if format_config.get("api_key") and format_config.get("models"):
                custom_models.extend(format_config["models"])
        
        # 检查官方API配置
        for provider in ["openai", "claude", "gemini"]:
            official_config = config_manager.get_provider_config(provider, False)
            
            # 检查是否有对应的API密钥
            has_official_key = False
            if provider == "openai":
                has_official_key = bool(os.getenv("OPENAI_API_KEY") or official_config.get("api_key"))
            elif provider == "claude":
                has_official_key = bool(os.getenv("ANTHROPIC_API_KEY") or official_config.get("api_key"))
            elif provider == "gemini":
                has_official_key = bool(os.getenv("GEMINI_API_KEY") or official_config.get("api_key"))
            
            if has_official_key and official_config.get("models"):
                official_models.extend(official_config["models"])
        
        # 根据偏好排序
        if prefer_custom:
            available_models = custom_models + official_models
        else:
            available_models = official_models + custom_models
        
        # 去重
        seen = set()
        unique_models = []
        for model in available_models:
            if model not in seen:
                seen.add(model)
                unique_models.append(model)
        
        if unique_models:
            return unique_models[0]
        else:
            return "gpt-4o-mini"  # 默认模型
            
    except Exception as e:
        print(f"从配置文件获取模型失败: {e}")
        return "gpt-4o-mini"

# 使用示例
def main():
    """使用示例"""
    # 直接使用配置文件中的设置
    client = LLMClient()
    
    print("🚀 LLM客户端测试 (基于新的 LLM Service，支持原生和提示词工具调用)")
    
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
    for model in available_models[:10]:  # 只显示前10个
        print(f"  - {model}")
    print(f"  ... 共 {len(available_models)} 个模型")
    
    # 测试从配置文件获取模型
    recommended_model = get_model_from_config()
    print(f"\n🎯 推荐使用的模型: {recommended_model}")
    
    # 测试配置的模型 - 现在可以直接使用字符串
    test_model = recommended_model  # 直接使用字符串
    
    test_history = [
        ChatMessage(role="user", content="你好，请介绍一下你自己")
    ]
    
    response = client.chat(
        history=test_history,
        model=test_model,  # 直接使用字符串
        tool_list=["file_write"],
        tool_call_capability=False  # 测试基于提示词的工具调用
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