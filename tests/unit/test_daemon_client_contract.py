import sys
import socket

import pytest

from omnibot import daemon_client


def test_daemon_url_uses_default_port():
    assert daemon_client.daemon_url() == "http://127.0.0.1:18764"


def test_build_daemon_command_uses_module_in_source_mode(monkeypatch):
    monkeypatch.setattr(daemon_client, "_is_packaged_runtime", lambda: False)

    cmd = daemon_client.build_daemon_command(api_port=19000, ws_port=19001)

    assert cmd[:3] == [sys.executable, "-m", "omnibot"]
    assert cmd[3:] == ["--api-port", "19000", "--ws-port", "19001", "daemon", "run"]


def test_build_daemon_command_uses_executable_in_packaged_mode(monkeypatch):
    monkeypatch.setattr(daemon_client, "_is_packaged_runtime", lambda: True)
    monkeypatch.setattr(daemon_client, "_self_executable", lambda: "/usr/local/bin/omnibot")

    cmd = daemon_client.build_daemon_command(api_port=19000, ws_port=19001)

    assert cmd == ["/usr/local/bin/omnibot", "--api-port", "19000", "--ws-port", "19001", "daemon", "run"]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


def test_ensure_runtime_calls_ensure_daemon(monkeypatch):
    calls = []

    def fake_ensure_daemon(api_port=18764, ws_port=18765, timeout=8.0):
        calls.append((api_port, ws_port, timeout))
        return "http://127.0.0.1:18764"

    monkeypatch.setattr(daemon_client, "ensure_daemon", fake_ensure_daemon)

    assert daemon_client.ensure_runtime(api_port=18764, ws_port=18765, timeout=3.0) == "http://127.0.0.1:18764"
    assert calls == [(18764, 18765, 3.0)]


def test_ensure_daemon_reports_busy_daemon_without_starting_duplicate(monkeypatch):
    starts = []

    def fake_create_connection(address, timeout=0.0):
        assert address == ("127.0.0.1", 18764)
        assert timeout <= 0.5

        class Connection:
            def close(self):
                pass

        return Connection()

    def fake_start_daemon(api_port=18764, ws_port=18765):
        starts.append((api_port, ws_port))
        raise AssertionError("busy daemon port should not start a duplicate daemon")

    monkeypatch.setattr(daemon_client, "health", lambda base_url, timeout=0.5: None)
    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(daemon_client, "start_daemon", fake_start_daemon)

    with pytest.raises(RuntimeError, match="running but not responding"):
        daemon_client.ensure_daemon(api_port=18764, ws_port=18765, timeout=0.01)

    assert starts == []


def test_call_action_accepts_custom_timeout(monkeypatch):
    calls = {}

    class Response:
        def raise_for_status(self):
            calls["raised"] = True

        def json(self):
            return {"status": "success"}

    def fake_post(url, json, timeout):
        calls["url"] = url
        calls["json"] = json
        calls["timeout"] = timeout
        return Response()

    monkeypatch.setattr(daemon_client.requests, "post", fake_post)

    result = daemon_client.call_action("scan", {"switch_tab_id": "tab-1"}, "http://127.0.0.1:18764", timeout=120)

    assert result == {"status": "success"}
    assert calls == {
        "url": "http://127.0.0.1:18764/api/actions/scan",
        "json": {"params": {"switch_tab_id": "tab-1"}},
        "timeout": 120,
        "raised": True,
    }


def test_call_action_retries_safe_action_after_remote_disconnect(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"status": "success"}

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        if len(calls) == 1:
            raise daemon_client.requests.exceptions.ConnectionError("Remote end closed connection")
        return Response()

    monkeypatch.setattr(daemon_client.requests, "post", fake_post)
    monkeypatch.setattr(daemon_client, "_wait_for_runtime_recovery", lambda *args, **kwargs: True)

    result = daemon_client.call_action(
        "screenshot",
        {"switch_tab_id": "tab-1"},
        "http://127.0.0.1:18764",
    )

    assert result == {"status": "success"}
    assert len(calls) == 2


def test_call_action_does_not_replay_unsafe_action_after_disconnect(monkeypatch):
    calls = []

    def fake_post(url, json, timeout):
        calls.append((url, json, timeout))
        raise daemon_client.requests.exceptions.ConnectionError("Remote end closed connection")

    monkeypatch.setattr(daemon_client.requests, "post", fake_post)

    with pytest.raises(daemon_client.requests.exceptions.ConnectionError):
        daemon_client.call_action(
            "click",
            {"selector": "#submit", "switch_tab_id": "tab-1"},
            "http://127.0.0.1:18764",
        )

    assert len(calls) == 1


def test_call_action_waits_for_extension_reconnect_then_retries(monkeypatch):
    responses = [
        {"status": "error", "msg": "No browser tabs connected."},
        {"status": "success", "value": True},
    ]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return responses.pop(0)

    monkeypatch.setattr(daemon_client.requests, "post", lambda *args, **kwargs: Response())
    monkeypatch.setattr(daemon_client, "_wait_for_runtime_recovery", lambda *args, **kwargs: True)

    result = daemon_client.call_action(
        "wait",
        {"load": "load", "switch_tab_id": "tab-1"},
        "http://127.0.0.1:18764",
    )

    assert result == {"status": "success", "value": True}
