#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared Context Construction Service 包 - 专门处理共享上下文的构造
读取所有相关历史对话和层级信息，智能构造Agent间的共享上下文
"""

from .shared_context_constructor import SharedContextConstructor

__version__ = "1.0.0"
__all__ = ["SharedContextConstructor"]
