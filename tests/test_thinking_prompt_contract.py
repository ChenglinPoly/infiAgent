#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from unittest.mock import patch

from services.llm_client import LLMResponse
from services.thinking_agent import ThinkingAgent


class _StubThinkingLLMClient:
    def resolve_model(self, category, preferred_model=None):
        return preferred_model or "demo-model"

    def resolve_tool_choice(self, category, model):
        return "none"

    def chat(self, **kwargs):
        return LLMResponse(
            status="success",
            output="ok",
            tool_calls=[],
            model="demo-model",
            finish_reason="stop",
        )


class ThinkingPromptContractTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.original_user_data_root = os.environ.get("MLA_USER_DATA_ROOT")
        os.environ["MLA_USER_DATA_ROOT"] = self.temp_dir.name
        self.addCleanup(self._restore_user_data_root)

    def _restore_user_data_root(self):
        if self.original_user_data_root is None:
            os.environ.pop("MLA_USER_DATA_ROOT", None)
        else:
            os.environ["MLA_USER_DATA_ROOT"] = self.original_user_data_root

    def test_thinking_system_prompt_requires_inner_content_only(self):
        with patch("services.thinking_agent.SimpleLLMClient", return_value=_StubThinkingLLMClient()):
            agent = ThinkingAgent()
        prompt = agent.system_prompt

        self.assertIn("写入<当前进度思考>标签内部的正文内容", prompt)
        self.assertIn("不要输出<当前进度思考>外层标签本身", prompt)
        self.assertNotIn("首次进行构造，你的输出不需要包含<当前进度思考>标签", prompt)

    def test_thinking_prompt_uses_canonical_action_window_from_legacy_env(self):
        with patch.dict(os.environ, {
            "MLA_ACTION_WINDOW_STEPS": "",
            "MLA_THINKING_STEPS": "2",
            "MLA_THINKING_INTERVAL": "2",
        }, clear=False):
            with patch("services.thinking_agent.SimpleLLMClient", return_value=_StubThinkingLLMClient()):
                agent = ThinkingAgent()

        self.assertIn("2步后", agent.system_prompt)
        self.assertNotIn("30步后", agent.system_prompt)

    def test_initial_analysis_request_requires_inner_content_only(self):
        with patch("services.thinking_agent.SimpleLLMClient", return_value=_StubThinkingLLMClient()):
            agent = ThinkingAgent()
        captured = {}

        def fake_chat(**kwargs):
            captured["history"] = kwargs["history"]
            return LLMResponse(
                status="success",
                output="ok",
                tool_calls=[],
                model="demo-model",
                finish_reason="stop",
            )

        with patch.object(agent.llm_client, "chat", side_effect=fake_chat):
            agent.analyze_first_thinking_detail(
                task_description="hello",
                agent_system_prompt="dummy prompt",
                available_tools=["file_write"],
                tools_config={},
            )

        history = captured["history"]
        self.assertEqual(len(history), 1)
        request_text = history[0].content
        self.assertIn("只输出标签内部内容", request_text)
        self.assertIn("不要输出<当前进度思考>外层标签", request_text)
        self.assertNotIn("只需要输出<当前进度思考>内的内容即可", request_text)


if __name__ == "__main__":
    unittest.main()
