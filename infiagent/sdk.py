#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
InfiAgent Python SDK。

设计原则：
- 实例化阶段只负责配置运行时环境
- 具体任务在 run(..., task_id=...) 阶段绑定
- user_data_root 一旦指定，conversation/share/stack/runtime 都跟随该根目录
- skills 仍保持独立目录语义，不强制跟随 user_data_root
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from core.agent_executor import AgentExecutor
from core.hierarchy_manager import get_hierarchy_manager
from core.state_cleaner import clean_before_start
from utils.config_loader import ConfigLoader
from utils.runtime_control import is_task_running, request_fresh
from utils.task_runtime import (
    append_task_message,
    get_task_share_paths,
    launch_task_process,
    list_known_tasks,
    reset_task_state,
    resume_task_with_fresh,
)
from utils.user_paths import (
    get_user_agent_library_root,
    get_user_config_dir,
    get_user_conversations_dir,
    get_user_data_root,
    get_user_llm_config_path,
    get_user_logs_dir,
    get_user_runtime_dir,
    get_user_skills_library_root,
    get_user_tools_library_root,
    runtime_env_scope,
)


def _normalize_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return str(Path(path).expanduser().resolve())


def _as_root_dir(path: Optional[str], expected_leaf: Optional[str] = None) -> Optional[str]:
    normalized = _normalize_path(path)
    if not normalized:
        return None
    p = Path(normalized)
    if expected_leaf and p.name == expected_leaf:
        return str(p.parent)
    return normalized


