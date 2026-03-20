#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.agent_executor import AgentExecutor
from core.events import AgentStartEvent, ThinkingEndEvent, ToolCallEndEvent, ToolCallStartEvent
from core.runtime_exceptions import InfiAgentRunError
from infiagent import infiagent
from utils.user_paths import get_task_file_prefix


class _FakeEventEmitter:
    def __init__(self):
        self.events = []

    def dispatch(self, event):
        self.events.append(event)


class _FakeAgentExecutor:
    instances = []
    result_payload = {"status": "success", "output": "done"}

    def __init__(
        self,
        agent_name,
        agent_config,
        config_loader,
        hierarchy_manager,
        direct_tools=False,
        extra_event_handlers=None,
        exit_on_error=True,
        raise_on_error=False,
        stream_llm_tokens=False,
    ):
        self.agent_name = agent_name
        self.extra_event_handlers = list(extra_event_handlers or [])
        self.exit_on_error = exit_on_error
        self.raise_on_error = raise_on_error
        self.stream_llm_tokens = stream_llm_tokens
        self.__class__.instances.append(self)

    def run(self, task_id, user_input):
        if self.stream_llm_tokens:
            token_events = [
                {
                    "event_type": "run.thinking.token",
                    "phase": "run",
                    "domain": "thinking",
                    "action": "token",
                    "payload": {
                        "agent_name": self.agent_name,
                        "model": "demo-thinking-model",
                        "text": "thinking chunk",
                        "token_kind": "content",
                        "is_initial": True,
                        "is_forced": False,
                    },
                },
                {
                    "event_type": "run.llm.token",
                    "phase": "run",
                    "domain": "llm",
                    "action": "token",
                    "payload": {
                        "agent_name": self.agent_name,
                        "model": "demo-execution-model",
                        "text": "execution chunk",
                        "token_kind": "content",
                    },
                },
            ]
            for handler in self.extra_event_handlers:
                emitter = getattr(handler, "emit", None)
                if callable(emitter):
                    for event in token_events:
                        emitter(event)

        event_sequence = [
            AgentStartEvent(agent_name=self.agent_name, task_input=user_input),
            ThinkingEndEvent(agent_name=self.agent_name, is_initial=True, result="plan ready"),
            ToolCallStartEvent(tool_name="demo_tool", arguments={"x": 1}),
            ToolCallEndEvent(tool_name="demo_tool", status="success", result={"status": "success", "output": "ok"}),
        ]
        for event in event_sequence:
            for handler in self.extra_event_handlers:
                handler.handle(event)
        payload = dict(self.__class__.result_payload)
        payload.setdefault("task_id", task_id)
        payload.setdefault("observed_max_turns", os.environ.get("MLA_MAX_TURNS", ""))
        return payload


class SDKObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)

    def test_run_can_collect_structured_events_and_callback(self):
        root = (self.base / "sdk_root").resolve()
        task_id = str((self.base / "task_with_events").resolve())
        agent = infiagent(user_data_root=str(root))
        callback_events = []

        _FakeAgentExecutor.instances.clear()
        _FakeAgentExecutor.result_payload = {"status": "success", "output": "done"}

        with patch("infiagent.sdk.AgentExecutor", _FakeAgentExecutor):
            result = agent.run(
                "hello from sdk",
                task_id=task_id,
                collect_events=True,
                on_event=callback_events.append,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["events"]), 4)
        self.assertEqual(result["events"][0]["event_type"], "agent.start")
        self.assertEqual(result["events"][1]["event_type"], "run.thinking.end")
        self.assertEqual(result["events"][2]["payload"]["arguments"], {"x": 1})
        self.assertEqual(callback_events, result["events"])

        instance = _FakeAgentExecutor.instances[-1]
        self.assertFalse(instance.exit_on_error)
        self.assertFalse(instance.raise_on_error)
        self.assertFalse(instance.stream_llm_tokens)

    def test_run_can_optionally_collect_stream_token_events(self):
        root = (self.base / "sdk_stream_root").resolve()
        task_id = str((self.base / "task_with_stream").resolve())
        agent = infiagent(user_data_root=str(root))
        callback_events = []

        _FakeAgentExecutor.instances.clear()
        _FakeAgentExecutor.result_payload = {"status": "success", "output": "done"}

        with patch("infiagent.sdk.AgentExecutor", _FakeAgentExecutor):
            result = agent.run(
                "stream me",
                task_id=task_id,
                collect_events=True,
                on_event=callback_events.append,
                stream_llm_tokens=True,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["events"][0]["event_type"], "run.thinking.token")
        self.assertEqual(result["events"][1]["event_type"], "run.llm.token")
        self.assertEqual(result["events"][0]["payload"]["text"], "thinking chunk")
        self.assertEqual(result["events"][1]["payload"]["text"], "execution chunk")
        self.assertEqual(callback_events, result["events"])
        instance = _FakeAgentExecutor.instances[-1]
        self.assertTrue(instance.stream_llm_tokens)

    def test_run_can_override_max_turns_via_sdk_parameter(self):
        root = (self.base / "sdk_max_turns_root").resolve()
        task_id = str((self.base / "task_with_max_turns").resolve())
        agent = infiagent(user_data_root=str(root))

        _FakeAgentExecutor.instances.clear()
        _FakeAgentExecutor.result_payload = {"status": "success", "output": "done"}

        with patch("infiagent.sdk.AgentExecutor", _FakeAgentExecutor):
            result = agent.run(
                "max turns please",
                task_id=task_id,
                max_turns=77,
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["observed_max_turns"], "77")

    def test_run_raise_on_error_turns_error_result_into_exception(self):
        root = (self.base / "sdk_error_root").resolve()
        task_id = str((self.base / "task_with_error").resolve())
        agent = infiagent(user_data_root=str(root))

        _FakeAgentExecutor.instances.clear()
        _FakeAgentExecutor.result_payload = {
            "status": "error",
            "output": "",
            "error_information": "demo failure",
        }

        with patch("infiagent.sdk.AgentExecutor", _FakeAgentExecutor):
            with self.assertRaises(InfiAgentRunError) as ctx:
                agent.run(
                    "please fail",
                    task_id=task_id,
                    collect_events=True,
                    include_trace=True,
                    raise_on_error=True,
                )

        exc = ctx.exception
        self.assertEqual(exc.result["status"], "error")
        self.assertEqual(exc.result["error_information"], "demo failure")
        self.assertEqual(len(exc.events), 4)
        self.assertIsNotNone(exc.trace)
        self.assertEqual(exc.trace["status"], "success")

    def test_task_trace_reads_agent_action_files(self):
        root = (self.base / "trace_root").resolve()
        task_id = str((self.base / "trace_task").resolve())
        agent = infiagent(user_data_root=str(root))

        with agent._runtime_scope():
            conversations_dir = root / "conversations"
            conversations_dir.mkdir(parents=True, exist_ok=True)
            prefix = get_task_file_prefix(task_id)
            trace_path = conversations_dir / f"{prefix}_demo_agent_001_actions.json"
            trace_path.write_text(json.dumps({
                "task_id": task_id,
                "agent_id": "demo_agent_001",
                "agent_name": "demo_agent",
                "task_input": "trace me",
                "current_turn": 3,
                "tool_call_counter": 2,
                "llm_turn_counter": 1,
                "latest_thinking": "latest plan",
                "pending_tools": [{"name": "demo_tool"}],
                "action_history_fact": [{
                    "tool_name": "demo_tool",
                    "arguments": {"path": "demo.txt"},
                    "result": {"status": "success", "output": "ok"},
                }],
                "action_history": [{"tool_name": "demo_tool"}],
                "system_prompt": "hidden unless requested",
                "last_updated": "2026-03-20T12:00:00+08:00",
            }, ensure_ascii=False), encoding="utf-8")
            debug_path = conversations_dir / f"{prefix}_llm_debug.jsonl"
            debug_path.write_text('{"demo": true}\n', encoding="utf-8")

        trace = agent.task_trace(task_id=task_id)
        self.assertEqual(trace["status"], "success")
        self.assertEqual(trace["agent_trace_count"], 1)
        self.assertEqual(trace["llm_debug_path"], str(debug_path))
        item = trace["agent_traces"][0]
        self.assertEqual(item["agent_name"], "demo_agent")
        self.assertEqual(item["latest_thinking"], "latest plan")
        self.assertEqual(item["action_history_fact"][0]["tool_name"], "demo_tool")
        self.assertNotIn("action_history", item)
        self.assertNotIn("system_prompt", item)

        trace_with_full_fields = agent.task_trace(
            task_id=task_id,
            include_render_history=True,
            include_system_prompt=True,
        )
        full_item = trace_with_full_fields["agent_traces"][0]
        self.assertIn("action_history", full_item)
        self.assertIn("system_prompt", full_item)

    def test_agent_executor_returns_error_result_in_library_mode(self):
        executor = AgentExecutor.__new__(AgentExecutor)
        executor.latest_thinking = "partial progress"
        executor.event_emitter = _FakeEventEmitter()
        executor.raise_on_error = False
        executor.exit_on_error = False
        executor.current_task_id = "/tmp/demo-task"
        executor.agent_name = "alpha_agent"

        try:
            raise RuntimeError("boom")
        except RuntimeError as err:
            result = executor._handle_execution_error(err)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "RuntimeError")
        self.assertEqual(result["agent_name"], "alpha_agent")
        self.assertTrue(result["error_information"])
        self.assertEqual(len(executor.event_emitter.events), 2)

    def test_agent_executor_can_raise_catchable_exception_in_library_mode(self):
        executor = AgentExecutor.__new__(AgentExecutor)
        executor.latest_thinking = ""
        executor.event_emitter = _FakeEventEmitter()
        executor.raise_on_error = True
        executor.exit_on_error = False
        executor.current_task_id = "/tmp/demo-task"
        executor.agent_name = "alpha_agent"

        with self.assertRaises(InfiAgentRunError) as ctx:
            try:
                raise RuntimeError("boom again")
            except RuntimeError as err:
                executor._handle_execution_error(err)

        exc = ctx.exception
        self.assertEqual(exc.task_id, "/tmp/demo-task")
        self.assertEqual(exc.agent_name, "alpha_agent")
        self.assertEqual(exc.result["error_type"], "RuntimeError")

    def test_agent_executor_result_enrichment_exposes_raw_model_outputs(self):
        executor = AgentExecutor.__new__(AgentExecutor)
        executor.execution_traces = [{
            "turn_index": 2,
            "model": "demo-exec-model",
            "content": "assistant plain output",
            "reasoning_content": "assistant reasoning",
            "finish_reason": "tool_calls",
            "tool_calls": [{"name": "demo_tool"}],
            "status": "success",
        }]
        executor.thinking_traces = [{
            "model": "demo-thinking-model",
            "content": "thinking plain output",
            "reasoning_content": "thinking reasoning",
            "formatted_result": "[🤖 初始规划]\n\nthinking plain output",
            "finish_reason": "stop",
            "status": "success",
            "is_initial": True,
            "is_forced": False,
        }]

        result = executor._with_model_outputs({"status": "success", "output": "final output"})
        self.assertEqual(result["last_execution_output"], "assistant plain output")
        self.assertEqual(result["last_execution_reasoning_content"], "assistant reasoning")
        self.assertEqual(result["last_execution_model"], "demo-exec-model")
        self.assertEqual(result["last_thinking_output"], "thinking plain output")
        self.assertEqual(result["last_thinking_reasoning_content"], "thinking reasoning")
        self.assertEqual(result["last_thinking_model"], "demo-thinking-model")
        self.assertEqual(result["model_outputs"]["last_execution"]["finish_reason"], "tool_calls")
        self.assertEqual(result["model_outputs"]["last_thinking"]["formatted_result"], "[🤖 初始规划]\n\nthinking plain output")


if __name__ == "__main__":
    unittest.main()
