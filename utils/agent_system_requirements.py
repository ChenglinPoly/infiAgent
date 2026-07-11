#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional


def _find_requirements_file(agent_system_name: str, agent_system_dir: str | Path, tools_root: str | Path | None = None) -> Optional[Path]:
    """Find a dependency manifest without installing it.

    The agent-system requirements auto-installer was removed because a hidden
    per-system venv made backend imports and shell command execution disagree
    about which Python environment was active. This helper remains only for
    compatibility and diagnostics.
    """
    candidates = [
        Path(agent_system_dir).expanduser().resolve() / "requirements.txt",
    ]
    if tools_root:
        candidates.append(Path(tools_root).expanduser().resolve() / "requirements.txt")
    for path in candidates:
        if path.exists() and path.is_file():
            return path
    return None


def ensure_agent_system_requirements_ready(
    *,
    agent_system_name: str,
    agent_system_dir: str | Path,
    tools_root: str | Path | None = None,
) -> Dict[str, Any]:
    """Compatibility shim: never auto-install agent-system requirements."""
    requirements_path = _find_requirements_file(agent_system_name, agent_system_dir, tools_root=tools_root)
    return {
        "status": "disabled",
        "reason": "agent_system_requirements_auto_install_removed",
        "agent_system": agent_system_name,
        "requirements_path": str(requirements_path) if requirements_path else "",
    }
