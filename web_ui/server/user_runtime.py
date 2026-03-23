#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web UI per-user runtime helpers.

Avoids switching global process env inside the Flask server by giving each user an
explicit runtime root, config root, agent library, tools library and skills dir.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from utils.user_paths import get_project_root


SERVER_DIR = Path(__file__).resolve().parent
WEB_UI_USER_DATA_ROOT = Path(
    os.environ.get("WEB_UI_USER_DATA_ROOT", str(SERVER_DIR / "user_data"))
).expanduser().resolve()


def sanitize_username(username: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(username or "").strip())
    value = value.strip("._-")
    return value or "user"


def get_web_user_home(username: str) -> Path:
    return WEB_UI_USER_DATA_ROOT / sanitize_username(username)


def get_web_user_data_root(username: str) -> Path:
    return get_web_user_home(username) / "mla_v3"


def get_web_user_config_dir(username: str) -> Path:
    return get_web_user_data_root(username) / "config"


def get_web_user_llm_config_path(username: str) -> Path:
    return get_web_user_config_dir(username) / "llm_config.yaml"


def get_web_user_app_config_path(username: str) -> Path:
    return get_web_user_config_dir(username) / "app_config.json"


def get_web_user_agent_library_root(username: str) -> Path:
    return get_web_user_data_root(username) / "agent_library"


def get_web_user_tools_library_root(username: str) -> Path:
    return get_web_user_data_root(username) / "tools_library"


def get_web_user_conversations_dir(username: str) -> Path:
    return get_web_user_data_root(username) / "conversations"


def get_web_user_logs_dir(username: str) -> Path:
    return get_web_user_data_root(username) / "logs"


def get_web_user_runtime_dir(username: str) -> Path:
    return get_web_user_data_root(username) / "runtime"


def get_web_user_skills_dir(username: str) -> Path:
    return get_web_user_home(username) / "skills"


def _blank_api_keys(value: Any) -> Any:
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            if str(k).strip().lower() == "api_key":
                result[k] = ""
            else:
                result[k] = _blank_api_keys(v)
        return result
    if isinstance(value, list):
        return [_blank_api_keys(v) for v in value]
    return value


def _seed_directory_children(src_root: Path, dest_root: Path) -> None:
    if not src_root.exists():
        return
    dest_root.mkdir(parents=True, exist_ok=True)
    for entry in src_root.iterdir():
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        dest = dest_root / entry.name
        if dest.exists():
            continue
        shutil.copytree(entry, dest)


def ensure_web_user_runtime(username: str) -> Path:
    user_home = get_web_user_home(username)
    user_root = get_web_user_data_root(username)
    config_dir = get_web_user_config_dir(username)
    agent_root = get_web_user_agent_library_root(username)
    tools_root = get_web_user_tools_library_root(username)
    conversations_dir = get_web_user_conversations_dir(username)
    logs_dir = get_web_user_logs_dir(username)
    runtime_dir = get_web_user_runtime_dir(username)
    skills_dir = get_web_user_skills_dir(username)

    for path in [
        user_home,
        user_root,
        config_dir,
        agent_root,
        tools_root,
        conversations_dir,
        logs_dir,
        runtime_dir,
        runtime_dir / "task_events",
        runtime_dir / "launched_tasks",
        skills_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)

    project_root = get_project_root()
    _seed_directory_children(project_root / "config" / "agent_library", agent_root)
    _seed_directory_children(project_root / "skills", skills_dir)

    llm_config_path = get_web_user_llm_config_path(username)
    if not llm_config_path.exists():
        example_path = project_root / "config" / "run_env_config" / "llm_config.example.yaml"
        if example_path.exists():
            try:
                parsed = yaml.safe_load(example_path.read_text(encoding="utf-8"))
                sanitized = _blank_api_keys(parsed)
                llm_config_path.write_text(
                    yaml.safe_dump(sanitized, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
            except Exception:
                llm_config_path.write_text('base_url: ""\napi_key: ""\nmodels:\n  - openai/gpt-4o-mini\n', encoding="utf-8")
        else:
            llm_config_path.write_text('base_url: ""\napi_key: ""\nmodels:\n  - openai/gpt-4o-mini\n', encoding="utf-8")

    app_config_path = get_web_user_app_config_path(username)
    if not app_config_path.exists():
        default_payload = {
            "runtime": {
                "action_window_steps": 30,
                "thinking_interval": 30,
                "max_turns": 100000,
                "fresh_enabled": False,
                "fresh_interval_sec": 0,
            },
            "env": {
                "command_mode": "direct",
                "seed_builtin_resources": True,
            },
            "context": {
                "user_history_compress_threshold_tokens": 1500,
                "structured_call_info_compress_threshold_agents": 10,
                "structured_call_info_compress_threshold_tokens": 2200,
            },
            "mcp": {
                "servers": [],
            },
        }
        app_config_path.write_text(
            json.dumps(default_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    return user_root
