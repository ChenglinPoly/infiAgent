from pathlib import Path

import pytest
import yaml

import tool_server_lite.tools.code_tools as code_tools
from tool_server_lite.tools.code_tools import ExecuteCommandTool
from tool_server_lite.tools.file_tools import FileReadTool, FileWriteTool
from utils.sandbox_policy import prepare_landlock_env


pytestmark = pytest.mark.unit


@pytest.fixture
def sandbox_env(tmp_path, monkeypatch):
    user_root = tmp_path / "user_root"
    config_dir = user_root / "config"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "sandbox_config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "sandbox": {
                    "enabled": True,
                    "engine": "landlock",
                    "file_tools": {"enforce_task_root": True},
                    "command": {
                        "enabled": True,
                        "engine": "landlock",
                        "fail_closed": True,
                        "host_read_roots": ["/usr", "/bin"],
                        "env_passthrough": ["GRB_LICENSE_FILE"],
                    },
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MLA_USER_DATA_ROOT", str(user_root))
    monkeypatch.setenv("INFIAGENT_USER_ROOT", str(user_root))
    monkeypatch.setenv("MLA_SANDBOX_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("MLA_SANDBOX_ENABLED", "true")
    return user_root


def test_file_tools_reject_parent_escape_when_sandbox_enabled(tmp_path, sandbox_env):
    task = tmp_path / "user_root" / "tasks" / "task_a"
    task.mkdir(parents=True)
    secret = tmp_path / "user_root" / "tasks" / "secret.txt"
    secret.write_text("secret", encoding="utf-8")

    read_result = FileReadTool().execute(str(task), {"path": "../secret.txt", "show_line_numbers": False})
    assert read_result["status"] == "error"
    assert "路径越界" in read_result["error"]

    write_result = FileWriteTool().execute(str(task), {"path": "../secret.txt", "content": "changed"})
    assert write_result["status"] == "error"
    assert secret.read_text(encoding="utf-8") == "secret"


def test_file_tools_reject_symlink_escape_when_sandbox_enabled(tmp_path, sandbox_env):
    task = tmp_path / "user_root" / "tasks" / "task_a"
    task.mkdir(parents=True)
    outside = tmp_path / "user_root" / "config" / "llm_config.yaml"
    outside.write_text("api_key: SECRET", encoding="utf-8")
    (task / "link.yaml").symlink_to(outside)

    result = FileReadTool().execute(str(task), {"path": "link.yaml", "show_line_numbers": False})
    assert result["status"] == "error"
    assert "路径越界" in result["error"]


def test_landlock_env_keeps_solver_env_and_strips_secret_names(tmp_path, sandbox_env):
    task = tmp_path / "user_root" / "tasks" / "task_a"
    task.mkdir(parents=True)
    env = {
        "PATH": "/usr/bin:/bin",
        "OPENAI_API_KEY": "secret",
        "GRB_LICENSE_FILE": "/opt/gurobi/gurobi.lic",
    }
    prepared = prepare_landlock_env(str(task), str(task), env)
    assert "OPENAI_API_KEY" not in prepared
    assert prepared["GRB_LICENSE_FILE"] == "/opt/gurobi/gurobi.lic"
    assert prepared["HOME"] == str(task / ".home")
    assert prepared["PIP_CACHE_DIR"] == str(task / ".cache" / "pip")
    assert "MLA_LANDLOCK_RULES_JSON" in prepared


def test_execute_command_uses_landlock_wrapper_when_enabled(tmp_path, sandbox_env, monkeypatch):
    task = tmp_path / "user_root" / "tasks" / "task_a"
    task.mkdir(parents=True)
    tool = ExecuteCommandTool()
    monkeypatch.setattr(code_tools, "should_wrap_command_with_landlock", lambda: True)

    cmd, shell, cwd = tool._subprocess_invocation("echo ok", task)
    assert shell is False
    assert cwd is None
    assert cmd[:3] == [__import__("sys").executable, "-m", "utils.landlock_exec"]
    assert cmd[-3:] == ["/bin/sh", "-c", "echo ok"]


def test_execute_command_uses_unix_permission_kwargs_when_fallback_enabled(tmp_path, sandbox_env, monkeypatch):
    task = tmp_path / "user_root" / "tasks" / "task_a"
    task.mkdir(parents=True)
    tool = ExecuteCommandTool()
    monkeypatch.setattr(code_tools, "should_apply_unix_permission_sandbox", lambda: True)
    monkeypatch.setattr(
        code_tools,
        "prepare_unix_permission_sandbox",
        lambda workspace, cwd: {"user": 234567, "group": 234567, "umask": 0o077},
    )

    kwargs = tool._subprocess_security_kwargs(task, task)
    assert kwargs == {"user": 234567, "group": 234567, "umask": 0o077}


