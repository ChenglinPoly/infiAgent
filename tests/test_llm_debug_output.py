#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import tempfile
import unittest
from pathlib import Path

from services.llm_client import SimpleLLMClient
from utils.user_paths import get_task_file_prefix


class LlmDebugOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_user_data_root = os.environ.get("MLA_USER_DATA_ROOT")
        os.environ["MLA_USER_DATA_ROOT"] = self.temp_dir.name
        self.addCleanup(self._restore_user_data_root)

        llm_config_path = Path(__file__).parent / "llm_config_dummy.yaml"
        self.client = SimpleLLMClient(llm_config_path=str(llm_config_path))

    def _restore_user_data_root(self):
        if self.original_user_data_root is None:
            os.environ.pop("MLA_USER_DATA_ROOT", None)
        else:
            os.environ["MLA_USER_DATA_ROOT"] = self.original_user_data_root

    def test_task_scoped_debug_records_append_to_conversation_jsonl(self):
        task_id = str(Path(self.temp_dir.name) / "workspace" / "demo-task")
        messages = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
        ]

        self.client._append_debug_record(
            messages=messages,
            model="openai/gpt-4o-mini",
            debug_task_id=task_id,
            debug_label="execution",
            tool_choice="required",
            tool_count=1,
            emit_tokens="token",
        )
        self.client._append_debug_record(
            messages=messages,
            model="openai/gpt-4o-mini",
            debug_task_id=task_id,
            debug_label="thinking",
            tool_choice="none",
            tool_count=0,
            emit_tokens="thinking",
        )

        debug_file = Path(self.temp_dir.name) / "conversations" / f"{get_task_file_prefix(task_id)}_llm_debug.jsonl"
        self.assertTrue(debug_file.exists())

        lines = debug_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)

        first_record = json.loads(lines[0])
        second_record = json.loads(lines[1])
        self.assertEqual(first_record["task_id"], task_id)
        self.assertEqual(first_record["debug_label"], "execution")
        self.assertEqual(second_record["debug_label"], "thinking")

    def test_debug_records_without_task_fall_back_to_runtime_debug_dir(self):
        self.client._append_debug_record(
            messages=[{"role": "user", "content": "hello"}],
            model="openai/gpt-4o-mini",
            debug_label="context_builder",
        )

        debug_file = Path(self.temp_dir.name) / "runtime" / "debug" / "llm_debug.jsonl"
        self.assertTrue(debug_file.exists())

        lines = debug_file.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertIsNone(record["task_id"])
        self.assertEqual(record["debug_label"], "context_builder")


if __name__ == "__main__":
    unittest.main()
