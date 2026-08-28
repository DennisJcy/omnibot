"""Contract tests for scripts/normalize_nuitka_standalone.py."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

import pytest


PLATFORM_DIRS = {
    "Windows": "windows-x64",
    "Linux": "linux-x64",
    "Darwin": "macos-arm64" if platform.machine() == "arm64" else "macos-x64",
}

EXEC_NAMES = {
    "Windows": "omnibot-windows-x64.exe",
    "Linux": "omnibot-linux-x64",
    "Darwin": "omnibot-macos-arm64" if platform.machine() == "arm64" else "omnibot-macos-x64",
}


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )


def test_normalize_moves_dist_into_platform_dir(tmp_path: Path):
    src_parent = tmp_path / "dist"
    src_parent.mkdir()
    src_dist = src_parent / "omnibot.dist"
    src_dist.mkdir()
    binary = src_dist / "omnibot"
    binary.write_bytes(b"#!/bin/sh\necho hi\n")
    src_dist / "support.cpython-313.so"
    (src_dist / "support.cpython-313.so").write_bytes(b"binary")
    src_dist / "lib"
    (src_dist / "lib").mkdir()
    (src_dist / "lib" / "data.txt").write_text("data", encoding="utf-8")

    output_root = tmp_path / "out"
    result = _run(
        [
            "scripts/normalize_nuitka_standalone.py",
            "--src",
            str(src_parent),
            "--output-dir",
            str(output_root),
            "--platform",
            "macos-arm64",
            "--version",
            "0.3.5",
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr

    payload = json.loads(result.stdout.strip().splitlines()[-1])
    expected_dir = output_root / "omnibot-macos-arm64"
    assert Path(payload["binary_path"]) == expected_dir / "omnibot-macos-arm64"
    assert Path(payload["package_dir"]) == expected_dir

    assert (expected_dir / "omnibot-macos-arm64").exists()
    assert (expected_dir / "support.cpython-313.so").exists()
    assert (expected_dir / "lib" / "data.txt").exists()
    assert not src_dist.exists()
    assert (expected_dir / "VERSION").read_text(encoding="utf-8") == "0.3.5"


def test_normalize_auto_discovers_entry_dist_directory(tmp_path: Path):
    src_parent = tmp_path / "dist"
    src_parent.mkdir()
    src_dist = src_parent / "_entry.dist"
    src_dist.mkdir()
    (src_dist / "omnibot-bin").write_bytes(b"#!/bin/sh\necho hi\n")
    (src_dist / "libpython.so").write_bytes(b"so")

    output_root = tmp_path / "out"
    result = _run(
        [
            "scripts/normalize_nuitka_standalone.py",
            "--src",
            str(src_parent),
            "--output-dir",
            str(output_root),
            "--platform",
            "macos-arm64",
            "--version",
            "0.3.6",
        ]
    )
    assert result.returncode == 0, result.stderr
    expected_dir = output_root / "omnibot-macos-arm64"
    assert (expected_dir / "omnibot-macos-arm64").exists()
    assert (expected_dir / "libpython.so").exists()
    assert not src_dist.exists()


def test_normalize_handles_windows_exe_extension(tmp_path: Path):
    src_dist = tmp_path / "omnibot.dist"
    src_dist.mkdir()
    binary = src_dist / "omnibot.exe"
    binary.write_bytes(b"MZ\x00\x00fake pe")

    output_root = tmp_path / "out"
    result = _run(
        [
            "scripts/normalize_nuitka_standalone.py",
            "--src",
            str(src_dist),
            "--output-dir",
            str(output_root),
            "--platform",
            "windows-x64",
            "--version",
            "0.3.5",
            "--json",
        ]
    )
    assert result.returncode == 0, result.stderr

    expected_dir = output_root / "omnibot-windows-x64"
    assert (expected_dir / "omnibot-windows-x64.exe").exists()
    assert (expected_dir / "VERSION").read_text(encoding="utf-8") == "0.3.5"


def test_normalize_fails_when_no_binary_found(tmp_path: Path):
    src_dist = tmp_path / "omnibot.dist"
    src_dist.mkdir()
    (src_dist / "random.so").write_bytes(b"binary")

    result = _run(
        [
            "scripts/normalize_nuitka_standalone.py",
            "--src",
            str(src_dist),
            "--output-dir",
            str(tmp_path / "out"),
            "--platform",
            "macos-arm64",
            "--version",
            "0.3.5",
        ]
    )
    assert result.returncode != 0
    assert "binary" in result.stderr.lower()
