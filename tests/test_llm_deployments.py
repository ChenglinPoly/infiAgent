#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多部署路由（缓存亲和 + 故障转移）单元测试。

只测部署选择/冷却/配置兼容层，不发真实网络请求。
"""

import tempfile
import time
import unittest
from pathlib import Path

import yaml

from services.llm_client import SimpleLLMClient
from utils.llm_config_builder import build_model_entry


def _write_config(tmpdir: Path, config: dict) -> str:
    path = tmpdir / "llm_config.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return str(path)


def _deployment_config(api_key_global: str = "") -> dict:
    return {
        "api_key": api_key_global,
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            {
                "name": "deepseek-v4-flash",
                "default": True,
                "deployments": [
                    {"model": "openrouter/deepseek/deepseek-v4-flash", "api_key": "k-or-1"},
                    {"model": "openrouter/deepseek/deepseek-v4-flash", "api_key": "k-or-2"},
                    {
                        "model": "openai/deepseek-v4-flash",
                        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                        "api_key": "k-bl-1",
                    },
                ],
            }
        ],
    }


class LLMDeploymentRoutingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _client(self, config: dict) -> SimpleLLMClient:
        return SimpleLLMClient(llm_config_path=_write_config(self.root, config))

    # ---------- 向后兼容 ----------

    def test_backward_compat_single_key_config(self):
        """老格式（全局 api_key + 纯模型名）完全不受影响。"""
        client = self._client(
            {
                "api_key": "sk-legacy",
                "base_url": "https://openrouter.ai/api/v1",
                "models": ["openrouter/deepseek/deepseek-v4-flash"],
            }
        )
        self.assertIsNone(client._select_deployment("openrouter/deepseek/deepseek-v4-flash"))
        self.assertEqual(client.api_key, "sk-legacy")
        self.assertFalse(client._has_alternative_deployment("openrouter/deepseek/deepseek-v4-flash"))

    def test_deployments_only_config_passes_key_check(self):
        """全局 api_key 为空但 deployments 内有密钥 → 初始化不应报“未配置API密钥”。"""
        client = self._client(_deployment_config(api_key_global=""))
        self.assertEqual(len(client._deployment_entries("deepseek-v4-flash")), 3)

    def test_no_key_anywhere_still_raises(self):
        config = {
            "api_key": "",
            "models": ["openrouter/deepseek/deepseek-v4-flash"],
        }
        with self.assertRaises(ValueError):
            self._client(config)

    # ---------- 选择：缓存亲和 + 故障转移 ----------

    def test_sticky_primary_then_failover_then_recover(self):
        client = self._client(_deployment_config())
        model = "deepseek-v4-flash"

        # 缓存亲和：健康时恒选主部署（连续两次都是 #0）
        first = client._select_deployment(model)
        second = client._select_deployment(model)
        self.assertEqual(first["_index"], 0)
        self.assertEqual(second["_index"], 0)
        self.assertEqual(first["api_key"], "k-or-1")

        # 主部署故障 → 选下一顺位
        client._mark_deployment_failure(first["_id"], "APIConnectionError: connection reset")
        third = client._select_deployment(model)
        self.assertEqual(third["_index"], 1)

        # 第二个也故障 → 跨平台切到百炼部署（带自己的 base_url）
        client._mark_deployment_failure(third["_id"], "RateLimitError: 429 too many requests")
        fourth = client._select_deployment(model)
        self.assertEqual(fourth["_index"], 2)
        self.assertEqual(fourth["base_url"], "https://dashscope.aliyuncs.com/compatible-mode/v1")

        # 冷却到期 → 回到主部署（缓存亲和恢复）
        client._deployment_cooldowns.clear()
        fifth = client._select_deployment(model)
        self.assertEqual(fifth["_index"], 0)

    def test_all_cooling_picks_earliest_expiry(self):
        client = self._client(_deployment_config())
        model = "deepseek-v4-flash"
        entries = client._deployment_entries(model)
        now = time.time()
        client._deployment_cooldowns[entries[0]["_id"]] = now + 300
        client._deployment_cooldowns[entries[1]["_id"]] = now + 60   # 最早到期
        client._deployment_cooldowns[entries[2]["_id"]] = now + 600
        picked = client._select_deployment(model)
        self.assertEqual(picked["_index"], 1)

    def test_auth_failure_gets_long_cooldown(self):
        client = self._client(_deployment_config())
        entries = client._deployment_entries("deepseek-v4-flash")
        client._mark_deployment_failure(entries[0]["_id"], "AuthenticationError: Invalid API key")
        remain = client._deployment_cooldowns[entries[0]["_id"]] - time.time()
        self.assertGreaterEqual(remain, 1700)  # 鉴权类 >= 1800s（留误差余量）

        client._mark_deployment_failure(entries[1]["_id"], "Timeout: request timed out")
        remain2 = client._deployment_cooldowns[entries[1]["_id"]] - time.time()
        self.assertLessEqual(remain2, 130)  # 传输类默认 120s

    def test_has_alternative_deployment(self):
        client = self._client(_deployment_config())
        model = "deepseek-v4-flash"
        self.assertTrue(client._has_alternative_deployment(model))
        # 全部冷却 → 无可用备用（鉴权错误此时应中止重试而不是空转）
        for e in client._deployment_entries(model):
            client._deployment_cooldowns[e["_id"]] = time.time() + 999
        self.assertFalse(client._has_alternative_deployment(model))

    # ---------- 错误分类 ----------

    def test_should_failover_error_classifier(self):
        positive = [
            "litellm.Timeout: Request timed out",
            "RateLimitError: 429 Too Many Requests",
            "APIConnectionError: Connection refused",
            "ServiceUnavailableError: 503",
            "InternalServerError: upstream overloaded",
            "insufficient quota",
            "AuthenticationError: Invalid API key",
        ]
        negative = [
            "tool arguments did not match schema",
            "expected array, but got string",
            "When using `tool_choice`, `tools` must be set",
            "",
        ]
        for msg in positive:
            self.assertTrue(SimpleLLMClient._should_failover_error(msg), msg)
        for msg in negative:
            self.assertFalse(SimpleLLMClient._should_failover_error(msg), msg or "<empty>")

    # ---------- SDK profiles 透传 ----------

    def test_build_model_entry_passes_deployments_through(self):
        entry = build_model_entry(
            {
                "provider": "openrouter",
                "model": "deepseek/deepseek-v4-flash",
                "deployments": [
                    {"model": "openrouter/deepseek/deepseek-v4-flash", "api_key": "k1"},
                    {"model": "openai/deepseek-v4-flash", "base_url": "https://x/v1", "api_key": "k2"},
                ],
            }
        )
        self.assertIsInstance(entry, dict)
        self.assertEqual(len(entry["deployments"]), 2)
        self.assertEqual(entry["deployments"][1]["api_key"], "k2")


if __name__ == "__main__":
    unittest.main()
