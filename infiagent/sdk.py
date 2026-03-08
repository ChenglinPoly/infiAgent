#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
正式 Python SDK。

示例：
    from infiagent import infiagent

    agent = infiagent(
        agent_library_dir="/path/to/agent_library",
        tools_dir="/path/to/tools_library",
        llm_config_path="/path/to/llm_config.yaml",
        workspace="/path/to/workspace",
        action_window_steps=12,
        thinking_interval=12,
    )

    result = agent.run(
        "请帮我分析这个项目",
        agent_system="OpenCowork",
        agent_name="alpha_agent",
    )
"""

from __future__ import annotations

import json
import os
import asyncio
from functools import partial
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.agent_executor import AgentExecutor
from core.hierarchy_manager import get_hierarchy_manager
from utils.config_loader import ConfigLoader
from utils.user_paths import apply_runtime_env_defaults


def _as_root_dir(path: Optional[str], expected_leaf: Optional[str] = None) -> Optional[str]:
    if not path:
        return None
    p = Path(path).expanduser().resolve()
    if expected_leaf and p.name == expected_leaf:
        return str(p.parent)
    return str(p)


class InfiAgent:
    def __init__(
        self,
        workspace: Optional[str] = None,
        user_data_root: Optional[str] = None,
        llm_config_path: Optional[str] = None,
        library_dir: Optional[str] = None,
        agent_library_dir: Optional[str] = None,
        skills_dir: Optional[str] = None,
        tools_dir: Optional[str] = None,
        default_agent_system: Optional[str] = None,
        default_agent_name: Optional[str] = None,
        action_window_steps: Optional[int] = None,
        thinking_interval: Optional[int] = None,
        fresh_enabled: Optional[bool] = None,
        fresh_interval_sec: Optional[int] = None,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        direct_tools: bool = True,
    ):
        # 默认目标可在 run(...) 时覆盖；SDK 初始化更偏向“配置运行环境”
        self.default_agent_system = default_agent_system or "OpenCowork"
        self.default_agent_name = default_agent_name or "alpha_agent"
        self.workspace = str(Path(workspace or os.getcwd()).expanduser().resolve())
        self.direct_tools = bool(direct_tools)

        effective_agent_library_dir = agent_library_dir or library_dir

        if user_data_root:
            os.environ["MLA_USER_DATA_ROOT"] = str(Path(user_data_root).expanduser().resolve())
        if llm_config_path:
            os.environ["MLA_LLM_CONFIG_PATH"] = str(Path(llm_config_path).expanduser().resolve())
        if effective_agent_library_dir:
            # ConfigLoader 期望的是“包含 agent_library 的根目录”，
            # 所以如果用户传的是具体 agent_library 文件夹，要上提一层。
            inferred_root = _as_root_dir(effective_agent_library_dir, "agent_library")
            if inferred_root:
                os.environ["MLA_USER_DATA_ROOT"] = inferred_root
                os.environ["MLA_AGENT_LIBRARY_DIR"] = inferred_root
        if skills_dir:
            os.environ["MLA_SKILLS_LIBRARY_DIR"] = str(Path(skills_dir).expanduser().resolve())
        if tools_dir:
            os.environ["MLA_TOOLS_LIBRARY_DIR"] = str(Path(tools_dir).expanduser().resolve())

        if action_window_steps is not None:
            os.environ["MLA_ACTION_WINDOW_STEPS"] = str(max(1, int(action_window_steps)))
        if thinking_interval is not None:
            os.environ["MLA_THINKING_INTERVAL"] = str(max(1, int(thinking_interval)))
        if fresh_enabled is not None:
            os.environ["MLA_FRESH_ENABLED"] = "true" if fresh_enabled else "false"
        if fresh_interval_sec is not None:
            os.environ["MLA_FRESH_INTERVAL_SEC"] = str(max(0, int(fresh_interval_sec)))
        if mcp_servers is not None:
            os.environ["MLA_MCP_CONFIG_JSON"] = json.dumps({"servers": mcp_servers}, ensure_ascii=False)

        apply_runtime_env_defaults()

    def run(
        self,
        user_input: str,
        *,
        agent_system: Optional[str] = None,
        agent_name: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        task_id = str(Path(workspace or self.workspace).expanduser().resolve())
        target_agent_system = agent_system or self.default_agent_system
        target_agent_name = agent_name or self.default_agent_name

        config_loader = ConfigLoader(target_agent_system)
        hierarchy_manager = get_hierarchy_manager(task_id)
        agent_config = config_loader.get_tool_config(target_agent_name)
        agent = AgentExecutor(
            agent_name=target_agent_name,
            agent_config=agent_config,
            config_loader=config_loader,
            hierarchy_manager=hierarchy_manager,
            direct_tools=self.direct_tools,
        )
        return agent.run(task_id, user_input)

    async def run_async(
        self,
        user_input: str,
        *,
        agent_system: Optional[str] = None,
        agent_name: Optional[str] = None,
        workspace: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 当前后端核心仍是同步执行器。这里先提供一个易用的 async 包装层，
        # 让上层服务/应用可以用 await 方式集成，而不需要自己写线程池封装。
        fn = partial(
            self.run,
            user_input,
            agent_system=agent_system,
            agent_name=agent_name,
            workspace=workspace,
        )
        return await asyncio.to_thread(fn)


def infiagent(**kwargs) -> InfiAgent:
    return InfiAgent(**kwargs)
