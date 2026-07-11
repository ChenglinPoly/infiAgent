#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from deploy.docker.runtime import DeploymentRuntime, load_spec
import deploy.docker.server as deploy_server


app = deploy_server.app
EXAMPLE_ROOT = Path("/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/deploy/infiagent_dev_scaffold/user_root").resolve()


def test_deploy_runtime_loads_example_spec():
    root = EXAMPLE_ROOT
    spec = load_spec(root)
    assert spec.user_root == root.resolve()
    assert spec.tasks_root.exists()
    assert spec.agent_library_root.exists()


def test_deploy_runtime_lists_scaffold_demo_agent():
    root = EXAMPLE_ROOT
    runtime = DeploymentRuntime()
    agents = runtime.list_agents(root, "scaffold_demo")
    assert agents["agent_system"] == "scaffold_demo"
    assert any(item["name"] == "alpha_agent" for item in agents["agents"])


def test_deploy_runtime_lists_scaffold_demo_agents():
    root = Path("/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3/deploy/infiagent_dev_scaffold/user_root")
    runtime = DeploymentRuntime()
    agents = runtime.list_agents(root, "scaffold_demo")
    names = {item["name"] for item in agents["agents"]}
    assert {"alpha_agent", "beta_agent"} <= names


def test_deploy_runtime_lists_skills_from_user_root(tmp_path):
    root = tmp_path / "user_root"
    skill_dir = root / "skills" / "demo_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    runtime = DeploymentRuntime()
    data = runtime.list_skills(root)
    assert data["items"][0]["name"] == "demo_skill"
    assert data["items"][0]["has_skill_md"] is True


def test_deploy_runtime_lists_agent_systems_from_user_root_without_default_system(tmp_path):
    root = tmp_path / "user_root"
    system_dir = root / "agent_library" / "ChatBI"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "general_prompts.yaml").write_text("general_prompts: {}\n", encoding="utf-8")
    (system_dir / "level_0_tools.yaml").write_text("tools: {}\n", encoding="utf-8")
    (system_dir / "level_3_agents.yaml").write_text(
        "tools:\n"
        "  alpha_agent:\n"
        "    type: llm_call_agent\n"
        "    name: alpha_agent\n",
        encoding="utf-8",
    )
    runtime = DeploymentRuntime()
    data = runtime.list_agent_systems(root)
    assert data["status"] == "success"
    assert data["agent_systems"][0]["name"] == "ChatBI"
    assert "alpha_agent" in data["agent_systems"][0]["agent_names"]


def test_deploy_runtime_uploads_are_marked_pending_and_consumed_in_message(tmp_path):
    root = tmp_path / "user_root"
    task_id = "demo_task"
    runtime = DeploymentRuntime()
    upload_result = runtime.upload_files(root, task_id, [("report.txt", b"hello")])
    assert upload_result["pending_uploads"] == [".upload/report.txt"]

    spec = load_spec(root)
    task_path = runtime._resolve_task_path(spec, task_id)
    message = runtime._augment_message_with_pending_uploads(task_path, "analyze this")
    assert "[uses upload files and folders:" in message
    state = runtime.list_uploads(root, task_id)
    assert state["pending"] == []
    assert state["files"] == [".upload/report.txt"]


def test_deploy_server_health_and_runtime():
    original_root = deploy_server.DEFAULT_USER_ROOT
    deploy_server.DEFAULT_USER_ROOT = EXAMPLE_ROOT
    client = TestClient(app)
    try:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        runtime_info = client.get("/api/v1/runtime")
        assert runtime_info.status_code == 200
        payload = runtime_info.json()
        assert "active_user_root" in payload
        assert "spec" in payload
        assert "available_user_roots" not in payload
    finally:
        deploy_server.DEFAULT_USER_ROOT = original_root


def test_deploy_server_agents_endpoint_uses_startup_user_root():
    original_root = deploy_server.DEFAULT_USER_ROOT
    deploy_server.DEFAULT_USER_ROOT = EXAMPLE_ROOT
    client = TestClient(app)
    try:
        payload = client.get("/api/v1/agents", params={"agent_system": "scaffold_demo"}).json()
        assert payload["agent_system"] == "scaffold_demo"
        assert any(item["name"] == "alpha_agent" for item in payload["agents"])
    finally:
        deploy_server.DEFAULT_USER_ROOT = original_root


def test_deploy_server_reasoning_mode_uses_sdk_normalization():
    payload = deploy_server.MessageRequest(
        task_id="demo_task",
        new_message="hello",
        reasoning_mode="react(lite)",
    ).effective_sdk_overrides()

    assert payload["reasoning_mode"] == "react_lite"
    assert payload["thinking_enabled"] is False


def test_deploy_server_sdk_override_reasoning_mode_is_not_overridden_by_default():
    payload = deploy_server.MessageRequest(
        task_id="demo_task",
        new_message="hello",
        sdk_overrides={"reasoning_mode": "lite"},
    ).effective_sdk_overrides()

    assert payload["reasoning_mode"] == "react_lite"
    assert payload["thinking_enabled"] is False


def test_deploy_runtime_pause_never_kills_runtime_process(tmp_path):
    root = tmp_path / "user_root"
    runtime = DeploymentRuntime()
    runtime.ensure_task(root, "demo_task", conversation_name="demo_task", agent_system="scaffold_demo", agent_name="alpha_agent")
    fake_agent = MagicMock()
    fake_agent.pause_task.return_value = {"status": "success"}
    runtime._agent = lambda spec, agent_system, agent_name: fake_agent

    runtime.pause(root, "demo_task", reason="manual pause")

    fake_agent.pause_task.assert_called_once()
    assert fake_agent.pause_task.call_args.kwargs["kill_background_processes"] is False


def test_deploy_runtime_reset_never_kills_runtime_process(tmp_path):
    root = tmp_path / "user_root"
    runtime = DeploymentRuntime()
    runtime.ensure_task(root, "demo_task", conversation_name="demo_task", agent_system="scaffold_demo", agent_name="alpha_agent")
    fake_agent = MagicMock()
    fake_agent.reset_task.return_value = {"status": "success"}
    runtime._agent = lambda spec, agent_system, agent_name: fake_agent

    runtime.reset(root, "demo_task", reason="manual reset", preserve_history=True, kill_background_processes=True)

    fake_agent.reset_task.assert_called_once()
    assert fake_agent.reset_task.call_args.kwargs["kill_background_processes"] is False
