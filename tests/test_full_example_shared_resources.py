#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import importlib.util
from pathlib import Path
import sys


PROJECT_ROOT = Path("/Users/chenglin/Desktop/research/agent_framwork/vscode_version/MLA_V3")
SCAFFOLD_ROOT = PROJECT_ROOT / "deploy" / "infiagent_dev_scaffold" / "user_root"
CATALOG_PATH = SCAFFOLD_ROOT / "resources" / "shared_catalog.json"


def _load_class(module_path: Path, class_name: str):
    spec = importlib.util.spec_from_file_location(module_path.stem, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    tools_root = str(SCAFFOLD_ROOT / "tools_library")
    inserted = False
    if tools_root not in sys.path:
        sys.path.insert(0, tools_root)
        inserted = True
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            while tools_root in sys.path:
                sys.path.remove(tools_root)
    return getattr(module, class_name)


def test_shared_catalog_lookup_tool_reads_shared_file():
    cls = _load_class(
        SCAFFOLD_ROOT / "tools_library" / "shared_catalog_lookup_tool" / "shared_catalog_lookup_tool.py",
        "SharedCatalogLookupTool",
    )
    tool = cls()
    result = tool.execute(
        str(SCAFFOLD_ROOT / "tasks" / "demo_task"),
        {
            "query": "alpha",
            "shared_runtime": {"catalog_path": str(CATALOG_PATH)},
        },
    )
    assert result["status"] == "success"
    assert "alpha-profile" in result["output"]


def test_shared_catalog_summary_tool_reads_shared_file():
    cls = _load_class(
        SCAFFOLD_ROOT / "tools_library" / "shared_catalog_summary_tool" / "shared_catalog_summary_tool.py",
        "SharedCatalogSummaryTool",
    )
    tool = cls()
    result = tool.execute(
        str(SCAFFOLD_ROOT / "tasks" / "demo_task"),
        {
            "shared_runtime": {"catalog_path": str(CATALOG_PATH)},
        },
    )
    assert result["status"] == "success"
    assert '"item_count": 3' in result["output"]
    assert '"owner": "scaffold_demo"' in result["output"]
