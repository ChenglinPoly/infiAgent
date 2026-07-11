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
from typing import Any, Dict, Tuple

from .file_tools import BaseTool
from utils.task_runtime import (
    append_task_message,
    get_task_share_paths,
    launch_task_process,
    list_known_tasks,
)
from utils.task_history_index import (
    search_task_history_records,
    sync_task_history_from_context,
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
            "launched": payload.get("launched", False),
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


class TaskHistorySearchTool(BaseTool):
    """检索历史任务数据库。"""

    name = "task_history_search"

    @staticmethod
    def _parse_round_range(raw_value: Any) -> Tuple[int, int, int, str]:
        """Return start_round, end_round, latest_count, error."""
        text = str(raw_value or "").strip()
        if not text:
            return 0, 0, 0, ""

        text = (
            text.replace("：", ":")
            .replace("—", "-")
            .replace("–", "-")
            .replace("至", "-")
            .replace("到", "-")
        )
        if text.startswith("-") and text[1:].isdigit():
            return 0, 0, max(1, int(text[1:])), ""

        separator = ":" if ":" in text else "-" if "-" in text else ""
        if not separator:
            if text.isdigit():
                value = max(1, int(text))
                return value, value, 0, ""
            return 0, 0, 0, f"无法解析 round_range={raw_value!r}，请使用 '1-3'、'4' 或 '-2'。"

        left, right = [part.strip() for part in text.split(separator, 1)]
        start_round = int(left) if left.isdigit() else 0
        end_round = int(right) if right.isdigit() else 0
        if start_round <= 0 and end_round <= 0:
            return 0, 0, 0, f"无法解析 round_range={raw_value!r}，请使用 '1-3'、'4' 或 '-2'。"
        if start_round > 0 and end_round > 0 and start_round > end_round:
            start_round, end_round = end_round, start_round
        return start_round, end_round, 0, ""

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        keyword = str(parameters.get("keyword") or "").strip()
        round_range = str(parameters.get("round_range") or parameters.get("range") or "").strip()
        start_round = int(parameters.get("start_round") or 0)
        end_round = int(parameters.get("end_round") or 0)
        latest_count = 0
        if round_range:
            start_round, end_round, latest_count, parse_error = self._parse_round_range(round_range)
            if parse_error:
                return {
                    "status": "error",
                    "output": "",
                    "error": parse_error,
                    "results": [],
                }
        elif start_round < 0:
            latest_count = abs(start_round)
            start_round = 0

        try:
            if task_id:
                try:
                    sync_task_history_from_context(task_id)
                except Exception:
                    pass
            payload = search_task_history_records(
                task_id=task_id,
                keyword=keyword,
                start_round=start_round,
                end_round=end_round,
            )
            results = payload.get("results", [])
            keyword_search_error = payload.get("keyword_search_error") or ""
            warnings = []
            if keyword_search_error:
                warnings.append(f"关键词 FTS 检索失败，已自动切换到 LIKE 兜底: {keyword_search_error}")
            if latest_count > 0:
                results = results[-latest_count:]

            if not results:
                output = "没有检索到匹配的历史任务信息。"
                if warnings:
                    output += "\n" + "\n".join(f"warning: {item}" for item in warnings)
                return {
                    "status": "success",
                    "output": output,
                    "error": "",
                    "results": [],
                    "warnings": warnings,
                }

            lines = []
            if warnings:
                lines.extend(f"warning: {item}" for item in warnings)
            query_desc = []
            if round_range:
                query_desc.append(f"round_range={round_range}")
            elif latest_count:
                query_desc.append(f"round_range=-{latest_count}")
            elif start_round or end_round:
                query_desc.append(f"round_range={start_round or ''}-{end_round or ''}")
            if keyword:
                query_desc.append(f"keyword={keyword}")
            if query_desc:
                lines.append("query: " + " | ".join(query_desc))
            for idx, item in enumerate(results, 1):
                lines.append(
                    f"{idx}. 第{item.get('round')}条历史任务 | start={item.get('start_time','')} | completion={item.get('completion_time','')}"
                )
                for instruction in item.get("instructions", [])[:3]:
                    lines.append(f"   instruction: {instruction[:300]}")
                if item.get("final_output"):
                    lines.append(f"   final_output: {str(item['final_output'])[:800]}")
                if item.get("latest_thinking"):
                    lines.append(f"   latest_thinking: {str(item['latest_thinking'])[:500]}")
                score = item.get("score")
                if score is not None:
                    lines.append(f"   score: {score:.4f}")

            return {
                "status": "success",
                "output": "\n".join(lines),
                "error": "",
                "results": results,
                "warnings": warnings,
            }
        except Exception as e:
            return {
                "status": "error",
                "output": "",
                "error": str(e),
                "results": [],
            }
