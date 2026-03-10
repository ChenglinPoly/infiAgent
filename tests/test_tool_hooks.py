#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import tempfile
import unittest
from pathlib import Path

from core.tool_executor import ToolExecutor
from utils.config_loader import ConfigLoader
from utils.user_paths import runtime_env_scope
from core.hierarchy_manager import get_hierarchy_manager


class ToolHooksTests(unittest.TestCase):
    def test_after_hook_triggers_with_result_filter(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            callback_file = temp / "hook_callback.py"
            sink = temp / "events.jsonl"
            callback_file.write_text(
                "\n".join([
                    "import json",
                    f"SINK = {str(sink)!r}",
                    "def on_tool_event(payload):",
                    "    with open(SINK, 'a', encoding='utf-8') as fh:",
                    "        fh.write(json.dumps(payload, ensure_ascii=False) + '\\n')",
                ]),
                encoding="utf-8",
            )

            hooks = [{
                "name": "final-only",
                "when": "after",
                "tool_names": ["final_output"],
                "callback": f"{callback_file}:on_tool_event",
                "result_filters": {"status": "success"},
            }]
            root = temp / "root"
            task_id = str((temp / "task").resolve())
            with runtime_env_scope({
                "MLA_USER_DATA_ROOT": str(root),
                "MLA_TOOL_HOOKS_JSON": json.dumps(hooks, ensure_ascii=False),
            }):
                executor = ToolExecutor(ConfigLoader("OpenCowork"), get_hierarchy_manager(task_id))
                executor.set_agent_context(agent_id="agent_demo", agent_name="alpha_agent")
                result = executor.execute("final_output", {"status": "success", "output": "ok"}, task_id)

            self.assertEqual(result["status"], "success")
            lines = sink.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["tool_name"], "final_output")
            self.assertEqual(payload["when"], "after")
            self.assertEqual(payload["result"]["output"], "ok")
            self.assertEqual(payload["agent_id"], "agent_demo")
            self.assertEqual(payload["agent_level"], 0)


if __name__ == "__main__":
    unittest.main()
