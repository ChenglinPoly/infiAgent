#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Conversation Service 包 - 专门处理对话历史的保存、加载和工具调用状态管理
"""

from .conversation_manager import ConversationManager, ConversationState, ToolCallEntry
from .models import ChatMessage

__version__ = "1.0.0"
__all__ = ["ConversationManager", "ConversationState", "ToolCallEntry", "ChatMessage"]
