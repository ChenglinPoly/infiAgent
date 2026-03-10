#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
任务级工具：
- 追加消息到指定 task
- 后台启动新 task
- 返回指定 task 的 share context 路径
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .file_tools import BaseTool
from utils.task_runtime import (
    append_task_message,
    get_task_share_paths,
    launch_task_process,
    list_known_tasks,
)
from core.hierarchy_manager import get_hierarchy_manager


class AddMessageTool(BaseTool):
    """向指定 task 的 current.instructions 追加一条消息。"""

    name = "add_message"

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        target_task_id = str(parameters.get("task_id") or task_id or "").strip()
        message = str(parameters.get("message") or "").strip()
        source = str(parameters.get("source") or "agent").strip() or "agent"
        resume_if_needed = bool(parameters.get("resume_if_needed", False))
        fallback_agent_system = str(parameters.get("agent_system") or "").strip() or None
        if fallback_agent_system is None:
            try:
                fallback_agent_system = (
                    get_hierarchy_manager(task_id).get_runtime_metadata().get("agent_system") or None
                )
            except Exception:
                fallback_agent_system = None

        ok, payload = append_task_message(
            task_id=target_task_id,
            message=message,
            source=source,
            resume_if_needed=resume_if_needed,
            fallback_agent_system=fallback_agent_system,
        )
        if not ok:
            return {
                "status": "error",
                "output": "",
                "error": payload.get("error") or "追加消息失败",
            }

        return {
            "status": "success",
            "output": (
                f"{payload.get('message', '')}\n"
                f"share_context: {payload.get('share_context_path', '')}"
            ).strip(),
            "error": "",
            "task_id": payload.get("task_id", target_task_id),
            "instruction_id": payload.get("instruction_id", ""),
            "share_context_path": payload.get("share_context_path", ""),
            "stack_path": payload.get("stack_path", ""),
            "running": payload.get("running", False),
            "resumed": payload.get("resumed", False),
        }


class StartBackgroundTaskTool(BaseTool):
    """后台启动一个新的 task 进程。"""

    name = "start_background_task"

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        target_task_id = str(parameters.get("task_id") or "").strip()
        if not target_task_id:
            return {
                "status": "error",
                "output": "",
                "error": "缺少必需参数: task_id"
            }

        user_input = str(parameters.get("user_input") or parameters.get("message") or "").strip()
        agent_system = str(parameters.get("agent_system") or "OpenCowork").strip() or "OpenCowork"
        agent_name = str(parameters.get("agent_name") or "alpha_agent").strip() or "alpha_agent"
        config = parameters.get("config")
        if config is not None and not isinstance(config, dict):
            return {
                "status": "error",
                "output": "",
                "error": "参数 config 必须是 object"
            }

        ok, payload = launch_task_process(
            task_id=str(Path(target_task_id).expanduser().resolve()),
            user_input=user_input,
            agent_system=agent_system,
            agent_name=agent_name,
            config=config,
            force_new=bool(parameters.get("force_new", False)),
            direct_tools=bool(parameters.get("direct_tools", True)),
        )
        if not ok:
            return {
                "status": "error",
                "output": "",
                "error": payload.get("error") or "后台启动任务失败",
            }

        return {
            "status": "success",
            "output": (
                f"{payload.get('message', '')}\n"
                f"log_path: {payload.get('log_path', '')}"
            ).strip(),
            "error": "",
            "task_id": payload.get("task_id", ""),
            "pid": payload.get("pid"),
            "log_path": payload.get("log_path", ""),
            "agent_system": payload.get("agent_system", agent_system),
            "agent_name": payload.get("agent_name", agent_name),
        }


class TaskShareContextPathTool(BaseTool):
    """返回指定 task 的 share context / stack 路径。"""

    name = "task_share_context_path"

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        target_task_id = str(parameters.get("task_id") or task_id or "").strip()
        if not target_task_id:
            return {
                "status": "error",
                "output": "",
                "error": "缺少 task_id"
            }

        paths = get_task_share_paths(target_task_id)
        return {
            "status": "success",
            "output": (
                "已定位对应 task 的共享上下文文件，请自行读取查看。\n"
                f"share_context_path: {paths['share_context_path']}\n"
                f"stack_path: {paths['stack_path']}"
            ),
            "error": "",
            **paths,
        }


class ListTaskIdsTool(BaseTool):
    """列出当前已知 task_id。"""

    name = "list_task_ids"

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        only_running = bool(parameters.get("only_running", False))
        payload = list_known_tasks(only_running=only_running)
        tasks = payload["tasks"]
        if not tasks:
            scope = "运行中的" if only_running else "已知的"
            return {
                "status": "success",
                "output": f"当前没有{scope} task。",
                "error": "",
                "tasks": [],
            }

        lines = []
        for idx, item in enumerate(tasks, 1):
            lines.append(
                f"{idx}. {item['task_id']} | running={item['running']} | share_context={item['share_context_path']}"
            )
        return {
            "status": "success",
            "output": "\n".join(lines),
            "error": "",
            "tasks": tasks,
        }
