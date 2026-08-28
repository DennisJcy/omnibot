from omnibot import bridge_registry, daemon_client


def test_bridge_base_url_prefers_first_registered_bridge(monkeypatch):
    monkeypatch.setattr(bridge_registry, "list_bridges", lambda: [{"device_id": "dev1", "endpoint": "tcp:127.0.0.1:19000"}])

    assert daemon_client.bridge_base_url() == "http://127.0.0.1:19000"


def test_bridge_base_url_returns_none_without_bridge(monkeypatch):
    monkeypatch.setattr(bridge_registry, "list_bridges", lambda: [])

    assert daemon_client.bridge_base_url() is None


def test_ensure_runtime_calls_ensure_daemon(monkeypatch):
    calls = []

    def fake_ensure_daemon(api_port=18764, ws_port=18765, timeout=8.0):
        calls.append((api_port, ws_port, timeout))
        return "http://127.0.0.1:18764"

    monkeypatch.setattr(daemon_client, "ensure_daemon", fake_ensure_daemon)

    assert daemon_client.ensure_runtime() == "http://127.0.0.1:18764"
    assert calls == [(18764, 18765, 8.0)]
