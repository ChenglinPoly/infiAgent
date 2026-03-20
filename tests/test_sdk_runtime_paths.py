#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import signal
import json
import tempfile
import time
import unittest
import warnings
from pathlib import Path

from infiagent import infiagent
from core.hierarchy_manager import get_hierarchy_manager
from tool_server_lite.tools.skill_tools import FreshTool
from tool_server_lite.tools.task_tools import AddMessageTool, ListTaskIdsTool, TaskShareContextPathTool
from utils.config_loader import ConfigLoader
from utils.runtime_control import pop_fresh_request, register_running_task, unregister_running_task
from utils.user_paths import runtime_env_scope


class SDKRuntimePathTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)

    def test_default_root_semantics_follow_current_env(self):
        root = (self.base / "default_root").resolve()
        task_id = str((self.base / "default_task").resolve())

        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(root)}):
            agent = infiagent()
            result = agent.add_message("default root message", task_id=task_id)
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["share_context_path"].startswith(str(root / "conversations")))

            listed = agent.list_task_ids()
            self.assertTrue(any(item["task_id"] == task_id for item in listed["tasks"]))

            share_paths = agent.task_share_context_path(task_id=task_id)
            self.assertTrue(share_paths["share_context_path"].startswith(str(root / "conversations")))
            self.assertTrue(share_paths["stack_path"].startswith(str(root / "conversations")))
            self.assertTrue((root / "config" / "app_config.json").exists())

    def test_custom_user_data_root_applies_to_sdk_and_runtime_control(self):
        root = (self.base / "custom_root").resolve()
        task_id = str((self.base / "custom_task").resolve())
        agent = infiagent(user_data_root=str(root))

        result = agent.add_message("sdk scoped message", task_id=task_id)
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["share_context_path"].startswith(str(root / "conversations")))

        with agent._runtime_scope():
            register_running_task(task_id, "alpha_agent", "hello", "OpenCowork")
            try:
                fresh_result = agent.fresh(task_id=task_id, reason="sdk-test-fresh")
                self.assertEqual(fresh_result["status"], "success")
                runtime_root = root / "runtime"
                self.assertTrue((runtime_root / "running_tasks").exists())
                self.assertEqual(pop_fresh_request(task_id), "sdk-test-fresh")
            finally:
                unregister_running_task(task_id)

    def test_task_tools_follow_custom_user_data_root(self):
        root = (self.base / "tool_root").resolve()
        task_id = str((self.base / "tool_task").resolve())

        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(root)}):
            add_tool = AddMessageTool()
            add_result = add_tool.execute(task_id, {"message": "tool message", "source": "agent"})
            self.assertEqual(add_result["status"], "success")
            self.assertTrue(add_result["share_context_path"].startswith(str(root / "conversations")))

            path_tool = TaskShareContextPathTool()
            path_result = path_tool.execute(task_id, {})
            self.assertEqual(path_result["status"], "success")
            self.assertTrue(path_result["share_context_path"].startswith(str(root / "conversations")))

            list_tool = ListTaskIdsTool()
            list_result = list_tool.execute(task_id, {})
            self.assertEqual(list_result["status"], "success")
            self.assertTrue(any(item["task_id"] == task_id for item in list_result["tasks"]))

            fresh_tool = FreshTool()
            fresh_signal = fresh_tool.execute(task_id, {})
            self.assertEqual(fresh_signal["status"], "success")
            self.assertEqual(fresh_signal["_fresh_task_id"], task_id)

    def test_user_data_root_alone_is_enough_for_agent_library_loading(self):
        root = (self.base / "config_root").resolve()
        agent = infiagent(user_data_root=str(root))

        with agent._runtime_scope():
            loader = ConfigLoader("OpenCowork")
            config = loader.get_tool_config("alpha_agent")
            for tool_name in [
                "fresh",
                "add_message",
                "start_background_task",
                "task_share_context_path",
                "list_task_ids",
            ]:
                self.assertIn(tool_name, loader.all_tools)

        self.assertEqual(config.get("type"), "llm_call_agent")
        self.assertTrue((root / "agent_library" / "OpenCowork").exists())

    def test_sdk_requires_explicit_task_id(self):
        agent = infiagent()
        with self.assertRaises(ValueError):
            agent.run("missing task id", task_id="")

    def test_sdk_instances_do_not_leak_user_data_roots(self):
        root_a = (self.base / "root_a").resolve()
        root_b = (self.base / "root_b").resolve()
        task_a = str((self.base / "task_a").resolve())
        task_b = str((self.base / "task_b").resolve())

        agent_a = infiagent(user_data_root=str(root_a))
        agent_b = infiagent(user_data_root=str(root_b))

        result_a = agent_a.add_message("message for a", task_id=task_a)
        result_b = agent_b.add_message("message for b", task_id=task_b)

        self.assertTrue(result_a["share_context_path"].startswith(str(root_a / "conversations")))
        self.assertTrue(result_b["share_context_path"].startswith(str(root_b / "conversations")))

        list_a = agent_a.list_task_ids()
        list_b = agent_b.list_task_ids()

        self.assertTrue(any(item["task_id"] == task_a for item in list_a["tasks"]))
        self.assertFalse(any(item["task_id"] == task_b for item in list_a["tasks"]))
        self.assertTrue(any(item["task_id"] == task_b for item in list_b["tasks"]))
        self.assertFalse(any(item["task_id"] == task_a for item in list_b["tasks"]))

    def test_run_returns_busy_when_task_already_running(self):
        root = (self.base / "busy_root").resolve()
        task_id = str((self.base / "busy_task").resolve())
        agent = infiagent(user_data_root=str(root))
        with agent._runtime_scope():
            register_running_task(task_id, "alpha_agent", "hello", "OpenCowork")
            try:
                result = agent.run("new request", task_id=task_id)
            finally:
                unregister_running_task(task_id)
        self.assertEqual(result["status"], "busy")
        self.assertEqual(result["task_id"], task_id)

    def test_background_task_launch_uses_user_data_root(self):
        root = (self.base / "launch_root").resolve()
        task_id = str((self.base / "launch_task").resolve())
        llm_config = str((Path(__file__).resolve().parent / "llm_config_dummy.yaml").resolve())
        agent = infiagent(user_data_root=str(root), llm_config_path=llm_config)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            result = agent.start_background_task(
                task_id=task_id,
                user_input="background launch smoke test",
                force_new=True,
            )
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["log_path"].startswith(str(root / "runtime" / "launched_tasks")))

        pid = result.get("pid")
        self.assertIsInstance(pid, int)
        time.sleep(0.5)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            for _ in range(20):
                try:
                    waited_pid, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    break
                if waited_pid == pid:
                    break
                time.sleep(0.1)

    def test_task_snapshot_falls_back_to_history_final_output(self):
        root = (self.base / "history_root").resolve()
        task_id = str((self.base / "history_task").resolve())
        agent = infiagent(user_data_root=str(root))

        with agent._runtime_scope():
            manager = get_hierarchy_manager(task_id)
            context = manager._load_context()
            context["history"] = [{
                "instructions": [],
                "hierarchy": {"worker_agent_demo": {"parent": None, "children": [], "level": 0}},
                "agents_status": {
                    "worker_agent_demo": {
                        "agent_name": "worker_agent",
                        "status": "completed",
                        "thinking_updated_at": "2026-03-10T10:00:00+08:00",
                        "latest_thinking": "done thinking",
                        "final_output": "done output",
                        "end_time": "2026-03-10T10:05:00+08:00",
                    }
                },
                "start_time": "2026-03-10T10:00:00+08:00",
                "completion_time": "2026-03-10T10:05:00+08:00",
            }]
            context["current"] = {
                "instructions": [],
                "hierarchy": {},
                "agents_status": {},
                "start_time": "2026-03-10T10:06:00+08:00",
                "last_updated": "2026-03-10T10:06:00+08:00",
            }
            manager._save_context(context)

        snapshot = agent.task_snapshot(task_id=task_id)
        self.assertEqual(snapshot["status"], "success")
        self.assertEqual(snapshot["last_final_output"], "done output")
        self.assertEqual(snapshot["last_final_output_at"], "2026-03-10T10:05:00+08:00")
        self.assertEqual(snapshot["latest_thinking"], "done thinking")

    def test_tool_hooks_are_exposed_in_launch_config(self):
        callback = str((self.base / "hook.py").resolve()) + ":on_tool_event"
        hooks = [{
            "name": "demo",
            "when": "after",
            "tool_names": ["final_output"],
            "callback": callback,
            "result_filters": {"status": "success"},
        }]
        agent = infiagent(user_data_root=str((self.base / "hook_root").resolve()), tool_hooks=hooks)
        launch_config = agent._build_launch_config()
        self.assertEqual(launch_config["tool_hooks"], hooks)

    def test_context_hooks_are_exposed_in_launch_config(self):
        callback = str((self.base / "ctx_hook.py").resolve()) + ":on_context"
        hooks = [{
            "name": "ctx-demo",
            "when": "after_build",
            "callback": callback,
        }]
        agent = infiagent(user_data_root=str((self.base / "ctx_hook_root").resolve()), context_hooks=hooks)
        launch_config = agent._build_launch_config()
        self.assertEqual(launch_config["context_hooks"], hooks)
        self.assertTrue(launch_config["seed_builtin_resources"])

    def test_max_turns_is_exposed_in_launch_config(self):
        agent = infiagent(
            user_data_root=str((self.base / "max_turns_root").resolve()),
            max_turns=321,
        )
        launch_config = agent._build_launch_config()
        self.assertEqual(launch_config["max_turns"], 321)
        runtime = agent.describe_runtime()
        self.assertEqual(runtime["max_turns"], 321)


if __name__ == "__main__":
    unittest.main()
