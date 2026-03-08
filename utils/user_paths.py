#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
用户目录路径与运行时配置辅助函数。

统一约定：
- 用户数据根目录默认在 ~/mla_v3
- 可通过环境变量 MLA_USER_DATA_ROOT 覆盖
- CLI / Desktop / 打包后的 Python 后端都应优先读取这里的配置和扩展资源
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List

import yaml


def get_project_root() -> Path:
    """获取当前 Python 后端项目根目录。"""
    return Path(__file__).resolve().parent.parent


def get_user_data_root() -> Path:
    """获取用户数据根目录，默认 ~/mla_v3。"""
    env_root = os.environ.get("MLA_USER_DATA_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()
    return (Path.home() / "mla_v3").resolve()


def get_user_config_dir() -> Path:
    return get_user_data_root() / "config"


def get_user_llm_config_path() -> Path:
    env_path = os.environ.get("MLA_LLM_CONFIG_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return get_user_config_dir() / "llm_config.yaml"


def get_user_app_config_path() -> Path:
    return get_user_config_dir() / "app_config.json"


def get_user_agent_library_root() -> Path:
    return get_user_data_root() / "agent_library"


def get_agent_hidden_root() -> Path:
    """主流 agent 生态通用目录：~/.agent/"""
    return (Path.home() / ".agent").resolve()


def get_user_skills_library_root() -> Path:
    env_path = os.environ.get("MLA_SKILLS_LIBRARY_DIR", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return get_agent_hidden_root() / "skills"


def get_user_tools_library_root() -> Path:
    env_path = os.environ.get("MLA_TOOLS_LIBRARY_DIR", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    return get_user_data_root() / "tools_library"


def get_user_conversations_dir() -> Path:
    return get_user_data_root() / "conversations"


def get_user_logs_dir() -> Path:
    return get_user_data_root() / "logs"


def ensure_user_data_root_scaffold() -> None:
    """确保用户目录结构存在。"""
    for path in [
        get_user_data_root(),
        get_agent_hidden_root(),
        get_user_config_dir(),
        get_user_agent_library_root(),
        get_user_skills_library_root(),
        get_user_tools_library_root(),
        get_user_conversations_dir(),
        get_user_logs_dir(),
    ]:
        path.mkdir(parents=True, exist_ok=True)


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


def seed_user_resources_if_missing() -> None:
    """
    将项目内置的默认 agent systems / skills 种到用户目录。
    仅在目标缺失时复制，不覆盖用户已有资源。
    """
    ensure_user_data_root_scaffold()
    project_root = get_project_root()
    _seed_directory_children(project_root / "config" / "agent_library", get_user_agent_library_root())
    # 兼容旧目录：若 ~/.agent/skills 为空，则将 ~/mla_v3/skills_library 中内容迁移/补齐过去
    old_skills_root = get_user_data_root() / "skills_library"
    if old_skills_root.exists():
        _seed_directory_children(old_skills_root, get_user_skills_library_root())
    _seed_directory_children(project_root / "skills", get_user_skills_library_root())


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


def ensure_user_llm_config_exists() -> Path:
    """
    确保用户目录中的 llm_config.yaml 存在。
    优先从 llm_config.example.yaml 复制；若不存在则写入最小配置。
    """
    ensure_user_data_root_scaffold()
    config_path = get_user_llm_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        return config_path

    project_root = get_project_root()
    example_path = project_root / "config" / "run_env_config" / "llm_config.example.yaml"

    if example_path.exists():
        try:
            raw = example_path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(raw)
            if parsed is None:
                config_path.write_text(raw, encoding="utf-8")
            else:
                sanitized = _blank_api_keys(parsed)
                config_path.write_text(
                    yaml.safe_dump(sanitized, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
            return config_path
        except Exception:
            pass

    minimal = "\n".join([
        "temperature: 0",
        "max_tokens: 0",
        "max_context_window: 200000",
        'base_url: ""',
        'api_key: ""',
        "models:",
        "  - openai/gpt-4o-mini",
        "multimodal: false",
        "compressor_multimodal: false",
        "",
    ])
    config_path.write_text(minimal, encoding="utf-8")
    return config_path


def load_user_app_config() -> Dict[str, Any]:
    """读取用户 app_config.json；不存在或解析失败时返回空 dict。"""
    path = get_user_app_config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_mcp_settings() -> Dict[str, Any]:
    """
    读取 MCP 配置。
    优先级：
    1. MLA_MCP_CONFIG_JSON 环境变量（JSON 字符串）
    2. app_config.json 中 mcp 字段
    """
    env_json = os.environ.get("MLA_MCP_CONFIG_JSON", "").strip()
    if env_json:
        try:
            data = json.loads(env_json)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    cfg = load_user_app_config()
    mcp = cfg.get("mcp", {}) if isinstance(cfg, dict) else {}
    return mcp if isinstance(mcp, dict) else {}


def get_runtime_settings() -> Dict[str, Any]:
    """
    读取运行时配置。
    统一管理：
    - 动作窗口步长
    - thinking 间隔
    - fresh 是否启用
    - fresh 定时触发间隔（秒）
    """
    cfg = load_user_app_config()
    runtime = cfg.get("runtime", {}) if isinstance(cfg, dict) else {}

    env_action_window = os.environ.get("MLA_ACTION_WINDOW_STEPS", "").strip()
    env_thinking_interval = os.environ.get("MLA_THINKING_INTERVAL", "").strip()
    env_fresh_enabled = os.environ.get("MLA_FRESH_ENABLED", "").strip().lower()
    env_fresh_interval = os.environ.get("MLA_FRESH_INTERVAL_SEC", "").strip()

    action_window_steps = int(env_action_window or runtime.get("action_window_steps", 10) or 10)
    thinking_interval = int(env_thinking_interval or runtime.get("thinking_interval", action_window_steps) or action_window_steps)
    fresh_enabled = (env_fresh_enabled in {"1", "true", "yes", "on"}) if env_fresh_enabled else bool(runtime.get("fresh_enabled", False))
    fresh_interval_sec = int(env_fresh_interval or runtime.get("fresh_interval_sec", 0) or 0)
    return {
        "action_window_steps": max(1, action_window_steps),
        "thinking_interval": max(1, thinking_interval),
        "fresh_enabled": fresh_enabled,
        "fresh_interval_sec": max(0, fresh_interval_sec),
    }


def get_default_command_mode() -> str:
    """
    获取 execute_command 默认模式。
    优先级：
    1. MLA_EXECUTE_COMMAND_MODE 环境变量
    2. ~/mla_v3/config/app_config.json 中 env.command_mode
    3. direct
    """
    env_mode = os.environ.get("MLA_EXECUTE_COMMAND_MODE", "").strip().lower()
    if env_mode:
        return env_mode

    cfg = load_user_app_config()
    mode = str(cfg.get("env", {}).get("command_mode", "")).strip().lower()
    return mode or "direct"


def apply_runtime_env_defaults() -> None:
    """
    为 Python 运行时补齐统一环境变量。
    让 CLI / Desktop / 打包后端都默认指向用户目录，而非仓库本地目录。
    """
    ensure_user_data_root_scaffold()
    seed_user_resources_if_missing()
    os.environ["MLA_LLM_CONFIG_PATH"] = str(ensure_user_llm_config_exists())
    os.environ["MLA_AGENT_LIBRARY_DIR"] = str(get_user_data_root())
    os.environ["MLA_SKILLS_LIBRARY_DIR"] = str(get_user_skills_library_root())
    os.environ["MLA_TOOLS_LIBRARY_DIR"] = str(get_user_tools_library_root())
    os.environ["MLA_EXECUTE_COMMAND_MODE"] = get_default_command_mode()
    runtime = get_runtime_settings()
    os.environ["MLA_ACTION_WINDOW_STEPS"] = str(runtime["action_window_steps"])
    os.environ["MLA_THINKING_INTERVAL"] = str(runtime["thinking_interval"])
    os.environ["MLA_FRESH_ENABLED"] = "true" if runtime["fresh_enabled"] else "false"
    os.environ["MLA_FRESH_INTERVAL_SEC"] = str(runtime["fresh_interval_sec"])
    mcp = get_mcp_settings()
    if mcp:
        os.environ["MLA_MCP_CONFIG_JSON"] = json.dumps(mcp, ensure_ascii=False)
