from pathlib import Path

import tool_server_lite.tools.code_tools as code_tools
from tool_server_lite.tools.code_tools import ExecuteCommandTool


def test_find_idle_terminal_window_id_returns_none_when_no_tagged_idle_tab(monkeypatch):
    tool = ExecuteCommandTool()

    monkeypatch.setattr(tool, "_run_osascript", lambda script, timeout=10: "")

    assert tool._find_idle_terminal_window_id() is None


def test_get_or_create_terminal_window_id_creates_fresh_window_when_all_tagged_tabs_busy(monkeypatch):
    tool = ExecuteCommandTool()

    monkeypatch.setattr(tool, "_terminal_window_exists", lambda window_id: False)
    monkeypatch.setattr(tool, "_force_reset_tagged_terminal_windows", lambda: None)

    captured = {}

    def fake_run(script, timeout=10):
        captured["script"] = script
        return "5678"

    monkeypatch.setattr(tool, "_run_osascript", fake_run)
    monkeypatch.setattr(code_tools, "TERMINAL_SESSION_WINDOW_ID", 1111)
    monkeypatch.setattr(code_tools, "TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH", False)

    assert tool._get_or_create_terminal_window_id() == 5678
    assert 'do script ""' in captured["script"]
    assert code_tools.TERMINAL_SESSION_WINDOW_ID == 5678


def test_launch_terminal_script_checks_busy_and_updates_cached_window(monkeypatch, tmp_path):
    tool = ExecuteCommandTool()
    script_path = tmp_path / "run.sh"
    script_path.write_text("#!/bin/bash\n", encoding="utf-8")

    monkeypatch.setattr(tool, "_get_or_create_terminal_window_id", lambda force_new=False: 1234)
    monkeypatch.setattr(tool, "_wait_for_terminal_window_idle", lambda window_id, timeout=1.5, poll_interval=0.1: True)
    monkeypatch.setattr(code_tools, "TERMINAL_SESSION_WINDOW_ID", None)
    monkeypatch.setattr(code_tools, "TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH", False)

    captured = {}

    def fake_run(script, timeout=10):
        captured["script"] = script
        return "4321"

    monkeypatch.setattr(tool, "_run_osascript", fake_run)

    tool._launch_terminal_script(script_path)

    assert 'busy of t' in captured["script"]
    assert 'do script ""' in captured["script"]
    assert code_tools.TERMINAL_SESSION_WINDOW_ID == 4321


def test_launch_terminal_script_interrupts_busy_session_instead_of_creating_new_window(monkeypatch, tmp_path):
    tool = ExecuteCommandTool()
    script_path = tmp_path / "run.sh"
    script_path.write_text("#!/bin/bash\n", encoding="utf-8")

    monkeypatch.setattr(tool, "_get_or_create_terminal_window_id", lambda force_new=False: 1234)
    waits = iter([False])
    monkeypatch.setattr(
        tool,
        "_wait_for_terminal_window_idle",
        lambda window_id, timeout=1.5, poll_interval=0.1: next(waits, True),
    )

    interrupted = {"called": 0}

    def fake_interrupt(window_id):
        interrupted["called"] += 1
        return True

    monkeypatch.setattr(tool, "_interrupt_terminal_window_processes", fake_interrupt)
    monkeypatch.setattr(code_tools, "TERMINAL_SESSION_ROTATE_ON_NEXT_LAUNCH", True)

    captured = {}

    def fake_run(script, timeout=10):
        captured["script"] = script
        return "4321"

    monkeypatch.setattr(tool, "_run_osascript", fake_run)

    tool._launch_terminal_script(script_path)

    assert interrupted["called"] == 1
    assert 'do script ""' in captured["script"]
