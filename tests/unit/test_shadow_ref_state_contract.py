from omnibot import actions, cdp
from omnibot.refs import RefMap
from types import SimpleNamespace


def test_backend_snapshot_ref_attr_uses_describe_node(monkeypatch):
    calls = []

    def fake_send_cdp(driver, tab_id, method, params, **kwargs):
        calls.append((method, params))
        return {"node": {"attributes": ["aria-label", "Shadow action"]}}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "https://example.test/base/")

    assert actions.get_backend_ref_value(object(), "tab-1", 42, "attr", "aria-label") == "Shadow action"
    assert calls == [("DOM.describeNode", {"backendNodeId": 42, "depth": 0})]


def test_backend_snapshot_ref_href_is_resolved_against_document_base(monkeypatch):
    monkeypatch.setattr(
        cdp,
        "send_cdp",
        lambda *args, **kwargs: {"node": {"attributes": ["href", "target.html?from=shadow#part"]}},
    )
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "https://example.test/base/")

    result = actions.get_backend_ref_value(object(), "tab-1", 42, "attr", "href")

    assert result == "https://example.test/base/target.html?from=shadow#part"


def test_backend_snapshot_ref_states_are_derived_from_backend_node(monkeypatch):
    def fake_send_cdp(driver, tab_id, method, params, **kwargs):
        if method == "DOM.getBoxModel":
            return {"model": {"border": [0, 0, 20, 0, 20, 20, 0, 20]}}
        if method == "DOM.describeNode":
            return {"node": {"attributes": []}}
        raise AssertionError(method)

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    assert actions.get_backend_ref_value(object(), "tab-1", 42, "visible") is True
    assert actions.get_backend_ref_value(object(), "tab-1", 42, "enabled") is True
    assert actions.get_backend_ref_value(object(), "tab-1", 42, "checked") is False


def test_is_state_dispatches_snapshot_refs_to_ref_observation(monkeypatch):
    class FakeDriver:
        def __init__(self):
            self.ctx = SimpleNamespace(
                refs=RefMap(),
                sessions={"tab-1": SimpleNamespace(created_by_tool=False)},
                tool_created_tabs=set(),
            )

        def get_context(self, token=None):
            return self.ctx

        def get_all_sessions(self, token=None):
            return [{"id": "tab-1", "tab_id": "101"}]

        def _cancel_tab_close(self, tab_id, token=None):
            pass

        def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=True):
            pass

    driver = FakeDriver()
    driver.ctx.refs.add("tab-1", role="button", name="Shadow action", backend_node_id=42)
    monkeypatch.setattr(actions, "get_ref_value", lambda *args, **kwargs: False)

    result = actions.is_state(driver, "checked", "@e1", switch_tab_id="tab-1")

    assert result == {"status": "success", "kind": "checked", "selector": "@e1", "value": False}
