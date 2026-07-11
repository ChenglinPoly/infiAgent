#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path
from utils.agent_system_requirements import (
    _find_requirements_file,
    ensure_agent_system_requirements_ready,
)
from utils.config_loader import ConfigLoader
from utils.user_paths import runtime_env_scope


class AgentSystemRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)

    def test_find_requirements_prefers_agent_system_dir(self):
        system_dir = self.base / "agent_library" / "DemoSystem"
        tools_dir = self.base / "tools_library"
        system_dir.mkdir(parents=True, exist_ok=True)
        tools_dir.mkdir(parents=True, exist_ok=True)
        (system_dir / "requirements.txt").write_text("package-a\n", encoding="utf-8")
        (tools_dir / "requirements.txt").write_text("package-b\n", encoding="utf-8")

        found = _find_requirements_file("DemoSystem", system_dir, tools_dir)
        self.assertEqual(found.resolve(), (system_dir / "requirements.txt").resolve())

    def test_find_requirements_falls_back_to_tools_root(self):
        system_dir = self.base / "agent_library" / "DemoSystem"
        tools_dir = self.base / "tools_library"
        system_dir.mkdir(parents=True, exist_ok=True)
        tools_dir.mkdir(parents=True, exist_ok=True)
        (tools_dir / "requirements.txt").write_text("package-b\n", encoding="utf-8")

        found = _find_requirements_file("DemoSystem", system_dir, tools_dir)
        self.assertEqual(found.resolve(), (tools_dir / "requirements.txt").resolve())

    def test_ensure_requirements_returns_disabled_without_file(self):
        system_dir = self.base / "agent_library" / "DemoSystem"
        system_dir.mkdir(parents=True, exist_ok=True)
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.base / "user_root")}):
            result = ensure_agent_system_requirements_ready(
                agent_system_name="DemoSystem",
                agent_system_dir=system_dir,
                tools_root=self.base / "tools_library",
            )
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(result["requirements_path"], "")

    def test_ensure_requirements_does_not_install_or_activate_site_packages(self):
        system_dir = self.base / "agent_library" / "DemoSystem"
        tools_dir = self.base / "tools_library"
        user_root = self.base / "user_root"
        system_dir.mkdir(parents=True, exist_ok=True)
        tools_dir.mkdir(parents=True, exist_ok=True)
        req_path = system_dir / "requirements.txt"
        req_path.write_text("demo-package==1.0.0\n", encoding="utf-8")

        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(user_root)}):
            result = ensure_agent_system_requirements_ready(
                agent_system_name="DemoSystem",
                agent_system_dir=system_dir,
                tools_root=tools_dir,
            )

        self.assertEqual(result["status"], "disabled")
        self.assertEqual(Path(result["requirements_path"]).resolve(), req_path.resolve())
        self.assertFalse((user_root / "runtime" / "agent_system_envs" / "DemoSystem").exists())

    def test_config_loader_does_not_trigger_agent_system_requirements(self):
        root = self.base / "user_root"
        system_dir = root / "agent_library" / "DemoSystem"
        system_dir.mkdir(parents=True, exist_ok=True)
        (system_dir / "general_prompts.yaml").write_text("general_prompts: {}\n", encoding="utf-8")
        (system_dir / "level_0_tools.yaml").write_text("tools: {}\n", encoding="utf-8")
        (system_dir / "requirements.txt").write_text("demo-package==1.0.0\n", encoding="utf-8")

        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(root)}):
            loader = ConfigLoader("DemoSystem", agent_library_root=str(root))

        self.assertEqual(loader.agent_system_name, "DemoSystem")
        self.assertEqual(loader.agent_system_requirements_status["status"], "disabled")
        self.assertFalse((root / "runtime" / "agent_system_envs" / "DemoSystem").exists())


if __name__ == "__main__":
    unittest.main()
