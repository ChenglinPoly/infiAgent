#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MCP 运行时管理。

说明：
- MCP server 本身不是一个本地工具类
- 但 MCP server 暴露出来的 tools 需要以 OpenAI tool schema 的形式提供给模型
- ToolExecutor 在运行时根据 tool_name 路由到 MCP client 执行
"""

from __future__ import annotations

import asyncio
import json
import re
import traceback
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Dict, List, Tuple

from utils.user_paths import get_mcp_settings

HAS_MCP = True
MCP_IMPORT_ERROR = ""
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client
except Exception as exc:  # pragma: no cover - depends on interpreter/platform
    HAS_MCP = False
    MCP_IMPORT_ERROR = str(exc)


def _sanitize_name(name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", str(name or "").strip())
    s = s.strip("_")
    return s or "mcp"


def _normalize_server_entry(raw: Any) -> Dict[str, Any] | None:
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        return {
            "name": _sanitize_name(raw.rsplit("/", 1)[-1] or "server"),
            "transport": "streamable_http",
            "url": raw,
            "enabled": True,
        }

    if not isinstance(raw, dict):
        return None

    if raw.get("enabled", True) is False:
        return None

    transport = str(raw.get("transport") or ("stdio" if raw.get("command") else "streamable_http")).strip().lower()
    name = _sanitize_name(raw.get("name") or raw.get("server_name") or raw.get("url") or raw.get("command") or "server")

    entry: Dict[str, Any] = {
        "name": name,
        "transport": transport,
        "enabled": True,
        "headers": raw.get("headers") if isinstance(raw.get("headers"), dict) else {},
        "timeout": raw.get("timeout", 30),
        "sse_read_timeout": raw.get("sse_read_timeout", 300),
    }
    if transport in {"streamable_http", "sse"}:
        entry["url"] = str(raw.get("url") or "").strip()
        if not entry["url"]:
            return None
    elif transport == "stdio":
        entry["command"] = str(raw.get("command") or "").strip()
        entry["args"] = [str(x) for x in (raw.get("args") or [])]
        entry["env"] = {str(k): str(v) for k, v in (raw.get("env") or {}).items()} if isinstance(raw.get("env"), dict) else None
        entry["cwd"] = raw.get("cwd")
        if not entry["command"]:
            return None
    else:
        return None
    return entry


def get_mcp_servers() -> List[Dict[str, Any]]:
    settings = get_mcp_settings()
    servers = settings.get("servers", []) if isinstance(settings, dict) else []
    if not isinstance(servers, list):
        return []
    out = []
    for item in servers:
        normalized = _normalize_server_entry(item)
        if normalized:
            out.append(normalized)
    return out


@asynccontextmanager
async def _open_session(server: Dict[str, Any]):
    if not HAS_MCP:
        raise RuntimeError(f"MCP Python client is unavailable: {MCP_IMPORT_ERROR}")
    transport = server["transport"]
    if transport == "stdio":
        params = StdioServerParameters(
            command=server["command"],
            args=server.get("args", []),
            env=server.get("env"),
            cwd=server.get("cwd"),
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=float(server.get("timeout", 30)))) as session:
                await session.initialize()
                yield session
        return

    if transport == "sse":
        async with sse_client(
            server["url"],
            headers=server.get("headers") or None,
            timeout=float(server.get("timeout", 30)),
            sse_read_timeout=float(server.get("sse_read_timeout", 300)),
        ) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=float(server.get("timeout", 30)))) as session:
                await session.initialize()
                yield session
        return

    async with streamablehttp_client(
        server["url"],
        headers=server.get("headers") or None,
        timeout=float(server.get("timeout", 30)),
        sse_read_timeout=float(server.get("sse_read_timeout", 300)),
    ) as (read, write, _get_session_id):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=float(server.get("timeout", 30)))) as session:
            await session.initialize()
            yield session


def _dump_model(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        try:
            return obj.model_dump()
        except Exception:
            pass
    if isinstance(obj, list):
        return [_dump_model(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dump_model(v) for k, v in obj.items()}
    return obj


def _format_tool_contents(contents: List[Any]) -> str:
    parts = []
    for item in contents or []:
        data = _dump_model(item)
        if isinstance(data, dict):
            if "text" in data and data["text"] is not None:
                parts.append(str(data["text"]))
            else:
                parts.append(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            parts.append(str(data))
    return "\n".join(p for p in parts if p).strip()


_mcp_tool_cache: Dict[str, Dict[str, Any]] | None = None
_mcp_failures_cache: List[Dict[str, Any]] | None = None


async def _discover_mcp_tools_async() -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    tools: Dict[str, Dict[str, Any]] = {}
    failures: List[Dict[str, Any]] = []
    if not HAS_MCP:
        if get_mcp_servers():
            failures.append({
                "server": "mcp_runtime",
                "error": f"MCP Python client is unavailable: {MCP_IMPORT_ERROR}",
                "traceback": "",
            })
        return tools, failures
    for server in get_mcp_servers():
        try:
            async with _open_session(server) as session:
                result = await session.list_tools()
                for tool in getattr(result, "tools", []) or []:
                    raw_name = getattr(tool, "name", "") or ""
                    synthetic_name = f"mcp__{server['name']}__{_sanitize_name(raw_name)}"
                    tools[synthetic_name] = {
                        "type": "tool_call_agent",
                        "name": synthetic_name,
                        "description": f"[MCP:{server['name']}] {getattr(tool, 'description', '') or raw_name}",
                        "parameters": getattr(tool, "inputSchema", None) or {"type": "object", "properties": {}},
                        "_mcp": {
                            "server": server,
                            "server_name": server["name"],
                            "tool_name": raw_name,
                        }
                    }
        except Exception as exc:
            failures.append({
                "server": server.get("name", "unknown"),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })
    return tools, failures


def reload_mcp_tools() -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    global _mcp_tool_cache, _mcp_failures_cache
    _mcp_tool_cache, _mcp_failures_cache = asyncio.run(_discover_mcp_tools_async())
    return _mcp_tool_cache, _mcp_failures_cache


def get_mcp_tools(force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
    global _mcp_tool_cache
    if force_reload or _mcp_tool_cache is None:
        reload_mcp_tools()
    return dict(_mcp_tool_cache or {})


def get_mcp_failures(force_reload: bool = False) -> List[Dict[str, Any]]:
    global _mcp_failures_cache
    if force_reload or _mcp_failures_cache is None:
        reload_mcp_tools()
    return list(_mcp_failures_cache or [])


async def _call_mcp_tool_async(tool_config: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
    mcp_meta = tool_config.get("_mcp", {}) if isinstance(tool_config, dict) else {}
    server = mcp_meta.get("server")
    tool_name = mcp_meta.get("tool_name")
    if not server or not tool_name:
        raise ValueError("无效的 MCP 工具配置")

    async with _open_session(server) as session:
        result = await session.call_tool(tool_name, arguments=arguments)
        contents = getattr(result, "content", []) or []
        is_error = bool(getattr(result, "isError", False))
        output_text = _format_tool_contents(contents)
        return {
            "status": "error" if is_error else "success",
            "output": output_text,
            "error": output_text if is_error else "",
            "_mcp_server": server.get("name"),
            "_mcp_tool_name": tool_name,
            "_mcp_raw": _dump_model(result),
        }


def call_mcp_tool(tool_config: Dict[str, Any], arguments: Dict[str, Any]) -> Dict[str, Any]:
    return asyncio.run(_call_mcp_tool_async(tool_config, arguments))
