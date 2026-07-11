#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import tempfile
import unittest
from pathlib import Path

from core.context_builder import ContextBuilder
from core.hierarchy_manager import get_hierarchy_manager
from tool_server_lite.tools.experience_tools import WriteExperienceTool
from utils.user_paths import runtime_env_scope


class ExperienceToolTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)

    def test_write_experience_append_and_list_task_scope(self):
        task_id = str((self.base / "task").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.base / "user_root")}):
            manager = get_hierarchy_manager(task_id)
            manager.set_runtime_metadata(agent_system="ExampleSystem", agent_name="alpha_agent", user_input="demo")
            manager._save_stack([{"agent_name": "alpha_agent", "level": 0, "user_input": "demo"}])

            tool = WriteExperienceTool()
            appended = tool.execute(task_id, {
                "operation": "append",
                "scope": "task",
                "content": "Remember this task-specific lesson.",
            })
            self.assertEqual(appended["status"], "success")
            entry_id = appended["results"][0]["entry"]

            listed = tool.execute(task_id, {
                "operation": "list",
                "scope": "task",
            })
            self.assertEqual(listed["status"], "success")
            parsed = json.loads(listed["output"])
            self.assertEqual(parsed["results"][0]["entries"][0]["entry_id"], entry_id)

    def test_write_experience_replace_and_delete_global_scope(self):
        task_id = str((self.base / "task2").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.base / "user_root")}):
            manager = get_hierarchy_manager(task_id)
            manager.set_runtime_metadata(agent_system="ExampleSystem", agent_name="alpha_agent", user_input="demo")
            manager._save_stack([{"agent_name": "alpha_agent", "level": 0, "user_input": "demo"}])

            tool = WriteExperienceTool()
            appended = tool.execute(task_id, {
                "operation": "append",
                "scope": "global",
                "content": "Global lesson one.",
            })
            entry_id = appended["results"][0]["entry"]

            replaced = tool.execute(task_id, {
                "operation": "replace",
                "scope": "global",
                "entry_id": entry_id,
                "content": "Global lesson replaced.",
            })
            self.assertEqual(replaced["status"], "success")
            self.assertEqual(replaced["results"][0]["status"], "replaced")

            deleted = tool.execute(task_id, {
                "operation": "delete",
                "scope": "global",
                "entry_id": entry_id,
            })
            self.assertEqual(deleted["status"], "success")
            self.assertEqual(deleted["results"][0]["status"], "deleted")

    def test_context_builder_injects_task_and_global_experience(self):
        task_id = str((self.base / "task3").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.base / "user_root")}):
            manager = get_hierarchy_manager(task_id)
            manager.set_runtime_metadata(agent_system="ExampleSystem", agent_name="alpha_agent", user_input="demo")
            manager._save_stack([{"agent_name": "alpha_agent", "level": 0, "user_input": "demo"}])

            tool = WriteExperienceTool()
            tool.execute(task_id, {
                "operation": "append",
                "scope": "task",
                "content": "Task scoped experience.",
            })
            tool.execute(task_id, {
                "operation": "append",
                "scope": "global",
                "content": "Global scoped experience.",
            })

            builder = ContextBuilder.__new__(ContextBuilder)
            builder.config_loader = type("Loader", (), {"agent_system_name": "ExampleSystem"})()
            text = builder._build_experience_blocks(task_id, "alpha_agent")
            self.assertIn("<任务经验>", text)
            self.assertIn("Task scoped experience.", text)
            self.assertIn("<全局经验>", text)
            self.assertIn("Global scoped experience.", text)


if __name__ == "__main__":
    unittest.main()
