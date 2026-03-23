#!/usr/bin/env python3
from pathlib import Path
import sys

APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

FINAL_OUTPUT_HOOK_CALLBACK = f"{(APP_ROOT / 'cheapclaw_hooks.py').resolve()}:on_tool_event"

from infiagent import infiagent
from tool_runtime_helpers import (
    bind_messages_to_task,
    ensure_conversation,
    load_panel,
    mutate_panel,
    now_iso,
    set_task_visible_skills,
)
from tool_server_lite.tools.file_tools import BaseTool


def _load_cheapclaw_settings(user_root: str):
    example_path = Path(__file__).resolve().parents[2] / "assets" / "config" / "app_config.example.json"
    try:
        example_payload = __import__("json").loads(example_path.read_text(encoding="utf-8"))
    except Exception:
        example_payload = {"cheapclaw": {"default_exposed_skills": ["docx", "pptx", "xlsx", "find-skills"], "default_mcp_servers": []}}
    config_path = Path(user_root).expanduser().resolve() / "cheapclaw" / "config" / "app_config.json"
    try:
        payload = __import__("json").loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        payload = example_payload
    cheapclaw = payload.get("cheapclaw", {}) if isinstance(payload, dict) else {}
    example_cheapclaw = example_payload.get("cheapclaw", {}) if isinstance(example_payload, dict) else {}
    default_skills = cheapclaw.get("default_exposed_skills", example_cheapclaw.get("default_exposed_skills", ["docx", "pptx", "xlsx", "find-skills"]))
    if not isinstance(default_skills, list):
        default_skills = list(example_cheapclaw.get("default_exposed_skills", ["docx", "pptx", "xlsx", "find-skills"]))
    default_mcp_servers = cheapclaw.get("default_mcp_servers", example_cheapclaw.get("default_mcp_servers", []))
    if not isinstance(default_mcp_servers, list):
        default_mcp_servers = list(example_cheapclaw.get("default_mcp_servers", []))
    return {
        "default_exposed_skills": [str(item).strip() for item in default_skills if str(item).strip()],
        "default_mcp_servers": [item for item in default_mcp_servers if isinstance(item, dict)],
    }


def _default_task_view(task_id):
    return {
        "task_id": task_id,
        "agent_system": "",
        "agent_name": "",
        "status": "unknown",
        "share_context_path": "",
        "stack_path": "",
        "log_path": "",
        "skills_dir": "",
        "default_exposed_skills": [],
        "mcp_servers": [],
        "last_thinking": "",
        "last_thinking_at": "",
        "last_final_output": "",
        "last_final_output_at": "",
        "last_action_at": "",
        "last_log_at": "",
        "last_launch_at": "",
        "fresh_retry_count": 0,
        "last_watchdog_note": "",
        "created_at": now_iso(),
    }


