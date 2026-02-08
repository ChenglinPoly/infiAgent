#!/usr/bin/env python3
# PyInstaller spec for MLA V3 backend (desktop packaging)
#
# Output (onedir):
#   <distpath>/mlav3-backend/mlav3-backend
#
# We intentionally keep console=True because the desktop app consumes JSONL from stdout.

from pathlib import Path
import os

block_cipher = None

# NOTE: In PyInstaller, spec files are executed via exec() and may not have __file__.
# Use SPECPATH (provided by PyInstaller) as the spec directory.
spec_dir = Path(globals().get("SPECPATH", os.getcwd())).resolve()
repo_root = spec_dir.parent

# Data files needed at runtime (YAML configs, agent systems, etc.)
datas = [
    (str(repo_root / "config"), "config"),
]

a = Analysis(
    ["start.py"],
    pathex=[str(repo_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
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

