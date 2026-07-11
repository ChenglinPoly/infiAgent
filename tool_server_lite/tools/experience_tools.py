#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .file_tools import BaseTool
from utils.experience_store import (
    ConcurrencyConflictError,
    append_experience_many,
    delete_experience_many,
    global_experience_path,
    list_experience_entries,
    file_revision,
    replace_experience_many,
    resolve_runtime_agent_context,
    task_experience_path,
)


def _resolve_targets(task_id: str, target_agent_name: str, scope: str) -> List[tuple[str, Path, str]]:
    runtime = resolve_runtime_agent_context(task_id)
    agent_name = str(target_agent_name or runtime["agent_name"]).strip() or runtime["agent_name"]
    agent_system = runtime["agent_system"]

    targets: List[tuple[str, Path, str]] = []
    if scope in {"task", "both"}:
        targets.append(("task", task_experience_path(task_id, agent_name), f"Task Experience: {agent_name}"))
    if scope in {"global", "both"}:
        targets.append(("global", global_experience_path(agent_system, agent_name), f"Global Experience: {agent_name}"))
    return targets


class WriteExperienceTool(BaseTool):
    """统一经验工具：追加 / 查看 / 更新 / 删除（并发安全，scope=both 事务一致）。"""

    name = "write_experience"

    def execute(self, task_id: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        try:
            operation = str(parameters.get("operation") or "append").strip().lower()
            scope = str(parameters.get("scope") or "task").strip().lower()
            target_agent_name = str(parameters.get("target_agent_name") or "").strip()
            content = str(parameters.get("content") or "").strip()
            source = str(parameters.get("source") or "agent").strip() or "agent"
            entry_id = str(parameters.get("entry_id") or "").strip()
            max_tokens = int(parameters.get("max_tokens") or 10000)
            expected_updated_at = str(parameters.get("expected_updated_at") or "").strip() or None
            raw_expected_revision = parameters.get("expected_revision")
            expected_revision = None
            if raw_expected_revision not in (None, ""):
                expected_revision = int(raw_expected_revision)

            if operation not in {"append", "list", "replace", "delete"}:
                return {"status": "error", "output": "", "error": "operation 必须是 append/list/replace/delete 之一。"}
            if scope not in {"task", "global", "both"}:
                return {"status": "error", "output": "", "error": "scope 必须是 task/global/both 之一。"}
            if expected_revision is not None and scope == "both":
                return {
                    "status": "error", "output": "",
                    "error": "expected_revision 是单文件级检查，scope=both 时请分别对 task/global 操作，或改用 expected_updated_at。",
                }

            targets = _resolve_targets(task_id, target_agent_name, scope)
            if not targets:
                return {"status": "error", "output": "", "error": "未解析到任何 experience 目标文件。"}

            if operation == "append" and not content:
                return {"status": "error", "output": "", "error": "append 操作需要 content。"}
            if operation == "replace" and (not content or not entry_id):
                return {"status": "error", "output": "", "error": "replace 操作需要 entry_id 和 content。"}
            if operation == "delete" and not entry_id:
                return {"status": "error", "output": "", "error": "delete 操作需要 entry_id。"}

            pairs = [(path, title) for _, path, title in targets]
            scopes = [target_scope for target_scope, _, _ in targets]
            result_items: List[Dict[str, Any]] = []

            if operation == "list":
                for target_scope, path, _ in targets:
                    result_items.append(
                        {
                            "scope": target_scope,
                            "path": str(path),
                            "revision": file_revision(path),
                            "entries": list_experience_entries(path),
                        }
                    )
            elif operation == "append":
                outcomes = append_experience_many(pairs, content, source=source, max_tokens=max_tokens)
                for target_scope, outcome in zip(scopes, outcomes):
                    result_items.append(
                        {
                            "scope": target_scope,
                            "path": outcome["path"],
                            "entry": outcome["entry_id"],
                            "revision": outcome["revision"],
                            "evicted_ids": outcome["evicted_ids"],
                            "status": "appended",
                        }
                    )
            elif operation == "replace":
                outcomes = replace_experience_many(
                    pairs, entry_id, content,
                    source=source, expected_revision=expected_revision, expected_updated_at=expected_updated_at,
                )
                for target_scope, outcome in zip(scopes, outcomes):
                    result_items.append(
                        {
                            "scope": target_scope,
                            "path": outcome["path"],
                            "entry": entry_id,
                            "revision": outcome["revision"],
                            "affected": outcome["affected"],
                            "status": "replaced" if outcome["replaced"] else "missing",
                        }
                    )
            elif operation == "delete":
                outcomes = delete_experience_many(
                    pairs, entry_id,
                    expected_revision=expected_revision, expected_updated_at=expected_updated_at,
                )
                for target_scope, outcome in zip(scopes, outcomes):
                    result_items.append(
                        {
                            "scope": target_scope,
                            "path": outcome["path"],
                            "entry": entry_id,
                            "revision": outcome["revision"],
                            "affected": outcome["affected"],
                            "status": "deleted" if outcome["deleted"] else "missing",
                        }
                    )

            return {
                "status": "success",
                "output": json.dumps({"operation": operation, "results": result_items}, ensure_ascii=False, indent=2),
                "error": "",
                "results": result_items,
            }
        except ConcurrencyConflictError as conflict:
            return {"status": "error", "output": "", "error": f"并发冲突: {conflict}"}
        except Exception as exc:
            return {"status": "error", "output": "", "error": f"{type(exc).__name__}: {exc}"}
