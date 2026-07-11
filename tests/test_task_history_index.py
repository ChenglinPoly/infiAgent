#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import tempfile
import unittest
from pathlib import Path

from core.context_builder import ContextBuilder
from tool_server_lite.tools.task_tools import TaskHistorySearchTool
from utils.task_history_index import search_task_history_records, search_task_history_sql, sync_task_history_from_context
from utils.user_paths import runtime_env_scope


class _DummyHierarchyManager:
    def __init__(self, context):
        self._context = context

    def get_context(self):
        return self._context

    def _save_context(self, context):
        self._context = context


class _DummyConfigLoader:
    agent_system_name = "OpenCowork"
    agent_config_dir = ""


class TaskHistoryIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()

    def _sample_context(self, task_id: str):
        return {
            "runtime": {
                "agent_system": "OpenCowork",
                "agent_name": "alpha_agent",
            },
            "current": {
                "instructions": [],
                "hierarchy": {},
                "agents_status": {},
            },
            "history": [
                {
                    "instructions": [
                        {"instruction": "继续完善季度总结文档"},
                        {"instruction": "检查上次生成的结论是否需要更新"},
                    ],
                    "start_time": "2026-03-01T10:00:00+08:00",
                    "completion_time": "2026-03-01T10:05:00+08:00",
                    "hierarchy": {
                        "alpha_agent_1": {"parent": None, "children": [], "level": 0},
                    },
                    "agents_status": {
                        "alpha_agent_1": {
                            "agent_name": "alpha_agent",
                            "status": "completed",
                            "final_output": "季度总结文档已生成在 summary.md",
                            "latest_thinking": "下一次应优先复用 summary.md 的既有结构。",
                        }
                    },
                }
            ],
        }

    def test_sync_and_sql_search_return_instruction_bundle(self):
        task_id = str((self.root / "task_a").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            context = self._sample_context(task_id)
            inserted = sync_task_history_from_context(task_id, context)
            self.assertGreater(inserted, 0)

            results = search_task_history_sql(query="summary", limit=5)
            self.assertTrue(results)
            self.assertIn("继续完善季度总结文档", results[0]["text"])
            self.assertIn("summary.md", results[0]["text"])

    def test_task_history_search_tool_reads_index(self):
        task_id = str((self.root / "task_b").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            context = self._sample_context(task_id)
            sync_task_history_from_context(task_id, context)

            tool = TaskHistorySearchTool()
            result = tool.execute(task_id, {"keyword": "summary"})
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["results"])
            self.assertIn("summary.md", result["output"])

    def test_task_history_search_handles_symbol_heavy_keyword(self):
        task_id = str((self.root / "task_symbol_keyword").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            context = self._sample_context(task_id)
            context["history"][0]["instructions"][0]["instruction"] = "继续处理 /tmp/demo:a-b(1)/result.md 相关任务"
            context["history"][0]["agents_status"]["alpha_agent_1"]["final_output"] = "已修复 /tmp/demo:a-b(1)/result.md"
            sync_task_history_from_context(task_id, context)

            tool = TaskHistorySearchTool()
            result = tool.execute(task_id, {"keyword": "/tmp/demo:a-b(1)/result.md"})
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["results"])
            self.assertIn("result.md", result["output"])

    def test_task_history_search_supports_simple_round_range(self):
        task_id = str((self.root / "task_round_range").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            context = self._sample_context(task_id)
            context["history"].append(
                {
                    "instructions": [{"instruction": "第二轮：继续补充文档"}],
                    "start_time": "2026-03-02T10:00:00+08:00",
                    "completion_time": "2026-03-02T10:05:00+08:00",
                    "hierarchy": {"alpha_agent_2": {"parent": None, "children": [], "level": 0}},
                    "agents_status": {
                        "alpha_agent_2": {
                            "agent_name": "alpha_agent",
                            "status": "completed",
                            "final_output": "第二轮输出写入 summary_v2.md",
                            "latest_thinking": "继续补充结论部分。",
                        }
                    },
                }
            )
            sync_task_history_from_context(task_id, context)

            tool = TaskHistorySearchTool()
            result = tool.execute(task_id, {"round_range": "-1"})

            self.assertEqual(result["status"], "success")
            self.assertEqual(len(result["results"]), 1)
            self.assertIn("第二轮", result["output"])

    def test_task_history_records_default_returns_all_entries_for_task(self):
        task_id = str((self.root / "task_c").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            context = self._sample_context(task_id)
            sync_task_history_from_context(task_id, context)

            payload = search_task_history_records(task_id=task_id)
            self.assertEqual(len(payload["results"]), 1)
            self.assertEqual(payload["results"][0]["round"], 1)

    def test_task_history_records_support_start_round(self):
        task_id = str((self.root / "task_d").resolve())
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            context = self._sample_context(task_id)
            context["history"].append(
                {
                    "instructions": [{"instruction": "第二轮：继续补充文档"}],
                    "start_time": "2026-03-02T10:00:00+08:00",
                    "completion_time": "2026-03-02T10:05:00+08:00",
                    "hierarchy": {"alpha_agent_2": {"parent": None, "children": [], "level": 0}},
                    "agents_status": {
                        "alpha_agent_2": {
                            "agent_name": "alpha_agent",
                            "status": "completed",
                            "final_output": "第二轮输出写入 summary_v2.md",
                            "latest_thinking": "继续补充结论部分。",
                        }
                    },
                }
            )
            sync_task_history_from_context(task_id, context)

            payload = search_task_history_records(task_id=task_id, start_round=2)
            self.assertEqual(len(payload["results"]), 1)
            self.assertIn("第二轮：继续补充文档", payload["results"][0]["instructions"][0])

    def test_recent_history_selection_uses_new_setting(self):
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            app_config_path = self.root / "config" / "app_config.json"
            app_config_path.parent.mkdir(parents=True, exist_ok=True)
            app_config_path.write_text(
                json.dumps(
                    {
                        "context": {
                            "user_history_recent_items": 1,
                            "user_history_compress_threshold_tokens": 99999,
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            for key in [
                "MLA_ACTION_WINDOW_STEPS",
                "MLA_USER_HISTORY_COMPRESS_THRESHOLD_TOKENS",
                "MLA_USER_HISTORY_RECENT_ITEMS",
            ]:
                os.environ.pop(key, None)
            hierarchy = _DummyHierarchyManager({"history": [{"a": 1}, {"b": 2}, {"c": 3}], "current": {}, "runtime": {}})
            builder = ContextBuilder(hierarchy, {}, _DummyConfigLoader(), llm_client=None)
            selected, visible_count, total_count = builder._select_user_history_entries(hierarchy.get_context()["history"])

            self.assertEqual(visible_count, 1)
            self.assertEqual(total_count, 3)
            self.assertEqual(selected, [{"c": 3}])

    def test_agent_system_specific_system_add_takes_precedence_over_default(self):
        task_id = str((self.root / "task_system_add").resolve())
        task_dir = Path(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "system-add.md").write_text("DEFAULT_SYSTEM_ADD", encoding="utf-8")
        (task_dir / "system-add.OpenCowork.md").write_text("SYSTEM_SCOPE_ADD", encoding="utf-8")
        (task_dir / "system-add.alpha_agent.md").write_text("ALPHA_SYSTEM_ADD", encoding="utf-8")

        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            hierarchy = _DummyHierarchyManager({"history": [], "current": {}, "runtime": {}})
            builder = ContextBuilder(hierarchy, {}, _DummyConfigLoader(), llm_client=None)
            content = builder._build_task_system_add(task_id, "alpha_agent")

        self.assertIn("SYSTEM_SCOPE_ADD", content)
        self.assertNotIn("ALPHA_SYSTEM_ADD", content)
        self.assertNotIn("DEFAULT_SYSTEM_ADD", content)


if __name__ == "__main__":
    unittest.main()
