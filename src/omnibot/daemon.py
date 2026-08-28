import json
import os
import signal
import threading
from typing import Any, Callable

import bottle

from . import actions
from .defaults import DEFAULT_API_HOST, DEFAULT_API_PORT, DEFAULT_WS_PORT
from .state import log_path, pid_path, state_dir
from .TMWebDriver import TMWebDriver

ActionFunc = Callable[..., dict[str, Any]]


class ThreadedWSGIServer(bottle.ServerAdapter):
    def run(self, handler):
        from socketserver import ThreadingMixIn
        from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

        class Server(ThreadingMixIn, WSGIServer):
            daemon_threads = True

        class QuietHandler(WSGIRequestHandler):
            def log_request(self, *args, **kwargs):
                if not self.quiet:
                    super().log_request(*args, **kwargs)

        QuietHandler.quiet = self.quiet
        self.srv = make_server(self.host, self.port, handler, server_class=Server, handler_class=QuietHandler)
        self.srv.serve_forever()

ACTION_REGISTRY: dict[str, ActionFunc] = {
    "tabs": actions.get_tabs,
    "read": actions.read,
    "execute_js": actions.execute_js,
    "batch": actions.batch,
    "wait": actions.wait,
    "navigate": actions.navigate,
    "screenshot": actions.screenshot,
    "snapshot": actions.snapshot,
    "click": actions.click,
    "dblclick": actions.dblclick,
    "fill": actions.fill,
    "type": actions.type_text,
    "press": actions.press,
    "keyboard": actions.keyboard,
    "keydown": actions.keydown,
    "keyup": actions.keyup,
    "hover": actions.hover,
    "focus": actions.focus,
    "select": actions.select,
    "check": actions.check,
    "uncheck": actions.uncheck,
    "scroll": actions.scroll,
    "scrollintoview": actions.scrollintoview,
    "drag": actions.drag,
    "upload": actions.upload,
    "get": actions.get,
    "is": actions.is_state,
    "find": actions.find,
    "close": actions.close,
    "tab": actions.tab,
    "window": actions.window,
    "frame": actions.frame,
    "back": actions.back,
    "forward": actions.forward,
    "reload": actions.reload_page,
    "pushstate": actions.pushstate,
    "mouse_click": actions.mouse_click,
    "mouse_move": actions.mouse_move,
    "mouse_scroll": actions.mouse_scroll,
    "mouse_drag": actions.mouse_drag,
    "verify_inspect": actions.verify_inspect,
    "dom_visible": actions.dom_visible,
    "dom_click": actions.dom_click,
    "dom_dblclick": actions.dom_dblclick,
    "dom_scroll": actions.dom_scroll,
    "console_logs": actions.console_logs,
    "console_errors": actions.console_errors,
    "console_clear": actions.console_clear,
    "dialog_logs": actions.dialog_logs,
    "dialog_clear": actions.dialog_clear,
    "dialog_handle": actions.dialog_handle,
    "network_logs": actions.network_logs,
    "network_summary": actions.network_summary_action,
    "network_capture_start": actions.network_capture_start,
    "network_capture_stop": actions.network_capture_stop,
    "network_capture_clear": actions.network_capture_clear,
    "raw_cdp": actions.raw_cdp,
    "clipboard_read": actions.clipboard_read,
    "clipboard_write": actions.clipboard_write,
    "viewport_get": actions.viewport_get,
    "viewport_set": actions.viewport_set,
    "assets_list": actions.assets_list,
    "assets_export": actions.assets_export,
    "browser_list": actions.browser_list,
    "browser_current": actions.browser_current,
    "browser_claim": actions.browser_claim,
    "browser_release": actions.browser_release,
    "history_search": actions.history_search,
    "bookmarks_tree": actions.bookmarks_tree,
    "downloads_search": actions.downloads_search,
    "downloads_open": actions.downloads_open,
    "sessions_recently_closed": actions.sessions_recently_closed,
    "top_sites": actions.top_sites,
    "browser_extensions": actions.browser_extensions,
    "browser_content_settings": actions.browser_content_settings,
    "browser_mouse_visual_state": actions.browser_mouse_visual_state,
    "browser_notify": actions.browser_notify,
    "session_name": actions.session_name,
    "session_list": actions.session_list,
    "record_start": actions.record_start,
    "record_stop": actions.record_stop,
    "replay": actions.replay,
    "trace_start": actions.trace_start,
    "trace_stop": actions.trace_stop,
    "visibility_status": actions.visibility_status,
    "visibility_set": actions.visibility_set,
    "visibility_launch": actions.visibility_launch,
}

