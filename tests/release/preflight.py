#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def run_step(label: str, command: list[str]) -> int:
    print(f"==> {label}: {' '.join(command)}", flush=True)
    proc = subprocess.run(command, cwd=str(ROOT))
    if proc.returncode != 0:
        print(f"FAILED: {label} exited with {proc.returncode}", file=sys.stderr)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Omnibot release preflight tests")
    parser.add_argument("--unit-only", action="store_true", help="run only fast unit tests")
    parser.add_argument("--skip-e2e", action="store_true", help="skip browser-backed E2E gates")
    args = parser.parse_args(argv)

    steps = [("unit", ["uv", "run", "python", "-m", "pytest", "tests/unit", "-q"])]
    if not args.unit_only and not args.skip_e2e:
        steps.extend([
            ("feature matrix", ["python3", "tests/e2e/feature_matrix_test.py", "--no-playwright"]),
            ("full workflow", ["python3", "tests/e2e/full_workflow_test.py", "--no-playwright"]),
        ])

    for label, command in steps:
        code = run_step(label, command)
        if code != 0:
            return code
    print("Release preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