class CheapClawStartTaskTool(BaseTool):
    name = "cheapclaw_start_task"

    def execute(self, task_id, parameters):
        channel = str(parameters.get("channel") or "").strip()
        conversation_id = str(parameters.get("conversation_id") or "").strip()
        task_name = str(parameters.get("task_name") or "").strip()
        user_input = str(parameters.get("user_input") or "").strip()
        provided_task_id = str(parameters.get("task_id") or "").strip()
        if not channel or not conversation_id or not task_name or not user_input or not provided_task_id:
            return {"status": "error", "output": "", "error": "task_id, channel, conversation_id, task_name and user_input are required"}

        user_root = str(Path(__import__("os").environ.get("MLA_USER_DATA_ROOT", "~/mla_v3")).expanduser().resolve())
        tools_root = str(Path(__file__).resolve().parents[1])
        cheapclaw_settings = _load_cheapclaw_settings(user_root)
        agent = infiagent(user_data_root=user_root, tools_dir=tools_root, seed_builtin_resources=False)
        resolved_task_id = str(Path(provided_task_id).expanduser().resolve())
        requested_agent_system = str(parameters.get("agent_system") or "CheapClawWorkerGeneral").strip() or "CheapClawWorkerGeneral"
        requested_agent_name = str(parameters.get("agent_name") or "").strip()
        if requested_agent_system == "CheapClawSupervisor":
            return {
                "status": "error",
                "output": "",
                "error": "禁止使用 CheapClawSupervisor 启动后台任务，主调度 agent 不能调用本身。",
            }

        systems_payload = agent.list_agent_systems()
        systems = {
            str(item.get("name") or ""): item
            for item in systems_payload.get("agent_systems", [])
            if isinstance(item, dict)
        }
        system_info = systems.get(requested_agent_system, {})
        available_agent_names = [str(name).strip() for name in system_info.get("agent_names", []) if str(name).strip()]
        if requested_agent_system == "CheapClawWorkerGeneral":
            selected_agent_name = "worker_agent"
        elif requested_agent_name and requested_agent_name in available_agent_names:
            selected_agent_name = requested_agent_name
        elif available_agent_names:
            selected_agent_name = available_agent_names[0]
        else:
            selected_agent_name = requested_agent_name or "worker_agent"

        config = {"tools_dir": tools_root}
        panel = load_panel()
        existing_task_view = next(
            (
                item for item in panel.get("channels", {}).get(channel, {}).get("conversations", {}).get(conversation_id, {}).get("linked_tasks", [])
                if item.get("task_id") == resolved_task_id
            ),
            {},
        )
        configured_defaults = list(existing_task_view.get("default_exposed_skills") or cheapclaw_settings.get("default_exposed_skills", ["docx", "pptx", "xlsx", "find-skills"]))
        requested_exposed = parameters.get("exposed_skills")
        if requested_exposed is None:
            exposed = configured_defaults
        else:
            merged = []
            for item in configured_defaults + list(requested_exposed or []):
                name = str(item).strip()
                if name and name not in merged:
                    merged.append(name)
            exposed = merged
        config["mcp_servers"] = list((parameters.get("config") or {}).get("mcp_servers") or existing_task_view.get("mcp_servers") or cheapclaw_settings.get("default_mcp_servers", []))
        config["visible_skills"] = list(exposed)

        config.update(parameters.get("config") or {})
        existing_hooks = list(config.get("tool_hooks") or [])
        if not any(str(item.get("callback") or "") == FINAL_OUTPUT_HOOK_CALLBACK for item in existing_hooks if isinstance(item, dict)):
            existing_hooks.append({
                "name": "cheapclaw-final-output",
                "callback": FINAL_OUTPUT_HOOK_CALLBACK,
                "when": "after",
                "tool_names": ["final_output"],
                "include_arguments": False,
                "include_result": True,
            })
        config["tool_hooks"] = existing_hooks

        result = agent.start_background_task(
            task_id=resolved_task_id,
            user_input=f"{user_input}\n\n[dispatched_at {now_iso()}]",
            agent_system=requested_agent_system,
            agent_name=selected_agent_name,
            force_new=bool(parameters.get("force_new", False)),
            config=config,
        )
        if result.get("status") != "success":
            return result

        snapshot = agent.task_snapshot(task_id=resolved_task_id)
        set_task_visible_skills(resolved_task_id, exposed)

        def _mutate(panel):
            conv = ensure_conversation(
                panel,
                channel=channel,
                conversation_id=conversation_id,
                conversation_type=str(parameters.get("conversation_type") or "group"),
                display_name=str(parameters.get("display_name") or conversation_id),
                require_mention=bool(parameters.get("require_mention", True)),
            )
            linked = conv.setdefault("linked_tasks", [])
            existing = next((item for item in linked if item.get("task_id") == resolved_task_id), None)
            view = _default_task_view(resolved_task_id)
            view.update({
                "agent_system": result.get("agent_system", "CheapClawWorkerGeneral"),
                "agent_name": result.get("agent_name", selected_agent_name),
                "status": "running",
                "share_context_path": snapshot.get("share_context_path", ""),
                "stack_path": snapshot.get("stack_path", ""),
                "log_path": result.get("log_path", ""),
                "skills_dir": "",
                "default_exposed_skills": list(exposed or []),
                "mcp_servers": list(config.get("mcp_servers") or []),
                "last_thinking": snapshot.get("latest_thinking", ""),
                "last_thinking_at": snapshot.get("latest_thinking_at", ""),
                "last_final_output": snapshot.get("last_final_output", ""),
                "last_final_output_at": snapshot.get("last_final_output_at", ""),
                "last_action_at": snapshot.get("last_updated", ""),
                "last_log_at": now_iso(),
                "last_launch_at": now_iso(),
                "last_watchdog_note": "task launched by supervisor",
                "user_input": str((snapshot.get("runtime") or {}).get("user_input") or user_input or ""),
                "latest_instruction": str(((snapshot.get("latest_instruction") or {}) if isinstance(snapshot.get("latest_instruction"), dict) else {}).get("instruction") or user_input or ""),
                "created_at": str((existing or existing_task_view).get("created_at") or "") or now_iso(),
            })
            if existing is None:
                linked.append(view)
            else:
                existing.update(view)
            conv.setdefault("pending_events", []).append({"type": "task_started", "task_id": resolved_task_id, "timestamp": now_iso()})
            conv["dirty"] = True
            conv["updated_at"] = now_iso()
            panel.setdefault("service_state", {})["main_agent_dirty"] = True
            return panel

        mutate_panel(_mutate)

        source_message_ids = parameters.get("source_message_ids") or []
        if isinstance(source_message_ids, list) and source_message_ids:
            bind_messages_to_task(channel, conversation_id, resolved_task_id, source_message_ids, note="new task started from supervisor decision")

        return {
            "status": "success",
            **result,
            "requested_agent_name": requested_agent_name,
            "selected_agent_name": selected_agent_name,
            "available_agent_names": available_agent_names,
            "share_context_path": snapshot.get("share_context_path", ""),
            "stack_path": snapshot.get("stack_path", ""),
        }
