#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

from tool_server_lite.registry import get_runtime_registry, get_runtime_registry_failures, reload_runtime_registry
from utils.user_paths import runtime_env_scope


class CustomToolHelperImportsTests(unittest.TestCase):
    def test_multiple_tools_can_import_shared_env_module_from_tools_library_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "user_root"
            tools_root = root / "tools_library"
            tools_root.mkdir(parents=True, exist_ok=True)

            (tools_root / "env.py").write_text(
                "\n".join([
                    "VALUE = 'shared-env-value'",
                    "def build_message(name):",
                    "    return f'{name}:{VALUE}'",
                ]),
                encoding="utf-8",
            )

            for tool_name in ("tool_one", "tool_two"):
                tool_dir = tools_root / tool_name
                tool_dir.mkdir(parents=True, exist_ok=True)
                (tool_dir / f"{tool_name}.py").write_text(
                    "\n".join([
                        "import env",
                        "from infiagent import BaseTool",
                        "",
                        f"class {''.join(part.title() for part in tool_name.split('_'))}(BaseTool):",
                        f"    name = '{tool_name}'",
                        "    def execute(self, task_id, parameters):",
                        f"        return {{'status': 'success', 'output': env.build_message('{tool_name}'), 'error': ''}}",
                    ]),
                    encoding="utf-8",
                )

            with runtime_env_scope({"MLA_USER_DATA_ROOT": str(root)}):
                registry, _, failures = reload_runtime_registry()

            self.assertIn("tool_one", registry)
            self.assertIn("tool_two", registry)
            self.assertFalse(any(item.get("name") in {"tool_one", "tool_two"} for item in failures))
            self.assertEqual(registry["tool_one"].execute("task", {})["output"], "tool_one:shared-env-value")
            self.assertEqual(registry["tool_two"].execute("task", {})["output"], "tool_two:shared-env-value")

    def test_tool_directory_can_contain_helper_py_files_when_main_file_matches_directory_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "user_root"
            tools_root = root / "tools_library"
            tool_dir = tools_root / "helper_demo_tool"
            tool_dir.mkdir(parents=True, exist_ok=True)

            (tool_dir / "helper.py").write_text(
                "VALUE = 'helper-ok'\n",
                encoding="utf-8",
            )
            (tool_dir / "helper_demo_tool.py").write_text(
                "\n".join([
                    "import helper",
                    "from infiagent import BaseTool",
                    "",
                    "class HelperDemoTool(BaseTool):",
                    "    name = 'helper_demo_tool'",
                    "    def execute(self, task_id, parameters):",
                    "        return {'status': 'success', 'output': helper.VALUE, 'error': ''}",
                ]),
                encoding="utf-8",
            )

            with runtime_env_scope({"MLA_USER_DATA_ROOT": str(root)}):
                registry = get_runtime_registry(force_reload=True)
                failures = get_runtime_registry_failures(force_reload=False)

            self.assertIn("helper_demo_tool", registry)
            self.assertFalse(any(item.get("name") == "helper_demo_tool" for item in failures))
            self.assertEqual(registry["helper_demo_tool"].execute("task", {})["output"], "helper-ok")


if __name__ == "__main__":
    unittest.main()
