#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Services 包 - 包含各种独立的服务模块
"""

from .llm_service import LLMWrapper
from .context_length_control_service import ContextLengthController
from .conversation_service import ConversationManager, ConversationState
from .agent_coordination_service import AgentHierarchyManager, get_cached_hierarchy_manager
from .shared_context_construction_service import SharedContextConstructor
from .thinking_service import ThinkingAgent, analyze_task_progress

__version__ = "1.0.0"
__all__ = ["LLMWrapper", "ContextLengthController", "ConversationManager", "ConversationState", "AgentHierarchyManager", "get_cached_hierarchy_manager", "SharedContextConstructor", "ThinkingAgent", "analyze_task_progress"]
