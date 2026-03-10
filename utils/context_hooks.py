#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List


def _load_callback(callback_spec: str):
    callback_spec = str(callback_spec or "").strip()
    if ":" not in callback_spec:
        raise ValueError(f"invalid callback spec: {callback_spec}")
    module_spec, func_name = callback_spec.rsplit(":", 1)
    module_spec = module_spec.strip()
    func_name = func_name.strip()
    if module_spec.endswith(".py") or module_spec.startswith("/"):
        path = Path(module_spec).expanduser().resolve()
        module_name = f"context_hook_{path.stem}_{abs(hash(str(path)))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load context hook module: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    else:
        module = importlib.import_module(module_spec)
    callback = getattr(module, func_name, None)
    if callback is None or not callable(callback):
        raise AttributeError(f"callback not found: {callback_spec}")
    return callback


def _load_context_hooks() -> List[Dict[str, Any]]:
    raw = os.environ.get("MLA_CONTEXT_HOOKS_JSON", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


def apply_context_hooks(
    *,
    stage: str,
    task_id: str,
    agent_id: str,
    agent_name: str,
    task_input: str,
    context_data: Dict[str, Any],
    context_text: str,
) -> str:
    updated_context = str(context_text or "")
    for hook in _load_context_hooks():
        when = str(hook.get("when") or "after_build").strip()
        if when not in {stage, "both"}:
            continue
        callback_spec = str(hook.get("callback") or "").strip()
        if not callback_spec:
            continue
        try:
            callback = _load_callback(callback_spec)
            payload = {
                "hook_name": str(hook.get("name") or ""),
                "stage": stage,
                "task_id": task_id,
                "agent_id": agent_id,
                "agent_name": agent_name,
                "task_input": task_input,
                "context_data": context_data,
                "context_text": updated_context,
            }
            result = callback(payload)
            if isinstance(result, str):
                updated_context = result
            elif isinstance(result, dict):
                if "context_text" in result and result["context_text"] is not None:
                    updated_context = str(result["context_text"])
        except Exception:
            continue
    return updated_context
