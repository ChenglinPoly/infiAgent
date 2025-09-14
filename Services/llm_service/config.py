#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Service 配置管理
"""

import os
import yaml
from typing import Dict, Optional, List
from pathlib import Path

class LLMServiceConfig:
    """LLM Service 配置管理器"""
    
    def __init__(self, config_file: str = None):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        if config_file is None:
            # 默认配置文件路径
            current_dir = Path(__file__).parent.parent.parent
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
                    return yaml.safe_load(f) or {}
            else:
                return self._get_default_config()
        except Exception as e:
            print(f"加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """获取默认配置"""
        return {
            "default": {
                "temperature": 0,
                "max_tokens": 10000,
                "timeout": 1000,
                "num_retries": 3
            },
            "openai": {"official": {}, "custom": {}},
            "claude": {"official": {}, "custom": {}},
            "gemini": {"official": {}, "custom": {}},
            "deepseek": {"official": {}, "custom": {}},
            "qwen": {"official": {}, "custom": {}}
        }
    
    def _load_env_variables(self):
        """从环境变量加载 API 配置"""
        # 从配置文件设置环境变量
        if "environment_variables" in self.config:
            for key, value in self.config["environment_variables"].items():
                if not os.getenv(key):
                    os.environ[key] = str(value)
        
        # OpenAI 配置
        if os.getenv('OPENAI_API_KEY'):
            if not self.config['openai']['official'].get('api_key'):
                self.config['openai']['official']['api_key'] = os.getenv('OPENAI_API_KEY')
        
        # Claude 配置
        if os.getenv('ANTHROPIC_API_KEY'):
            if not self.config['claude']['official'].get('api_key'):
                self.config['claude']['official']['api_key'] = os.getenv('ANTHROPIC_API_KEY')
        
        # Gemini 配置
        if os.getenv('GEMINI_API_KEY'):
            if not self.config['gemini']['official'].get('api_key'):
                self.config['gemini']['official']['api_key'] = os.getenv('GEMINI_API_KEY')
    
    def get_provider_config(self, provider: str, use_custom: bool = False) -> Dict:
        """获取提供商配置"""
        provider_config = self.config.get(provider, {})
        config_type = "custom" if use_custom else "official"
        return provider_config.get(config_type, {})
    
    def get_default_config(self) -> Dict:
        """获取默认配置"""
        return self.config.get("default", {})
    
    def get_model_config(self, model: str) -> Dict:
        """
        根据模型名称获取对应的配置
        
        Args:
            model: 模型名称
            
        Returns:
            Dict: 模型配置
        """
        model_lower = model.lower()
        
        # 根据模型名称判断提供商
        if any(x in model_lower for x in ["gpt", "o1", "o3", "chatgpt"]):
            return self.get_provider_config("openai")
        elif "claude" in model_lower:
            return self.get_provider_config("claude")
        elif "gemini" in model_lower:
            return self.get_provider_config("gemini")
        elif "deepseek" in model_lower:
            return self.get_provider_config("deepseek")
        elif "qwen" in model_lower:
            return self.get_provider_config("qwen")
        else:
            return {}
    
    def get_available_models(self) -> List[str]:
        """获取所有可用的模型列表"""
        models = []
        
        for provider in ["openai", "claude", "gemini", "deepseek", "qwen"]:
            official_config = self.get_provider_config(provider, False)
            custom_config = self.get_provider_config(provider, True)
            
            # 检查是否有API密钥
            if official_config.get("api_key") and official_config.get("models"):
                models.extend(official_config["models"])
            
            if custom_config.get("api_key") and custom_config.get("models"):
                models.extend(custom_config["models"])
        
        return list(set(models))  # 去重
