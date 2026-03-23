#!/usr/bin/env python3
"""CheapClaw runtime hooks for background worker tool events."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from .tool_runtime_helpers import emit_task_event, now_iso
except ImportError:
    from tool_runtime_helpers import emit_task_event, now_iso


def on_tool_event(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return
    if payload.get("when") != "after":
        return
    if payload.get("tool_name") != "final_output":
        return
    if int(payload.get("agent_level") or 0) != 0:
        return

    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        return
    if Path(task_id).name == "supervisor_task":
        return

    result = payload.get("result") or {}
    if not isinstance(result, dict):
        result = {}

    emit_task_event({
        "event_type": "task_final_output",
        "task_id": task_id,
        "agent_id": str(payload.get("agent_id") or ""),
        "agent_name": str(payload.get("agent_name") or ""),
        "status": str(result.get("status") or ""),
        "output": str(result.get("output") or ""),
        "error_information": str(result.get("error_information") or ""),
        "observed_at": now_iso(),
        "pid": os.getpid(),
    })
