#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Append-only raw LLM traces for later evaluation/training data curation."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from utils.user_paths import get_task_file_prefix, get_user_training_traces_dir


SCHEMA_VERSION = "infiagent.raw_io.v1"


def make_trace_id(prefix: str = "trace") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        try:
            return _json_safe(value.model_dump())
        except Exception:
            pass
    if hasattr(value, "dict"):
        try:
            return _json_safe(value.dict())
        except Exception:
            pass
    return repr(value)


def _resolve_trace_path(task_id: Optional[str]) -> Path:
    root = get_user_training_traces_dir()
    root.mkdir(parents=True, exist_ok=True)
    prefix = get_task_file_prefix(str(task_id or "").strip()) if task_id else "global"
    return root / f"{prefix}_raw_io.jsonl"


def append_raw_trace_record(
    *,
    kind: str,
    task_id: Optional[str],
    trace_id: Optional[str] = None,
    agent_system: str = "",
    agent_id: str = "",
    agent_name: str = "",
    debug_label: str = "",
    request: Optional[Dict[str, Any]] = None,
    response: Optional[Dict[str, Any]] = None,
    error: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Append one JSONL raw LLM trace record under `~/mla_v3/training_traces/`.

    Records should represent what is sent to LiteLLM and what LiteLLM returns.
    Tool execution-layer hidden parameters do not belong here because the model
    never sees them; tool results are captured only when they later appear as
    `role=tool` messages in an LLM request.
    """
    try:
        file_path = _resolve_trace_path(task_id)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "trace_id": trace_id or make_trace_id(str(kind or "trace").replace(".", "_")),
            "timestamp": datetime.now().isoformat(),
            "pid": os.getpid(),
            "kind": str(kind or "unknown"),
            "task_id": str(task_id or "").strip() or None,
            "task_prefix": get_task_file_prefix(str(task_id or "").strip()) if task_id else None,
            "agent_system": str(agent_system or ""),
            "agent_id": str(agent_id or ""),
            "agent_name": str(agent_name or ""),
            "debug_label": str(debug_label or ""),
            "request": _json_safe(request or {}),
            "response": _json_safe(response or {}),
            "error": _json_safe(error or {}),
            "metadata": _json_safe(metadata or {}),
        }
        with open(file_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return file_path
    except Exception:
        return None
