import json

from omnibot import daemon
from omnibot.TMWebDriver import Session, TMWebDriver, TokenManager, UserContext


def test_dispatch_rejects_unknown_action():
    result = daemon.dispatch_action("missing", {}, driver=object(), registry={})

    assert result["status"] == "error"
    assert result["error_code"] == "UNKNOWN_ACTION"
    assert "Unknown action" in result["msg"]


def test_dispatch_distinguishes_disconnected_extension_from_empty_tabs():
    class Driver:
        def count_extension_clients(self):
            return 0

        def get_context(self, token=None):
            raise RuntimeError("observability unavailable")

    result = daemon.dispatch_action(
        "tabs",
        {},
        driver=Driver(),
        registry={"tabs": lambda driver: {"status": "error", "msg": "No browser tabs connected."}},
    )

    assert result["error_code"] == "EXTENSION_DISCONNECTED"


def test_dispatch_calls_registered_action():
    registry = {"navigate": lambda driver, url, new_tab=True: {"status": "success", "url": url, "new_tab": new_tab}}

    result = daemon.dispatch_action("navigate", {"url": "https://example.com", "new_tab": False}, driver=object(), registry=registry)

    assert result == {"status": "success", "url": "https://example.com", "new_tab": False}


def test_json_response_serializes_unicode():
    body = daemon.json_response({"status": "success", "msg": "已扫描"})

    assert json.loads(body) == {"status": "success", "msg": "已扫描"}


def test_dispatch_injects_request_token_without_exposing_payload_key():
    seen = {}

    def action(driver, *, token=None):
        seen["token"] = token
        return {"status": "success"}

    result = daemon.dispatch_action("get", {"_token": "worker-a"}, driver=object(), registry={"get": action})

    assert result == {"status": "success"}
    assert seen == {"token": "worker-a"}


def test_dispatch_records_action_params_when_recording():
    driver = object.__new__(TMWebDriver)
    ctx = UserContext("worker-a")
    ctx.recording = True
    driver.get_context = lambda token=None: ctx

    result = daemon.dispatch_action(
        "fill",
        {"selector": "#email", "value": "record@example.com", "_token": "worker-a"},
        driver=driver,
        registry={"fill": lambda driver, **kwargs: {"status": "success", "value": kwargs["value"]}},
    )

    assert result["status"] == "success"
    assert ctx.recorded_actions == [
        {"action": "fill", "params": {"selector": "#email", "value": "record@example.com"}}
    ]


def test_dispatch_traces_action_and_does_not_record_control_actions():
    driver = object.__new__(TMWebDriver)
    ctx = UserContext("worker-a")
    ctx.recording = True
    ctx.trace_enabled = True
    driver.get_context = lambda token=None: ctx

    result = daemon.dispatch_action(
        "snapshot",
        {"_token": "worker-a"},
        driver=driver,
        registry={"snapshot": lambda driver, **kwargs: {"status": "success", "content": "ok"}},
    )

    assert result["status"] == "success"
    assert ctx.recorded_actions[0]["action"] == "snapshot"
    assert ctx.trace_events[0]["action"] == "snapshot"
    assert ctx.trace_events[0]["result"] == result


def test_dispatch_does_not_record_recording_control_actions():
    driver = object.__new__(TMWebDriver)
    ctx = UserContext("worker-a")
    ctx.recording = True
    driver.get_context = lambda token=None: ctx

    daemon.dispatch_action("record_start", {"_token": "worker-a"}, driver=driver, registry={"record_start": lambda driver, **kwargs: {"status": "success"}})
    daemon.dispatch_action("record_stop", {"_token": "worker-a"}, driver=driver, registry={"record_stop": lambda driver, **kwargs: {"status": "success"}})

    assert ctx.recorded_actions == []


def test_run_foreground_uses_threaded_http_server(monkeypatch):
    calls = {}

    class Driver:
        pass

    class PidPath:
        def write_text(self, value, encoding="utf-8"):
            calls["pid"] = value

        def unlink(self):
            calls["unlinked"] = True

    def fake_bottle_run(app, host, port, quiet=True, server=None):
        calls["host"] = host
        calls["port"] = port
        calls["quiet"] = quiet
        calls["server"] = server

    monkeypatch.setattr(daemon, "TMWebDriver", lambda port, multi_user, allowed_tokens: Driver())
    monkeypatch.setattr(daemon, "pid_path", lambda: PidPath())
    monkeypatch.setattr(daemon.bottle, "run", fake_bottle_run)

    daemon.run_foreground(api_host="127.0.0.1", api_port=19000, ws_port=19001)

    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 19000
    assert calls["quiet"] is True
    assert calls["server"] == daemon.ThreadedWSGIServer
    assert calls["unlinked"] is True


def test_full_scan_action_is_not_registered():
    assert "full_scan" not in daemon.ACTION_REGISTRY


def test_scan_action_is_not_registered():
    assert "scan" not in daemon.ACTION_REGISTRY


def test_multi_user_contexts_share_extension_tabs_but_keep_state_isolated():
    driver = object.__new__(TMWebDriver)
    driver.multi_user = True
    driver.is_remote = False
    driver.token_manager = TokenManager()
    default_ctx = UserContext("__default__")
    worker_a_ctx = UserContext("worker-a")
    worker_b_ctx = UserContext("worker-b")
    driver.token_manager.contexts = {
        "__default__": default_ctx,
        "worker-a": worker_a_ctx,
        "worker-b": worker_b_ctx,
    }

    default_ctx.sessions["browser:tab-a"] = Session("browser:tab-a", {"url": "https://a.test", "type": "ext_ws", "tab_id": "tab-a", "client_id": "browser"})
    default_ctx.sessions["browser:tab-b"] = Session("browser:tab-b", {"url": "https://b.test", "type": "ext_ws", "tab_id": "tab-b", "client_id": "browser"})
    worker_a_ctx.claimed_tabs = {"browser:tab-a"}
    worker_b_ctx.claimed_tabs = {"browser:tab-b"}

    assert {tab["id"] for tab in driver.get_all_sessions(token="worker-a")} == {"browser:tab-a", "browser:tab-b"}
    assert {tab["id"] for tab in driver.get_all_sessions(token="worker-b")} == {"browser:tab-a", "browser:tab-b"}
    assert driver.get_context("worker-a").claimed_tabs == {"browser:tab-a"}
    assert driver.get_context("worker-b").claimed_tabs == {"browser:tab-b"}


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
