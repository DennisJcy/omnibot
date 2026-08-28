import os
import socket
import threading
from pathlib import Path
from typing import Callable

import bottle

from .paths import default_storage_dir


def ipc_dir() -> Path:
    path = default_storage_dir() / "ipc"
    path.mkdir(parents=True, exist_ok=True)
    return path


def make_endpoint(device_id: str, base_dir: Path | None = None) -> str:
    if os.name == "posix":
        root = base_dir or ipc_dir()
        root.mkdir(parents=True, exist_ok=True)
        safe = "".join(ch for ch in device_id if ch.isalnum() or ch in "._-") or "default"
        return f"unix:{root / f'{safe}.sock'}"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()
    return f"tcp:{host}:{port}"


def endpoint_to_url(endpoint: str) -> str:
    if endpoint.startswith("tcp:"):
        return "http://" + endpoint.removeprefix("tcp:")
    if endpoint.startswith("unix:"):
        return "http://localhost"
    raise ValueError(f"Unsupported endpoint: {endpoint}")


def make_app(dispatch: Callable[[str, dict], dict]) -> bottle.Bottle:
    app = bottle.Bottle()

    @app.get("/api/health")
    def health():
        bottle.response.content_type = "application/json"
        return {"status": "ok"}

    @app.post("/api/actions/<action_name>")
    def action(action_name: str):
        payload = bottle.request.json or {}
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            bottle.response.status = 400
            return {"status": "error", "msg": "params must be an object"}
        return dispatch(action_name, params)

    return app


def serve_app(app: bottle.Bottle, endpoint: str) -> None:
    if endpoint.startswith("tcp:"):
        host, port = endpoint.removeprefix("tcp:").rsplit(":", 1)
        bottle.run(app, host=host, port=int(port), quiet=True)
        return
    if endpoint.startswith("unix:"):
        from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server
        from socketserver import UnixStreamServer

        socket_path = endpoint.removeprefix("unix:")
        Path(socket_path).unlink(missing_ok=True)

        class UnixWSGIServer(UnixStreamServer, WSGIServer):
            address_family = socket.AF_UNIX

        class QuietHandler(WSGIRequestHandler):
            def address_string(self):
                return "local"

            def log_request(self, *args):
                pass

        make_server(socket_path, 0, app, server_class=UnixWSGIServer, handler_class=QuietHandler).serve_forever()
        return
    raise ValueError(f"Unsupported endpoint: {endpoint}")
