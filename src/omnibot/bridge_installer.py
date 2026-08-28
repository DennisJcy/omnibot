import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from . import bridge_registry
from .paths import default_storage_dir


NATIVE_HOST_NAME = "ai.omnibot.bridge"
BROWSER_LABELS = {
    "chrome": "Chrome",
    "edge": "Edge",
    "brave": "Brave",
    "arc": "Arc",
}


def install_dir() -> Path:
    path = default_storage_dir() / "native-bridge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_manifest(launcher_path: Path, extension_id: str) -> dict[str, Any]:
    return {
        "name": NATIVE_HOST_NAME,
        "description": "omnibot native bridge for browser extension communication",
        "path": str(launcher_path),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }


def normalize_browser(browser: str | None) -> str | None:
    if not browser:
        return None
    value = browser.strip().lower()
    return value if value in BROWSER_LABELS else value


def browser_manifest_path(browser: str) -> Path:
    browser = normalize_browser(browser) or "chrome"
    home = Path.home()
    filename = f"{NATIVE_HOST_NAME}.json"
    if sys.platform == "darwin":
        app_support = home / "Library" / "Application Support"
        dirs = {
            "chrome": app_support / "Google" / "Chrome" / "NativeMessagingHosts",
            "edge": app_support / "Microsoft Edge" / "NativeMessagingHosts",
            "brave": app_support / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
            "arc": app_support / "Arc" / "NativeMessagingHosts",
        }
        return dirs.get(browser, dirs["chrome"]) / filename
    if sys.platform.startswith("linux"):
        config = home / ".config"
        dirs = {
            "chrome": config / "google-chrome" / "NativeMessagingHosts",
            "edge": config / "microsoft-edge" / "NativeMessagingHosts",
            "brave": config / "BraveSoftware" / "Brave-Browser" / "NativeMessagingHosts",
            "arc": config / "Arc" / "NativeMessagingHosts",
        }
        return dirs.get(browser, dirs["chrome"]) / filename
    return install_dir() / filename


def extension_id_from_client_id(client_id: str | None, browser: str | None = None) -> str | None:
    if not client_id:
        return None
    parts = str(client_id).split("-", 2)
    if len(parts) < 3:
        return None
    client_browser, extension_id, _ = parts
    if browser and normalize_browser(client_browser) != normalize_browser(browser):
        return None
    return extension_id or None


def find_extension_id(sessions: list[dict[str, Any]], browser: str | None = None) -> str | None:
    target_browser = normalize_browser(browser)
    fallback: str | None = None
    for session in sessions:
        session_browser = normalize_browser(str(session.get("browser") or ""))
        explicit = session.get("extension_id") or session.get("extensionId")
        if explicit:
            if not target_browser or not session_browser or session_browser == target_browser:
                return str(explicit)
            fallback = fallback or str(explicit)
        parsed = extension_id_from_client_id(str(session.get("client_id") or ""), browser=target_browser)
        if parsed:
            return parsed
        parsed_any = extension_id_from_client_id(str(session.get("client_id") or ""))
        if parsed_any:
            fallback = fallback or parsed_any
    return fallback if not target_browser else None


def write_launcher(directory: Path, executable: str | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    exe = executable or sys.executable
    if os.name == "nt":
        path = directory / "omnibot-bridge-host.bat"
        path.write_text(f'@echo off\r\n"{exe}" bridge-host %*\r\n', encoding="utf-8")
        return path
    path = directory / "omnibot-bridge-host.sh"
    path.write_text(f'#!/bin/sh\nexec "{exe}" bridge-host "$@"\n', encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def is_executable_accepted_by_gatekeeper(executable: str) -> bool:
    if sys.platform != "darwin":
        return True
    try:
        result = subprocess.run(
            ["spctl", "--assess", "--type", "execute", "--verbose=4", executable],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return False
    return result.returncode == 0


def install_bridge(extension_id: str, browser: str | None = None) -> dict[str, Any]:
    directory = install_dir()
    executable = sys.executable
    if not is_executable_accepted_by_gatekeeper(executable):
        raise RuntimeError(
            "Native bridge executable is not accepted by macOS Gatekeeper. "
            "Use a Developer ID signed/notarized omnibot build, or remove the bridge and use daemon/WebSocket mode for local testing."
        )
    launcher = write_launcher(directory)
    manifest = build_manifest(launcher, extension_id)
    manifest_path = browser_manifest_path(browser or "chrome") if browser else directory / f"{NATIVE_HOST_NAME}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"status": "success", "manifest": str(manifest_path), "launcher": str(launcher), "browser": browser, "extension_id": extension_id}


def wait_for_bridge(timeout: float = 60.0, interval: float = 1.0) -> dict[str, Any] | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        bridges = bridge_registry.list_bridges()
        if bridges:
            return bridges[0]
        time.sleep(interval)
    return None


def uninstall_bridge(browser: str | None = None) -> dict[str, Any]:
    manifest_path = browser_manifest_path(browser) if browser else install_dir() / f"{NATIVE_HOST_NAME}.json"
    manifest_path.unlink(missing_ok=True)
    return {"status": "success", "browser": browser}
