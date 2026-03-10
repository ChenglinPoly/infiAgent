#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils.windows_compat import safe_print


def _load_hooks_config() -> List[Dict[str, Any]]:
    raw = os.environ.get("MLA_TOOL_HOOKS_JSON", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except Exception as exc:
        safe_print(f"⚠️  解析 MLA_TOOL_HOOKS_JSON 失败: {exc}")
        return []
    if not isinstance(payload, list):
        return []
    hooks: List[Dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        callback = str(item.get("callback") or "").strip()
        if not callback:
            continue
        when = str(item.get("when") or "after").strip().lower()
        if when not in {"before", "after", "both"}:
            when = "after"
        tool_names = item.get("tool_names")
        if isinstance(tool_names, str):
            tool_names = [tool_names]
        if not isinstance(tool_names, list) or not tool_names:
            tool_names = ["*"]
        hooks.append({
            "name": str(item.get("name") or callback).strip(),
            "callback": callback,
            "when": when,
            "tool_names": [str(name).strip() for name in tool_names if str(name).strip()],
            "include_arguments": bool(item.get("include_arguments", True)),
            "include_result": bool(item.get("include_result", True)),
            "argument_filters": item.get("argument_filters") if isinstance(item.get("argument_filters"), dict) else {},
            "result_filters": item.get("result_filters") if isinstance(item.get("result_filters"), dict) else {},
        })
    return hooks


def _lookup_path(payload: Any, dotted_path: str) -> Any:
    current = payload
    for part in str(dotted_path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                current = current[int(part)]
                continue
            except Exception:
                return None
        return None
    return current


def _match_filters(payload: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    if not filters:
        return True
    for dotted_path, expected in filters.items():
        actual = _lookup_path(payload, dotted_path)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        else:
            if actual != expected:
                return False
    return True


@lru_cache(maxsize=64)
def _resolve_callback(spec: str) -> Callable[[Dict[str, Any]], Any]:
    target, sep, func_name = spec.rpartition(":")
    if not sep or not target or not func_name:
        raise ValueError(f"无效 callback 规范: {spec}")

    if target.endswith(".py") and Path(target).expanduser().exists():
        path = Path(target).expanduser().resolve()
        module_name = f"mla_tool_hook_{abs(hash((str(path), func_name))) % 100000000}"
        module_spec = importlib.util.spec_from_file_location(module_name, path)
        if module_spec is None or module_spec.loader is None:
            raise ValueError(f"无法加载 hook 文件: {path}")
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
    else:
        module = importlib.import_module(target)

    callback = getattr(module, func_name, None)
    if callback is None or not callable(callback):
        raise ValueError(f"hook 回调不存在或不可调用: {spec}")
    return callback


def trigger_tool_hooks(
    *,
    when: str,
    tool_name: str,
    task_id: str,
    arguments: Optional[Dict[str, Any]] = None,
    result: Optional[Dict[str, Any]] = None,
    agent_id: str = "",
    agent_name: str = "",
    agent_level: Optional[int] = None,
) -> None:
    when = str(when or "").strip().lower()
    if when not in {"before", "after"}:
        return
    hooks = _load_hooks_config()
    if not hooks:
        return

    arguments = arguments if isinstance(arguments, dict) else {}
    result = result if isinstance(result, dict) else {}

    for hook in hooks:
        hook_when = hook.get("when", "after")
        if hook_when not in {when, "both"}:
            continue
        tool_names = hook.get("tool_names") or ["*"]
        if "*" not in tool_names and tool_name not in tool_names:
            continue
        if not _match_filters(arguments, hook.get("argument_filters") or {}):
            continue
        if when == "after" and not _match_filters(result, hook.get("result_filters") or {}):
            continue

        payload: Dict[str, Any] = {
            "hook_name": hook.get("name") or hook.get("callback"),
            "when": when,
            "tool_name": tool_name,
            "task_id": task_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_level": agent_level,
        }
        if hook.get("include_arguments", True):
            payload["arguments"] = arguments
        if when == "after" and hook.get("include_result", True):
            payload["result"] = result

        try:
            callback = _resolve_callback(str(hook["callback"]))
            callback(payload)
        except Exception as exc:
            safe_print(f"⚠️  tool hook 执行失败 {hook.get('name') or hook.get('callback')}: {exc}")
