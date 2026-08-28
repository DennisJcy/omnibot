import os
import sys
import threading
import uuid
from typing import Any

from . import bridge_registry, daemon, ipc_server, native_messaging, paths
from .TMWebDriver import TMWebDriver, log


def persistent_device_id() -> str:
    """Stable per-installation bridge id — a stored random UUID, no hardware probing."""
    path = paths.default_storage_dir() / "device_id"
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except Exception:
        pass
    device_id = uuid.uuid4().hex
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(device_id, encoding="utf-8")
    except Exception as e:
        log(f"Failed to persist device id: {e}")
    return device_id


def device_id_from_hello(message: dict[str, Any]) -> str:
    return str(message.get("deviceId") or persistent_device_id())


def dispatch_action(action_name: str, params: dict[str, Any], driver: TMWebDriver, registry=None) -> dict[str, Any]:
    return daemon.dispatch_action(action_name, params, driver=driver, registry=registry)


def run() -> int:
    first = native_messaging.read_message(sys.stdin.buffer)
    if first is None:
        return 0

    device_id = device_id_from_hello(first)
    driver = TMWebDriver(port=daemon.DEFAULT_WS_PORT, multi_user=False, allowed_tokens=None)
    endpoint = ipc_server.make_endpoint(device_id)
    app = ipc_server.make_app(lambda action, params: dispatch_action(action, params, driver))

    server_thread = threading.Thread(target=lambda: ipc_server.serve_app(app, endpoint), daemon=True)
    server_thread.start()
    bridge_registry.register_bridge({"device_id": device_id, "pid": os.getpid(), "endpoint": endpoint})
    native_messaging.write_message(sys.stdout.buffer, {"type": "status", "status": "ready", "deviceId": device_id, "endpoint": endpoint})

    try:
        while native_messaging.read_message(sys.stdin.buffer) is not None:
            pass
    finally:
        bridge_registry.unregister_bridge(device_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
