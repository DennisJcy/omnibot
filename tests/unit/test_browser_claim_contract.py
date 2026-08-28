from omnibot import actions
from omnibot.TMWebDriver import Session, UserContext


class ContractDriver:
    def __init__(self):
        self.ctx = UserContext("browser-claim-contract")

    def get_context(self, token=None):
        return self.ctx

    def get_all_sessions(self, token=None):
        return self.ctx.get_all_active_sessions()


def test_browser_claim_current_fails_without_active_session():
    driver = ContractDriver()

    result = actions.browser_claim(driver, "current", token="browser-claim-contract")

    assert result["status"] == "error"
    assert "No current browser tab" in result["error"]


def test_browser_claim_current_resolves_latest_active_session():
    driver = ContractDriver()
    token = "browser-claim-contract"
    ctx = driver.get_context(token)
    ctx.latest_session_id = "client:123"
    ctx.sessions["client:123"] = Session("client:123", {"type": "ext_ws", "url": "https://example.com"}, object())

    result = actions.browser_claim(driver, "current", token=token)

    assert result["status"] == "success"
    assert result["tab_id"] == "client:123"
    assert ctx.claimed_tabs == {"client:123"}


def test_browser_claim_current_fails_for_disconnected_latest_session():
    driver = ContractDriver()
    token = "browser-claim-contract"
    ctx = driver.get_context(token)
    ctx.latest_session_id = "client:123"
    session = Session("client:123", {"type": "ext_ws", "url": "https://example.com"}, object())
    session.mark_disconnected()
    ctx.sessions["client:123"] = session

    result = actions.browser_claim(driver, "current", token=token)

    assert result["status"] == "error"
    assert "No current browser tab" in result["error"]


def test_browser_claim_rejects_unknown_tab_id():
    driver = ContractDriver()
    token = "browser-claim-contract"

    result = actions.browser_claim(driver, "999999-invalid", token=token)

    assert result["status"] == "error"
    assert result["error"]
    assert driver.get_context(token).claimed_tabs == set()


def test_browser_claim_resolves_raw_tab_id_to_active_session_id():
    driver = ContractDriver()
    token = "browser-claim-contract"
    ctx = driver.get_context(token)
    session = Session(
        "client:123",
        {"type": "ext_ws", "tab_id": "123", "url": "https://example.com"},
        object(),
    )
    ctx.sessions[session.id] = session

    result = actions.browser_claim(driver, "123", token=token)

    assert result == {"status": "success", "tab_id": "client:123", "claimed": True}
    assert ctx.claimed_tabs == {"client:123"}


def test_browser_release_resolves_raw_tab_id_after_claim():
    driver = ContractDriver()
    token = "browser-claim-contract"
    ctx = driver.get_context(token)
    session = Session(
        "client:123",
        {"type": "ext_ws", "tab_id": "123", "url": "https://example.com"},
        object(),
    )
    ctx.sessions[session.id] = session
    ctx.claimed_tabs.add("client:123")

    result = actions.browser_release(driver, "123", token=token)

    assert result == {"status": "success", "tab_id": "client:123", "claimed": False}
    assert ctx.claimed_tabs == set()
