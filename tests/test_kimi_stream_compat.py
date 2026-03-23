#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from services.llm_client import SimpleLLMClient, _EmbeddedToolCallStreamState


class KimiStreamCompatTests(unittest.TestCase):
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

    def test_embedded_tool_call_sections_are_hidden_from_visible_text(self):
        state = _EmbeddedToolCallStreamState()
        visible_parts = []
        chunks = [
            "我先检查目录",
            "<|tool_calls_section_begin|><|tool_call_begin|>functions.dir_list:0",
            "<|tool_call_argument_begin|>{\"path\": \".\"}<|tool_call_end|><|tool_calls_section_end|>",
        ]
        for chunk in chunks:
            visible_parts.append(state.feed(chunk))
        tail, raw_markup = state.finish()
        visible_parts.append(tail)

        self.assertEqual("".join(visible_parts), "我先检查目录")

        tool_calls = self.client._parse_embedded_tool_calls(raw_markup)
        self.assertEqual(len(tool_calls), 1)
        self.assertEqual(tool_calls[0].id, "functions.dir_list:0")
        self.assertEqual(tool_calls[0].name, "dir_list")
        self.assertEqual(tool_calls[0].arguments, {"path": "."})

    def test_kimi_raw_marker_stream_falls_back_to_non_stream_and_parses_tool(self):
        model_name = "openrouter/moonshotai/kimi-k2.5"
        calls = []

        def fake_completion(**kwargs):
            calls.append(bool(kwargs.get("stream", False)))
            if kwargs.get("stream", False):
                chunk = SimpleNamespace(
                    model=model_name,
                    choices=[
                        SimpleNamespace(
                            delta=SimpleNamespace(
                                content=(
                                    "我先检查目录"
                                    "<|tool_calls_section_begin|>"
                                    "<|tool_call_begin|>functions.dir_list:0"
                                    "<|tool_call_argument_begin|>{\"path\": \".\"}"
                                ),
                                reasoning_content="",
                                tool_calls=[],
                            ),
                            finish_reason="stop",
                        )
                    ],
                )
                return iter([chunk])

            response = SimpleNamespace(
                model=model_name,
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=(
                                "我先检查目录"
                                "<|tool_calls_section_begin|>"
                                "<|tool_call_begin|>functions.dir_list:0"
                                "<|tool_call_argument_begin|>{\"path\": \".\"}"
                                "<|tool_call_end|><|tool_calls_section_end|>"
                            ),
                            reasoning_content="",
                            tool_calls=[],
                        ),
                        finish_reason="stop",
                    )
                ],
            )
            return response

        with patch("services.llm_client.completion", side_effect=fake_completion):
            with patch.object(self.client, "_append_debug_record", lambda **kwargs: None):
                with patch.object(self.client, "_build_tools_definition", lambda tool_list: [{"type": "function"}]):
                    response = self.client._chat_internal(
                        history=[],
                        model=model_name,
                        system_prompt="system",
                        tool_list=["dir_list"],
                        tool_choice="required",
                        temperature=0,
                        max_tokens=0,
                    )

        self.assertEqual(calls, [True, False])
        self.assertEqual(response.status, "success")
        self.assertEqual(response.output, "我先检查目录")
        self.assertEqual(len(response.tool_calls), 1)
        self.assertEqual(response.tool_calls[0].id, "functions.dir_list:0")
        self.assertEqual(response.tool_calls[0].name, "dir_list")
        self.assertEqual(response.tool_calls[0].arguments, {"path": "."})

if __name__ == "__main__":
    unittest.main()
