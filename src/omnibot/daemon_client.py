import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from .defaults import DEFAULT_API_HOST, DEFAULT_API_PORT, DEFAULT_WS_PORT
from .state import log_path

_RETRY_SAFE_ACTIONS = {
    "tabs",
    "read",
    "wait",
    "screenshot",
    "snapshot",
    "get",
    "is",
    "verify_inspect",
    "console_logs",
    "console_errors",
    "network_logs",
    "network_summary",
    "viewport_get",
    "assets_list",
    "browser_list",
    "browser_current",
    "history_search",
    "bookmarks_tree",
    "downloads_search",
    "sessions_recently_closed",
    "top_sites",
    "browser_extensions",
    "browser_content_settings",
    "browser_mouse_visual_state",
}


def _bypass_proxy_for_local_daemon() -> None:
    """Keep local CLI↔daemon traffic off user-configured HTTP proxies."""
    local_hosts = "127.0.0.1,localhost"
    for key in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(key, "")
        entries = {item.strip() for item in current.split(",") if item.strip()}
        entries.update(local_hosts.split(","))
        os.environ[key] = ",".join(sorted(entries))


_bypass_proxy_for_local_daemon()


def daemon_url(host: str = DEFAULT_API_HOST, port: int = DEFAULT_API_PORT) -> str:
    return f"http://{host}:{port}"


def _is_packaged_runtime() -> bool:
    # Current releases ship as a standalone binary. Source checkouts should keep
    # using `python -m omnibot`, while packaged binaries must invoke themselves
    # directly because Python-style `-m` execution is rejected.
    # Note: sys.executable in Nuitka standalone points to a non-existent python3
    # binary, so we check sys.argv[0] instead.
    exe = os.path.basename(sys.argv[0]).lower() if sys.argv else ""
    return bool(exe) and not exe.startswith("python")


def _self_executable() -> str:
    """Return the path to invoke this binary again."""
    return os.path.realpath(sys.argv[0]) if sys.argv else sys.executable


def build_daemon_command(api_port: int = DEFAULT_API_PORT, ws_port: int = DEFAULT_WS_PORT) -> list[str]:
    if _is_packaged_runtime():
        return [_self_executable(), "--api-port", str(api_port), "--ws-port", str(ws_port), "daemon", "run"]
    return [sys.executable, "-m", "omnibot", "--api-port", str(api_port), "--ws-port", str(ws_port), "daemon", "run"]


def health(base_url: str, timeout: float = 1.5) -> dict[str, Any] | None:
    try:
        response = requests.get(f"{base_url}/api/health", timeout=timeout)
        if response.ok:
            return response.json()
    except Exception:
        return None
    return None


def _port_is_open(host: str = DEFAULT_API_HOST, port: int = DEFAULT_API_PORT, timeout: float = 0.3) -> bool:
    try:
        conn = socket.create_connection((host, port), timeout=timeout)
    except OSError:
        return False
    conn.close()
    return True


def _rotate_logs(retention_days: int = 2) -> None:
    log_file = log_path()
    if not log_file.exists():
        return
    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
    if mtime.date() < datetime.now().date():
        rotated = log_file.with_name(f"daemon.{mtime.strftime('%Y-%m-%d')}.log")
        log_file.rename(rotated)
    cutoff = datetime.now() - timedelta(days=retention_days)
    for old in log_file.parent.glob("daemon.*.log"):
        try:
            date_str = old.stem.split(".", 1)[1]
            file_date = datetime.strptime(date_str, "%Y-%m-%d")
            if file_date < cutoff:
                old.unlink()
        except (ValueError, IndexError, OSError):
            pass


def start_daemon(api_port: int = DEFAULT_API_PORT, ws_port: int = DEFAULT_WS_PORT) -> subprocess.Popen:
    _rotate_logs()
    log_file = log_path().open("ab")
    return subprocess.Popen(
        build_daemon_command(api_port=api_port, ws_port=ws_port),
        stdout=log_file,
        stderr=log_file,
        stdin=subprocess.DEVNULL,
        close_fds=True,
    )


def ensure_daemon(api_port: int = DEFAULT_API_PORT, ws_port: int = DEFAULT_WS_PORT, timeout: float = 8.0) -> str:
    base_url = daemon_url(port=api_port)
    if health(base_url):
        return base_url
    if _port_is_open(port=api_port):
        raise RuntimeError(
            f"omnibot daemon is running but not responding to health checks at {base_url}; "
            "a long action may be in progress. Wait for it to finish or stop the daemon explicitly."
        )
    proc = start_daemon(api_port=api_port, ws_port=ws_port)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if health(base_url):
            return base_url
        if proc.poll() is not None and health(base_url):
            return base_url
        time.sleep(0.2)
    raise RuntimeError(f"omnibot daemon did not become ready at {base_url}. Check {log_path()}")


def bridge_base_url() -> str | None:
    from . import bridge_registry, ipc_server

    bridges = bridge_registry.list_bridges()
    if not bridges:
        return None
    return ipc_server.endpoint_to_url(str(bridges[0]["endpoint"]))


def ensure_runtime(api_port: int = DEFAULT_API_PORT, ws_port: int = DEFAULT_WS_PORT, timeout: float = 8.0) -> str:
    bridge_url = bridge_base_url()
    if bridge_url and health(bridge_url):
        return bridge_url
    return ensure_daemon(api_port=api_port, ws_port=ws_port, timeout=timeout)


def _action_is_retry_safe(action: str, params: dict[str, Any]) -> bool:
    if action in _RETRY_SAFE_ACTIONS:
        return True
    # `goto` maps to navigate with new_tab=False. Replaying the same URL in
    # the same tab is idempotent; new-tab navigation is deliberately excluded.
    return action == "navigate" and params.get("new_tab") is False


def _wait_for_runtime_recovery(base_url: str, *, require_tabs: bool, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = health(base_url, timeout=min(0.5, max(0.1, deadline - time.monotonic())))
        if status and (not require_tabs or int(status.get("tabs_count", 0)) > 0):
            return True
        time.sleep(0.1)
    return False


def call_action(action: str, params: dict[str, Any], base_url: str, timeout: float = 60) -> dict[str, Any]:
    url = f"{base_url}/api/actions/{action}"

    def post() -> dict[str, Any]:
        response = requests.post(url, json={"params": params}, timeout=timeout)
        response.raise_for_status()
        return response.json()

    retry_safe = _action_is_retry_safe(action, params)
    try:
        result = post()
    except (requests.exceptions.ConnectionError, requests.exceptions.ChunkedEncodingError):
        if not retry_safe or not _wait_for_runtime_recovery(base_url, require_tabs=False):
            raise
        return post()

    message = str(result.get("msg", "")) if isinstance(result, dict) else ""
    if (
        retry_safe
        and result.get("status") == "error"
        and ("No browser tabs connected" in message or "extension is not connected" in message)
        and _wait_for_runtime_recovery(base_url, require_tabs=True)
    ):
        return post()
    return result


def stop_daemon(base_url: str) -> dict[str, Any]:
    response = requests.post(f"{base_url}/api/stop", timeout=5)
    response.raise_for_status()
    return response.json()


def read_pid() -> int | None:
    from .state import pid_path

    try:
        return int(pid_path().read_text(encoding="utf-8").strip())
    except Exception:
        return None
