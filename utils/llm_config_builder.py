#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
结构化模型配置 -> 兼容 llm_config.yaml 的构建器。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Optional


MODEL_SLOT_TO_CONFIG_KEY = {
    "main": "models",
    "execution": "models",
    "figure": "figure_models",
    "image_generation": "figure_models",
    "compressor": "compressor_models",
    "read_figure": "read_figure_models",
    "thinking": "thinking_models",
}


def normalize_provider_kind(value: Optional[str]) -> str:
    raw = str(value or "").strip().lower().replace("-", "_")
    aliases = {
        "openai": "openai_official",
        "openai_official": "openai_official",
        "openai_compatible": "openai_compatible",
        "openrouter": "openrouter",
        "google": "google_official",
        "google_official": "google_official",
        "anthropic": "anthropic_official",
        "anthropic_official": "anthropic_official",
        "local": "local_openai_compatible",
        "local_openai_compatible": "local_openai_compatible",
    }
    return aliases.get(raw, raw or "openai_compatible")


def normalize_model_name(provider_kind: str, model_name: str) -> str:
    provider_kind = normalize_provider_kind(provider_kind)
    raw_name = str(model_name or "").strip()
    if not raw_name:
        return ""

    prefixes = ("openrouter/", "openai/", "google/", "anthropic/")
    if raw_name.startswith(prefixes):
        return raw_name

    prefix_map = {
        "openrouter": "openrouter/",
        "openai_compatible": "openai/",
        "openai_official": "openai/",
        "google_official": "google/",
        "anthropic_official": "anthropic/",
        "local_openai_compatible": "openai/",
    }
    prefix = prefix_map.get(provider_kind, "openai/")
    return f"{prefix}{raw_name}"


def build_model_entry(profile: Dict[str, Any]) -> Dict[str, Any] | str:
    provider_kind = normalize_provider_kind(profile.get("provider"))
    model_name = normalize_model_name(provider_kind, profile.get("model") or profile.get("name") or "")
    if not model_name:
        return ""

    entry: Dict[str, Any] = {"name": model_name}
    base_url = str(profile.get("base_url") or "").strip()
    api_key = str(profile.get("api_key") or "").strip()
    tool_choice = str(profile.get("tool_choice") or "").strip().lower()

    if base_url:
        entry["base_url"] = base_url
    if api_key:
        entry["api_key"] = api_key
    if tool_choice in {"required", "auto", "none"}:
        entry["tool_choice"] = tool_choice

    extra_provider = profile.get("provider_options")
    if isinstance(extra_provider, dict) and extra_provider:
        entry["provider"] = deepcopy(extra_provider)

    # 多部署路由（缓存亲和 + 故障转移）：原样透传给 llm_client
    deployments = profile.get("deployments")
    if isinstance(deployments, list) and deployments:
        entry["deployments"] = deepcopy(deployments)

    if set(entry.keys()) == {"name"}:
        return model_name
    return entry


def build_llm_config_from_profiles(
    payload: Dict[str, Any],
    *,
    base_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = deepcopy(base_config or {})
    payload = deepcopy(payload or {})

    scalar_keys = [
        "temperature",
        "max_tokens",
        "max_context_window",
        "timeout",
        "stream_timeout",
        "first_chunk_timeout",
        "multimodal",
        "compressor_multimodal",
    ]
    for key in scalar_keys:
        if key in payload and payload[key] is not None:
            config[key] = payload[key]

    config.setdefault("base_url", "")
    config.setdefault("api_key", "")

    mode = str(payload.get("mode") or "unified").strip().lower()
    use_unified = mode != "split"

    shared_profile = payload.get("unified") if isinstance(payload.get("unified"), dict) else None

    slot_sources = {
        "main": payload.get("main"),
        "figure": payload.get("figure"),
        "compressor": payload.get("compressor"),
        "read_figure": payload.get("read_figure"),
        "thinking": payload.get("thinking"),
    }

    for slot_name, config_key in MODEL_SLOT_TO_CONFIG_KEY.items():
        if slot_name not in {"main", "figure", "compressor", "read_figure", "thinking"}:
            continue
        slot_profile = shared_profile if use_unified else slot_sources.get(slot_name)
        if not isinstance(slot_profile, dict):
            continue
        entry = build_model_entry(slot_profile)
        if entry:
            config[config_key] = [entry]

    return config