class InfiAgent:
    def __init__(
        self,
        workspace: Optional[str] = None,
        user_data_root: Optional[str] = None,
        llm_config_path: Optional[str] = None,
        library_dir: Optional[str] = None,
        agent_library_dir: Optional[str] = None,
        skills_dir: Optional[str] = None,
        tools_dir: Optional[str] = None,
        default_agent_system: Optional[str] = None,
        default_agent_name: Optional[str] = None,
        action_window_steps: Optional[int] = None,
        thinking_interval: Optional[int] = None,
        fresh_enabled: Optional[bool] = None,
        fresh_interval_sec: Optional[int] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        tool_hooks: Optional[List[Dict[str, Any]]] = None,
        context_hooks: Optional[List[Dict[str, Any]]] = None,
        seed_builtin_resources: bool = True,
        direct_tools: bool = True,
    ):
        self.default_agent_system = str(default_agent_system or "OpenCowork").strip() or "OpenCowork"
        self.default_agent_name = str(default_agent_name or "alpha_agent").strip() or "alpha_agent"
        self.direct_tools = bool(direct_tools)

        # `workspace` 仅保留为兼容旧构造参数；新语义要求在 run(...) 时显式提供 task_id。
        self.legacy_workspace = _normalize_path(workspace)

        explicit_agent_library_root = _as_root_dir(agent_library_dir or library_dir, "agent_library")
        resolved_user_data_root = _normalize_path(user_data_root) or explicit_agent_library_root

        self.runtime_env_overrides: Dict[str, Any] = {}
        if resolved_user_data_root:
            self.runtime_env_overrides["MLA_USER_DATA_ROOT"] = resolved_user_data_root
        if llm_config_path:
            self.runtime_env_overrides["MLA_LLM_CONFIG_PATH"] = _normalize_path(llm_config_path)
        if explicit_agent_library_root:
            self.runtime_env_overrides["MLA_AGENT_LIBRARY_DIR"] = explicit_agent_library_root
        if skills_dir:
            self.runtime_env_overrides["MLA_SKILLS_LIBRARY_DIR"] = _normalize_path(skills_dir)
        if tools_dir:
            self.runtime_env_overrides["MLA_TOOLS_LIBRARY_DIR"] = _normalize_path(tools_dir)
        if action_window_steps is not None:
            self.runtime_env_overrides["MLA_ACTION_WINDOW_STEPS"] = str(max(1, int(action_window_steps)))
        if thinking_interval is not None:
            self.runtime_env_overrides["MLA_THINKING_INTERVAL"] = str(max(1, int(thinking_interval)))
        if fresh_enabled is not None:
            self.runtime_env_overrides["MLA_FRESH_ENABLED"] = "true" if fresh_enabled else "false"
        if fresh_interval_sec is not None:
            self.runtime_env_overrides["MLA_FRESH_INTERVAL_SEC"] = str(max(0, int(fresh_interval_sec)))
        if mcp_servers is not None:
            self.runtime_env_overrides["MLA_MCP_CONFIG_JSON"] = json.dumps({"servers": mcp_servers}, ensure_ascii=False)
        if tool_hooks is not None:
            self.runtime_env_overrides["MLA_TOOL_HOOKS_JSON"] = json.dumps(tool_hooks, ensure_ascii=False)
        if context_hooks is not None:
            self.runtime_env_overrides["MLA_CONTEXT_HOOKS_JSON"] = json.dumps(context_hooks, ensure_ascii=False)
        self.runtime_env_overrides["MLA_SEED_BUILTIN_RESOURCES"] = "true" if seed_builtin_resources else "false"

        self.user_data_root = resolved_user_data_root
        self.llm_config_path = _normalize_path(llm_config_path)
        self.agent_library_root = explicit_agent_library_root
        self.skills_dir = _normalize_path(skills_dir)
        self.tools_dir = _normalize_path(tools_dir)
        self.action_window_steps = max(1, int(action_window_steps)) if action_window_steps is not None else None
        self.thinking_interval = max(1, int(thinking_interval)) if thinking_interval is not None else None
        self.fresh_enabled = fresh_enabled if fresh_enabled is not None else None
        self.fresh_interval_sec = max(0, int(fresh_interval_sec)) if fresh_interval_sec is not None else None
        self.mcp_servers = mcp_servers
        self.tool_hooks = tool_hooks
        self.context_hooks = context_hooks
        self.seed_builtin_resources = bool(seed_builtin_resources)

    def _runtime_scope(self):
        return runtime_env_scope(self.runtime_env_overrides)

    def _resolve_task_id(
        self,
        *,
        task_id: Optional[str] = None,
        workspace: Optional[str] = None,
        required: bool = True,
    ) -> Optional[str]:
        raw_task_id = task_id or workspace
        if not raw_task_id and not required:
            return None
        if not raw_task_id:
            raise ValueError("必须显式提供 task_id。SDK 实例化阶段不再绑定 workspace。")
        return str(Path(raw_task_id).expanduser().resolve())

    def _build_launch_config(self) -> Dict[str, Any]:
        config: Dict[str, Any] = {}
        if self.user_data_root:
            config["user_data_root"] = self.user_data_root
        if self.llm_config_path:
            config["llm_config_path"] = self.llm_config_path
        if self.agent_library_root:
            config["agent_library_dir"] = self.agent_library_root
        if self.skills_dir:
            config["skills_dir"] = self.skills_dir
        if self.tools_dir:
            config["tools_dir"] = self.tools_dir
        if self.action_window_steps is not None:
            config["action_window_steps"] = self.action_window_steps
        if self.thinking_interval is not None:
            config["thinking_interval"] = self.thinking_interval
        if self.fresh_enabled is not None:
            config["fresh_enabled"] = self.fresh_enabled
        if self.fresh_interval_sec is not None:
            config["fresh_interval_sec"] = self.fresh_interval_sec
        if self.mcp_servers is not None:
            config["mcp_servers"] = self.mcp_servers
        if self.tool_hooks is not None:
            config["tool_hooks"] = self.tool_hooks
        if self.context_hooks is not None:
            config["context_hooks"] = self.context_hooks
        config["seed_builtin_resources"] = self.seed_builtin_resources
        return config

    def run(
        self,
        user_input: str,
        *,
        task_id: str,
        agent_system: Optional[str] = None,
        agent_name: Optional[str] = None,
        force_new: bool = False,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_task_id = self._resolve_task_id(task_id=task_id, workspace=workspace)
        target_agent_system = agent_system or self.default_agent_system
        target_agent_name = agent_name or self.default_agent_name

        with self._runtime_scope():
            if is_task_running(target_task_id):
                return {
                    "status": "busy",
                    "task_id": target_task_id,
                    "output": "",
                    "error": f"任务已在运行: {target_task_id}",
                }
            config_loader = ConfigLoader(target_agent_system)
            hierarchy_manager = get_hierarchy_manager(target_task_id)

            if force_new:
                context = hierarchy_manager._load_context()
                context["current"] = {
                    "instructions": [],
                    "hierarchy": {},
                    "agents_status": {},
                    "start_time": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                }
                hierarchy_manager._save_context(context)
                hierarchy_manager._save_stack([])
            else:
                clean_before_start(target_task_id, user_input)

            hierarchy_manager.start_new_instruction(user_input)

            agent_config = config_loader.get_tool_config(target_agent_name)
            if agent_config.get("type") != "llm_call_agent":
                raise ValueError(f"{target_agent_name} 不是一个 LLM Agent")
            agent = AgentExecutor(
                agent_name=target_agent_name,
                agent_config=agent_config,
                config_loader=config_loader,
                hierarchy_manager=hierarchy_manager,
                direct_tools=self.direct_tools,
            )
            return agent.run(target_task_id, user_input)

    def fresh(
        self,
        *,
        task_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        target_task_id = self._resolve_task_id(task_id=task_id)
        with self._runtime_scope():
            if is_task_running(target_task_id):
                request_fresh(reason=reason, task_id=target_task_id)
                output = f"已向运行中的任务发送 fresh 请求: {target_task_id}"
            else:
                ok, msg = resume_task_with_fresh(
                    task_id=target_task_id,
                    reason=reason,
                    fallback_agent_system=self.default_agent_system,
                    direct_tools=self.direct_tools,
                    env_overrides=self.runtime_env_overrides,
                )
                if not ok:
                    return {
                        "status": "error",
                        "task_id": target_task_id,
                        "output": "",
                        "error": msg,
                    }
                output = msg
            return {
                "status": "success",
                "task_id": target_task_id,
                "output": output,
            }

    def add_message(
        self,
        message: str,
        *,
        task_id: str,
        source: str = "agent",
        resume_if_needed: bool = False,
        agent_system: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_task_id = self._resolve_task_id(task_id=task_id)
        with self._runtime_scope():
            ok, payload = append_task_message(
                task_id=target_task_id,
                message=message,
                source=source,
                resume_if_needed=resume_if_needed,
                fallback_agent_system=agent_system or self.default_agent_system,
                direct_tools=self.direct_tools,
                env_overrides=self.runtime_env_overrides,
            )
            if not ok:
                return {
                    "status": "error",
                    "task_id": target_task_id,
                    "output": "",
                    "error": payload.get("error") or "add_message failed",
                }
            return {
                "status": "success",
                **payload,
            }

    def start_background_task(
        self,
        *,
        task_id: str,
        user_input: str,
        agent_system: Optional[str] = None,
        agent_name: Optional[str] = None,
        force_new: bool = False,
        direct_tools: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        merged_config = self._build_launch_config()
        if config:
            merged_config.update(config)
        with self._runtime_scope():
            ok, payload = launch_task_process(
                task_id=self._resolve_task_id(task_id=task_id),
                user_input=user_input,
                agent_system=agent_system or self.default_agent_system,
                agent_name=agent_name or self.default_agent_name,
                force_new=force_new,
                direct_tools=self.direct_tools if direct_tools is None else bool(direct_tools),
                config=merged_config,
            )
        if not ok:
            return {"status": "error", **payload}
        return {"status": "success", **payload}

    def task_share_context_path(self, *, task_id: str) -> Dict[str, Any]:
        with self._runtime_scope():
            return {
                "status": "success",
                **get_task_share_paths(self._resolve_task_id(task_id=task_id)),
            }

    def list_task_ids(self, *, only_running: bool = False) -> Dict[str, Any]:
        with self._runtime_scope():
            return {
                "status": "success",
                **list_known_tasks(only_running=only_running),
            }

    def describe_runtime(self) -> Dict[str, Any]:
        with self._runtime_scope():
            return {
                "status": "success",
                "user_data_root": str(get_user_data_root()),
                "config_dir": str(get_user_config_dir()),
                "llm_config_path": str(get_user_llm_config_path()),
                "agent_library_dir": str(get_user_agent_library_root()),
                "skills_dir": str(get_user_skills_library_root()),
                "tools_dir": str(get_user_tools_library_root()),
                "conversations_dir": str(get_user_conversations_dir()),
                "logs_dir": str(get_user_logs_dir()),
                "runtime_dir": str(get_user_runtime_dir()),
                "app_config_path": str(get_user_config_dir() / "app_config.json"),
                "default_agent_system": self.default_agent_system,
                "default_agent_name": self.default_agent_name,
                "direct_tools": self.direct_tools,
                "seed_builtin_resources": self.seed_builtin_resources,
            }

    def list_agent_systems(self) -> Dict[str, Any]:
        with self._runtime_scope():
            root = get_user_agent_library_root()
            systems = []
            if root.exists():
                for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
                    if not child.is_dir() or child.name.startswith("."):
                        continue
                    agent_names: List[str] = []
                    agents_path = child / "level_3_agents.yaml"
                    if agents_path.exists():
                        try:
                            payload = yaml.safe_load(agents_path.read_text(encoding="utf-8")) or {}
                            tools = payload.get("tools", {}) if isinstance(payload, dict) else {}
                            if isinstance(tools, dict):
                                for name, config in tools.items():
                                    if not isinstance(config, dict):
                                        continue
                                    if config.get("type") == "llm_call_agent":
                                        agent_names.append(str(config.get("name") or name))
                        except Exception:
                            agent_names = []
                    systems.append({
                        "name": child.name,
                        "path": str(child),
                        "has_general_prompts": (child / "general_prompts.yaml").exists(),
                        "has_level_0_tools": (child / "level_0_tools.yaml").exists(),
                        "agent_names": sorted(set(agent_names)),
                    })
            return {
                "status": "success",
                "agent_systems": systems,
            }

    def task_snapshot(self, *, task_id: str) -> Dict[str, Any]:
        target_task_id = self._resolve_task_id(task_id=task_id)
        with self._runtime_scope():
            paths = get_task_share_paths(target_task_id)
            share_context_path = Path(paths["share_context_path"])
            data: Dict[str, Any] = {}
            if share_context_path.exists():
                try:
                    data = json.loads(share_context_path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}

            current = data.get("current", {}) if isinstance(data, dict) else {}
            runtime_meta = data.get("runtime", {}) if isinstance(data, dict) else {}
            history = data.get("history", []) if isinstance(data, dict) else []
            instructions = current.get("instructions", []) if isinstance(current, dict) else []
            agents_status = current.get("agents_status", {}) if isinstance(current, dict) else {}

            latest_thinking = ""
            latest_thinking_at = ""
            last_final_output = ""
            last_final_output_at = ""

            agent_infos: List[Dict[str, Any]] = []
            if isinstance(agents_status, dict):
                agent_infos.extend([item for item in agents_status.values() if isinstance(item, dict)])
            if isinstance(history, list):
                for entry in history:
                    if not isinstance(entry, dict):
                        continue
                    archived_agents = entry.get("agents_status", {})
                    if isinstance(archived_agents, dict):
                        agent_infos.extend([item for item in archived_agents.values() if isinstance(item, dict)])

            for agent_info in agent_infos:
                if not isinstance(agent_info, dict):
                    continue
                thinking_at = str(agent_info.get("thinking_updated_at") or "")
                if thinking_at >= latest_thinking_at and agent_info.get("latest_thinking"):
                    latest_thinking = str(agent_info.get("latest_thinking") or "")
                    latest_thinking_at = thinking_at
                final_at = str(agent_info.get("end_time") or "")
                if final_at >= last_final_output_at and agent_info.get("final_output"):
                    last_final_output = str(agent_info.get("final_output") or "")
                    last_final_output_at = final_at

            return {
                "status": "success",
                "task_id": target_task_id,
                "running": is_task_running(target_task_id),
                "share_context_path": paths["share_context_path"],
                "stack_path": paths["stack_path"],
                "instruction_count": len(instructions) if isinstance(instructions, list) else 0,
                "latest_instruction": instructions[-1] if isinstance(instructions, list) and instructions else None,
                "history_count": len(history) if isinstance(history, list) else 0,
                "last_updated": str(current.get("last_updated") or ""),
                "runtime": runtime_meta if isinstance(runtime_meta, dict) else {},
                "latest_thinking": latest_thinking,
                "latest_thinking_at": latest_thinking_at,
                "last_final_output": last_final_output,
                "last_final_output_at": last_final_output_at,
            }

    def reset_task(
        self,
        *,
        task_id: str,
        preserve_history: bool = True,
        kill_background_processes: bool = True,
        reason: str = "",
    ) -> Dict[str, Any]:
        target_task_id = self._resolve_task_id(task_id=task_id)
        with self._runtime_scope():
            ok, payload = reset_task_state(
                task_id=target_task_id,
                preserve_history=preserve_history,
                kill_background_processes=kill_background_processes,
                reason=reason,
            )
        if not ok:
            return {"status": "error", "task_id": target_task_id, **payload}
        return {"status": "success", **payload}

    async def run_async(
        self,
        user_input: str,
        *,
        task_id: str,
        agent_system: Optional[str] = None,
        agent_name: Optional[str] = None,
        force_new: bool = False,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        fn = partial(
            self.run,
            user_input,
            task_id=task_id,
            agent_system=agent_system,
            agent_name=agent_name,
            force_new=force_new,
            workspace=workspace,
        )
        return await asyncio.to_thread(fn)

    async def fresh_async(self, *, task_id: str, reason: str = "") -> Dict[str, Any]:
        return await asyncio.to_thread(self.fresh, task_id=task_id, reason=reason)

    async def add_message_async(
        self,
        message: str,
        *,
        task_id: str,
        source: str = "agent",
        resume_if_needed: bool = False,
        agent_system: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.add_message,
            message,
            task_id=task_id,
            source=source,
            resume_if_needed=resume_if_needed,
            agent_system=agent_system,
        )

    async def start_background_task_async(
        self,
        *,
        task_id: str,
        user_input: str,
        agent_system: Optional[str] = None,
        agent_name: Optional[str] = None,
        force_new: bool = False,
        direct_tools: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.start_background_task,
            task_id=task_id,
            user_input=user_input,
            agent_system=agent_system,
            agent_name=agent_name,
            force_new=force_new,
            direct_tools=direct_tools,
            config=config,
        )

    async def task_share_context_path_async(self, *, task_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.task_share_context_path, task_id=task_id)

    async def list_task_ids_async(self, *, only_running: bool = False) -> Dict[str, Any]:
        return await asyncio.to_thread(self.list_task_ids, only_running=only_running)

    async def describe_runtime_async(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.describe_runtime)

    async def list_agent_systems_async(self) -> Dict[str, Any]:
        return await asyncio.to_thread(self.list_agent_systems)

    async def task_snapshot_async(self, *, task_id: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self.task_snapshot, task_id=task_id)

    async def reset_task_async(
        self,
        *,
        task_id: str,
        preserve_history: bool = True,
        kill_background_processes: bool = True,
        reason: str = "",
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self.reset_task,
            task_id=task_id,
            preserve_history=preserve_history,
            kill_background_processes=kill_background_processes,
            reason=reason,
        )


def infiagent(**kwargs) -> InfiAgent:
    return InfiAgent(**kwargs)
