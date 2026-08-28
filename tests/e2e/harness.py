from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = ROOT / "tests"
REPORT_ROOT = TESTS_ROOT / "reports"
TIMEOUT_S = 30


def resolve_omnibot_cmd() -> list[str]:
    raw = os.environ.get("OMNIBOT_CMD") or os.environ.get("OMNIBOT_BIN")
    if raw:
        return shlex.split(raw)
    repo_venv = ROOT / ".venv" / "bin" / "omnibot"
    if repo_venv.exists():
        return [str(repo_venv)]
    return ["uv", "run", "omnibot"]


OMNIBOT_CMD = resolve_omnibot_cmd()


def timestamped_report_dir(prefix: str) -> Path:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    path = REPORT_ROOT / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_omnibot(args: list[str], *, token: str = "", timeout: int = TIMEOUT_S) -> dict[str, Any]:
    env = os.environ.copy()
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    if token:
        env["OMNIBOT_SESSION_TOKEN"] = token
    cmd = OMNIBOT_CMD + args
    try:
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"status": "error", "msg": "command timed out", "cmd": cmd}
    if proc.returncode != 0:
        return {"status": "error", "msg": proc.stderr.strip() or proc.stdout.strip(), "cmd": cmd, "returncode": proc.returncode}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "success", "output": proc.stdout, "stderr": proc.stderr}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return None


@dataclass
class FixtureServer:
    root: tempfile.TemporaryDirectory[str]
    server: ThreadingHTTPServer
    thread: threading.Thread
    base_url: str

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.root.cleanup()


def start_fixture_server(files: dict[str, str]) -> FixtureServer:
    root = tempfile.TemporaryDirectory()
    root_path = Path(root.name)
    for name, content in files.items():
        target = root_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    handler = lambda *args, **kwargs: QuietHandler(*args, directory=root.name, **kwargs)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return FixtureServer(root=root, server=server, thread=thread, base_url=f"http://{host}:{port}")


def extract_tab_id(result: dict[str, Any]) -> str:
    tab = result.get("tab") if isinstance(result.get("tab"), dict) else {}
    return str(result.get("tab_id") or result.get("id") or tab.get("id") or tab.get("tab_id") or "")


def assert_success(result: dict[str, Any], label: str) -> None:
    if result.get("status") == "error":
        raise AssertionError(f"{label} failed: {result}")
