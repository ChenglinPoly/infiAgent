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

