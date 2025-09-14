#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent Coordination Service 包 - 专门处理Agent层级管理和协同上下文构造
"""

from .agent_hierarchy_manager import AgentHierarchyManager, get_cached_hierarchy_manager

__version__ = "1.0.0"
__all__ = ["AgentHierarchyManager", "get_cached_hierarchy_manager"]
