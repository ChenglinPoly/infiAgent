#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
运行时控制信号。

目前用于：
- 外部 fresh 请求（来自桌面端/UI）
"""

from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
_fresh_reason: Optional[str] = None


def request_fresh(reason: str = ""):
    global _fresh_reason
    with _lock:
        _fresh_reason = str(reason or "").strip() or "external fresh request"


def pop_fresh_request() -> Optional[str]:
    global _fresh_reason
    with _lock:
        reason = _fresh_reason
        _fresh_reason = None
        return reason
