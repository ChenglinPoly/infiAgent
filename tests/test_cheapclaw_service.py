#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib.util
import json
import os
import shutil
import signal
import sys
import tempfile
import time
import unittest
import warnings
from datetime import datetime
from pathlib import Path
from unittest import mock

from core.hierarchy_manager import get_hierarchy_manager
from utils.config_loader import ConfigLoader
from tool_server_lite.registry import reload_runtime_registry
from utils.user_paths import runtime_env_scope

MODULE_PATH = Path(__file__).resolve().parent.parent / "apps" / "cheapclaw" / "cheapclaw_service.py"
SPEC = importlib.util.spec_from_file_location("cheapclaw_service", MODULE_PATH)
CHEAPCLAW = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = CHEAPCLAW
SPEC.loader.exec_module(CHEAPCLAW)

CheapClawPanelStore = CHEAPCLAW.CheapClawPanelStore
CheapClawPaths = CHEAPCLAW.CheapClawPaths
CheapClawService = CHEAPCLAW.CheapClawService
TelegramAdapter = CHEAPCLAW.TelegramAdapter
HELPER_SPEC = importlib.util.spec_from_file_location(
    "cheapclaw_list_conversation_tasks_tool",
    Path(__file__).resolve().parent.parent / "apps" / "cheapclaw" / "tools_library" / "cheapclaw_list_conversation_tasks" / "cheapclaw_list_conversation_tasks.py",
)
HELPER_MODULE = importlib.util.module_from_spec(HELPER_SPEC)
assert HELPER_SPEC and HELPER_SPEC.loader
sys.modules[HELPER_SPEC.name] = HELPER_MODULE
HELPER_SPEC.loader.exec_module(HELPER_MODULE)
CheapClawListConversationTasksTool = HELPER_MODULE.CheapClawListConversationTasksTool


class CheapClawServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name).resolve()
        self.llm_config = str((Path(__file__).resolve().parent / "llm_config_dummy.yaml").resolve())

    def test_panel_store_bootstraps_layout(self):
        paths = CheapClawPaths.from_user_data_root(self.root)
        store = CheapClawPanelStore(paths)
        panel = store.load_panel()

        self.assertTrue(paths.panel_path.exists())
        self.assertTrue(paths.plans_path.exists())
        self.assertEqual(panel["service_state"]["main_agent_task_id"], str(paths.supervisor_task_id))
        self.assertEqual(panel["channels"], {})

    def test_record_social_message_updates_panel_and_history(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        service.record_social_message(
            channel="telegram",
            conversation_id="group_123",
            conversation_type="group",
            display_name="ML Group",
            sender_id="u1",
            sender_name="alice",
            message_text="@bot continue yesterday task",
            is_mention_to_bot=True,
        )

        panel = service.panel_store.load_panel()
        conv = panel["channels"]["telegram"]["conversations"]["group_123"]
        self.assertTrue(conv["dirty"])
        self.assertEqual(conv["unread_event_count"], 1)
        self.assertEqual(len(conv["messages"]), 1)
        history_path = Path(conv["message_history_path"])
        self.assertTrue(history_path.exists())
        self.assertTrue(Path(conv["context_summary_path"]).exists())
        lines = history_path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["text"], "@bot continue yesterday task")

    def test_supervisor_input_contains_latest_user_text(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        service.record_social_message(
            channel="telegram",
            conversation_id="group_input",
            conversation_type="person",
            sender_id="u1",
            sender_name="alice",
            message_text="请把默认输出改成前 20 个",
            message_id="m20",
            is_mention_to_bot=True,
        )
        payload = json.loads(service._build_supervisor_input("dirty_panel"))
        conv = payload["dirty_conversations"][0]
        self.assertEqual(conv["latest_user_message"]["text"], "请把默认输出改成前 20 个")
        self.assertEqual(conv["pending_user_messages"][0]["message_id"], "m20")
        self.assertNotIn("panel_path", payload)
        self.assertNotIn("plans_path", payload)
        self.assertNotIn("message_history_path", conv)
        self.assertIn("context_excerpt", conv)
        self.assertIn("lookup_hints", conv)

    def test_supervisor_input_is_event_focused_not_path_heavy(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        task_id = str((self.root / "cheapclaw" / "tasks" / "telegram" / "conv_focus" / "task_one").resolve())
        def seed_conversation(panel):
            conv = CHEAPCLAW.ensure_conversation(panel, channel="telegram", conversation_id="conv_focus", conversation_type="group")
            conv["messages"] = [{
                "message_id": "m1",
                "direction": "inbound",
                "timestamp": "2026-03-10T12:00:00+08:00",
                "text": "@bot 帮我继续刚才那个任务",
            }]
            conv["pending_events"] = [{
                "type": "social_message",
                "message_id": "m1",
                "timestamp": "2026-03-10T12:00:00+08:00",
            }]
            conv["dirty"] = True
            conv["latest_user_message_at"] = "2026-03-10T12:00:00+08:00"
            panel.setdefault("service_state", {})["main_agent_dirty"] = True
            return panel

        service.panel_store.mutate(seed_conversation)
        def add_pending_event(panel):
            conv = panel["channels"]["telegram"]["conversations"]["conv_focus"]
            conv["linked_tasks"] = [{
                "task_id": task_id,
                "agent_system": "CheapClawWorkerGeneral",
                "agent_name": "worker_agent",
                "status": "idle",
                "last_final_output": "任务已完成初稿，请根据用户反馈继续修改。",
                "last_final_output_at": "2026-03-10T12:00:00+08:00",
                "share_context_path": "/tmp/share.json",
                "log_path": "/tmp/task.log",
                "watchdog_suspected_state": "healthy",
            }]
            conv["pending_events"].append({
                "type": "task_completed",
                "task_id": task_id,
                "timestamp": "2026-03-10T12:01:00+08:00",
            })
            return panel

        service.panel_store.mutate(add_pending_event)
        payload = json.loads(service._build_supervisor_input("dirty_panel"))
        conv = payload["dirty_conversations"][0]
        self.assertIn("pending_events", conv)
        self.assertIn("context_excerpt", conv)
        self.assertIn(task_id, conv["context_excerpt"])
        self.assertNotIn("linked_tasks", conv)
        self.assertNotIn("message_task_bindings", conv)
        self.assertNotIn("relevant_tasks", conv)

    def test_compute_next_scheduled_run_supports_daily_and_weekly(self):
        now = datetime.fromisoformat("2026-03-10T07:30:00+08:00")
        daily = CHEAPCLAW.compute_next_scheduled_run(
            schedule_type="daily",
            time_of_day="08:00",
            now=now,
        )
        weekly = CHEAPCLAW.compute_next_scheduled_run(
            schedule_type="weekly",
            time_of_day="08:00",
            days_of_week=["wed"],
            now=now,
        )
        self.assertEqual(daily, "2026-03-10T08:00:00+08:00")
        self.assertEqual(weekly, "2026-03-11T08:00:00+08:00")

    def test_message_ids_can_be_bound_to_task(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        service.record_social_message(
            channel="telegram",
            conversation_id="group_bind",
            conversation_type="group",
            sender_id="u1",
            sender_name="alice",
            message_text="@bot continue report",
            message_id="m1",
            is_mention_to_bot=True,
        )
        task_id = str((self.root / "task_bind").resolve())
        service.add_task_message(
            task_id=task_id,
            message="continue the same report",
            source="user",
            channel="telegram",
            conversation_id="group_bind",
            source_message_ids=["m1"],
        )
        panel = service.panel_store.load_panel()
        conv = panel["channels"]["telegram"]["conversations"]["group_bind"]
        bindings = conv["message_task_bindings"]
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0]["message_id"], "m1")
        self.assertEqual(bindings[0]["task_id"], task_id)

    def test_sdk_runtime_introspection_is_public(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        runtime = service.describe_runtime()
        systems = service.list_agent_systems()

        self.assertEqual(runtime["user_data_root"], str(self.root))
        self.assertFalse(runtime["seed_builtin_resources"])
        self.assertTrue(any(item["name"] == "CheapClawSupervisor" for item in systems["agent_systems"]))
        self.assertTrue(any(item["name"] == "CheapClawWorkerGeneral" for item in systems["agent_systems"]))
        self.assertTrue(any("agent_names" in item for item in systems["agent_systems"]))

    def test_send_file_tool_queues_attachment(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        sample = self.root / "sample.txt"
        sample.write_text("cheapclaw file test", encoding="utf-8")

        tool_path = Path(__file__).resolve().parent.parent / "apps" / "cheapclaw" / "tools_library" / "cheapclaw_send_file" / "cheapclaw_send_file.py"
        spec = importlib.util.spec_from_file_location("cheapclaw_send_file_tool", tool_path)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        tool = module.CheapClawSendFileTool()

        from utils.user_paths import runtime_env_scope

        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            result = tool.execute("", {
                "channel": "telegram",
                "conversation_id": "c1",
                "local_path": str(sample),
                "message": "file ready",
            })

        self.assertEqual(result["status"], "success")
        payload = json.loads((self.root / "cheapclaw" / "outbox" / f"{result['event_id']}.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["channel"], "telegram")
        self.assertEqual(payload["attachments"][0]["local_path"], str(sample))

    def test_reconcile_task_statuses_updates_panel_from_share_history(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        task_id = str((self.root / "cheapclaw" / "tasks" / "telegram" / "conv_status" / "fib_task").resolve())
        with service._runtime_scope():
            manager = get_hierarchy_manager(task_id)
            context = manager._load_context()
            context["history"] = [{
                "instructions": [],
                "hierarchy": {"worker_agent_demo": {"parent": None, "children": [], "level": 0}},
                "agents_status": {
                    "worker_agent_demo": {
                        "agent_name": "worker_agent",
                        "status": "completed",
                        "final_output": "task finished",
                        "end_time": "2026-03-10T12:00:00+08:00",
                    }
                },
                "start_time": "2026-03-10T11:58:00+08:00",
                "completion_time": "2026-03-10T12:00:00+08:00",
            }]
            manager._save_context(context)
            service.panel_store.mutate(lambda panel: CHEAPCLAW.ensure_conversation(panel, channel="telegram", conversation_id="conv_status"))
            CHEAPCLAW.update_conversation_task("telegram", "conv_status", task_id, {
                "status": "running",
                "last_final_output": "",
                "last_final_output_at": "",
            }, mark_dirty=False)

        observations = service.reconcile_task_statuses()
        self.assertTrue(any(item["task_id"] == task_id for item in observations))
        panel = service.panel_store.load_panel()
        conv = panel["channels"]["telegram"]["conversations"]["conv_status"]
        task_view = next(item for item in conv["linked_tasks"] if item["task_id"] == task_id)
        self.assertEqual(task_view["status"], "idle")
        self.assertEqual(task_view["last_final_output"], "task finished")
        self.assertEqual(task_view["watchdog_suspected_state"], "healthy")
        self.assertTrue(any(item["type"] == "task_completed" for item in conv["pending_events"]))
        self.assertTrue(conv["dirty"])

    def test_telegram_group_message_detects_mention_entity(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        adapter = TelegramAdapter({"bot_token": "dummy"}, service)
        adapter._me_cache = {"username": "consine_15_bot", "id": 123456}
        message = {
            "text": "@consine_15_bot help me",
            "entities": [{"type": "mention", "offset": 0, "length": 15}],
        }
        self.assertTrue(adapter._message_mentions_bot(message, message["text"], True))

    def test_telegram_group_message_detects_reply_to_bot(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        adapter = TelegramAdapter({"bot_token": "dummy"}, service)
        adapter._me_cache = {"username": "consine_15_bot", "id": 123456}
        message = {
            "text": "continue that",
            "reply_to_message": {"from": {"id": 123456, "username": "consine_15_bot", "is_bot": True}},
        }
        self.assertTrue(adapter._message_mentions_bot(message, message["text"], True))

    def test_telegram_poll_events_accepts_supergroup_mention(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        adapter = TelegramAdapter({"bot_token": "dummy"}, service)
        adapter._me_cache = {"username": "consine_15_bot", "id": 123456}
        with mock.patch.object(adapter, "_request", return_value={
            "ok": True,
            "result": [{
                "update_id": 77,
                "message": {
                    "message_id": 9,
                    "date": int(time.time()),
                    "text": "@consine_15_bot do this",
                    "entities": [{"type": "mention", "offset": 0, "length": 15}],
                    "chat": {"id": -10001, "type": "supergroup", "title": "Ops Group"},
                    "from": {"id": 42, "first_name": "Alice"},
                },
            }],
        }):
            items = adapter.poll_events()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["conversation_type"], "group")
        self.assertTrue(items[0]["is_mention_to_bot"])

    def test_bootstrap_installs_agent_systems_tools_and_skill(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        result = service.bootstrap_assets(force=True)

        self.assertEqual(result["status"], "success")
        self.assertTrue((self.root / "agent_library" / "CheapClawSupervisor" / "level_3_agents.yaml").exists())
        self.assertTrue((self.root / "agent_library" / "CheapClawWorkerGeneral" / "level_3_agents.yaml").exists())
        self.assertTrue((Path(service.describe_runtime()["skills_dir"]) / "cheapclaw-watchdog" / "SKILL.md").exists())
        self.assertTrue((Path(service.describe_runtime()["skills_dir"]) / "find-skills" / "SKILL.md").exists())
        self.assertTrue(Path(result["tools_dir"]).joinpath("cheapclaw_read_panel", "cheapclaw_read_panel.py").exists())

        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            loader = ConfigLoader("CheapClawSupervisor")
            self.assertIn("cheapclaw_start_task", loader.all_tools)
            self.assertIn("cheapclaw_send_file", loader.all_tools)
            self.assertNotIn("human_in_loop", loader.all_tools)
            self.assertIn("supervisor_agent", loader.all_tools)
            worker_loader = ConfigLoader("CheapClawWorkerGeneral")
            self.assertIn("cheapclaw_reveal_skills", worker_loader.all_tools)
            self.assertIn("worker_agent", worker_loader.all_tools)
            self.assertNotIn("human_in_loop", worker_loader.all_tools)

    def test_bootstrap_removes_bundled_systems_even_without_force(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        agent_root = self.root / "agent_library"
        (agent_root / "OpenCowork").mkdir(parents=True, exist_ok=True)
        (agent_root / "Researcher").mkdir(parents=True, exist_ok=True)

        service.bootstrap_assets(force=False)

        self.assertFalse((agent_root / "OpenCowork").exists())
        self.assertFalse((agent_root / "Researcher").exists())
        self.assertTrue((agent_root / "CheapClawSupervisor").exists())
        self.assertTrue((agent_root / "CheapClawWorkerGeneral").exists())

    def test_start_task_rejects_supervisor_system(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        result = service.start_task(
            channel="telegram",
            conversation_id="self_loop",
            task_name="bad",
            user_input="should fail",
            agent_system="CheapClawSupervisor",
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("不能调用本身", result["error"])

    def test_start_task_uses_default_exposed_skills_and_dispatch_timestamp(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            result = service.start_task(
                channel="telegram",
                conversation_id="skill_defaults",
                conversation_type="person",
                task_name="default-skill-worker",
                user_input="same input baseline",
                force_new=True,
            )
        self.assertEqual(result["status"], "success")
        overlay = result.get("overlay_skills") or {}
        revealed = overlay.get("revealed_skills") or []
        self.assertIn("docx", revealed)
        self.assertIn("find-skills", revealed)
        self.assertIn("pptx", revealed)
        self.assertIn("xlsx", revealed)

        pid = result.get("pid")
        self.assertIsInstance(pid, int)
        time.sleep(0.5)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def test_runtime_registry_loads_cheapclaw_custom_tools_from_dynamic_tools_dir(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        runtime = service.describe_runtime()
        with runtime_env_scope({
            "MLA_USER_DATA_ROOT": str(self.root),
            "MLA_TOOLS_LIBRARY_DIR": runtime["tools_dir"],
        }):
            registry, metadata, failures = reload_runtime_registry()
        self.assertIn("cheapclaw_read_panel", registry)
        self.assertIn("cheapclaw_start_task", registry)
        self.assertEqual(metadata["cheapclaw_start_task"]["source"], "custom")
        self.assertFalse(any(item.get("name") == "cheapclaw_start_task" for item in failures))

    def test_build_task_skills_overlay_creates_manifest(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        skills = service.list_global_skills()["skills"]
        self.assertTrue(skills)
        selected = skills[0]["name"]

        result = service.build_task_skills_overlay(
            task_id=str((self.root / "tasks" / "demo_task").resolve()),
            exposed_skills=[selected],
        )
        overlay_root = Path(result["overlay_root"])

        self.assertTrue((overlay_root / "manifest.json").exists())
        self.assertEqual(result["revealed_skills"], [selected])
        self.assertTrue((overlay_root / selected).exists())

    def test_update_task_preferences_persists_default_skills_and_mcp(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            result = service.start_task(
                channel="telegram",
                conversation_id="prefs_group",
                conversation_type="group",
                display_name="Prefs Group",
                task_name="prefs-worker",
                user_input="background smoke test",
                force_new=True,
            )
        task_id = result["task_id"]
        updated = service.update_task_preferences(
            task_id=task_id,
            default_exposed_skills=["docx", "find-skills"],
            mcp_servers=[{"name": "github", "transport": "streamable_http", "url": "https://example.com/mcp"}],
        )
        self.assertEqual(updated["status"], "success")
        self.assertEqual(updated["default_exposed_skills"], ["docx", "find-skills"])
        self.assertEqual(updated["mcp_servers"][0]["name"], "github")
        panel = service.panel_store.load_panel()
        task_view = next(item for item in panel["channels"]["telegram"]["conversations"]["prefs_group"]["linked_tasks"] if item["task_id"] == task_id)
        self.assertEqual(task_view["default_exposed_skills"], ["docx", "find-skills"])
        self.assertEqual(task_view["mcp_servers"][0]["name"], "github")

        pid = result.get("pid")
        self.assertIsInstance(pid, int)
        time.sleep(0.5)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def test_start_task_binds_panel_entry(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            result = service.start_task(
                channel="telegram",
                conversation_id="group_456",
                conversation_type="group",
                display_name="Ops Group",
                task_name="ops-summary",
                user_input="background smoke test",
                force_new=True,
            )

        self.assertEqual(result["status"], "success")
        panel = service.panel_store.load_panel()
        conv = panel["channels"]["telegram"]["conversations"]["group_456"]
        self.assertEqual(len(conv["linked_tasks"]), 1)
        task_view = conv["linked_tasks"][0]
        self.assertEqual(task_view["task_id"], result["task_id"])
        self.assertTrue(task_view["log_path"].startswith(str(self.root / "runtime" / "launched_tasks")))
        self.assertTrue(Path(task_view["share_context_path"]).name.endswith("_share_context.json"))

        pid = result.get("pid")
        self.assertIsInstance(pid, int)
        time.sleep(0.5)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        else:
            for _ in range(20):
                try:
                    waited_pid, _ = os.waitpid(pid, os.WNOHANG)
                except ChildProcessError:
                    break
                if waited_pid == pid:
                    break
                time.sleep(0.1)

    def test_start_task_falls_back_to_valid_worker_agent(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            result = service.start_task(
                channel="telegram",
                conversation_id="group_fallback",
                conversation_type="group",
                display_name="Fallback Group",
                task_name="fallback-worker",
                user_input="background smoke test",
                force_new=True,
                agent_system="CheapClawWorkerGeneral",
                agent_name="nonexistent_worker",
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["agent_name"], "worker_agent")

        pid = result.get("pid")
        self.assertIsInstance(pid, int)
        time.sleep(0.5)
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def test_list_conversation_tasks_returns_recommended_task(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        old_task = str((self.root / "cheapclaw" / "tasks" / "telegram" / "conv" / "old_task").resolve())
        new_task = str((self.root / "cheapclaw" / "tasks" / "telegram" / "conv" / "new_task").resolve())
        service.record_social_message(
            channel="telegram",
            conversation_id="conv",
            conversation_type="person",
            sender_id="u1",
            sender_name="alice",
            message_text="first request",
            message_id="m1",
            is_mention_to_bot=True,
        )
        service.start_task(
            channel="telegram",
            conversation_id="conv",
            conversation_type="person",
            task_id=old_task,
            task_name="old",
            user_input="first job",
            force_new=True,
        )
        service.record_social_message(
            channel="telegram",
            conversation_id="conv",
            conversation_type="person",
            sender_id="u1",
            sender_name="alice",
            message_text="change that result",
            message_id="m2",
            is_mention_to_bot=True,
        )
        service.start_task(
            channel="telegram",
            conversation_id="conv",
            conversation_type="person",
            task_id=new_task,
            task_name="new",
            user_input="second job",
            force_new=True,
            source_message_ids=["m2"],
        )

        from utils.user_paths import runtime_env_scope

        tool = CheapClawListConversationTasksTool()
        with runtime_env_scope({"MLA_USER_DATA_ROOT": str(self.root)}):
            payload = tool.execute("", {"channel": "telegram", "conversation_id": "conv"})
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["recommended_task_id"], new_task)
        self.assertEqual(payload["latest_bound_task_id"], new_task)
        self.assertIn(payload["recommended_action"], {"append_to_running_task", "continue_existing_task"})
        self.assertTrue(payload["heuristic_note"])

    def test_add_task_message_appends_timestamp(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        task_id = str((self.root / "manual_task").resolve())

        result = service.add_task_message(
            task_id=task_id,
            message="keep previous outputs and only extend them",
            source="user",
        )
        self.assertEqual(result["status"], "success")
        snapshot = service.get_task_snapshot(task_id=task_id)
        latest_instruction = snapshot["latest_instruction"]
        self.assertIn("message_appended_at", latest_instruction["instruction"])
        self.assertTrue(snapshot["share_context_path"].startswith(str(self.root / "conversations")))

    def test_reset_task_public_api_clears_current_instructions(self):
        service = CheapClawService(user_data_root=str(self.root), llm_config_path=self.llm_config)
        task_id = str((self.root / "reset_task").resolve())
        service.add_task_message(task_id=task_id, message="first", source="user")
        before = service.get_task_snapshot(task_id=task_id)
        self.assertEqual(before["instruction_count"], 1)

        result = service.reset_task(task_id=task_id, reason="unit-test")
        self.assertEqual(result["status"], "success")

        after = service.get_task_snapshot(task_id=task_id)
        self.assertEqual(after["instruction_count"], 0)
        self.assertEqual(after["history_count"], 1)

    def test_external_copy_can_import_service_module(self):
        external_root = self.root / "external_service"
        external_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MODULE_PATH, external_root / "cheapclaw_service.py")
        shutil.copy2(MODULE_PATH.parent / "tool_runtime_helpers.py", external_root / "tool_runtime_helpers.py")

        spec = importlib.util.spec_from_file_location("external_cheapclaw_service", external_root / "cheapclaw_service.py")
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        self.assertTrue(hasattr(module, "CheapClawService"))
        self.assertTrue(hasattr(module, "CheapClawPaths"))

    def test_external_copy_can_import_custom_tool_module(self):
        external_root = self.root / "external_tool_app"
        tool_dir = external_root / "tools_library" / "cheapclaw_generate_task_id"
        tool_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MODULE_PATH.parent / "tool_runtime_helpers.py", external_root / "tool_runtime_helpers.py")
        shutil.copy2(
            MODULE_PATH.parent / "tools_library" / "cheapclaw_generate_task_id" / "cheapclaw_generate_task_id.py",
            tool_dir / "cheapclaw_generate_task_id.py",
        )

        spec = importlib.util.spec_from_file_location(
            "external_cheapclaw_generate_task_id",
            tool_dir / "cheapclaw_generate_task_id.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        self.assertTrue(hasattr(module, "CheapClawGenerateTaskIdTool"))


if __name__ == "__main__":
    unittest.main()
