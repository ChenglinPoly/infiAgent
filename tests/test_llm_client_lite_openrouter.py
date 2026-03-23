#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import unittest

from tool_server_lite.llm_client_lite import LLMClientLite


class LLMClientLiteOpenRouterTests(unittest.TestCase):
    def test_openrouter_model_name_is_normalized(self):
        self.assertEqual(
            LLMClientLite._normalize_openrouter_model_name(
                "google/gemini-3-pro-image-preview",
                "https://openrouter.ai/api/v1",
            ),
            "openrouter/google/gemini-3-pro-image-preview",
        )

    def test_prefixed_openrouter_model_name_is_left_unchanged(self):
        self.assertEqual(
            LLMClientLite._normalize_openrouter_model_name(
                "openrouter/google/gemini-3-pro-image-preview",
                "https://openrouter.ai/api/v1",
            ),
            "openrouter/google/gemini-3-pro-image-preview",
        )

    def test_non_openrouter_base_url_does_not_change_model_name(self):
        self.assertEqual(
            LLMClientLite._normalize_openrouter_model_name(
                "google/gemini-3-pro-image-preview",
                "https://generativelanguage.googleapis.com",
            ),
            "google/gemini-3-pro-image-preview",
        )


if __name__ == "__main__":
    unittest.main()
