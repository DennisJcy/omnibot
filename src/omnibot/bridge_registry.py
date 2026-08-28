import json
import os
from pathlib import Path
from typing import Any

from .paths import default_storage_dir


def registry_dir() -> Path:
    path = default_storage_dir() / "bridges"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _bridge_path(device_id: str) -> Path:
    safe = "".join(ch for ch in device_id if ch.isalnum() or ch in "._-") or "default"
    return registry_dir() / f"{safe}.json"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def register_bridge(info: dict[str, Any]) -> None:
    device_id = str(info["device_id"])
    payload = dict(info)
    payload["device_id"] = device_id
    _bridge_path(device_id).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def unregister_bridge(device_id: str) -> None:
    try:
        _bridge_path(device_id).unlink()
    except FileNotFoundError:
        pass


def list_bridges() -> list[dict[str, Any]]:
    bridges: list[dict[str, Any]] = []
    for path in registry_dir().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0))
        except Exception:
            path.unlink(missing_ok=True)
            continue
        if not _pid_alive(pid):
            path.unlink(missing_ok=True)
            continue
        bridges.append(data)
    return sorted(bridges, key=lambda item: str(item.get("device_id", "")))
