import pytest

from omnibot import cdp


class FakeDriver:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def _raw_tab_id(self, tab_id, token=None):
        return str(tab_id)

    def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
        self.calls.append({
            "code": code,
            "timeout": timeout,
            "session_id": session_id,
            "token": token,
            "group_status": group_status,
            "status_tab_id": status_tab_id,
        })
        return self.result


def test_send_cdp_sends_extension_command_to_target_tab():
    driver = FakeDriver({"data": {"ok": True, "data": {"title": "Example"}}})

    result = cdp.send_cdp(driver, tab_id="123", method="Runtime.evaluate", params={"expression": "document.title"}, token="tok")

    assert result == {"title": "Example"}
    assert driver.calls == [{
        "code": {"cmd": "cdp", "tabId": 123, "method": "Runtime.evaluate", "params": {"expression": "document.title"}},
        "timeout": 15,
        "session_id": None,
        "token": "tok",
        "group_status": None,
        "status_tab_id": 123,
    }]


def test_send_cdp_preserves_new_tabs_metadata():
    driver = FakeDriver({
        "data": {"ok": True, "data": {"result": {"value": True}}},
        "newTabs": [{"id": 456, "url": "https://example.com/next", "browserClientId": "edge-client"}],
    })

    result = cdp.send_cdp(driver, tab_id="123", method="Runtime.evaluate")

    assert result["result"] == {"value": True}
    assert result["_omnibot_newTabs"] == [
        {"id": 456, "url": "https://example.com/next", "browserClientId": "edge-client"}
    ]


def test_send_cdp_can_request_new_tab_watch():
    driver = FakeDriver({"data": {"ok": True, "data": {"result": {"value": True}}}})

    cdp.send_cdp(driver, tab_id="123", method="Runtime.evaluate", params={"expression": "button.click()"}, watch_new_tabs=True)

    assert driver.calls[0]["code"] == {
        "cmd": "cdp",
        "tabId": 123,
        "method": "Runtime.evaluate",
        "params": {"expression": "button.click()"},
        "watchNewTabs": True,
    }


def test_send_cdp_raises_clear_error_from_extension_response():
    driver = FakeDriver({"data": {"ok": False, "error": "No tabId"}})

    with pytest.raises(cdp.CdpError, match="No tabId"):
        cdp.send_cdp(driver, tab_id="123", method="DOM.enable")


def test_evaluate_returns_runtime_value():
    driver = FakeDriver({"data": {"ok": True, "data": {"result": {"value": 42}}}})

    assert cdp.evaluate(driver, tab_id="123", expression="21 * 2") == 42
