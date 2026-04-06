#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的 token 预算辅助工具。

设计目标：
- 主调用前做一次硬预算检查
- 允许在明显安全的小输入场景下跳过昂贵的精确编码
- 对多模态/工具 schema 提供保守估算
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


try:
    import tiktoken
    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENCODING = None


def rough_token_estimate_text(text: str) -> int:
    value = str(text or "")
    chinese_chars = sum(1 for c in value if "\u4e00" <= c <= "\u9fff")
    other_chars = len(value) - chinese_chars
    return max(0, int(chinese_chars / 1.5 + other_chars / 4))


def rough_token_estimate_value(value: Any) -> int:
    if isinstance(value, str):
        return rough_token_estimate_text(value)
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    return rough_token_estimate_text(text)


def count_tokens_text(text: str, *, force_exact: bool = False, exact_trigger_tokens: int = 2048) -> int:
    rough = rough_token_estimate_text(text)
    if _ENCODING is None:
        return rough
    if not force_exact and rough < max(1, int(exact_trigger_tokens)):
        return rough
    try:
        return len(_ENCODING.encode(str(text or "")))
    except Exception:
        return rough


def count_tokens_value(value: Any, *, force_exact: bool = False, exact_trigger_tokens: int = 2048) -> int:
    if isinstance(value, str):
        return count_tokens_text(value, force_exact=force_exact, exact_trigger_tokens=exact_trigger_tokens)
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        text = str(value)
    return count_tokens_text(text, force_exact=force_exact, exact_trigger_tokens=exact_trigger_tokens)


def default_reserved_output_tokens(context_limit: int, explicit_max_tokens: Optional[int] = None) -> int:
    if explicit_max_tokens and int(explicit_max_tokens) > 0:
        return int(explicit_max_tokens)
    return max(1024, min(4096, int(max(1, int(context_limit)) * 0.15)))


def default_safety_margin(context_limit: int) -> int:
    return max(512, min(4096, int(max(1, int(context_limit)) * 0.05)))


def normalize_message_for_budget(message: Any) -> Dict[str, Any]:
    if isinstance(message, dict):
        normalized = {
            "role": message.get("role"),
        }
        if "content" in message:
            normalized["content"] = message.get("content")
        if message.get("reasoning_content"):
            normalized["reasoning_content"] = message.get("reasoning_content")
        if message.get("tool_calls"):
            normalized["tool_calls"] = message.get("tool_calls")
        if message.get("tool_call_id"):
            normalized["tool_call_id"] = message.get("tool_call_id")
        if message.get("name"):
            normalized["name"] = message.get("name")
        return normalized

    role = getattr(message, "role", None)
    content = getattr(message, "content", None)
    reasoning_content = getattr(message, "reasoning_content", None)
    normalized = {"role": role, "content": content}
    if reasoning_content:
        normalized["reasoning_content"] = reasoning_content
    return normalized


def count_message_tokens(
    messages: Iterable[Any],
    *,
    force_exact: bool = False,
    exact_trigger_tokens: int = 2048,
    image_token_cost: int = 1024,
) -> tuple[int, int]:
    """
    Returns:
      (message_tokens_without_image_surcharge, image_surcharge_tokens)
    """
    normalized_messages: List[Dict[str, Any]] = []
    image_count = 0

    for message in messages or []:
        normalized = normalize_message_for_budget(message)
        content = normalized.get("content")
        if isinstance(content, list):
            stripped_parts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    image_count += 1
                    stripped_parts.append({"type": "image_url", "image_url": {"url": "<image>"}})
                else:
                    stripped_parts.append(item)
            normalized["content"] = stripped_parts
        normalized_messages.append(normalized)

    tokens = count_tokens_value(
        normalized_messages,
        force_exact=force_exact,
        exact_trigger_tokens=exact_trigger_tokens,
    )
    return tokens, image_count * max(0, int(image_token_cost))


@dataclass
class RequestBudget:
    context_limit: int
    reserved_output_tokens: int
    safety_margin_tokens: int
    system_prompt_tokens: int
    message_tokens: int
    tool_tokens: int
    image_surcharge_tokens: int
    available_input_tokens: int
    used_input_tokens: int
    total_with_reserved_tokens: int
    over_budget: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "context_limit": self.context_limit,
            "reserved_output_tokens": self.reserved_output_tokens,
            "safety_margin_tokens": self.safety_margin_tokens,
            "system_prompt_tokens": self.system_prompt_tokens,
            "message_tokens": self.message_tokens,
            "tool_tokens": self.tool_tokens,
            "image_surcharge_tokens": self.image_surcharge_tokens,
            "available_input_tokens": self.available_input_tokens,
            "used_input_tokens": self.used_input_tokens,
            "total_with_reserved_tokens": self.total_with_reserved_tokens,
            "over_budget": self.over_budget,
        }


def build_request_budget(
    *,
    system_prompt: str,
    messages: Iterable[Any],
    tools_definition: Optional[List[Dict[str, Any]]],
    context_limit: int,
    max_tokens: Optional[int] = None,
    force_exact: bool = False,
    exact_trigger_tokens: int = 2048,
    image_token_cost: int = 1024,
) -> RequestBudget:
    context_limit = max(1, int(context_limit))
    reserved_output = default_reserved_output_tokens(context_limit, max_tokens)
    safety_margin = default_safety_margin(context_limit)
    system_tokens = count_tokens_text(
        system_prompt,
        force_exact=force_exact,
        exact_trigger_tokens=exact_trigger_tokens,
    )
    message_tokens, image_tokens = count_message_tokens(
        messages,
        force_exact=force_exact,
        exact_trigger_tokens=exact_trigger_tokens,
        image_token_cost=image_token_cost,
    )
    tool_tokens = count_tokens_value(
        tools_definition or [],
        force_exact=force_exact,
        exact_trigger_tokens=exact_trigger_tokens,
    )
    used_input = system_tokens + message_tokens + tool_tokens + image_tokens
    available_input = max(0, context_limit - reserved_output - safety_margin)
    total_with_reserved = used_input + reserved_output + safety_margin
    return RequestBudget(
        context_limit=context_limit,
        reserved_output_tokens=reserved_output,
        safety_margin_tokens=safety_margin,
        system_prompt_tokens=system_tokens,
        message_tokens=message_tokens,
        tool_tokens=tool_tokens,
        image_surcharge_tokens=image_tokens,
        available_input_tokens=available_input,
        used_input_tokens=used_input,
        total_with_reserved_tokens=total_with_reserved,
        over_budget=used_input > available_input,
    )
