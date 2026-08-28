# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for omnibot.

Usage:
    pyinstaller build-config/omnibot.spec

Builds: dist/omnibot (Linux/macOS) or dist/omnibot.exe (Windows)
"""

import sys
from pathlib import Path

# Project root (parent of build-config/)
ROOT = Path(SPECPATH).parent
PKG = ROOT / "src" / "omnibot"

block_cipher = None

# Collect SOP data files
sop_path = str(PKG / "sop")

a = Analysis(
    [str(ROOT / "build-config" / "_entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (sop_path, "omnibot/sop"),
    ],
    hiddenimports=[
        # MCP framework
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
        "mcp.server.lowlevel",
        "mcp.server.models",
        "mcp.types",
        "mcp.shared",
        # WebSocket + HTTP
        "simple_websocket_server",
        "bs4",
        "bs4.builder",
        "bottle",
        "requests",
        # Streamable-HTTP transport (starlette + uvicorn)
        "starlette",
        "starlette.applications",
        "starlette.middleware",
        "starlette.middleware.base",
        "starlette.responses",
        "uvicorn",
        "uvicorn.config",
        "uvicorn.main",
        "uvicorn.server",
        "anyio",
        # stdlib used dynamically
        "wsgiref.simple_server",
        "socketserver",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "jupyter",
        "IPython",
        "notebook",
        "pytest",
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="omnibot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
