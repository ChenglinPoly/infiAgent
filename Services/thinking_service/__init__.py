#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thinking Service 包 - 专门处理Agent的思考和任务进展分析
"""

from .thinking_agent import ThinkingAgent, analyze_task_progress

__version__ = "1.0.0"
__all__ = ["ThinkingAgent", "analyze_task_progress"]
