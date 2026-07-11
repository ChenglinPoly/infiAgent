#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

import yaml

from infiagent import infiagent
from utils.llm_config_builder import build_llm_config_from_profiles


class LlmConfigBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()

    def test_unified_profile_builds_all_model_slots(self):
        config = build_llm_config_from_profiles(
            {
                "mode": "unified",
                "unified": {
                    "provider": "openai_official",
                    "model": "gpt-4.1-mini",
                    "api_key": "sk-demo",
                },
                "temperature": 0.2,
            }
        )

        self.assertEqual(config["temperature"], 0.2)
        self.assertEqual(config["models"][0]["name"], "openai/gpt-4.1-mini")
        self.assertEqual(config["figure_models"][0]["name"], "openai/gpt-4.1-mini")
        self.assertEqual(config["compressor_models"][0]["name"], "openai/gpt-4.1-mini")
        self.assertEqual(config["read_figure_models"][0]["name"], "openai/gpt-4.1-mini")
        self.assertEqual(config["thinking_models"][0]["name"], "openai/gpt-4.1-mini")

    def test_split_profiles_support_local_model_without_api_key(self):
        config = build_llm_config_from_profiles(
            {
                "mode": "split",
                "main": {
                    "provider": "local_openai_compatible",
                    "model": "qwen2.5:14b",
                    "base_url": "http://localhost:11434/v1",
                    "api_key": "",
                },
                "thinking": {
                    "provider": "google_official",
                    "model": "gemini-2.5-flash",
                    "api_key": "google-demo",
                },
            }
        )

        self.assertEqual(config["models"][0]["name"], "openai/qwen2.5:14b")
        self.assertEqual(config["models"][0]["base_url"], "http://localhost:11434/v1")
        self.assertNotIn("api_key", config["models"][0])
        self.assertEqual(config["thinking_models"][0]["name"], "google/gemini-2.5-flash")

    def test_sdk_materializes_model_profiles_to_runtime_yaml(self):
        agent = infiagent(
            user_data_root=str(self.root),
            model_profiles={
                "mode": "unified",
                "unified": {
                    "provider": "openrouter",
                    "model": "openai/gpt-4.1-mini",
                    "api_key": "demo-key-not-real",
                    "base_url": "https://openrouter.ai/api/v1",
                },
            },
        )

        self.assertTrue(agent.llm_config_path)
        cfg_path = Path(agent.llm_config_path)
        self.assertTrue(cfg_path.exists())

        parsed = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(parsed["models"][0]["name"], "openai/gpt-4.1-mini")
        self.assertEqual(parsed["models"][0]["api_key"], "demo-key-not-real")
        self.assertEqual(parsed["models"][0]["base_url"], "https://openrouter.ai/api/v1")


if __name__ == "__main__":
    unittest.main()
