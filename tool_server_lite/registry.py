#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一工具运行时注册中心。

职责：
1. 提供 built-in 工具注册表（single source of truth）
2. 扫描用户目录中的自定义 Python 工具并尝试加载
3. 为 direct-tools 与 legacy HTTP tool server 提供同一份运行时注册表
"""

from __future__ import annotations

import importlib.util
import inspect
import traceback
import types
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from utils.user_paths import get_user_tools_library_root
from tool_server_lite.tools.file_tools import BaseTool


ToolFactory = Callable[[], Any]


def _build_builtin_factories() -> Dict[str, ToolFactory]:
    from tool_server_lite.tools import (
        FileReadTool,
        FileWriteTool,
        DirListTool,
        DirCreateTool,
        FileMoveTool,
        FileDeleteTool,
        WebSearchTool,
        GoogleScholarSearchTool,
        ArxivSearchTool,
        CrawlPageTool,
        FileDownloadTool,
        ParseDocumentTool,
        VisionTool,
        ImageReadTool,
        CreateImageTool,
        AudioTool,
        PaperAnalyzeTool,
        MarkdownToPdfTool,
        MarkdownToDocxTool,
        TexToPdfTool,
        HumanInLoopTool,
        ExecuteCommandTool,
        GrepTool,
        ReferenceListTool,
        ReferenceAddTool,
        ReferenceDeleteTool,
        ImagesToPptTool,
        LoadSkillTool,
        OffloadSkillTool,
        FreshTool,
    )

    factories: Dict[str, ToolFactory] = {
        "file_read": FileReadTool,
        "file_write": FileWriteTool,
        "dir_list": DirListTool,
        "dir_create": DirCreateTool,
        "file_move": FileMoveTool,
        "file_delete": FileDeleteTool,
        "web_search": WebSearchTool,
        "google_scholar_search": GoogleScholarSearchTool,
        "arxiv_search": ArxivSearchTool,
        "crawl_page": CrawlPageTool,
        "file_download": FileDownloadTool,
        "parse_document": ParseDocumentTool,
        "vision_tool": VisionTool,
        "image_read": ImageReadTool,
        "create_image": CreateImageTool,
        "audio_tool": AudioTool,
        "paper_analyze_tool": PaperAnalyzeTool,
        "md_to_pdf": MarkdownToPdfTool,
        "md_to_docx": MarkdownToDocxTool,
        "tex_to_pdf": TexToPdfTool,
        "human_in_loop": HumanInLoopTool,
        "execute_command": ExecuteCommandTool,
        "grep": GrepTool,
        "reference_list": ReferenceListTool,
        "reference_add": ReferenceAddTool,
        "reference_delete": ReferenceDeleteTool,
        "images_to_ppt": ImagesToPptTool,
        "load_skill": LoadSkillTool,
        "offload_skill": OffloadSkillTool,
        "fresh": FreshTool,
    }

    try:
        from tool_server_lite.tools import (
            BrowserLaunchTool,
            BrowserCloseTool,
            BrowserNewPageTool,
            BrowserSwitchPageTool,
            BrowserClosePageTool,
            BrowserListPagesTool,
            BrowserNavigateTool,
            BrowserSnapshotTool,
            BrowserExecuteJsTool,
            BrowserClickTool,
            BrowserTypeTool,
            BrowserWaitTool,
            BrowserMouseMoveTool,
            BrowserMouseClickCoordsTool,
            BrowserDragAndDropTool,
            BrowserHoverTool,
            BrowserScrollTool,
        )

        factories.update({
            "browser_launch": BrowserLaunchTool,
            "browser_close": BrowserCloseTool,
            "browser_new_page": BrowserNewPageTool,
            "browser_switch_page": BrowserSwitchPageTool,
            "browser_close_page": BrowserClosePageTool,
            "browser_list_pages": BrowserListPagesTool,
            "browser_navigate": BrowserNavigateTool,
            "browser_snapshot": BrowserSnapshotTool,
            "browser_execute_js": BrowserExecuteJsTool,
            "browser_click": BrowserClickTool,
            "browser_type": BrowserTypeTool,
            "browser_wait": BrowserWaitTool,
            "browser_mouse_move": BrowserMouseMoveTool,
            "browser_mouse_click_coords": BrowserMouseClickCoordsTool,
            "browser_drag_and_drop": BrowserDragAndDropTool,
            "browser_hover": BrowserHoverTool,
            "browser_scroll": BrowserScrollTool,
        })
    except ImportError:
        pass

    return factories


def get_builtin_tool_factories() -> Dict[str, ToolFactory]:
    return dict(_build_builtin_factories())


def _load_module_from_path(file_path: Path) -> types.ModuleType:
    module_name = f"mla_custom_tool_{file_path.stem}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法为 {file_path.name} 创建模块规范")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_valid_custom_tool_class(obj: Any, module_name: str) -> bool:
    if not inspect.isclass(obj):
        return False
    if obj.__module__ != module_name:
        return False
    if obj is BaseTool:
        return False
    if obj.__name__.startswith("_"):
        return False
    if not (hasattr(obj, "execute") or hasattr(obj, "execute_async")):
        return False
    return True


def _discover_custom_tool_class(module: types.ModuleType) -> type:
    candidates = [
        obj for _, obj in inspect.getmembers(module)
        if _is_valid_custom_tool_class(obj, module.__name__)
    ]
    if not candidates:
        raise ValueError("未找到符合约定的工具类（需要公开类并实现 execute 或 execute_async）")
    if len(candidates) > 1:
        raise ValueError("检测到多个候选工具类，请保证每个文件只定义一个公开工具类")
    return candidates[0]


def _instantiate_custom_tool(file_path: Path) -> Tuple[str, Any, Dict[str, Any]]:
    module = _load_module_from_path(file_path)
    tool_cls = _discover_custom_tool_class(module)
    tool = tool_cls()

    tool_name = getattr(tool, "name", None) or getattr(tool_cls, "name", None) or file_path.stem
    tool_name = str(tool_name).strip()
    if not tool_name:
        raise ValueError("工具名称为空，请设置类属性 name 或使用合法文件名")

    metadata = {
        "name": tool_name,
        "source": "custom",
        "path": str(file_path),
        "class_name": tool_cls.__name__,
        "status": "loaded",
        "error": "",
    }
    return tool_name, tool, metadata


_registry_cache: Dict[str, Any] | None = None
_registry_metadata_cache: Dict[str, Dict[str, Any]] | None = None
_registry_failures_cache: List[Dict[str, Any]] | None = None


def build_runtime_registry() -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    registry: Dict[str, Any] = {}
    metadata: Dict[str, Dict[str, Any]] = {}
    failures: List[Dict[str, Any]] = []

    for name, factory in get_builtin_tool_factories().items():
        try:
            registry[name] = factory()
            metadata[name] = {
                "name": name,
                "source": "builtin",
                "path": "",
                "class_name": type(registry[name]).__name__,
                "status": "loaded",
                "error": "",
            }
        except Exception as exc:
            failures.append({
                "name": name,
                "source": "builtin",
                "path": "",
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })

    custom_root = get_user_tools_library_root()
    custom_root.mkdir(parents=True, exist_ok=True)
    for tool_dir in sorted(custom_root.iterdir()):
        if not tool_dir.is_dir() or tool_dir.name.startswith("."):
            continue
        py_files = [p for p in sorted(tool_dir.glob("*.py")) if p.is_file()]
        if not py_files:
            failures.append({
                "name": tool_dir.name,
                "source": "custom",
                "path": str(tool_dir),
                "status": "error",
                "error": "工具目录中未找到 Python 文件",
                "traceback": "",
            })
            continue

        if len(py_files) > 1:
            failures.append({
                "name": tool_dir.name,
                "source": "custom",
                "path": str(tool_dir),
                "status": "error",
                "error": "工具目录中存在多个 Python 文件，请保持每个工具目录仅包含一个主工具文件",
                "traceback": "",
            })
            continue

        file_path = py_files[0]
        try:
            tool_name, tool, tool_meta = _instantiate_custom_tool(file_path)
            if tool_name in registry:
                raise ValueError(f"工具名冲突: {tool_name}")
            registry[tool_name] = tool
            metadata[tool_name] = tool_meta
        except Exception as exc:
            failures.append({
                "name": tool_dir.name,
                "source": "custom",
                "path": str(file_path),
                "status": "error",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            })

    return registry, metadata, failures


def reload_runtime_registry() -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    global _registry_cache, _registry_metadata_cache, _registry_failures_cache
    _registry_cache, _registry_metadata_cache, _registry_failures_cache = build_runtime_registry()
    return _registry_cache, _registry_metadata_cache, _registry_failures_cache


def get_runtime_registry(force_reload: bool = False) -> Dict[str, Any]:
    global _registry_cache
    if force_reload or _registry_cache is None:
        reload_runtime_registry()
    return dict(_registry_cache or {})


def get_runtime_registry_metadata(force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
    global _registry_metadata_cache
    if force_reload or _registry_metadata_cache is None:
        reload_runtime_registry()
    return dict(_registry_metadata_cache or {})


def get_runtime_registry_failures(force_reload: bool = False) -> List[Dict[str, Any]]:
    global _registry_failures_cache
    if force_reload or _registry_failures_cache is None:
        reload_runtime_registry()
    return list(_registry_failures_cache or [])
