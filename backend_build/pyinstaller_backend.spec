#!/usr/bin/env python3
# PyInstaller spec for MLA V3 backend (desktop packaging)
#
# Output (onedir):
#   <distpath>/mlav3-backend/mlav3-backend
#
# We intentionally keep console=True because the desktop app consumes JSONL from stdout.

from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# NOTE: In PyInstaller, spec files are executed via exec() and may not have __file__.
# Use SPECPATH (provided by PyInstaller) as the spec directory.
spec_dir = Path(globals().get("SPECPATH", os.getcwd())).resolve()
repo_root = spec_dir.parent

# Data files needed at runtime (YAML configs, agent systems, etc.)
datas = [
    (str(repo_root / "config"), "config"),
]

# LiteLLM uses dynamic imports and importlib.resources; ensure submodules/data are bundled.
hiddenimports = []
try:
    hiddenimports += collect_submodules("litellm")
except Exception:
    hiddenimports += ["litellm.litellm_core_utils.tokenizers"]

try:
    datas += collect_data_files("litellm")
except Exception:
    pass

# tiktoken uses external registry data via `tiktoken_ext` to resolve encodings like cl100k_base.
# In frozen builds, missing `tiktoken_ext` causes: "Unknown encoding cl100k_base. Plugins found: []"
try:
    hiddenimports += collect_submodules("tiktoken_ext")
except Exception:
    hiddenimports += ["tiktoken_ext.openai_public"]

try:
    datas += collect_data_files("tiktoken_ext")
except Exception:
    pass

# rich loads unicode cell-width tables via dynamic imports like:
#   import_module(".unicode17-0-0", "rich._unicode_data")
# Those submodules have hyphens in their module names and are not discovered by
# static analysis, so we must explicitly include them, otherwise frozen builds hit:
#   No module named 'rich._unicode_data.unicode17-0-0'
try:
    import rich  # type: ignore
    rich_dir = Path(rich.__file__).resolve().parent
    ud_dir = rich_dir / "_unicode_data"
    if ud_dir.exists():
        for p in ud_dir.glob("unicode*.py"):
            stem = p.stem  # e.g. "unicode17-0-0"
            hiddenimports.append(f"rich._unicode_data.{stem}")
            # PyInstaller 的 modulegraph 可能不会把带 '-' 的模块名当作“模块”收集进 PYZ。
            # 保险起见，把这些 unicode*.py 当作 data 文件拷进 bundle 的 rich/_unicode_data/，
            # 让 importlib 在运行时能从文件系统导入它们。
            datas.append((str(p), "rich/_unicode_data"))
except Exception:
    pass

# crawl4ai ships runtime JS snippets under `crawl4ai/js_snippet/*`.
# In frozen builds these package data files are not always auto-collected,
# causing errors like:
#   "Script update_image_dimensions not found in .../_internal/crawl4ai/js_snippet"
try:
    hiddenimports += collect_submodules("crawl4ai")
except Exception:
    pass

try:
    datas += collect_data_files("crawl4ai")
except Exception:
    pass

a = Analysis(
    [str(repo_root / "start.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "desktop_app",
        "web_ui",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="mlav3-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="mlav3-backend",
)

