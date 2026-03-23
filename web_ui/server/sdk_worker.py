#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Web UI SDK worker.

Runs one task per process using the Python SDK and emits JSONL events on stdout.
Normal logs are redirected to stderr to keep stdout machine-readable.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infiagent import infiagent
from core.runtime_exceptions import InfiAgentRunError
from tool_server_lite.tools.human_tools import respond_hil_task, respond_tool_confirmation
import utils.event_emitter as event_emitter_module

_EMIT_LOCK = threading.Lock()


def emit_json(payload: Dict[str, Any]) -> None:
    with _EMIT_LOCK:
        sys.stdout_orig.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout_orig.flush()


class WorkerBridgeEmitter:
    def __init__(self):
        self.enabled = True
        self.call_id = "sdk-worker"
        self.start_time = time.time()

    def emit(self, event: Dict[str, Any]):
        if not isinstance(event, dict):
            return
        event_type = str(event.get("type") or "").strip()
        if event_type in {"human_in_loop", "tool_confirmation"}:
            emit_json(event)

    def start(self, call_id: str, project: str, agent: str, task: str):
        self.call_id = call_id
        self.start_time = time.time()

    def token(self, text: str):
        # SDK stream tokens are relayed through on_event, not the legacy emitter.
        return

    def progress(self, phase: str, pct: int):
        return

    def notice(self, text: str):
        emit_json({"type": "notice", "text": str(text or "")})

    def warn(self, text: str):
        emit_json({"type": "warn", "text": str(text or "")})

    def error(self, text: str):
        emit_json({"type": "error", "text": str(text or "")})

    def artifact(self, kind: str, path: str = None, summary: str = None, preview: str = None):
        emit_json({
            "type": "artifact",
            "kind": kind,
            "path": path,
            "summary": summary,
            "preview": preview,
        })

    def human_in_loop(self, hil_id: str, title: str, message: str, ui: Dict[str, Any], timeout_sec: int = 1800, resume_hint: str = None):
        emit_json({
            "type": "human_in_loop",
            "hil_id": hil_id,
            "title": title,
            "message": message,
            "ui": ui,
            "timeout_sec": timeout_sec,
            "resume_hint": resume_hint,
        })

    def result(self, ok: bool, summary: str, artifacts=None):
        emit_json({
            "type": "result",
            "ok": bool(ok),
            "summary": str(summary or ""),
            "artifacts": list(artifacts or []),
        })

    def end(self, status: str, extra: Dict[str, Any] = None):
        payload = {
            "type": "end",
            "status": str(status or ""),
            "duration_ms": int((time.time() - self.start_time) * 1000),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        emit_json(payload)


def map_sdk_event(event: Dict[str, Any]) -> Dict[str, Any] | None:
    event_type = str(event.get("event_type") or "")
    payload = event.get("payload", {}) if isinstance(event.get("payload"), dict) else {}

    if event_type == "agent.start":
        return {
            "type": "agent_start",
            "agent": payload.get("agent_name", ""),
            "task": payload.get("task_input", ""),
        }
    if event_type == "agent.end":
        return {
            "type": "agent_end",
            "status": payload.get("status", ""),
        }
    if event_type == "run.thinking.start":
        return {
            "type": "thinking_start",
            "agent": payload.get("agent_name", ""),
            "is_initial": bool(payload.get("is_initial")),
            "is_forced": bool(payload.get("is_forced")),
        }
    if event_type == "run.thinking.end":
        return {
            "type": "thinking_end",
            "agent": payload.get("agent_name", ""),
            "result": payload.get("result", "") or payload.get("raw_output", ""),
            "model": payload.get("model", ""),
        }
    if event_type == "run.thinking.token":
        return {
            "type": "thinking_token",
            "agent": payload.get("agent_name", ""),
            "model": payload.get("model", ""),
            "text": payload.get("text", ""),
        }
    if event_type == "run.thinking.reasoning_token":
        return {
            "type": "thinking_token",
            "agent": payload.get("agent_name", ""),
            "model": payload.get("model", ""),
            "text": payload.get("text", ""),
            "token_kind": "reasoning",
        }
    if event_type == "run.llm.token":
        return {
            "type": "token",
            "agent": payload.get("agent_name", ""),
            "model": payload.get("model", ""),
            "text": payload.get("text", ""),
        }
    if event_type == "run.llm.reasoning_token":
        return {
            "type": "reasoning_token",
            "agent": payload.get("agent_name", ""),
            "model": payload.get("model", ""),
            "text": payload.get("text", ""),
        }
    if event_type == "run.tool.start":
        return {
            "type": "tool_call",
            "name": payload.get("tool_name", ""),
            "tool_name": payload.get("tool_name", ""),
            "arguments": payload.get("arguments", {}) or {},
        }
    if event_type == "run.tool.end":
        result = payload.get("result", {}) if isinstance(payload.get("result"), dict) else {}
        error_text = str(result.get("error_information") or result.get("error") or "")
        preview = str(result.get("output", "") or "")
        return {
            "type": "tool_result",
            "name": payload.get("tool_name", ""),
            "tool_name": payload.get("tool_name", ""),
            "status": payload.get("status", ""),
            "output_preview": preview[:2000],
            "error": error_text,
        }
    return None


def start_control_thread() -> None:
    def _worker():
        for line in sys.stdin:
            line = (line or "").strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue
            message_type = str(payload.get("type") or "").strip()
            if message_type == "hil_response":
                hil_id = str(payload.get("hil_id") or "").strip()
                response = payload.get("response")
                if hil_id and response is not None:
                    respond_hil_task(hil_id, str(response))
            elif message_type == "tool_confirmation_response":
                confirm_id = str(payload.get("confirm_id") or "").strip()
                approved = payload.get("approved")
                if confirm_id and approved is not None:
                    respond_tool_confirmation(confirm_id, bool(approved))

    thread = threading.Thread(target=_worker, daemon=True, name="sdk-worker-stdin")
    thread.start()


def main() -> int:
    sys.stdout_orig = sys.stdout
    sys.stdout = sys.stderr

    parser = argparse.ArgumentParser(description="Web UI SDK worker")
    parser.add_argument("--task_id", required=True)
    parser.add_argument("--user_data_root", required=True)
    parser.add_argument("--skills_dir", required=True)
    parser.add_argument("--agent_system", required=True)
    parser.add_argument("--agent_name", required=True)
    parser.add_argument("--user_input", required=True)
    args = parser.parse_args()

    bridge = WorkerBridgeEmitter()
    event_emitter_module._event_emitter = bridge
    start_control_thread()
    bridge.start("sdk-worker", args.task_id, args.agent_name, args.user_input)

    started_at = time.time()
    emit_json({
        "type": "start",
        "agent": args.agent_name,
        "task": args.user_input,
        "task_id": args.task_id,
    })

    def on_event(event: Dict[str, Any]) -> None:
        mapped = map_sdk_event(event)
        if mapped:
            emit_json(mapped)

    agent = infiagent(
        user_data_root=args.user_data_root,
        skills_dir=args.skills_dir,
        default_agent_system=args.agent_system,
        default_agent_name=args.agent_name,
        seed_builtin_resources=True,
        direct_tools=True,
    )

    try:
        result = agent.run(
            args.user_input,
            task_id=args.task_id,
            agent_system=args.agent_system,
            agent_name=args.agent_name,
            collect_events=False,
            on_event=on_event,
            include_trace=False,
            raise_on_error=True,
            stream_llm_tokens=True,
        )
        ok = str(result.get("status") or "") == "success"
        summary = str(result.get("output") or result.get("error") or "")
        emit_json({
            "type": "result",
            "ok": ok,
            "summary": summary,
        })
        emit_json({
            "type": "end",
            "status": "ok" if ok else "error",
            "duration_ms": int((time.time() - started_at) * 1000),
        })
        return 0 if ok else 1
    except InfiAgentRunError as exc:
        text = str(exc.result.get("error") or exc.result.get("error_information") or str(exc))
        emit_json({"type": "error", "text": text})
        emit_json({
            "type": "end",
            "status": "error",
            "duration_ms": int((time.time() - started_at) * 1000),
        })
        return 1
    except Exception as exc:
        emit_json({"type": "error", "text": str(exc)})
        emit_json({
            "type": "end",
            "status": "error",
            "duration_ms": int((time.time() - started_at) * 1000),
        })
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
