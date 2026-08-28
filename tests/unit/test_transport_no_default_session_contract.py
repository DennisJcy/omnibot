from types import SimpleNamespace

import pytest

from omnibot.TMWebDriver import TMWebDriver


class FakeSession:
    def __init__(self, session_id="client:1", tab_id="1", session_type="ext_ws", active=True, client_id="client"):
        self.id = session_id
        self.tab_id = tab_id
        self.type = session_type
        self.client_id = client_id
        self.ws_client = SimpleNamespace(sent=[])
        self.http_queue = None
        self.info = {"id": session_id, "tab_id": tab_id, "url": "https://example.test"}
        self._active = active

    def is_active(self):
        return self._active


def driver_without_servers():
    driver = object.__new__(TMWebDriver)
    driver.multi_user = False
    driver.is_remote = False
    driver._default_ctx = SimpleNamespace(
        sessions={},
        results={},
        acks={},
        tool_created_tabs=set(),
        explicit_target_tabs=set(),
        latest_session_id=None,
        clean_sessions=lambda: None,
    )
    return driver


def test_page_script_requires_explicit_session_id():
    driver = driver_without_servers()
    session = FakeSession()
    driver._default_ctx.sessions[session.id] = session

    with pytest.raises(ValueError, match="session_id is required"):
        driver.execute_js("return location.href")


def test_extension_command_can_select_transport_without_page_target():
    driver = driver_without_servers()
    session = FakeSession()
    driver._default_ctx.sessions[session.id] = session
    driver._default_ctx.latest_session_id = session.id

    import json

    sent_payloads = []

    class Client:
        def send_message(self, payload):
            sent_payloads.append(payload)
            exec_id = json.loads(payload)["id"]
            driver._default_ctx.acks[exec_id] = True
            driver._default_ctx.results[exec_id] = {"success": True, "data": {"id": 123}, "newTabs": [], "browserClientId": "client"}

    session.ws_client = Client()

    result = driver.execute_js('{"cmd":"tabs","method":"create","url":"https://example.test"}')

    assert result == {"data": {"id": 123}, "browserClientId": "client"}
    assert sent_payloads
    payload = json.loads(sent_payloads[0])
    assert payload["tabId"] == 1


def test_dict_extension_command_can_select_transport_without_page_target():
    driver = driver_without_servers()
    session = FakeSession()
    driver._default_ctx.sessions[session.id] = session
    driver._default_ctx.latest_session_id = session.id

    import json

    sent_payloads = []

    class Client:
        def send_message(self, payload):
            sent_payloads.append(payload)
            exec_id = json.loads(payload)["id"]
            driver._default_ctx.acks[exec_id] = True
            driver._default_ctx.results[exec_id] = {"success": True, "data": {"ok": True}, "newTabs": [], "browserClientId": "client"}

    session.ws_client = Client()

    result = driver.execute_js({"cmd": "cdp", "tabId": 123, "method": "Runtime.evaluate", "params": {}})

    assert result == {"data": {"ok": True}, "browserClientId": "client"}
    assert sent_payloads
    payload = json.loads(sent_payloads[0])
    assert payload["tabId"] == 1


def test_tabs_create_can_use_extension_client_without_tab_sessions():
    driver = driver_without_servers()
    driver._default_ctx.extension_clients = {}
    driver._default_ctx.latest_extension_client_id = "client"

    import json

    sent_payloads = []

    class Client:
        def send_message(self, payload):
            sent_payloads.append(payload)
            exec_id = json.loads(payload)["id"]
            driver._default_ctx.acks[exec_id] = True
            driver._default_ctx.results[exec_id] = {
                "success": True,
                "data": {"id": 456, "url": "https://example.test", "title": ""},
                "newTabs": [],
                "browserClientId": "client",
            }

    driver._default_ctx.extension_clients["client"] = Client()

    result = driver.execute_js({"cmd": "tabs", "method": "create", "url": "https://example.test"})

    assert result == {
        "data": {"id": 456, "url": "https://example.test", "title": ""},
        "browserClientId": "client",
    }
    payload = json.loads(sent_payloads[0])
    assert "tabId" not in payload
    assert payload["code"] == {"cmd": "tabs", "method": "create", "url": "https://example.test"}


def test_new_tab_raises_when_no_transport_available():
    driver = driver_without_servers()

    with pytest.raises(ValueError, match="会话ID None 未连接"):
        driver.new_tab("https://example.test")


def test_internal_extension_status_commands_are_extension_commands():
    assert TMWebDriver._is_extension_command({"cmd": "tabStatus", "method": "cleanup", "tabId": 123})
    assert TMWebDriver._is_extension_command({"cmd": "tabFavicon", "method": "restore", "tabId": 123})
    assert TMWebDriver._is_extension_command({"cmd": "windows", "method": "create", "url": "about:blank"})


def test_jump_requires_session_id():
    driver = driver_without_servers()

    with pytest.raises(ValueError, match="session_id is required"):
        driver.jump("https://example.test")


def test_no_default_session_id_field_on_context():
    from omnibot.TMWebDriver import UserContext

    ctx = UserContext("test-token")
    assert not hasattr(ctx, "default_session_id")


def test_set_session_returns_id_without_mutating_context():
    from omnibot.TMWebDriver import Session

    driver = driver_without_servers()
    session = FakeSession(session_id="client:1", tab_id="1")
    driver._default_ctx.sessions[session.id] = session
    driver._default_ctx.latest_session_id = session.id

    result = driver.set_session("example.test")
    assert result == "client:1"
    assert not hasattr(driver._default_ctx, "default_session_id")
