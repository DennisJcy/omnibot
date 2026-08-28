from omnibot import actions


class FakeDriver:
    def __init__(self):
        self.calls = []

    def _raw_tab_id(self, tab_id, token=None):
        return tab_id


def test_network_logs_uses_network_capture_command(monkeypatch):
    calls = []

    def fake_extension_command(driver, payload, tab_id=None, timeout=10, token=None):
        calls.append((payload, tab_id, timeout, token))
        return {"ok": True, "entries": [{"method": "Network.requestWillBeSent", "params": {"request": {"url": "https://api.example/order", "method": "POST"}}}]}

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.network_logs(FakeDriver(), tab_id="123", token="tok")

    assert calls[0][0] == {"cmd": "networkCapture", "op": "logs"}
    assert calls[0][1] == "123"
    assert result["status"] == "success"
    assert len(result["entries"]) == 1
    assert result["entries"][0]["event"] == "request"
    assert result["entries"][0]["method"] == "POST"


def test_network_capture_start_stop_clear(monkeypatch):
    calls = []

    def fake_extension_command(driver, payload, tab_id=None, timeout=10, token=None):
        calls.append(payload)
        return {"ok": True, "entries": []}

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    actions.network_capture_start(FakeDriver(), tab_id="123", token="tok")
    actions.network_capture_stop(FakeDriver(), tab_id="123", token="tok")
    actions.network_capture_clear(FakeDriver(), tab_id="123", token="tok")

    assert calls == [
        {"cmd": "networkCapture", "op": "start"},
        {"cmd": "networkCapture", "op": "stop"},
        {"cmd": "networkCapture", "op": "clear"},
    ]


def test_network_logs_unknown_cmd_returns_upgrade_hint(monkeypatch):
    def fake_extension_command(driver, payload, tab_id=None, timeout=10, token=None):
        return {"ok": False, "error": "Unknown cmd: networkCapture"}

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.network_logs(FakeDriver(), tab_id="123", token="tok")

    assert result["status"] == "error"
    assert "Reload or update the Omnibot browser extension" in result["msg"]


def test_network_summary_uses_normalized_entries(monkeypatch):
    def fake_extension_command(driver, payload, tab_id=None, timeout=10, token=None):
        return {"ok": True, "entries": [
            {"method": "Network.requestWillBeSent", "params": {"request": {"url": "https://api.example/order", "method": "POST"}, "type": "XHR"}},
            {"method": "Network.responseReceived", "params": {"response": {"url": "https://api.example/order", "status": 200}, "type": "XHR"}},
        ]}

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.network_summary_action(FakeDriver(), tab_id="123", token="tok")

    assert result["status"] == "success"
    assert result["total"] == 2
    assert result["methods"]["POST"] == 1
    assert result["hosts"]["api.example"] == 2
    assert "https://api.example/order" in result["api_candidates"]
