#!/usr/bin/env python3
"""Normalize a Nuitka ``--mode=standalone`` build output into the directory
layout that the npm platform packages expect.

Nuitka standalone writes its bundle as ``omnibot.dist/`` next to the source
project: an executable (or ``omnibot.exe``) and a tree of ``.so`` / ``.pyd``
/ supporting files. The npm packages want::

    dist/omnibot-<platform>/
        omnibot-<platform>(.exe)        # renamed binary
        *.so, *.pyd, lib/, ...          # everything else
        VERSION                         # plain text file

This script consumes the ``omnibot.dist/`` directory, moves it into the
package directory, renames the binary to a stable platform name, and
writes a ``VERSION`` file.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


SUPPORTED_PLATFORMS = (
    "macos-arm64",
    "macos-x64",
    "linux-x64",
    "windows-x64",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True, help="Path to the Nuitka omnibot.dist/ directory.")
    parser.add_argument("--output-dir", required=True, help="Output root; the platform package directory will be created here.")
    parser.add_argument("--platform", required=True, choices=SUPPORTED_PLATFORMS, help="Target platform identifier.")
    parser.add_argument("--version", required=True, help="Version string written to VERSION file.")
    parser.add_argument("--binary-name", default=None, help="Override the binary name (defaults to omnibot-<platform>).")
    parser.add_argument("--json", action="store_true", help="Emit the result summary as JSON on the last line of stdout.")
    return parser.parse_args(argv)


def find_binary(src: Path, platform: str) -> Path:
    if platform.startswith("windows"):
        candidates = [src / "omnibot-bin.exe", src / "omnibot.exe"]
    else:
        candidates = [src / "omnibot-bin", src / "omnibot", src / "omnibot.bin"]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"No binary found in {src} for platform {platform}. "
        f"Expected one of: {[str(c) for c in candidates]}"
    )


def _resolve_source(src: Path, output_dir: Path) -> Path:
    """Return the actual standalone directory given the user-supplied --src.

    Accepts either an explicit ``omnibot.dist/`` (legacy Nuitka) or
    ``<entry>.dist/`` (current Nuitka) directory, or a parent that
    contains exactly one ``*.dist`` directory.
    """
    if src.is_dir() and src.name.endswith(".dist"):
        return src
    if src.is_dir():
        candidates = sorted(p for p in src.iterdir() if p.is_dir() and p.name.endswith(".dist"))
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise FileNotFoundError(
                f"No '*.dist' directory found inside {src}. Pass --src directly to a '*.dist' directory."
            )
        names = ", ".join(c.name for c in candidates)
        raise ValueError(f"Multiple '*.dist' directories found inside {src}: {names}. Pass --src to one explicitly.")
    raise FileNotFoundError(f"Source path does not exist: {src}")


def normalize(args: argparse.Namespace) -> dict[str, str]:
    output_root = Path(args.output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    src = _resolve_source(Path(args.src).resolve(), output_root)

    binary_name = args.binary_name or f"omnibot-{args.platform}"
    if args.platform.startswith("windows") and not binary_name.endswith(".exe"):
        binary_name = f"{binary_name}.exe"

    package_dir = output_root / f"omnibot-{args.platform}"
    if package_dir.exists():
        shutil.rmtree(package_dir)
    package_dir.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(str(src), str(package_dir))

    binary_src = find_binary(package_dir, args.platform)
    binary_dest = package_dir / binary_name
    if binary_src != binary_dest:
        binary_src.rename(binary_dest)
        try:
            binary_dest.chmod(0o755)
        except PermissionError:
            pass

    (package_dir / "VERSION").write_text(args.version, encoding="utf-8")

    return {
        "package_dir": str(package_dir),
        "binary_path": str(binary_dest),
        "platform": args.platform,
        "version": args.version,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = normalize(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result))
    else:
        print(f"package_dir: {result['package_dir']}")
        print(f"binary_path: {result['binary_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
