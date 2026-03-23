#!/usr/bin/env python3
"""Standalone CheapClaw application built on top of the public InfiAgent SDK."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import requests

from infiagent import InfiAgent, infiagent

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

try:
    from .tool_runtime_helpers import (
        ack_outbox_event,
        ack_task_event,
        append_history,
        bind_messages_to_task,
        compute_next_scheduled_run,
        ensure_conversation,
        generate_task_id,
        get_channels_root,
        list_global_skills,
        list_outbox_events,
        list_task_events,
        load_plans,
        now_iso,
        parse_iso,
        queue_outbound_message,
        refresh_conversation_context_file,
        save_plans,
        set_task_visible_skills,
        _short_text,
        slugify,
        update_conversation_task,
    )
except ImportError:
    from tool_runtime_helpers import (
        ack_outbox_event,
        ack_task_event,
        append_history,
        bind_messages_to_task,
        compute_next_scheduled_run,
        ensure_conversation,
        generate_task_id,
        get_channels_root,
        list_global_skills,
        list_outbox_events,
        list_task_events,
        load_plans,
        now_iso,
        parse_iso,
        queue_outbound_message,
        refresh_conversation_context_file,
        save_plans,
        set_task_visible_skills,
        _short_text,
        slugify,
        update_conversation_task,
    )

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


APP_ROOT = Path(__file__).resolve().parent
ASSET_ROOT = APP_ROOT / "assets"
ASSET_AGENT_LIBRARY_ROOT = ASSET_ROOT / "agent_library"
ASSET_CONFIG_ROOT = ASSET_ROOT / "config"
ASSET_APP_CONFIG_EXAMPLE_PATH = ASSET_CONFIG_ROOT / "app_config.example.json"
ASSET_CHANNELS_EXAMPLE_PATH = ASSET_CONFIG_ROOT / "channels.example.json"
APP_TOOLS_ROOT = APP_ROOT / "tools_library"
APP_SKILLS_ROOT = APP_ROOT / "skills"
APP_WEB_ROOT = APP_ROOT / "web"
SERVICE_LOG_PATH: Optional[Path] = None
ACTIVE_SERVICE: Optional["CheapClawService"] = None
FINAL_OUTPUT_HOOK_CALLBACK = f"{(APP_ROOT / 'cheapclaw_hooks.py').resolve()}:on_tool_event"


def _tail_text(path: Path, max_chars: int = 4000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def _log(message: str) -> None:
    line = f"[CheapClaw {datetime.now().astimezone().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    global SERVICE_LOG_PATH
    if SERVICE_LOG_PATH is not None:
        try:
            SERVICE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SERVICE_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:
            pass


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_cheapclaw_app_config_example() -> Dict[str, Any]:
    fallback = {
        "runtime": {
            "action_window_steps": 20,
            "thinking_interval": 20,
            "fresh_enabled": False,
            "fresh_interval_sec": 0,
        },
        "env": {
            "command_mode": "direct",
            "seed_builtin_resources": False,
        },
        "cheapclaw": {
            "watchdog_interval_sec": 10800,
            "default_exposed_skills": ["docx", "pptx", "xlsx", "find-skills"],
            "default_mcp_servers": [],
            "feishu_mode": "long_connection",
            "service_log_file": "cheapclaw_service.log",
        },
    }
    return _load_json(ASSET_APP_CONFIG_EXAMPLE_PATH, fallback)


def _extract_cheapclaw_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = payload if isinstance(payload, dict) else {}
    example_payload = _load_cheapclaw_app_config_example()
    example_cheapclaw = example_payload.get("cheapclaw", {}) if isinstance(example_payload.get("cheapclaw"), dict) else {}
    cheapclaw = payload.get("cheapclaw", {}) if isinstance(payload.get("cheapclaw"), dict) else {}
    default_skills = cheapclaw.get("default_exposed_skills", example_cheapclaw.get("default_exposed_skills", ["docx", "pptx", "xlsx", "find-skills"]))
    if not isinstance(default_skills, list):
        default_skills = list(example_cheapclaw.get("default_exposed_skills", ["docx", "pptx", "xlsx", "find-skills"]))
    default_mcp_servers = cheapclaw.get("default_mcp_servers", example_cheapclaw.get("default_mcp_servers", []))
    if not isinstance(default_mcp_servers, list):
        default_mcp_servers = list(example_cheapclaw.get("default_mcp_servers", []))
    return {
        "watchdog_interval_sec": max(60, int(cheapclaw.get("watchdog_interval_sec", example_cheapclaw.get("watchdog_interval_sec", 10800)) or example_cheapclaw.get("watchdog_interval_sec", 10800))),
        "default_exposed_skills": [str(item).strip() for item in default_skills if str(item).strip()],
        "default_mcp_servers": [item for item in default_mcp_servers if isinstance(item, dict)],
        "feishu_mode": str(cheapclaw.get("feishu_mode", example_cheapclaw.get("feishu_mode", "long_connection")) or example_cheapclaw.get("feishu_mode", "long_connection")).strip(),
        "service_log_file": str(cheapclaw.get("service_log_file", example_cheapclaw.get("service_log_file", "cheapclaw_service.log")) or example_cheapclaw.get("service_log_file", "cheapclaw_service.log")).strip(),
    }


@dataclass(frozen=True)
class CheapClawPaths:
    user_data_root: Path
    cheapclaw_root: Path
    panel_dir: Path
    panel_path: Path
    panel_lock_path: Path
    panel_backups_dir: Path
    plans_path: Path
    config_dir: Path
    app_config_path: Path
    app_config_example_path: Path
    channels_config_path: Path
    channels_example_path: Path
    channels_root: Path
    outbox_dir: Path
    tasks_root: Path
    task_skills_root: Path
    supervisor_task_id: Path
    runtime_dir: Path
    runtime_state_path: Path

    @classmethod
    def from_user_data_root(cls, user_data_root: str | Path, app_name: str = "cheapclaw") -> "CheapClawPaths":
        root = Path(user_data_root).expanduser().resolve()
        cheapclaw_root = root / app_name
        panel_dir = cheapclaw_root / "panel"
        runtime_dir = cheapclaw_root / "runtime"
        config_dir = cheapclaw_root / "config"
        return cls(
            user_data_root=root,
            cheapclaw_root=cheapclaw_root,
            panel_dir=panel_dir,
            panel_path=panel_dir / "panel.json",
            panel_lock_path=panel_dir / "panel.lock",
            panel_backups_dir=panel_dir / "backups",
            plans_path=cheapclaw_root / "plans.json",
            config_dir=config_dir,
            app_config_path=config_dir / "app_config.json",
            app_config_example_path=config_dir / "app_config.example.json",
            channels_config_path=config_dir / "channels.json",
            channels_example_path=config_dir / "channels.example.json",
            channels_root=cheapclaw_root / "channels",
            outbox_dir=cheapclaw_root / "outbox",
            tasks_root=cheapclaw_root / "tasks",
            task_skills_root=cheapclaw_root / "task_skills",
            supervisor_task_id=cheapclaw_root / "supervisor_task",
            runtime_dir=runtime_dir,
            runtime_state_path=runtime_dir / "state.json",
        )


class CheapClawPanelStore:
    def __init__(self, paths: CheapClawPaths, history_preview_limit: int = 50):
        self.paths = paths
        self.history_preview_limit = max(1, int(history_preview_limit))
        self._thread_lock = threading.RLock()
        self.ensure_layout()

    def ensure_layout(self) -> None:
        for path in [
            self.paths.cheapclaw_root,
            self.paths.panel_dir,
            self.paths.panel_backups_dir,
            self.paths.config_dir,
            self.paths.runtime_dir,
            self.paths.channels_root,
            self.paths.outbox_dir,
            self.paths.tasks_root,
            self.paths.task_skills_root,
        ]:
            path.mkdir(parents=True, exist_ok=True)
        if not self.paths.panel_path.exists():
            _atomic_write_text(
                self.paths.panel_path,
                json.dumps(
                    {
                        "version": 1,
                        "channels": {},
                        "service_state": {
                            "main_agent_task_id": str(self.paths.supervisor_task_id),
                            "main_agent_running": False,
                            "main_agent_run_id": "",
                            "main_agent_last_started_at": "",
                            "main_agent_last_finished_at": "",
                            "main_agent_dirty": False,
                            "watchdog_last_run_at": "",
                            "last_backup_path": "",
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        if not self.paths.plans_path.exists():
            _atomic_write_text(self.paths.plans_path, json.dumps({"version": 1, "plans": []}, ensure_ascii=False, indent=2))
        if not self.paths.runtime_state_path.exists():
            _atomic_write_text(self.paths.runtime_state_path, json.dumps({"webhook_server": {}, "telegram_offsets": {}}, ensure_ascii=False, indent=2))

    @contextmanager
    def _file_lock(self):
        self.paths.panel_dir.mkdir(parents=True, exist_ok=True)
        with self._thread_lock:
            with open(self.paths.panel_lock_path, "a+", encoding="utf-8") as lock_file:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def load_panel(self) -> Dict[str, Any]:
        return self._normalize_panel(_load_json(self.paths.panel_path, {"version": 1, "channels": {}, "service_state": {}}))

    def save_panel(self, panel: Dict[str, Any], *, backup: bool = True) -> Dict[str, Any]:
        normalized = self._normalize_panel(panel)
        with self._file_lock():
            self._write_panel_locked(normalized, backup=backup)
        return normalized

    def mutate(self, updater: Callable[[Dict[str, Any]], Dict[str, Any] | None]) -> Dict[str, Any]:
        with self._file_lock():
            current = self.load_panel()
            updated = updater(current)
            panel = current if updated is None else updated
            normalized = self._normalize_panel(panel)
            self._write_panel_locked(normalized, backup=True)
            return normalized

    def _write_panel_locked(self, panel: Dict[str, Any], *, backup: bool) -> None:
        if backup and self.paths.panel_path.exists():
            backup_path = self.paths.panel_backups_dir / f"panel_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
            backup_path.write_text(self.paths.panel_path.read_text(encoding="utf-8"), encoding="utf-8")
            panel.setdefault("service_state", {})["last_backup_path"] = str(backup_path)
        _atomic_write_text(self.paths.panel_path, json.dumps(panel, ensure_ascii=False, indent=2))

    def _normalize_panel(self, panel: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(panel, dict):
            panel = {}
        panel.setdefault("version", 1)
        panel.setdefault("channels", {})
        panel.setdefault("service_state", {})
        defaults = {
            "main_agent_task_id": str(self.paths.supervisor_task_id),
            "main_agent_running": False,
            "main_agent_run_id": "",
            "main_agent_last_started_at": "",
            "main_agent_last_finished_at": "",
            "main_agent_dirty": False,
            "watchdog_last_run_at": "",
            "last_backup_path": "",
        }
        for key, value in defaults.items():
            panel["service_state"].setdefault(key, value)
        for channel, payload in list(panel["channels"].items()):
            if not isinstance(payload, dict):
                panel["channels"][channel] = {"conversations": {}}
                payload = panel["channels"][channel]
            payload.setdefault("conversations", {})
            for conversation_id, conversation in list(payload["conversations"].items()):
                payload["conversations"][conversation_id] = self._normalize_conversation(channel, conversation_id, conversation)
        return panel

    def _normalize_conversation(self, channel: str, conversation_id: str, conversation: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(conversation, dict):
            conversation = {}
        defaults = {
            "channel": channel,
            "conversation_id": conversation_id,
            "conversation_type": "group",
            "display_name": conversation_id,
            "trigger_policy": {"require_mention": True},
            "message_history_path": str(get_channels_root() / slugify(channel) / slugify(conversation_id) / "social_history.jsonl"),
            "context_summary_path": str(get_channels_root() / slugify(channel) / slugify(conversation_id) / "latest_context.md"),
            "messages": [],
            "linked_tasks": [],
            "pending_events": [],
            "dirty": False,
            "last_snapshot_path": "",
            "updated_at": "",
            "running_task_count": 0,
            "has_stale_running_tasks": False,
            "latest_user_message_at": "",
            "latest_bot_message_at": "",
            "unread_event_count": 0,
            "last_reply_summary": "",
            "conversation_tags": [],
            "message_task_bindings": [],
        }
        for key, value in defaults.items():
            conversation.setdefault(key, value)
        normalized_tasks = []
        for item in conversation.get("linked_tasks", []):
            if not isinstance(item, dict):
                continue
            task_id = str(item.get("task_id") or "").strip()
            if not task_id:
                continue
            task_defaults = {
                "task_id": task_id,
                "created_at": "",
                "agent_system": "",
                "agent_name": "",
                "status": "unknown",
                "share_context_path": "",
                "stack_path": "",
                "log_path": "",
                "skills_dir": "",
                "default_exposed_skills": [],
                "mcp_servers": [],
                "last_thinking": "",
                "last_thinking_at": "",
                "last_final_output": "",
                "last_final_output_at": "",
                "last_action_at": "",
                "last_log_at": "",
                "fresh_retry_count": 0,
                "last_watchdog_note": "",
                "pid_alive": None,
                "watchdog_observation": "",
                "watchdog_suspected_state": "",
            }
            task_defaults.update(item)
            normalized_tasks.append(task_defaults)
        conversation["linked_tasks"] = normalized_tasks
        conversation["running_task_count"] = sum(1 for item in normalized_tasks if item.get("status") == "running")
        conversation["unread_event_count"] = len(conversation.get("pending_events", []))
        return conversation

    def dirty_conversations(self) -> List[Dict[str, Any]]:
        panel = self.load_panel()
        items = []
        for channel_payload in panel.get("channels", {}).values():
            for conv in channel_payload.get("conversations", {}).values():
                if conv.get("dirty"):
                    items.append(conv)
        return items

    def record_social_message(self, **kwargs) -> Dict[str, Any]:
        timestamp = kwargs.get("timestamp") or now_iso()
        channel = str(kwargs.get("channel") or "").strip()
        conversation_id = str(kwargs.get("conversation_id") or "").strip()
        message_text = str(kwargs.get("message_text") or "").strip()
        attachments = kwargs.get("attachments") or []
        if not channel or not conversation_id or (not message_text and not attachments):
            raise ValueError("channel, conversation_id and message_text/attachments are required")

        def _update(panel: Dict[str, Any]) -> Dict[str, Any]:
            conv = ensure_conversation(
                panel,
                channel=channel,
                conversation_id=conversation_id,
                conversation_type=str(kwargs.get("conversation_type") or "group"),
                display_name=kwargs.get("display_name") or conversation_id,
                require_mention=bool(kwargs.get("require_mention", True)),
            )
            event = {
                "message_id": str(kwargs.get("message_id") or "").strip(),
                "timestamp": timestamp,
                "sender_id": str(kwargs.get("sender_id") or "").strip(),
                "sender_name": str(kwargs.get("sender_name") or "").strip(),
                "text": message_text,
                "attachments": attachments,
                "is_mention_to_bot": bool(kwargs.get("is_mention_to_bot", False)),
                "direction": "inbound",
            }
            history_path = Path(conv["message_history_path"])
            history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(history_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            conv.setdefault("messages", []).append(event)
            del conv["messages"][:-self.history_preview_limit]
            conv.setdefault("pending_events", []).append({"type": "social_message", "timestamp": timestamp, "message_id": event["message_id"]})
            if kwargs.get("mark_dirty", True):
                conv["dirty"] = True
                panel["service_state"]["main_agent_dirty"] = True
            conv["updated_at"] = timestamp
            conv["latest_user_message_at"] = timestamp
            conv["unread_event_count"] = len(conv["pending_events"])
            return panel
        panel = self.mutate(_update)
        refresh_conversation_context_file(channel, conversation_id, panel)
        return panel

    def set_main_agent_state(self, *, running: bool, run_id: str = "", mark_dirty: Optional[bool] = None) -> Dict[str, Any]:
        def _update(panel: Dict[str, Any]) -> Dict[str, Any]:
            state = panel["service_state"]
            state["main_agent_running"] = bool(running)
            if run_id:
                state["main_agent_run_id"] = run_id
            if running:
                state["main_agent_last_started_at"] = now_iso()
            else:
                state["main_agent_last_finished_at"] = now_iso()
            if mark_dirty is not None:
                state["main_agent_dirty"] = bool(mark_dirty)
            return panel
        return self.mutate(_update)

    def mark_watchdog_tick(self) -> Dict[str, Any]:
        def _update(panel: Dict[str, Any]) -> Dict[str, Any]:
            panel["service_state"]["watchdog_last_run_at"] = now_iso()
            return panel
        return self.mutate(_update)


class ChannelAdapter:
    name = "base"

    def __init__(self, config: Dict[str, Any], service: "CheapClawService"):
        self.config = config
        self.service = service

    def poll_events(self) -> List[Dict[str, Any]]:
        return []

    def send_message(self, conversation_id: str, message: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, str]:
        raise NotImplementedError

    @staticmethod
    def _normalize_attachments(attachments: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        items = []
        for item in attachments or []:
            if not isinstance(item, dict):
                continue
            local_path = str(item.get("local_path") or item.get("path") or "").strip()
            if not local_path:
                continue
            path = Path(local_path).expanduser().resolve()
            if not path.exists() or not path.is_file():
                continue
            guessed_mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            items.append({
                "path": path,
                "filename": str(item.get("filename") or path.name),
                "mime_type": str(item.get("mime_type") or guessed_mime),
                "kind": str(item.get("kind") or "auto").strip().lower() or "auto",
                "caption": str(item.get("caption") or "").strip(),
            })
        return items

    def handle_webhook_get(self, path: str, query: Dict[str, List[str]], headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
        return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"not found"

    def handle_webhook_post(self, path: str, body: bytes, headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
        return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"not found"


def _ensure_cheapclaw_app_config(paths: CheapClawPaths) -> Dict[str, Any]:
    paths.config_dir.mkdir(parents=True, exist_ok=True)
    example_payload = _load_cheapclaw_app_config_example()
    _atomic_write_text(paths.app_config_example_path, json.dumps(example_payload, ensure_ascii=False, indent=2))
    if not paths.app_config_path.exists():
        _atomic_write_text(paths.app_config_path, json.dumps(example_payload, ensure_ascii=False, indent=2))
    payload = _load_json(paths.app_config_path, example_payload)
    if not isinstance(payload, dict):
        payload = {}
    runtime_cfg = payload.setdefault("runtime", {})
    if not isinstance(runtime_cfg, dict):
        runtime_cfg = {}
        payload["runtime"] = runtime_cfg
    runtime_cfg.setdefault("action_window_steps", example_payload["runtime"]["action_window_steps"])
    runtime_cfg.setdefault("thinking_interval", example_payload["runtime"]["thinking_interval"])
    runtime_cfg.setdefault("fresh_enabled", example_payload["runtime"]["fresh_enabled"])
    runtime_cfg.setdefault("fresh_interval_sec", example_payload["runtime"]["fresh_interval_sec"])
    if int(runtime_cfg.get("action_window_steps", 20) or 20) == 20 and int(runtime_cfg.get("thinking_interval", 20) or 20) == 10:
        runtime_cfg["thinking_interval"] = 20
    env_cfg = payload.setdefault("env", {})
    if not isinstance(env_cfg, dict):
        env_cfg = {}
        payload["env"] = env_cfg
    env_cfg["seed_builtin_resources"] = False
    env_cfg.setdefault("command_mode", example_payload["env"]["command_mode"])
    cheapclaw_cfg = payload.setdefault("cheapclaw", {})
    if not isinstance(cheapclaw_cfg, dict):
        cheapclaw_cfg = {}
        payload["cheapclaw"] = cheapclaw_cfg
    for key, value in example_payload["cheapclaw"].items():
        cheapclaw_cfg.setdefault(key, value)
    default_skills = cheapclaw_cfg.get("default_exposed_skills", [])
    if not isinstance(default_skills, list):
        default_skills = list(example_payload["cheapclaw"].get("default_exposed_skills", []))
    for skill_name in example_payload["cheapclaw"].get("default_exposed_skills", []):
        if skill_name not in default_skills:
            default_skills.append(skill_name)
    cheapclaw_cfg["default_exposed_skills"] = default_skills
    if not isinstance(cheapclaw_cfg.get("default_mcp_servers"), list):
        cheapclaw_cfg["default_mcp_servers"] = list(example_payload["cheapclaw"].get("default_mcp_servers", []))
    _atomic_write_text(paths.app_config_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def _sync_root_app_config_from_cheapclaw(user_data_root: Path, cheapclaw_cfg: Dict[str, Any]) -> None:
    root_path = Path(user_data_root).expanduser().resolve() / "config" / "app_config.json"
    root_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_json(root_path, {})
    if not isinstance(payload, dict):
        payload = {}
    runtime_cfg = cheapclaw_cfg.get("runtime", {}) if isinstance(cheapclaw_cfg, dict) else {}
    env_cfg = payload.setdefault("env", {})
    env_cfg["seed_builtin_resources"] = False
    env_cfg.setdefault("command_mode", "direct")
    runtime = payload.setdefault("runtime", {})
    if isinstance(runtime_cfg, dict):
        for key in ("action_window_steps", "thinking_interval", "fresh_enabled", "fresh_interval_sec"):
            if key in runtime_cfg:
                runtime[key] = runtime_cfg[key]
    payload.pop("cheapclaw", None)
    root_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class TelegramAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self, config: Dict[str, Any], service: "CheapClawService"):
        super().__init__(config, service)
        self.bot_token = str(config.get("bot_token") or "").strip()
        self.allowed_chats = {str(item) for item in config.get("allowed_chats", [])}
        self._api_root = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self._state = self.service.load_runtime_state()
        self._me_cache = self._state.get("telegram_bot_me") or {}

    def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._api_root:
            return {}
        response = requests.request(method, self._api_root + endpoint, timeout=30, **kwargs)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}

    def _get_me(self) -> Dict[str, Any]:
        if self._me_cache:
            return self._me_cache
        data = self._request("GET", "/getMe")
        self._me_cache = data.get("result", {}) if data.get("ok") else {}
        state = self.service.load_runtime_state()
        state["telegram_bot_me"] = self._me_cache
        self.service.save_runtime_state(state)
        return self._me_cache

    def _message_mentions_bot(self, message: Dict[str, Any], text: str, is_group: bool) -> bool:
        if not is_group:
            return True
        me = self._get_me() or {}
        bot_username = str(me.get("username") or "").strip()
        bot_id = str(me.get("id") or "").strip()
        if bot_username and f"@{bot_username}".lower() in text.lower():
            return True

        for entity in (message.get("entities") or []) + (message.get("caption_entities") or []):
            if not isinstance(entity, dict):
                continue
            entity_type = str(entity.get("type") or "")
            if entity_type == "mention" and bot_username:
                offset = int(entity.get("offset") or 0)
                length = int(entity.get("length") or 0)
                if text[offset:offset + length].lower() == f"@{bot_username}".lower():
                    return True
            if entity_type == "text_mention":
                user = entity.get("user") or {}
                if bot_id and str(user.get("id") or "") == bot_id:
                    return True

        reply_to = message.get("reply_to_message") or {}
        reply_from = reply_to.get("from") or {}
        if bot_id and str(reply_from.get("id") or "") == bot_id:
            return True
        if reply_from.get("is_bot") and bot_username and str(reply_from.get("username") or "").lower() == bot_username.lower():
            return True
        return False

    def poll_events(self) -> List[Dict[str, Any]]:
        if not self.bot_token:
            return []
        state = self.service.load_runtime_state()
        offsets = state.setdefault("telegram_offsets", {})
        offset = int(offsets.get("default", 0) or 0)
        data = self._request("GET", "/getUpdates", params={"timeout": 1, "offset": offset + 1})
        items = []
        for result in data.get("result", []):
            update_id = int(result.get("update_id") or 0)
            message = (
                result.get("message")
                or result.get("edited_message")
                or result.get("channel_post")
                or result.get("edited_channel_post")
                or result.get("business_message")
                or result.get("edited_business_message")
                or {}
            )
            chat = message.get("chat") or {}
            chat_id = str(chat.get("id") or "").strip()
            if not chat_id:
                continue
            if self.allowed_chats and chat_id not in self.allowed_chats:
                continue
            text = str(message.get("text") or message.get("caption") or "").strip()
            is_group = chat.get("type") in {"group", "supergroup"}
            mention = self._message_mentions_bot(message, text, is_group)
            if is_group and not mention:
                offsets["default"] = update_id
                continue
            from_user = message.get("from") or message.get("sender_chat") or {}
            sender_name = " ".join(
                part for part in [
                    str(from_user.get("first_name") or "").strip(),
                    str(from_user.get("last_name") or "").strip(),
                ] if part
            ).strip()
            if not sender_name:
                sender_name = str(from_user.get("title") or from_user.get("username") or "")
            items.append({
                "event_id": f"telegram_{update_id}",
                "channel": "telegram",
                "conversation_id": chat_id,
                "conversation_type": "group" if is_group else "person",
                "display_name": str(chat.get("title") or chat.get("username") or chat_id),
                "sender_id": str(from_user.get("id") or ""),
                "sender_name": sender_name,
                "message_id": str(message.get("message_id") or ""),
                "message_text": text,
                "attachments": [],
                "timestamp": datetime.fromtimestamp(int(message.get("date") or time.time())).astimezone().isoformat(timespec="seconds"),
                "is_mention_to_bot": mention,
                "require_mention": is_group,
            })
            offsets["default"] = update_id
        self.service.save_runtime_state(state)
        return items

    def send_message(self, conversation_id: str, message: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, str]:
        if not self.bot_token:
            return False, "telegram bot_token is missing"
        last_remote_id = ""
        normalized = self._normalize_attachments(attachments)
        if message:
            payload = {"chat_id": conversation_id, "text": message}
            try:
                data = self._request("POST", "/sendMessage", json=payload)
            except Exception as exc:
                return False, str(exc)
            if not data.get("ok"):
                return False, json.dumps(data, ensure_ascii=False)
            last_remote_id = str((data.get("result") or {}).get("message_id") or "")
        for item in normalized:
            mime_type = item["mime_type"]
            method = "/sendPhoto" if mime_type.startswith("image/") else "/sendDocument"
            field = "photo" if method == "/sendPhoto" else "document"
            data_payload = {"chat_id": conversation_id}
            caption = item["caption"] or (message if not last_remote_id else "")
            if caption:
                data_payload["caption"] = caption
            with open(item["path"], "rb") as fh:
                files = {field: (item["filename"], fh, mime_type)}
                try:
                    data = self._request("POST", method, data=data_payload, files=files)
                except Exception as exc:
                    return False, str(exc)
            if not data.get("ok"):
                return False, json.dumps(data, ensure_ascii=False)
            last_remote_id = str((data.get("result") or {}).get("message_id") or "")
        if not message and not normalized:
            return False, "telegram message or attachments are required"
        return True, last_remote_id


class FeishuAdapter(ChannelAdapter):
    name = "feishu"

    def __init__(self, config: Dict[str, Any], service: "CheapClawService"):
        super().__init__(config, service)
        self.app_id = str(config.get("app_id") or "").strip()
        self.app_secret = str(config.get("app_secret") or "").strip()
        self.verify_token = str(config.get("verify_token") or "").strip()
        self.encrypt_key = str(config.get("encrypt_key") or "").strip()
        self.mode = str(config.get("mode") or "long_connection").strip() or "long_connection"
        self.api_root = "https://open.feishu.cn/open-apis"
        self._queue_lock = threading.Lock()
        self._queued_events: List[Dict[str, Any]] = []
        self._long_conn_thread: Optional[threading.Thread] = None
        self._long_conn_started = False
        if self.mode == "long_connection":
            self._start_long_connection()

    def _enqueue_event(self, payload: Dict[str, Any]) -> None:
        with self._queue_lock:
            self._queued_events.append(payload)

    def _normalize_message_event(self, header: Dict[str, Any], event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        message = event.get("message") or {}
        sender = event.get("sender") or {}
        if header.get("event_type") != "im.message.receive_v1":
            return None
        text = ""
        content_raw = message.get("content")
        if isinstance(content_raw, str):
            try:
                content = json.loads(content_raw)
            except Exception:
                content = {}
            text = str(content.get("text") or "").strip()
        chat_type = str(message.get("chat_type") or "")
        chat_id = str(message.get("chat_id") or "").strip()
        if not chat_id:
            return None
        mention = (chat_type != "group") or ("<at" in text)
        return {
            "event_id": f"feishu_{message.get('message_id')}",
            "channel": "feishu",
            "conversation_id": chat_id,
            "conversation_type": "group" if chat_type == "group" else "person",
            "display_name": chat_id,
            "sender_id": str((sender.get("sender_id") or {}).get("open_id") or ""),
            "sender_name": str((sender.get("sender_id") or {}).get("user_id") or ""),
            "message_id": str(message.get("message_id") or ""),
            "message_text": text,
            "attachments": [],
            "timestamp": now_iso(),
            "is_mention_to_bot": mention,
            "require_mention": chat_type == "group",
        }

    def _start_long_connection(self) -> None:
        if self._long_conn_started:
            return
        self._long_conn_started = True
        if not self.app_id or not self.app_secret:
            _log("Feishu long connection skipped: missing app_id/app_secret")
            return

        def _runner() -> None:
            try:
                import lark_oapi as lark

                def _handle_message(data) -> None:
                    try:
                        payload = json.loads(lark.JSON.marshal(data) or "{}")
                        normalized = self._normalize_message_event(payload.get("header") or {}, payload.get("event") or {})
                        if normalized:
                            self._enqueue_event(normalized)
                    except Exception as exc:
                        _log(f"Feishu long connection event parse failed: {exc}")

                event_handler = lark.EventDispatcherHandler.builder(
                    self.encrypt_key,
                    self.verify_token,
                ).register_p2_im_message_receive_v1(_handle_message).build()

                client = lark.ws.Client(
                    self.app_id,
                    self.app_secret,
                    event_handler=event_handler,
                    log_level=lark.LogLevel.INFO,
                )
                _log("Feishu long connection started")
                client.start()
            except Exception as exc:
                _log(f"Feishu long connection stopped: {exc}")

        self._long_conn_thread = threading.Thread(target=_runner, daemon=True, name="cheapclaw-feishu-long-conn")
        self._long_conn_thread.start()

    def poll_events(self) -> List[Dict[str, Any]]:
        if self.mode != "long_connection":
            return []
        with self._queue_lock:
            items = list(self._queued_events)
            self._queued_events.clear()
            return items

    def _tenant_access_token(self) -> str:
        state = self.service.load_runtime_state()
        cached = state.get("feishu_token") or {}
        expire_at = parse_iso(cached.get("expire_at", ""))
        if cached.get("token") and expire_at and expire_at > datetime.now().astimezone() + timedelta(seconds=60):
            return str(cached["token"])
        if not self.app_id or not self.app_secret:
            return ""
        response = requests.post(
            f"{self.api_root}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        token = str(data.get("tenant_access_token") or "")
        expire_at = datetime.now().astimezone() + timedelta(seconds=int(data.get("expire", 0) or 0))
        state["feishu_token"] = {"token": token, "expire_at": expire_at.isoformat(timespec="seconds")}
        self.service.save_runtime_state(state)
        return token

    def handle_webhook_post(self, path: str, body: bytes, headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return 400, {"Content-Type": "application/json"}, b'{"error":"invalid json"}'

        challenge = payload.get("challenge")
        if challenge:
            return 200, {"Content-Type": "application/json"}, json.dumps({"challenge": challenge}).encode("utf-8")

        normalized = self._normalize_message_event(payload.get("header") or {}, payload.get("event") or {})
        if normalized:
            self.service.ingest_event(normalized)
        return 200, {"Content-Type": "application/json"}, b'{"ok":true}'

    def send_message(self, conversation_id: str, message: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, str]:
        token = self._tenant_access_token()
        if not token:
            return False, "feishu app_id/app_secret are missing"
        last_remote_id = ""
        normalized = self._normalize_attachments(attachments)
        if message:
            response = requests.post(
                f"{self.api_root}/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                json={"receive_id": conversation_id, "msg_type": "text", "content": json.dumps({"text": message}, ensure_ascii=False)},
                timeout=30,
            )
            if response.status_code >= 300:
                return False, response.text
            data = response.json()
            last_remote_id = str(((data.get("data") or {}).get("message_id")) or "")
        for item in normalized:
            mime_type = item["mime_type"]
            is_image = mime_type.startswith("image/")
            upload_url = f"{self.api_root}/im/v1/images" if is_image else f"{self.api_root}/im/v1/files"
            with open(item["path"], "rb") as fh:
                files = {"image" if is_image else "file": (item["filename"], fh, mime_type)}
                data_payload = {"image_type": "message"} if is_image else {"file_type": "stream", "file_name": item["filename"]}
                upload_resp = requests.post(
                    upload_url,
                    headers={"Authorization": f"Bearer {token}"},
                    data=data_payload,
                    files=files,
                    timeout=60,
                )
            if upload_resp.status_code >= 300:
                return False, upload_resp.text
            upload_data = upload_resp.json()
            key_name = "image_key" if is_image else "file_key"
            media_key = str(((upload_data.get("data") or {}).get(key_name)) or "")
            if not media_key:
                return False, json.dumps(upload_data, ensure_ascii=False)
            msg_type = "image" if is_image else "file"
            content = {key_name: media_key}
            send_resp = requests.post(
                f"{self.api_root}/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
                json={"receive_id": conversation_id, "msg_type": msg_type, "content": json.dumps(content, ensure_ascii=False)},
                timeout=30,
            )
            if send_resp.status_code >= 300:
                return False, send_resp.text
            data = send_resp.json()
            last_remote_id = str(((data.get("data") or {}).get("message_id")) or "")
        if not message and not normalized:
            return False, "feishu message or attachments are required"
        return True, last_remote_id


class WhatsAppCloudAdapter(ChannelAdapter):
    name = "whatsapp"

    def __init__(self, config: Dict[str, Any], service: "CheapClawService"):
        super().__init__(config, service)
        self.access_token = str(config.get("access_token") or "").strip()
        self.phone_number_id = str(config.get("phone_number_id") or "").strip()
        self.verify_token = str(config.get("verify_token") or "").strip()
        self.api_version = str(config.get("api_version") or "v21.0").strip()
        self.api_root = f"https://graph.facebook.com/{self.api_version}"

    def handle_webhook_get(self, path: str, query: Dict[str, List[str]], headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
        mode = (query.get("hub.mode") or [""])[0]
        token = (query.get("hub.verify_token") or [""])[0]
        challenge = (query.get("hub.challenge") or [""])[0]
        if mode == "subscribe" and token and token == self.verify_token:
            return 200, {"Content-Type": "text/plain; charset=utf-8"}, challenge.encode("utf-8")
        return 403, {"Content-Type": "text/plain; charset=utf-8"}, b"forbidden"

    def handle_webhook_post(self, path: str, body: bytes, headers: Dict[str, str]) -> Tuple[int, Dict[str, str], bytes]:
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            return 400, {"Content-Type": "application/json"}, b'{"error":"invalid json"}'
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                contacts = value.get("contacts") or []
                contact_name = str((contacts[0].get("profile") or {}).get("name") or "") if contacts else ""
                for message in value.get("messages", []) or []:
                    text = str(((message.get("text") or {}).get("body")) or "").strip()
                    from_id = str(message.get("from") or "").strip()
                    self.service.ingest_event({
                        "event_id": f"whatsapp_{message.get('id')}",
                        "channel": "whatsapp",
                        "conversation_id": from_id,
                        "conversation_type": "person",
                        "display_name": contact_name or from_id,
                        "sender_id": from_id,
                        "sender_name": contact_name,
                        "message_id": str(message.get("id") or ""),
                        "message_text": text,
                        "attachments": [],
                        "timestamp": now_iso(),
                        "is_mention_to_bot": True,
                        "require_mention": False,
                    })
        return 200, {"Content-Type": "application/json"}, b'{"ok":true}'

    def send_message(self, conversation_id: str, message: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Tuple[bool, str]:
        if not self.access_token or not self.phone_number_id:
            return False, "whatsapp access_token or phone_number_id is missing"
        last_remote_id = ""
        normalized = self._normalize_attachments(attachments)
        if message:
            response = requests.post(
                f"{self.api_root}/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
                json={"messaging_product": "whatsapp", "to": conversation_id, "type": "text", "text": {"body": message}},
                timeout=30,
            )
            if response.status_code >= 300:
                return False, response.text
            data = response.json()
            if data.get("messages"):
                last_remote_id = str((data.get("messages") or [{}])[0].get("id") or "")
        for item in normalized:
            mime_type = item["mime_type"]
            media_type = "image" if mime_type.startswith("image/") else "document"
            with open(item["path"], "rb") as fh:
                files = {"file": (item["filename"], fh, mime_type)}
                upload_resp = requests.post(
                    f"{self.api_root}/{self.phone_number_id}/media",
                    headers={"Authorization": f"Bearer {self.access_token}"},
                    data={"messaging_product": "whatsapp", "type": mime_type},
                    files=files,
                    timeout=60,
                )
            if upload_resp.status_code >= 300:
                return False, upload_resp.text
            upload_data = upload_resp.json()
            media_id = str(upload_data.get("id") or "")
            if not media_id:
                return False, json.dumps(upload_data, ensure_ascii=False)
            payload = {
                "messaging_product": "whatsapp",
                "to": conversation_id,
                "type": media_type,
                media_type: {"id": media_id},
            }
            if media_type == "document":
                payload[media_type]["filename"] = item["filename"]
            caption = item["caption"] or (message if not last_remote_id else "")
            if caption:
                payload[media_type]["caption"] = caption
            send_resp = requests.post(
                f"{self.api_root}/{self.phone_number_id}/messages",
                headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            if send_resp.status_code >= 300:
                return False, send_resp.text
            data = send_resp.json()
            if data.get("messages"):
                last_remote_id = str((data.get("messages") or [{}])[0].get("id") or "")
        if not message and not normalized:
            return False, "whatsapp message or attachments are required"
        return True, last_remote_id


class CheapClawService:
    def __init__(
        self,
        *,
        user_data_root: str,
        llm_config_path: Optional[str] = None,
        default_agent_system: str = "CheapClawWorkerGeneral",
        default_agent_name: str = "worker_agent",
        supervisor_agent_system: str = "CheapClawSupervisor",
        supervisor_agent_name: str = "supervisor_agent",
        tools_dir: Optional[str] = None,
        skills_dir: Optional[str] = None,
        history_preview_limit: int = 50,
        watchdog_interval_sec: Optional[int] = None,
    ):
        global ACTIVE_SERVICE
        resolved_user_root = Path(user_data_root).expanduser().resolve()
        self.paths = CheapClawPaths.from_user_data_root(resolved_user_root)
        cheapclaw_cfg = _ensure_cheapclaw_app_config(self.paths)
        _sync_root_app_config_from_cheapclaw(resolved_user_root, cheapclaw_cfg)
        cheapclaw_settings = _extract_cheapclaw_settings(cheapclaw_cfg)
        runtime_cfg = cheapclaw_cfg.get("runtime", {}) if isinstance(cheapclaw_cfg, dict) else {}
        asset_tools_dir = str((Path(tools_dir).expanduser().resolve()) if tools_dir else APP_TOOLS_ROOT.resolve())
        self.sdk: InfiAgent = infiagent(
            user_data_root=str(resolved_user_root),
            llm_config_path=llm_config_path,
            default_agent_system=default_agent_system,
            default_agent_name=default_agent_name,
            tools_dir=asset_tools_dir,
            skills_dir=skills_dir,
            action_window_steps=runtime_cfg.get("action_window_steps"),
            thinking_interval=runtime_cfg.get("thinking_interval"),
            fresh_enabled=runtime_cfg.get("fresh_enabled"),
            fresh_interval_sec=runtime_cfg.get("fresh_interval_sec"),
            seed_builtin_resources=False,
        )
        runtime = self.sdk.describe_runtime()
        self.runtime = runtime
        global SERVICE_LOG_PATH
        SERVICE_LOG_PATH = Path(runtime["logs_dir"]) / cheapclaw_settings["service_log_file"]
        self.panel_store = CheapClawPanelStore(self.paths, history_preview_limit=history_preview_limit)
        self.default_agent_system = default_agent_system
        self.default_agent_name = default_agent_name
        self.supervisor_agent_system = supervisor_agent_system
        self.supervisor_agent_name = supervisor_agent_name
        self.app_tools_dir = asset_tools_dir
        self.default_exposed_skills = cheapclaw_settings["default_exposed_skills"]
        self.default_mcp_servers = cheapclaw_settings["default_mcp_servers"]
        self.asset_agent_library_root = ASSET_AGENT_LIBRARY_ROOT.resolve()
        self.asset_channels_example_path = ASSET_CHANNELS_EXAMPLE_PATH.resolve()
        self.app_skills_root = APP_SKILLS_ROOT.resolve()
        self._supervisor_lock = threading.Lock()
        self.watchdog_interval_sec = max(60, int(watchdog_interval_sec or cheapclaw_settings["watchdog_interval_sec"]))
        self.adapters: Dict[str, ChannelAdapter] = {}
        self.bootstrap_assets(force=False)
        self.reload_adapters()
        ACTIVE_SERVICE = self
        _log(
            f"service initialized: user_data_root={runtime['user_data_root']} "
            f"watchdog_interval_sec={self.watchdog_interval_sec}"
        )

    @contextmanager
    def _runtime_scope(self):
        with self.sdk._runtime_scope():
            yield

    def bootstrap_assets(self, force: bool = False) -> Dict[str, Any]:
        runtime = self.sdk.describe_runtime()
        user_root = Path(runtime["user_data_root"])
        cheapclaw_cfg = _ensure_cheapclaw_app_config(self.paths)
        _sync_root_app_config_from_cheapclaw(user_root, cheapclaw_cfg)
        agent_root = Path(runtime["agent_library_dir"])
        skills_root = Path(runtime["skills_dir"])
        agent_root.mkdir(parents=True, exist_ok=True)
        skills_root.mkdir(parents=True, exist_ok=True)
        allowed_systems = {item.name for item in self.asset_agent_library_root.iterdir() if item.is_dir()}
        if not runtime.get("seed_builtin_resources", True):
            for entry in list(agent_root.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name in allowed_systems:
                    continue
                try:
                    shutil.rmtree(entry)
                except FileNotFoundError:
                    pass

        installed_systems = []
        for system_dir in sorted(self.asset_agent_library_root.iterdir(), key=lambda item: item.name.lower()):
            if not system_dir.is_dir():
                continue
            target = agent_root / system_dir.name
            if force and target.exists():
                shutil.rmtree(target)
            shutil.copytree(system_dir, target, dirs_exist_ok=True)
            installed_systems.append(str(target))

        for skill_dir in sorted(self.app_skills_root.iterdir(), key=lambda item: item.name.lower()) if self.app_skills_root.exists() else []:
            if not skill_dir.is_dir():
                continue
            target = skills_root / skill_dir.name
            if force and target.exists():
                shutil.rmtree(target)
            shutil.copytree(skill_dir, target, dirs_exist_ok=True)

        if force or not self.paths.channels_example_path.exists():
            shutil.copyfile(self.asset_channels_example_path, self.paths.channels_example_path)
        if not self.paths.channels_config_path.exists():
            shutil.copyfile(self.asset_channels_example_path, self.paths.channels_config_path)

        return {
            "status": "success",
            "tools_dir": self.app_tools_dir,
            "installed_agent_systems": installed_systems,
            "supervisor_agent_system": self.supervisor_agent_system,
            "worker_agent_system": self.default_agent_system,
            "app_config_path": str(self.paths.app_config_path),
            "app_config_example_path": str(self.paths.app_config_example_path),
            "channels_config_path": str(self.paths.channels_config_path),
            "channels_example_path": str(self.paths.channels_example_path),
            "skills_root": str(skills_root),
        }

    def describe_runtime(self) -> Dict[str, Any]:
        return self.sdk.describe_runtime()

    def list_agent_systems(self) -> Dict[str, Any]:
        return self.sdk.list_agent_systems()

    def list_global_skills(self) -> Dict[str, Any]:
        return {"status": "success", "skills_root": self.runtime["skills_dir"], "skills": list_global_skills(self.runtime["skills_dir"])}

    def _find_task_entry(self, task_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        target_task_id = str(Path(task_id).expanduser().resolve())
        panel = self.panel_store.load_panel()
        for channel_payload in panel.get("channels", {}).values():
            for conv in channel_payload.get("conversations", {}).values():
                for item in conv.get("linked_tasks", []):
                    if str(item.get("task_id") or "") == target_task_id:
                        return conv, item
        return None, None

    def get_task_preferences(self, *, task_id: str) -> Dict[str, Any]:
        _, item = self._find_task_entry(task_id)
        if item is None:
            return {
                "status": "success",
                "task_id": str(Path(task_id).expanduser().resolve()),
                "default_exposed_skills": list(self.default_exposed_skills),
                "mcp_servers": list(self.default_mcp_servers),
            }
        return {
            "status": "success",
            "task_id": str(Path(task_id).expanduser().resolve()),
            "default_exposed_skills": list(item.get("default_exposed_skills") or self.default_exposed_skills),
            "mcp_servers": list(item.get("mcp_servers") or self.default_mcp_servers),
        }

    def update_task_preferences(
        self,
        *,
        task_id: str,
        default_exposed_skills: Optional[Iterable[str]] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        with self._runtime_scope():
            resolved_task_id = str(Path(task_id).expanduser().resolve())
            conv, item = self._find_task_entry(resolved_task_id)
            if conv is None or item is None:
                return {"status": "error", "error": f"task_id not found in panel: {resolved_task_id}"}

            task_patch: Dict[str, Any] = {"updated_at": now_iso()}
            if default_exposed_skills is not None:
                selected_skills = [str(name).strip() for name in default_exposed_skills if str(name).strip()]
                set_task_visible_skills(resolved_task_id, selected_skills)
                task_patch["default_exposed_skills"] = selected_skills
                task_patch["skills_dir"] = ""
            if mcp_servers is not None:
                task_patch["mcp_servers"] = [entry for entry in mcp_servers if isinstance(entry, dict)]

            panel = update_conversation_task(
                str(conv.get("channel") or ""),
                str(conv.get("conversation_id") or ""),
                resolved_task_id,
                task_patch,
                mark_dirty=False,
            )
            updated_item = next(
                (linked for linked in panel.get("channels", {}).get(str(conv.get("channel") or ""), {}).get("conversations", {}).get(str(conv.get("conversation_id") or ""), {}).get("linked_tasks", []) if linked.get("task_id") == resolved_task_id),
                {},
            )
            return {
                "status": "success",
                "task_id": resolved_task_id,
                "default_exposed_skills": list(updated_item.get("default_exposed_skills") or self.default_exposed_skills),
                "mcp_servers": list(updated_item.get("mcp_servers") or self.default_mcp_servers),
                "skills_dir": str(updated_item.get("skills_dir") or ""),
            }

    def load_runtime_state(self) -> Dict[str, Any]:
        self.paths.runtime_state_path.parent.mkdir(parents=True, exist_ok=True)
        return _load_json(self.paths.runtime_state_path, {"webhook_server": {}, "telegram_offsets": {}})

    def save_runtime_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        _atomic_write_text(self.paths.runtime_state_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return payload

    def load_channel_config(self) -> Dict[str, Any]:
        return _load_json(self.paths.channels_config_path, _load_json(self.paths.channels_example_path, {}))

    def reload_adapters(self) -> Dict[str, ChannelAdapter]:
        config = self.load_channel_config()
        adapters: Dict[str, ChannelAdapter] = {}
        if config.get("telegram", {}).get("enabled"):
            adapters["telegram"] = TelegramAdapter(config.get("telegram", {}), self)
        if config.get("feishu", {}).get("enabled"):
            adapters["feishu"] = FeishuAdapter(config.get("feishu", {}), self)
        if config.get("whatsapp", {}).get("enabled"):
            adapters["whatsapp"] = WhatsAppCloudAdapter(config.get("whatsapp", {}), self)
        self.adapters = adapters
        return adapters

    def ingest_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        with self._runtime_scope():
            return self.panel_store.record_social_message(**event)

    def build_task_id(self, *, channel: str, conversation_id: str, task_name: str) -> str:
        with self._runtime_scope():
            return generate_task_id(channel, conversation_id, task_name)

    def build_task_skills_overlay(self, *, task_id: str, exposed_skills: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        with self._runtime_scope():
            payload = set_task_visible_skills(task_id, exposed_skills or [])
        return {"status": "success", **payload}

    def record_social_message(self, **kwargs) -> Dict[str, Any]:
        with self._runtime_scope():
            return self.panel_store.record_social_message(**kwargs)

    def start_task(self, **kwargs) -> Dict[str, Any]:
        with self._runtime_scope():
            channel = str(kwargs.get("channel") or "").strip()
            conversation_id = str(kwargs.get("conversation_id") or "").strip()
            task_name = str(kwargs.get("task_name") or "").strip()
            user_input = str(kwargs.get("user_input") or "").strip()
            if not channel or not conversation_id or not task_name or not user_input:
                return {"status": "error", "error": "channel, conversation_id, task_name and user_input are required"}
            resolved_task_id = str(Path(kwargs.get("task_id") or self.build_task_id(channel=channel, conversation_id=conversation_id, task_name=task_name)).expanduser().resolve())
            requested_agent_system = str(kwargs.get("agent_system") or self.default_agent_system).strip() or self.default_agent_system
            requested_agent_name = str(kwargs.get("agent_name") or "").strip()
            if requested_agent_system == self.supervisor_agent_system:
                return {"status": "error", "error": f"禁止使用 {self.supervisor_agent_system} 启动后台任务，主 agent 不能调用本身。"}
            systems_payload = self.sdk.list_agent_systems()
            systems = {
                str(item.get("name") or ""): item
                for item in systems_payload.get("agent_systems", [])
                if isinstance(item, dict)
            }
            system_info = systems.get(requested_agent_system, {})
            available_agent_names = [str(name).strip() for name in system_info.get("agent_names", []) if str(name).strip()]
            if requested_agent_system == "CheapClawWorkerGeneral":
                selected_agent_name = "worker_agent"
            elif requested_agent_name and requested_agent_name in available_agent_names:
                selected_agent_name = requested_agent_name
            elif available_agent_names:
                selected_agent_name = available_agent_names[0]
            else:
                selected_agent_name = requested_agent_name or self.default_agent_name
            merged_config = dict(kwargs.get("config") or {})
            merged_config.setdefault("tools_dir", self.app_tools_dir)
            exposed_skills = kwargs.get("exposed_skills")
            task_preferences = self.get_task_preferences(task_id=resolved_task_id)
            if exposed_skills is None:
                exposed_skills = list(task_preferences.get("default_exposed_skills") or self.default_exposed_skills)
            else:
                merged_visible = []
                for item in list(task_preferences.get("default_exposed_skills") or self.default_exposed_skills) + list(exposed_skills or []):
                    name = str(item).strip()
                    if name and name not in merged_visible:
                        merged_visible.append(name)
                exposed_skills = merged_visible
            if "mcp_servers" not in merged_config:
                merged_config["mcp_servers"] = list(task_preferences.get("mcp_servers") or self.default_mcp_servers)
            if exposed_skills is not None:
                merged_config["visible_skills"] = list(exposed_skills)
            existing_hooks = list(merged_config.get("tool_hooks") or [])
            if not any(str(item.get("callback") or "") == FINAL_OUTPUT_HOOK_CALLBACK for item in existing_hooks if isinstance(item, dict)):
                existing_hooks.append({
                    "name": "cheapclaw-final-output",
                    "callback": FINAL_OUTPUT_HOOK_CALLBACK,
                    "when": "after",
                    "tool_names": ["final_output"],
                    "include_arguments": False,
                    "include_result": True,
                })
            merged_config["tool_hooks"] = existing_hooks
            dispatch_input = f"{user_input}\n\n[dispatched_at {now_iso()}]"
            result = self.sdk.start_background_task(
                task_id=resolved_task_id,
                user_input=dispatch_input,
                agent_system=requested_agent_system,
                agent_name=selected_agent_name,
                force_new=bool(kwargs.get("force_new", False)),
                config=merged_config or None,
            )
            if result.get("status") != "success":
                return result
            snapshot = self.sdk.task_snapshot(task_id=resolved_task_id)
            set_task_visible_skills(resolved_task_id, exposed_skills or [])
            latest_instruction = snapshot.get("latest_instruction") or {}
            if not isinstance(latest_instruction, dict):
                latest_instruction = {}
            update_conversation_task(
                channel,
                conversation_id,
                resolved_task_id,
                {
                    "agent_system": result.get("agent_system") or requested_agent_system,
                    "agent_name": result.get("agent_name") or selected_agent_name,
                    "status": "running",
                    "share_context_path": snapshot.get("share_context_path", ""),
                    "stack_path": snapshot.get("stack_path", ""),
                    "log_path": result.get("log_path", ""),
                    "skills_dir": "",
                    "default_exposed_skills": list(exposed_skills or []),
                    "mcp_servers": list(merged_config.get("mcp_servers") or []),
                    "last_thinking": snapshot.get("latest_thinking", ""),
                    "last_thinking_at": snapshot.get("latest_thinking_at", ""),
                    "last_final_output": snapshot.get("last_final_output", ""),
                    "last_final_output_at": snapshot.get("last_final_output_at", ""),
                    "last_action_at": snapshot.get("last_updated", ""),
                    "last_log_at": now_iso(),
                    "last_launch_at": now_iso(),
                    "last_watchdog_note": "task launched",
                    "user_input": str((snapshot.get("runtime") or {}).get("user_input") or dispatch_input or ""),
                    "latest_instruction": str(latest_instruction.get("instruction") or dispatch_input or ""),
                    "created_at": next(
                        (
                            str(existing.get("created_at") or "")
                            for existing in self.panel_store.load_panel().get("channels", {}).get(channel, {}).get("conversations", {}).get(conversation_id, {}).get("linked_tasks", [])
                            if existing.get("task_id") == resolved_task_id
                        ),
                        now_iso(),
                    ) or now_iso(),
                },
                mark_dirty=True,
            )
            source_message_ids = kwargs.get("source_message_ids") or []
            if source_message_ids:
                bind_messages_to_task(
                    channel,
                    conversation_id,
                    resolved_task_id,
                    source_message_ids,
                    note="task started from supervisor decision",
                )
            return {
                **result,
                "requested_agent_name": requested_agent_name,
                "selected_agent_name": selected_agent_name,
                "available_agent_names": available_agent_names,
                "overlay_skills": overlay_result,
                "share_context_path": snapshot.get("share_context_path", ""),
                "stack_path": snapshot.get("stack_path", ""),
            }

    def add_task_message(
        self,
        *,
        task_id: str,
        message: str,
        source: str = "agent",
        resume_if_needed: bool = False,
        agent_system: Optional[str] = None,
        channel: Optional[str] = None,
        conversation_id: Optional[str] = None,
        source_message_ids: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        with self._runtime_scope():
            timestamped = f"{message}\n\n[message_appended_at {now_iso()}]"
            result = self.sdk.add_message(timestamped, task_id=str(Path(task_id).expanduser().resolve()), source=source, resume_if_needed=resume_if_needed, agent_system=agent_system)
            if result.get("status") == "success" and channel and conversation_id and source_message_ids:
                bind_messages_to_task(
                    str(channel),
                    str(conversation_id),
                    str(Path(task_id).expanduser().resolve()),
                    source_message_ids,
                    note="message appended to existing task",
                )
            return result

    def fresh_task(self, *, task_id: str, reason: str = "") -> Dict[str, Any]:
        with self._runtime_scope():
            return self.sdk.fresh(task_id=str(Path(task_id).expanduser().resolve()), reason=reason)

    def reset_task(self, *, task_id: str, preserve_history: bool = True, kill_background_processes: bool = True, reason: str = "") -> Dict[str, Any]:
        with self._runtime_scope():
            return self.sdk.reset_task(task_id=str(Path(task_id).expanduser().resolve()), preserve_history=preserve_history, kill_background_processes=kill_background_processes, reason=reason)

    def get_task_snapshot(self, *, task_id: str) -> Dict[str, Any]:
        with self._runtime_scope():
            snapshot = self.sdk.task_snapshot(task_id=str(Path(task_id).expanduser().resolve()))
            panel = self.panel_store.load_panel()
            for channel_payload in panel.get("channels", {}).values():
                for conv in channel_payload.get("conversations", {}).values():
                    for item in conv.get("linked_tasks", []):
                        if item.get("task_id") == snapshot["task_id"]:
                            snapshot["log_path"] = item.get("log_path", "")
                            snapshot["conversation"] = {"channel": conv.get("channel"), "conversation_id": conv.get("conversation_id"), "display_name": conv.get("display_name")}
                            return snapshot
            snapshot.setdefault("log_path", "")
            return snapshot

    def refresh_task_view(self, *, channel: str, conversation_id: str, task_id: str, mark_dirty: bool = False) -> Dict[str, Any]:
        snapshot = self.get_task_snapshot(task_id=task_id)
        patch = {
            "status": "running" if snapshot.get("running") else "idle",
            "share_context_path": snapshot.get("share_context_path", ""),
            "stack_path": snapshot.get("stack_path", ""),
            "last_thinking": snapshot.get("latest_thinking", ""),
            "last_thinking_at": snapshot.get("latest_thinking_at", ""),
            "last_final_output": snapshot.get("last_final_output", ""),
            "last_final_output_at": snapshot.get("last_final_output_at", ""),
            "last_action_at": snapshot.get("last_updated", ""),
            "last_log_at": now_iso(),
        }
        return update_conversation_task(channel, conversation_id, str(Path(task_id).expanduser().resolve()), patch, mark_dirty=mark_dirty)

    def process_task_events(self) -> List[Dict[str, Any]]:
        with self._runtime_scope():
            panel = self.panel_store.load_panel()
            results: List[Dict[str, Any]] = []
            changed = False
            for event in list_task_events():
                event_id = str(event.get("event_id") or "")
                event_type = str(event.get("event_type") or "")
                task_id = str(event.get("task_id") or "")
                observed_at = str(event.get("observed_at") or now_iso())
                matched = False

                if event_type == "task_final_output" and task_id:
                    for channel_payload in panel.get("channels", {}).values():
                        for conv in channel_payload.get("conversations", {}).values():
                            for item in conv.get("linked_tasks", []):
                                if item.get("task_id") != task_id:
                                    continue
                                previous_final_at = str(item.get("last_final_output_at") or "")
                                previous_output = str(item.get("last_final_output") or "")
                                item.update({
                                    "status": "idle",
                                    "last_final_output": str(event.get("output") or ""),
                                    "last_final_output_at": observed_at,
                                    "last_action_at": observed_at,
                                    "pid_alive": False,
                                    "watchdog_observation": "",
                                    "watchdog_suspected_state": "healthy",
                                })
                                if previous_final_at != observed_at or previous_output != str(event.get("output") or ""):
                                    conv.setdefault("pending_events", []).append({
                                        "type": "task_completed",
                                        "task_id": task_id,
                                        "timestamp": observed_at,
                                    })
                                    conv["dirty"] = True
                                    panel.setdefault("service_state", {})["main_agent_dirty"] = True
                                conv["updated_at"] = now_iso()
                                conv["running_task_count"] = sum(1 for linked in conv.get("linked_tasks", []) if linked.get("status") == "running")
                                conv["unread_event_count"] = len(conv.get("pending_events", []))
                                matched = True
                                changed = True
                                break
                            if matched:
                                break
                        if matched:
                            break

                ack_task_event(event_id)
                results.append({
                    "event_id": event_id,
                    "event_type": event_type,
                    "task_id": task_id,
                    "matched": matched,
                })

            if changed:
                self.panel_store.save_panel(panel)
            return results

    def reconcile_task_statuses(self) -> List[Dict[str, Any]]:
        observations: List[Dict[str, Any]] = []
        panel = self.panel_store.load_panel()
        changed = False
        for channel_name, channel_payload in panel.get("channels", {}).items():
            for conversation_id, conv in channel_payload.get("conversations", {}).items():
                for item in conv.get("linked_tasks", []):
                    task_id = str(item.get("task_id") or "")
                    if not task_id:
                        continue
                    snapshot = self.get_task_snapshot(task_id=task_id)
                    now_dt = datetime.now().astimezone()
                    latest_instruction = snapshot.get("latest_instruction") or {}
                    if not isinstance(latest_instruction, dict):
                        latest_instruction = {}
                    log_path = Path(item.get("log_path") or snapshot.get("log_path") or "")
                    last_log_at = datetime.fromtimestamp(log_path.stat().st_mtime).astimezone().isoformat(timespec="seconds") if log_path.exists() else ""
                    patch = {
                        "status": "running" if snapshot.get("running") else "idle",
                        "share_context_path": snapshot.get("share_context_path", ""),
                        "stack_path": snapshot.get("stack_path", ""),
                        "last_thinking": snapshot.get("latest_thinking", ""),
                        "last_thinking_at": snapshot.get("latest_thinking_at", ""),
                        "last_final_output": snapshot.get("last_final_output", ""),
                        "last_final_output_at": snapshot.get("last_final_output_at", ""),
                        "last_action_at": snapshot.get("last_updated", ""),
                        "last_log_at": last_log_at,
                        "last_launch_at": str(item.get("last_launch_at") or ""),
                        "pid_alive": bool(snapshot.get("running")),
                        "watchdog_observation": "" if snapshot.get("last_final_output") else str(item.get("watchdog_observation") or ""),
                        "watchdog_suspected_state": "healthy" if snapshot.get("last_final_output") else str(item.get("watchdog_suspected_state") or ""),
                        "user_input": str((snapshot.get("runtime") or {}).get("user_input") or item.get("user_input") or ""),
                        "latest_instruction": str(latest_instruction.get("instruction") or item.get("latest_instruction") or ""),
                    }
                    final_changed = (
                        bool(snapshot.get("last_final_output"))
                        and (
                            str(item.get("last_final_output_at") or "") != str(snapshot.get("last_final_output_at") or "")
                            or str(item.get("last_final_output") or "") != str(snapshot.get("last_final_output") or "")
                        )
                    )
                    failed_changed = (
                        not snapshot.get("running")
                        and not snapshot.get("last_final_output")
                        and (
                            (parse_iso(str(item.get("last_launch_at") or "")) or now_dt) <= now_dt - timedelta(seconds=45)
                        )
                        and (
                            not last_log_at
                            or (parse_iso(last_log_at) is not None and parse_iso(last_log_at) <= now_dt - timedelta(seconds=15))
                        )
                        and (
                            str(item.get("status") or "") == "running"
                            or bool(item.get("pid_alive"))
                        )
                    )
                    if final_changed:
                        conv.setdefault("pending_events", []).append({
                            "type": "task_completed",
                            "task_id": task_id,
                            "timestamp": str(snapshot.get("last_final_output_at") or now_iso()),
                        })
                        conv["dirty"] = True
                        panel.setdefault("service_state", {})["main_agent_dirty"] = True
                    elif failed_changed:
                        conv.setdefault("pending_events", []).append({
                            "type": "task_failed",
                            "task_id": task_id,
                            "timestamp": str(snapshot.get("last_updated") or now_iso()),
                            "suspected_state": "process_dead",
                            "summary": "task stopped without final_output",
                        })
                        conv["dirty"] = True
                        panel.setdefault("service_state", {})["main_agent_dirty"] = True
                    if any(str(item.get(key) or "") != str(value or "") for key, value in patch.items()):
                        item.update(patch)
                        changed = True
                    observations.append({"channel": channel_name, "conversation_id": conversation_id, "task_id": task_id, **patch})
                conv["running_task_count"] = sum(1 for linked in conv.get("linked_tasks", []) if linked.get("status") == "running")
                conv["has_stale_running_tasks"] = any(
                    linked.get("status") == "running" and not linked.get("pid_alive")
                    for linked in conv.get("linked_tasks", [])
                )
                conv["unread_event_count"] = len(conv.get("pending_events", []))
        if changed:
            self.panel_store.save_panel(panel)
        return observations

    def queue_message(self, *, channel: str, conversation_id: str, message: str, attachments: Optional[List[Dict[str, Any]]] = None, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._runtime_scope():
            return queue_outbound_message(channel=channel, conversation_id=conversation_id, message=message, attachments=attachments, metadata=metadata)

    def send_message_now(self, *, channel: str, conversation_id: str, message: str, attachments: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        adapter = self.adapters.get(str(channel).strip())
        if adapter is None:
            return {"status": "error", "output": "", "error": f"adapter not configured: {channel}"}
        ok, remote_id = adapter.send_message(str(conversation_id), str(message), attachments or [])
        if not ok:
            return {"status": "error", "output": "", "error": str(remote_id)}
        append_history(
            channel=str(channel),
            conversation_id=str(conversation_id),
            event={
                "message_id": str(remote_id or uuid.uuid4().hex[:12]),
                "timestamp": now_iso(),
                "sender_id": "cheapclaw",
                "sender_name": "cheapclaw",
                "text": str(message or ""),
                "attachments": attachments or [],
                "is_mention_to_bot": False,
                "direction": "outbound",
            },
        )
        return {
            "status": "success",
            "output": f"sent outbound message {remote_id}",
            "remote_id": str(remote_id or ""),
            "channel": str(channel),
            "conversation_id": str(conversation_id),
        }

    def process_outbox(self) -> List[Dict[str, Any]]:
        with self._runtime_scope():
            results = []
            for event in list_outbox_events():
                channel = str(event.get("channel") or "").strip()
                adapter = self.adapters.get(channel)
                if adapter is None:
                    results.append({"event_id": event.get("event_id"), "status": "error", "error": f"adapter not configured: {channel}"})
                    continue
                ok, remote_id = adapter.send_message(str(event.get("conversation_id") or ""), str(event.get("message") or ""), event.get("attachments") or [])
                if ok:
                    ack_outbox_event(str(event.get("event_id") or ""))
                    append_history(
                        channel=channel,
                        conversation_id=str(event.get("conversation_id") or ""),
                        event={
                            "message_id": remote_id or str(event.get("event_id") or ""),
                            "timestamp": now_iso(),
                            "sender_id": "cheapclaw",
                            "sender_name": "cheapclaw",
                            "text": str(event.get("message") or ""),
                            "attachments": event.get("attachments") or [],
                            "is_mention_to_bot": False,
                            "direction": "outbound",
                        },
                    )
                    results.append({"event_id": event.get("event_id"), "status": "success", "remote_id": remote_id})
                else:
                    results.append({"event_id": event.get("event_id"), "status": "error", "error": remote_id})
            return results

    def poll_channels(self) -> List[Dict[str, Any]]:
        events = []
        for adapter in self.adapters.values():
            for event in adapter.poll_events():
                self.ingest_event(event)
                events.append(event)
        return events

    def tick_watchdog(self) -> List[Dict[str, Any]]:
        observations = []
        panel = self.panel_store.load_panel()
        for channel_name, channel_payload in panel.get("channels", {}).items():
            for conversation_id, conv in channel_payload.get("conversations", {}).items():
                for item in conv.get("linked_tasks", []):
                    task_id = item.get("task_id")
                    if not task_id:
                        continue
                    snapshot = self.get_task_snapshot(task_id=task_id)
                    log_path = Path(item.get("log_path") or snapshot.get("log_path") or "")
                    last_log_at = datetime.fromtimestamp(log_path.stat().st_mtime).astimezone().isoformat(timespec="seconds") if log_path.exists() else ""
                    latest_thinking_at = snapshot.get("latest_thinking_at", "")
                    suspected = "healthy"
                    note = ""
                    if snapshot.get("running") and not latest_thinking_at and not last_log_at:
                        suspected = "quiet_but_alive"
                        note = "running but no thinking/log timestamp yet"
                    elif snapshot.get("running") and latest_thinking_at:
                        thinking_dt = parse_iso(latest_thinking_at)
                        if thinking_dt and thinking_dt < datetime.now().astimezone() - timedelta(hours=1):
                            suspected = "possibly_stalled"
                            note = "thinking has not moved for over 1 hour"
                    elif not snapshot.get("running") and not snapshot.get("last_final_output"):
                        suspected = "process_dead"
                        note = "task stopped without final output"
                    patch = {
                        "status": "running" if snapshot.get("running") else "idle",
                        "share_context_path": snapshot.get("share_context_path", ""),
                        "stack_path": snapshot.get("stack_path", ""),
                        "last_thinking": snapshot.get("latest_thinking", ""),
                        "last_thinking_at": latest_thinking_at,
                        "last_final_output": snapshot.get("last_final_output", ""),
                        "last_final_output_at": snapshot.get("last_final_output_at", ""),
                        "last_action_at": snapshot.get("last_updated", ""),
                        "last_log_at": last_log_at,
                        "pid_alive": snapshot.get("running"),
                        "watchdog_observation": note,
                        "watchdog_suspected_state": suspected,
                    }
                    if item.get("last_final_output_at") != snapshot.get("last_final_output_at") and snapshot.get("last_final_output"):
                        conv.setdefault("pending_events", []).append({"type": "task_completed", "task_id": task_id, "timestamp": now_iso()})
                        conv["dirty"] = True
                        panel["service_state"]["main_agent_dirty"] = True
                    elif item.get("watchdog_suspected_state") != suspected and suspected != "healthy":
                        conv.setdefault("pending_events", []).append({"type": "watchdog_tick", "task_id": task_id, "suspected_state": suspected, "timestamp": now_iso()})
                        conv["dirty"] = True
                        panel["service_state"]["main_agent_dirty"] = True
                    item.update(patch)
                    observations.append({"channel": channel_name, "conversation_id": conversation_id, "task_id": task_id, **patch})
                conv["running_task_count"] = sum(1 for item in conv.get("linked_tasks", []) if item.get("status") == "running")
                conv["unread_event_count"] = len(conv.get("pending_events", []))
        panel["service_state"]["watchdog_last_run_at"] = now_iso()
        self.panel_store.save_panel(panel)
        return observations

    def _watchdog_due(self) -> bool:
        panel = self.panel_store.load_panel()
        last_run_at = parse_iso(str(panel.get("service_state", {}).get("watchdog_last_run_at") or ""))
        if last_run_at is None:
            return True
        return last_run_at <= datetime.now().astimezone() - timedelta(seconds=self.watchdog_interval_sec)

    def tick_plans(self) -> List[Dict[str, Any]]:
        payload = load_plans()
        results = []
        now = datetime.now().astimezone()
        changed = False
        for plan in payload.get("plans", []):
            if not plan.get("enabled", True):
                continue
            due_at = parse_iso(str(plan.get("next_run_at") or ""))
            if not due_at or due_at > now:
                continue
            task_id = str(plan.get("task_id") or "").strip()
            if plan.get("scope") == "task" and task_id:
                snapshot = self.get_task_snapshot(task_id=task_id)
                if snapshot.get("running"):
                    plan["last_result"] = "deferred: task running"
                    plan["next_run_at"] = (now + timedelta(minutes=5)).isoformat(timespec="seconds")
                    changed = True
                    results.append({"plan_id": plan.get("plan_id"), "status": "deferred"})
                    continue
                self.add_task_message(task_id=task_id, message=str(plan.get("message") or "scheduled task tick"), source="system", resume_if_needed=True)
                plan["last_result"] = "appended task message"
            else:
                channel = str(plan.get("channel") or "").strip()
                conversation_id = str(plan.get("conversation_id") or "").strip()
                if channel and conversation_id:
                    panel = load_panel()
                    conv = ensure_conversation(panel, channel=channel, conversation_id=conversation_id)
                    conv.setdefault("pending_events", []).append({"type": "plan_tick", "plan_id": plan.get("plan_id"), "timestamp": now_iso(), "message": str(plan.get("message") or "")})
                    conv["dirty"] = True
                    panel.setdefault("service_state", {})["main_agent_dirty"] = True
                    save_panel(panel)
                plan["last_result"] = "queued main_agent tick"
            plan["last_run_at"] = now_iso()
            schedule_type = str(plan.get("schedule_type") or "").strip()
            if schedule_type in {"daily", "weekly"} and str(plan.get("time_of_day") or "").strip():
                plan["next_run_at"] = compute_next_scheduled_run(
                    schedule_type=schedule_type,
                    time_of_day=str(plan.get("time_of_day") or ""),
                    days_of_week=plan.get("days_of_week") or [],
                    now=now,
                )
            elif int(plan.get("interval_sec") or 0) > 0:
                plan["next_run_at"] = (now + timedelta(seconds=int(plan.get("interval_sec") or 0))).isoformat(timespec="seconds")
            else:
                plan["enabled"] = False
            changed = True
            results.append({"plan_id": plan.get("plan_id"), "status": plan.get("last_result")})
        if changed:
            save_plans(payload)
        return results

    def _build_supervisor_input(self, reason: str) -> str:
        panel = self.panel_store.load_panel()
        dirty = self.panel_store.dirty_conversations()
        summaries = []
        for conv in dirty:
            messages = [item for item in conv.get("messages", []) if isinstance(item, dict)]
            pending_events = [item for item in conv.get("pending_events", []) if isinstance(item, dict)]
            new_user_messages = []
            task_events = []
            linked_by_task_id = {
                str(item.get("task_id") or ""): item
                for item in conv.get("linked_tasks", [])
                if str(item.get("task_id") or "")
            }

            for event in pending_events:
                event_type = str(event.get("type") or "").strip()
                if event_type == "social_message":
                    message_id = str(event.get("message_id") or "").strip()
                    matched = next(
                        (
                            message for message in messages
                            if str(message.get("message_id") or "") == message_id
                        ),
                        {},
                    )
                    new_user_messages.append({
                        "channel": str(conv.get("channel") or ""),
                        "conversation_id": str(conv.get("conversation_id") or ""),
                        "message_id": message_id,
                        "timestamp": str(matched.get("timestamp") or event.get("timestamp") or ""),
                        "text": str(matched.get("text") or ""),
                    })
                    continue

                if event_type == "task_completed":
                    task_id = str(event.get("task_id") or "").strip()
                    linked = linked_by_task_id.get(task_id, {})
                    task_events.append({
                        "type": "task_completed",
                        "channel": str(conv.get("channel") or ""),
                        "conversation_id": str(conv.get("conversation_id") or ""),
                        "task_id": task_id,
                        "task_input": _short_text(str(
                            linked.get("latest_instruction")
                            or linked.get("last_instruction")
                            or linked.get("user_input")
                            or ""
                        ).strip(), limit=360),
                        "output": _short_text(str(linked.get("last_final_output") or ""), limit=420),
                        "output_at": str(linked.get("last_final_output_at") or event.get("timestamp") or ""),
                    })
                    continue

                task_events.append({
                    "type": event_type,
                    "channel": str(conv.get("channel") or ""),
                    "conversation_id": str(conv.get("conversation_id") or ""),
                    "task_id": str(event.get("task_id") or "").strip(),
                    "timestamp": str(event.get("timestamp") or ""),
                    "summary": str(event.get("message") or event.get("note") or event.get("suspected_state") or "")[:240],
                })

            summaries.append({
                "channel": conv.get("channel"),
                "conversation_id": conv.get("conversation_id"),
                "display_name": conv.get("display_name"),
                "conversation_type": conv.get("conversation_type"),
                "new_user_messages": new_user_messages,
                "task_events": task_events,
            })
        payload = {
            "trigger_reason": reason,
            "summary_rules": "这里只给所有新用户消息和所有新任务事件的短摘要。若你判断本次 dirty 可能和旧消息或旧 task 相关，再主动查询历史对话、任务列表或完整面板。",
            "dirty_conversations": summaries,
            "service_state": {
                "main_agent_running": bool(panel.get("service_state", {}).get("main_agent_running")),
                "main_agent_last_started_at": str(panel.get("service_state", {}).get("main_agent_last_started_at") or ""),
                "watchdog_last_run_at": str(panel.get("service_state", {}).get("watchdog_last_run_at") or ""),
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def run_supervisor_once(self, reason: str = "dirty_panel") -> Dict[str, Any]:
        if not self._supervisor_lock.acquire(blocking=False):
            panel = self.panel_store.load_panel()
            panel.setdefault("service_state", {})["main_agent_dirty"] = True
            self.panel_store.save_panel(panel)
            return {"status": "busy", "output": "supervisor already running"}
        run_id = f"sup_{uuid.uuid4().hex[:10]}"
        try:
            self.panel_store.set_main_agent_state(running=True, run_id=run_id)
            result = self.sdk.run(
                self._build_supervisor_input(reason),
                task_id=str(self.paths.supervisor_task_id),
                agent_system=self.supervisor_agent_system,
                agent_name=self.supervisor_agent_name,
                force_new=False,
            )
            return result
        finally:
            self.panel_store.set_main_agent_state(running=False)
            self._supervisor_lock.release()

    def run_once(self) -> Dict[str, Any]:
        polled = self.poll_channels()
        plans = self.tick_plans()
        task_events = self.process_task_events()
        reconciled = self.reconcile_task_statuses()
        watchdog = self.tick_watchdog() if self._watchdog_due() else []
        outbox = self.process_outbox()
        panel = self.panel_store.load_panel()
        supervisor = None
        if panel.get("service_state", {}).get("main_agent_dirty") and self.panel_store.dirty_conversations():
            supervisor = self.run_supervisor_once(reason="dirty_panel")
            outbox.extend(self.process_outbox())
        return {
            "status": "success",
            "polled_events": polled,
            "plan_results": plans,
            "task_events": task_events,
            "reconciled_tasks": reconciled,
            "watchdog": watchdog,
            "outbox": outbox,
            "supervisor": supervisor,
        }

    def run_forever(self, poll_interval: int = 15) -> None:
        poll_interval = max(1, int(poll_interval))
        while True:
            try:
                result = self.run_once()
                _log(
                    "cycle complete: "
                    f"polled={len(result.get('polled_events', []))}, "
                    f"plans={len(result.get('plan_results', []))}, "
                    f"task_events={len(result.get('task_events', []))}, "
                    f"reconciled={len(result.get('reconciled_tasks', []))}, "
                    f"watchdog={len(result.get('watchdog', []))}, "
                    f"outbox={len(result.get('outbox', []))}, "
                    f"supervisor={result.get('supervisor', {}).get('status') if isinstance(result.get('supervisor'), dict) else 'idle'}"
                )
            except Exception as exc:
                _log(f"cycle failed: {exc}")
                traceback.print_exc()
            time.sleep(poll_interval)

    @staticmethod
    def _task_created_sort_value(task: Dict[str, Any]) -> str:
        created_at = str(task.get("created_at") or "")
        if created_at:
            return created_at
        task_id = str(task.get("task_id") or "")
        try:
            name = Path(task_id).name
            stamp = name.split("_", 2)[:2]
            if len(stamp) == 2:
                parsed = datetime.strptime("_".join(stamp), "%Y%m%d_%H%M%S")
                return parsed.astimezone().isoformat(timespec="seconds")
        except Exception:
            pass
        return ""

    def serve_webhooks(self, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
        service = self

        class Handler(BaseHTTPRequestHandler):
            def _dispatch(self):
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/")
                headers = {key: value for key, value in self.headers.items()}
                if self.command == "GET":
                    if path in {"", "/", "/dashboard"}:
                        dashboard_path = APP_WEB_ROOT / "dashboard.html"
                        body = dashboard_path.read_bytes()
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    if path == "/api/panel":
                        body = json.dumps(service.dashboard_payload(), ensure_ascii=False, indent=2).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    if path == "/api/global-skills":
                        body = json.dumps(service.list_global_skills(), ensure_ascii=False, indent=2).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    if path == "/api/task-settings":
                        task_id = str((parse_qs(parsed.query).get("task_id") or [""])[0] or "").strip()
                        if not task_id:
                            self.send_error(400, "task_id is required")
                            return
                        body = json.dumps(service.get_task_preferences(task_id=task_id), ensure_ascii=False, indent=2).encode("utf-8")
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(body)
                        return
                    query = parse_qs(parsed.query)
                    adapter = service._adapter_for_webhook(path)
                    if adapter is None:
                        self.send_error(404)
                        return
                    status, out_headers, body = adapter.handle_webhook_get(path, query, headers)
                else:
                    body_raw = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
                    if path == "/api/task-settings":
                        try:
                            payload = json.loads(body_raw.decode("utf-8") or "{}")
                        except Exception:
                            self.send_error(400, "invalid json body")
                            return
                        task_id = str(payload.get("task_id") or "").strip()
                        if not task_id:
                            self.send_error(400, "task_id is required")
                            return
                        result = service.update_task_preferences(
                            task_id=task_id,
                            default_exposed_skills=payload.get("default_exposed_skills"),
                            mcp_servers=payload.get("mcp_servers"),
                        )
                        status = 200 if result.get("status") == "success" else 400
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"))
                        return
                    adapter = service._adapter_for_webhook(path)
                    if adapter is None:
                        self.send_error(404)
                        return
                    status, out_headers, body = adapter.handle_webhook_post(path, body_raw, headers)
                self.send_response(status)
                for key, value in out_headers.items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self._dispatch()

            def do_POST(self):
                self._dispatch()

            def log_message(self, fmt, *args):
                return

        server = ThreadingHTTPServer((host, int(port)), Handler)
        state = self.load_runtime_state()
        state["webhook_server"] = {"host": host, "port": int(port), "started_at": now_iso()}
        self.save_runtime_state(state)
        return server

    def dashboard_payload(self) -> Dict[str, Any]:
        panel = json.loads(json.dumps(self.panel_store.load_panel(), ensure_ascii=False))
        for channel_payload in panel.get("channels", {}).values():
            for conv in channel_payload.get("conversations", {}).values():
                linked = [item for item in conv.get("linked_tasks", []) if isinstance(item, dict)]
                linked.sort(
                    key=lambda item: (
                        self._task_created_sort_value(item),
                        str(item.get("last_final_output_at") or ""),
                        str(item.get("last_action_at") or ""),
                        str(item.get("task_id") or ""),
                    ),
                    reverse=True,
                )
                conv["linked_tasks"] = linked
        return panel

    def _adapter_for_webhook(self, path: str) -> Optional[ChannelAdapter]:
        if path.endswith("/feishu"):
            return self.adapters.get("feishu")
        if path.endswith("/whatsapp"):
            return self.adapters.get("whatsapp")
        return None

    def credentials_needed(self) -> Dict[str, List[str]]:
        return {
            "telegram": ["bot_token"],
            "feishu": ["app_id", "app_secret", "verify_token"],
            "whatsapp": ["access_token", "phone_number_id", "verify_token"],
        }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CheapClaw standalone service")
    parser.add_argument("--user-data-root", required=True, help="User data root used by MLA runtime")
    parser.add_argument("--llm-config-path", default=None, help="Optional llm_config.yaml override")
    parser.add_argument("--bootstrap", action="store_true", help="Install CheapClaw tools, agent systems and example configs into the target user_data_root")
    parser.add_argument("--show-runtime", action="store_true", help="Print runtime description and exit")
    parser.add_argument("--show-panel", action="store_true", help="Print panel JSON and exit")
    parser.add_argument("--show-credentials", action="store_true", help="Print live channel credentials required for testing and exit")
    parser.add_argument("--run-once", action="store_true", help="Run one CheapClaw polling/watchdog/supervisor cycle")
    parser.add_argument("--run-loop", action="store_true", help="Run the CheapClaw service loop")
    parser.add_argument("--poll-interval", type=int, default=15, help="Polling interval in seconds for --run-loop")
    parser.add_argument("--serve-webhooks", action="store_true", help="Start the webhook server for Feishu / WhatsApp")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    service = CheapClawService(user_data_root=args.user_data_root, llm_config_path=args.llm_config_path)

    if args.bootstrap:
        print(json.dumps(service.bootstrap_assets(force=True), ensure_ascii=False, indent=2))
        return 0
    if args.show_runtime:
        print(json.dumps(service.describe_runtime(), ensure_ascii=False, indent=2))
        return 0
    if args.show_panel:
        print(json.dumps(service.panel_store.load_panel(), ensure_ascii=False, indent=2))
        return 0
    if args.show_credentials:
        print(json.dumps(service.credentials_needed(), ensure_ascii=False, indent=2))
        return 0
    if args.run_once:
        print(json.dumps(service.run_once(), ensure_ascii=False, indent=2))
        return 0
    if args.serve_webhooks and not args.run_loop:
        server = service.serve_webhooks(host=args.host, port=args.port)
        _log(f"webhook server started on {args.host}:{args.port}")
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return 0
    if args.run_loop:
        server = None
        thread = None
        if args.serve_webhooks:
            server = service.serve_webhooks(host=args.host, port=args.port)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            _log(f"webhook server started on {args.host}:{args.port}")
        try:
            _log(f"service loop started with poll_interval={args.poll_interval}s")
            service.run_forever(poll_interval=args.poll_interval)
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