_OBSERVABILITY_CONTROL_ACTIONS = {
    "record_start",
    "record_stop",
    "trace_start",
    "trace_stop",
}


def json_response(payload: dict[str, Any]) -> str:
    bottle.response.content_type = "application/json"
    return json.dumps(payload, ensure_ascii=False, default=str)


def _error_code(result: dict[str, Any], driver: TMWebDriver) -> str | None:
    if result.get("error_code"):
        return str(result["error_code"])
    status = result.get("status")
    if status not in {"error", "timeout"}:
        return None
    if status == "timeout":
        return "ACTION_TIMEOUT"
    message = str(result.get("msg") or result.get("error") or "")
    lowered = message.lower()
    if "unknown action" in lowered:
        return "UNKNOWN_ACTION"
    if "no browser tabs connected" in lowered:
        counter = getattr(driver, "count_extension_clients", None)
        if callable(counter):
            try:
                if int(counter()) == 0:
                    return "EXTENSION_DISCONNECTED"
            except Exception:
                pass
        return "NO_BROWSER_TABS"
    if "not found or ambiguous" in lowered or "no tab with id" in lowered or "no tab with given id" in lowered:
        return "TAB_NOT_FOUND"
    if "extension" in lowered and ("not connected" in lowered or "disconnected" in lowered):
        return "EXTENSION_DISCONNECTED"
    return "ACTION_FAILED"


def dispatch_action(action_name: str, params: dict[str, Any], driver: TMWebDriver, registry: dict[str, ActionFunc] | None = None) -> dict[str, Any]:
    actual_registry = registry or ACTION_REGISTRY
    func = actual_registry.get(action_name)
    if func is None:
        return {"status": "error", "error_code": "UNKNOWN_ACTION", "msg": f"Unknown action: {action_name}"}
    original_params = dict(params)
    action_params = dict(original_params)
    token = action_params.pop("_token", None)
    if token:
        action_params["token"] = token
    try:
        result = func(driver, **action_params)
    except Exception as exc:
        result = {"status": "error", "msg": str(exc)}
    code = _error_code(result, driver)
    if code:
        result["error_code"] = code

    if action_name not in _OBSERVABILITY_CONTROL_ACTIONS:
        try:
            ctx = driver.get_context(token)
            recorded_params = {key: value for key, value in original_params.items() if key != "_token"}
            if ctx.recording:
                ctx.recorded_actions.append({"action": action_name, "params": recorded_params})
            if ctx.trace_enabled:
                from . import trace

                ctx.trace_events.append(trace.trace_event(action_name, recorded_params, result))
        except Exception:
            # Observability must never change the result of the browser action.
            pass
    return result


def make_app(driver: TMWebDriver) -> bottle.Bottle:
    app = bottle.Bottle()

    @app.get("/api/health")
    def health():
        sessions = driver.get_all_sessions()
        return json_response({"status": "ok", "pid": os.getpid(), "tabs_count": len(sessions), "extension_clients_count": driver.count_extension_clients(), "extension_versions": driver.extension_versions(), "ws_port": driver.port})

    @app.post("/api/actions/<action_name>")
    def run_action(action_name: str):
        payload = bottle.request.json or {}
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            return json_response({"status": "error", "msg": "params must be an object"})
        return json_response(dispatch_action(action_name, params, driver))

    @app.post("/api/stop")
    def stop():
        def shutdown():
            os.kill(os.getpid(), signal.SIGTERM)

        threading.Timer(0.2, shutdown).start()
        return json_response({"status": "stopping", "pid": os.getpid()})

    return app


def run_foreground(api_host: str = DEFAULT_API_HOST, api_port: int = DEFAULT_API_PORT, ws_port: int = DEFAULT_WS_PORT) -> None:
    driver = TMWebDriver(port=ws_port, multi_user=True, allowed_tokens=None)
    pid_path().write_text(str(os.getpid()), encoding="utf-8")
    try:
        bottle.run(make_app(driver), host=api_host, port=api_port, quiet=True, server=ThreadedWSGIServer)
    finally:
        try:
            pid_path().unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    run_foreground()
