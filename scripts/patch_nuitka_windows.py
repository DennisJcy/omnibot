#!/usr/bin/env python3
"""Patch Nuitka on Windows to fix UnicodeDecodeError in getDistributionName.

Nuitka 4.x calls ``hasattr(distribution, "metadata")`` which triggers Python's
``importlib.metadata.PathDistribution.metadata`` property. On Windows with
Python 3.13+, this internally calls ``read_text('')`` on the ``.dist-info``
directory, which can return non-UTF-8 data and raise ``UnicodeDecodeError``.

This script wraps the metadata access in a try-except so the compilation
can proceed. Run this once after creating the Windows venv:

    python scripts/patch_nuitka_windows.py
"""
from __future__ import annotations

import pathlib
import sys


def find_nuitka_distributions_py() -> pathlib.Path:
    candidate = pathlib.Path(sys.prefix) / "Lib" / "site-packages" / "nuitka" / "utils" / "Distributions.py"
    if candidate.exists():
        return candidate
    for p in sys.path:
        f = pathlib.Path(p) / "nuitka" / "utils" / "Distributions.py"
        if f.exists():
            return f
    raise FileNotFoundError("Cannot locate nuitka/utils/Distributions.py")


def patch_file(filepath: pathlib.Path) -> bool:
    text = filepath.read_text(encoding="utf-8")
    old = (
        '    if hasattr(distribution, "metadata"):\n'
        '        result = distribution.metadata["Name"]'
    )
    new = (
        "    try:\n"
        '        result = distribution.metadata["Name"]\n'
        "    except (UnicodeDecodeError, OSError, AttributeError):\n"
        "        result = None"
    )
    if new.strip() in text:
        print(f"Already patched: {filepath}")
        return False
    if old not in text:
        print(f"WARN: expected pattern not found in {filepath}, skipping")
        return False
    text = text.replace(old, new, 1)
    filepath.write_text(text, encoding="utf-8")
    print(f"Patched OK: {filepath}")
    return True


def main() -> None:
    target = find_nuitka_distributions_py()
    patch_file(target)


if __name__ == "__main__":
    main()
