#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM Service 包 - 统一处理原生和基于提示词的工具调用
"""

from .llm_wrapper import LLMWrapper, ToolCall, LLMResponse

__version__ = "1.0.0"
__all__ = ["LLMWrapper", "ToolCall", "LLMResponse"]
