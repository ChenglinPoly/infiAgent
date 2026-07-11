#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

import yaml

from services.action_compressor import ActionCompressor
from services.llm_client import ChatMessage, SimpleLLMClient
from utils import token_budget
from utils.token_budget import build_request_budget


class _DummyLLMClient:
    max_context_window = 18000
    compressor_multimodal = False

    def resolve_model(self, category="compressor", preferred=None):
        return preferred or "openai/gpt-4o-mini"

    def resolve_tool_choice(self, category="compressor", model=None):
        return "none"


class TokenBudgetingTests(unittest.TestCase):
    def _make_llm_config(self, *, max_context_window=18000, max_tokens=0) -> str:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "llm_config.yaml"
        payload = {
            "temperature": 0,
            "max_tokens": max_tokens,
            "max_context_window": max_context_window,
            "base_url": "http://127.0.0.1:1",
            "api_key": "DUMMY_KEY_FOR_TEST",
            "timeout": 5,
            "stream_timeout": 5,
            "first_chunk_timeout": 5,
            "models": ["openai/gpt-4o-mini"],
            "multimodal": False,
            "compressor_multimodal": False,
        }
        path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return str(path)

    def test_build_request_budget_reserves_output_and_margin(self):
        budget = build_request_budget(
            system_prompt="hello",
            messages=[{"role": "user", "content": "world"}],
            tools_definition=[],
            context_limit=18000,
            max_tokens=None,
            force_exact=False,
        )
        self.assertEqual(budget.context_limit, 18000)
        self.assertGreaterEqual(budget.reserved_output_tokens, 1024)
        self.assertGreaterEqual(budget.safety_margin_tokens, 512)
        self.assertGreater(budget.available_input_tokens, 0)

    def test_token_counting_does_not_download_when_cache_is_missing(self):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        token_budget._ENCODING = None
        token_budget._ENCODING_LOAD_ATTEMPTED = False

        with patch.dict(
            os.environ,
            {
                "TIKTOKEN_CACHE_DIR": str(Path(temp_dir.name) / "missing-cache"),
                "MLA_TOKENIZER_ALLOW_DOWNLOAD": "0",
                "MLA_TOKENIZER_DISABLE_TIKTOKEN": "0",
            },
        ):
            with patch("tiktoken.get_encoding", side_effect=AssertionError("unexpected tokenizer download")):
                self.assertGreater(token_budget.count_tokens_text("A" * 10000, force_exact=True), 0)

        token_budget._ENCODING = None
        token_budget._ENCODING_LOAD_ATTEMPTED = False

    def test_action_compressor_constructor_does_not_load_tiktoken(self):
        with patch("tiktoken.get_encoding", side_effect=AssertionError("unexpected tokenizer download")):
            compressor = ActionCompressor(_DummyLLMClient())
        self.assertGreater(compressor.count_tokens("hello world"), 0)

    def test_llm_client_hard_budget_stops_before_completion(self):
        config_path = self._make_llm_config(max_context_window=18000)
        client = SimpleLLMClient(llm_config_path=config_path)
        huge_text = "A" * 200000

        with patch("services.llm_client.completion") as mocked_completion:
            with self.assertRaises(Exception) as ctx:
                client.chat(
                    history=[ChatMessage(role="user", content=huge_text)],
                    model=client.models[0],
                    system_prompt="system prompt",
                    tool_list=[],
                    max_retries=0,
                )
        mocked_completion.assert_not_called()
        self.assertIn("上下文窗口", str(ctx.exception))

    def test_action_budget_counts_assistant_and_reasoning_content(self):
        compressor = ActionCompressor(_DummyLLMClient())
        action_history = [{
            "tool_name": "_react_reflection",
            "arguments": {},
            "result": {"status": "success", "output": "short"},
            "assistant_content": "A" * 4000,
            "reasoning_content": "B" * 4000,
        }]
        stripped_history = [{
            "tool_name": "_react_reflection",
            "arguments": {},
            "result": {"status": "success", "output": "short"},
            "assistant_content": "",
            "reasoning_content": "",
        }]
        xml_only = compressor.count_tokens(compressor._actions_to_xml(stripped_history))
        full_budget = compressor.count_action_context_tokens(action_history)
        self.assertGreater(full_budget, xml_only)

    def test_small_window_no_longer_forces_compression_when_action_is_tiny(self):
        compressor = ActionCompressor(_DummyLLMClient())
        action_history = [{
            "tool_name": "dir_list",
            "arguments": {"path": "."},
            "result": {"status": "success", "output": "ok"},
            "assistant_content": "",
            "reasoning_content": "",
        }]
        result = compressor.compress_if_needed(
            action_history,
            max_context_window=18000,
            thinking="",
            task_input="",
            max_action_tokens=8000,
        )
        self.assertEqual(result, action_history)

    def test_single_action_can_compress_assistant_content(self):
        compressor = ActionCompressor(_DummyLLMClient())
        action_history = [{
            "tool_name": "_react_reflection",
            "arguments": {},
            "result": {"status": "success", "output": "ok"},
            "assistant_content": "X" * 5000,
            "reasoning_content": "",
        }]
        with patch.object(compressor, "_llm_compress_field", return_value="compressed"):
            result = compressor.compress_if_needed(
                action_history,
                max_context_window=18000,
                thinking="",
                task_input="",
                max_action_tokens=512,
            )
        self.assertEqual(result[0]["assistant_content"], "compressed")


if __name__ == "__main__":
    unittest.main()
