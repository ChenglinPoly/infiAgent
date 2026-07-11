#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Optional


VALID_REASONING_MODES = ("thinking", "react", "react_lite")


def parse_bool(value: Any) -> Optional[bool]:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def normalize_reasoning_mode(value: Any = None, *, thinking_enabled: Any = None) -> str:
    raw = str(value or "").strip().lower()
    normalized = (
        raw.replace(" ", "")
        .replace("-", "_")
        .replace("(", "_")
        .replace(")", "")
    )
    aliases = {
        "thinking": "thinking",
        "think": "thinking",
        "react": "react",
        "react_lite": "react_lite",
        "reactlite": "react_lite",
        "lite": "react_lite",
    }
    if normalized in aliases:
        return aliases[normalized]

    enabled = parse_bool(thinking_enabled)
    if enabled is not None:
        return "thinking" if enabled else "react"
    return "thinking"


def reasoning_mode_to_thinking_enabled(mode: Any) -> bool:
    return normalize_reasoning_mode(mode) == "thinking"
