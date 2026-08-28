import json
from types import SimpleNamespace

import pytest

from omnibot import actions, cdp
from omnibot.refs import RefMap
from omnibot.TMWebDriver import Session, TMWebDriver, UserContext


class FakeDriver:
    def __init__(self):
        self.ctx = SimpleNamespace(sessions={}, tool_created_tabs=set(), explicit_target_tabs={"tab-1"}, refs=RefMap(), latest_session_id="tab-1")
        self.sessions = [{"id": "tab-1", "tab_id": "101", "url": "https://example.com", "title": "Example", "type": "ext_ws", "connected_at": 1}]
        self.cancelled = []
        self.scheduled = []
        self.executed = []

    def get_context(self, token=None):
        return self.ctx

    def get_all_sessions(self, token=None):
        return [dict(s) for s in self.sessions]

    def _cancel_tab_close(self, tab_id, token=None):
        self.cancelled.append(tab_id)

    def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=True):
        self.scheduled.append({"tab_id": tab_id, "close": close})

    def _raw_tab_id(self, tab_id, token=None):
        for session in self.sessions:
            if session["id"] == tab_id:
                return session["tab_id"]
        return str(tab_id).rsplit(":", 1)[-1]

    def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
        self.executed.append({"code": code, "timeout": timeout, "session_id": session_id, "group_status": group_status, "status_tab_id": status_tab_id})
        if code == "return false;":
            return {"data": False}
        if code == "return document.documentElement.scrollTop;":
            return {"data": 0}
        return {"data": True}

    def broadcast_extension_event(self, payload, token=None):
        if not hasattr(self, "broadcasts"):
            self.broadcasts = []
        self.broadcasts.append(payload)
        self.broadcast = payload


def test_get_tabs_removes_transport_only_fields():
    result = actions.get_tabs(FakeDriver())

    assert result == {
        "tabs": [{"id": "tab-1", "tab_id": "101", "url": "https://example.com", "title": "Example"}],
    }


def test_tab_list_prunes_aliases_for_disconnected_sessions():
    driver = FakeDriver()
    driver.ctx.tab_aliases = {"live": "tab-1", "stale": "missing-tab"}

    result = actions.tab(driver, tab_command="list")

    assert result["aliases"] == {"live": "tab-1"}
    assert driver.ctx.tab_aliases == {"live": "tab-1"}


def test_window_new_uses_window_creation_and_returns_window_id():
    driver = FakeDriver()
    driver.new_window = lambda url, timeout=15, token=None: {
        "windowId": 42,
        "tab": {"id": "edge-client:202", "tab_id": "202", "url": "about:blank", "title": ""},
    }

    result = actions.window(driver, "new")

    assert result == {
        "status": "success",
        "window_id": 42,
        "tab": {"id": "edge-client:202", "tab_id": "202", "url": "about:blank", "title": ""},
    }
    assert driver.cancelled == ["edge-client:202"]
    assert driver.scheduled == [{"tab_id": "edge-client:202", "close": True}]


def test_batch_reports_per_command_failure_in_top_level_status(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(
        actions,
        "extension_command",
        lambda *args, **kwargs: [
            {"result": {"type": "string", "value": "ok"}},
            {"ok": False, "error": "unknown cmd: bogus"},
        ],
    )

    result = actions.batch(driver, [{"cmd": "cdp"}, {"cmd": "bogus"}], tab_id="tab-1")

    assert result["status"] == "error"
    assert result["failures"] == [{"index": 1, "result": {"ok": False, "error": "unknown cmd: bogus"}}]
    assert result["results"][0]["result"]["value"] == "ok"


def test_daemon_registry_removes_implicit_target_actions():
    from omnibot import daemon

    assert "switch_tab" not in daemon.ACTION_REGISTRY
    assert "focus_tab" not in daemon.ACTION_REGISTRY


def test_replay_remaps_recorded_tab_ids_and_preserves_token(monkeypatch):
    driver = FakeDriver()
    calls = []

    def fake_navigate(driver, **params):
        calls.append(("navigate", params))
        return {"status": "success", "tab": {"id": "new-tab"}}

    def fake_get(driver, **params):
        calls.append(("get", params))
        return {"status": "success", "value": "Agent Controls Probe"}

    monkeypatch.setattr(actions, "navigate", fake_navigate)
    monkeypatch.setattr(actions, "get", fake_get)

    result = actions.replay(
        driver,
        flow=[
            {"action": "navigate", "params": {"url": "https://example.test", "new_tab": True}},
            {"action": "get", "params": {"kind": "title", "switch_tab_id": "recorded-tab"}},
        ],
        token="replay-token",
    )

    assert result["status"] == "success"
    assert calls == [
        ("navigate", {"url": "https://example.test", "new_tab": True, "token": "replay-token"}),
        ("get", {"kind": "title", "switch_tab_id": "new-tab", "token": "replay-token"}),
    ]


def test_actions_module_removes_implicit_target_functions():
    assert not hasattr(actions, "switch_tab")
    assert not hasattr(actions, "focus_tab")


def test_wait_returns_timeout_shape_when_condition_never_truthy(monkeypatch):
    driver = FakeDriver()
    now = {"value": 100.0}

    def fake_time():
        now["value"] += 1.0
        return now["value"]

    monkeypatch.setattr(actions.time, "time", fake_time)
    monkeypatch.setattr(actions.time, "sleep", lambda _: None)

    result = actions.wait(driver, "return false;", switch_tab_id="tab-1", timeout=1, interval=0.1)

    assert result["status"] == "timeout"
    assert result["tab_id"] == "tab-1"
    assert result["attempts"] >= 1


def test_numeric_wait_reschedules_tool_created_target_after_done(monkeypatch):
    driver = FakeDriver()
    driver.ctx.tool_created_tabs.add("tab-1")
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=True)
    monkeypatch.setattr(actions.time, "sleep", lambda _: None)

    result = actions.wait(driver, wait_target="2000", switch_tab_id="tab-1")

    assert result == {"status": "success", "value": True, "attempts": 1, "tab_id": "tab-1"}
    assert driver.cancelled == ["tab-1"]
    assert driver.scheduled == [{"tab_id": "tab-1", "close": True}]


def test_wait_accepts_text_shorthand_without_treating_it_as_css_selector(monkeypatch):
    driver = FakeDriver()
    seen = []

    def fake_evaluate(_driver, _tab_id, condition, **_kwargs):
        seen.append(condition)
        return True

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)
    result = actions.wait(driver, wait_target="text=dynamic done", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert "innerText.includes(\"dynamic done\")" in seen[0]


def test_tool_created_tab_cleanup_allows_agent_paced_followup_actions():
    driver = FakeDriver()
    scheduled = []
    driver.ctx.tool_created_tabs.add("tab-1")
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=True)
    driver._schedule_tab_close = lambda tab_id, timeout=60, token=None, close=True: scheduled.append(
        {"tab_id": tab_id, "timeout": timeout, "close": close}
    )

    actions._schedule_tab_cleanup_after_operation(driver, driver.ctx, "tab-1")

    assert scheduled == [{"tab_id": "tab-1", "timeout": 60, "close": True}]


def test_screenshot_returns_base64_payload(monkeypatch):
    driver = FakeDriver()

    def fake_extension_command(d, cmd, tab_id=None, timeout=15, token=None, group_status=None):
        assert cmd["method"] == "Page.captureScreenshot"
        assert tab_id == "tab-1"
        return {"data": {"data": "png-base64"}}

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.screenshot(driver, tab_id="tab-1")

    assert result == {"status": "success", "format": "png", "base64": "png-base64"}


def test_screenshot_handles_raw_base64_extension_response(monkeypatch):
    driver = FakeDriver()

    def fake_extension_command(d, cmd, tab_id=None, timeout=15, token=None, group_status=None):
        return {"data": "raw-png-base64"}

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.screenshot(driver, tab_id="tab-1")

    assert result == {"status": "success", "format": "png", "base64": "raw-png-base64"}


def test_screenshot_waits_for_fonts_and_two_paint_frames_before_capture(monkeypatch):
    driver = FakeDriver()
    calls = []

    def fake_evaluate(d, tab_id, expression, **kwargs):
        calls.append(("stabilize", tab_id, expression, kwargs))
        return {
            "url": "https://example.com/login",
            "title": "Sign in",
            "viewport": {"width": 390, "height": 844, "deviceScaleFactor": 2},
        }

    def fake_extension_command(d, cmd, tab_id=None, timeout=15, token=None, group_status=None):
        calls.append(("capture", tab_id, cmd, {}))
        return {"data": {"data": "png-base64"}}

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.screenshot(driver, tab_id="tab-1")

    assert result["status"] == "success"
    assert result["url"] == "https://example.com/login"
    assert result["title"] == "Sign in"
    assert result["viewport"] == {"width": 390, "height": 844, "deviceScaleFactor": 2}
    assert [call[0] for call in calls] == ["stabilize", "capture"]
    assert "document.fonts.ready" in calls[0][2]
    assert "requestAnimationFrame(() => requestAnimationFrame(resolve))" in calls[0][2]
    assert calls[0][3]["timeout"] == 2


def test_visual_ref_clip_scrolls_and_returns_live_box(monkeypatch):
    driver = FakeDriver()
    driver.ctx.refs.add("tab-1", role="article", name="A post", backend_node_id=42, kind="visual")
    calls = []

    def fake_evaluate(d, tab_id, expression, **kwargs):
        calls.append((tab_id, expression))
        return {"x": 10, "y": 20, "width": 300, "height": 180}

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)

    clip = actions._visual_ref_clip(driver, "tab-1", "@e1")

    assert clip == {"x": 10.0, "y": 20.0, "width": 300.0, "height": 180.0}
    assert calls[0][0] == "tab-1"
    assert "getBoundingClientRect" in calls[0][1]
    assert len(calls) == 1


def test_dialog_logs_uses_extension_dialog_capture(monkeypatch):
    driver = FakeDriver()
    calls = []

    def fake_extension_command(d, cmd, tab_id=None, timeout=15, token=None, group_status=None):
        calls.append({"cmd": cmd, "tab_id": tab_id, "timeout": timeout})
        return {"ok": True, "entries": [{"type": "confirm", "message": "Delete item?"}]}

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.dialog_logs(driver, tab_id="tab-1")

    assert result == {"status": "success", "entries": [{"type": "confirm", "message": "Delete item?"}]}
    assert calls == [{"cmd": {"cmd": "dialogCapture", "op": "logs"}, "tab_id": "tab-1", "timeout": 10}]


def test_dialog_logs_deduplicates_wrapper_and_cdp_entries(monkeypatch):
    driver = FakeDriver()

    def fake_extension_command(d, cmd, tab_id=None, timeout=15, token=None, group_status=None):
        return {
            "ok": True,
            "entries": [
                {
                    "type": "prompt",
                    "message": "Agent prompt?",
                    "defaultPrompt": "default text",
                    "hasBrowserHandler": False,
                    "timestamp": 1000,
                },
                {
                    "type": "prompt",
                    "message": "Agent prompt?",
                    "defaultPrompt": "default text",
                    "hasBrowserHandler": True,
                    "timestamp": 1000,
                },
            ],
        }

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.dialog_logs(driver, tab_id="tab-1")

    assert result == {
        "status": "success",
        "entries": [
            {
                "type": "prompt",
                "message": "Agent prompt?",
                "defaultPrompt": "default text",
                "hasBrowserHandler": True,
                "timestamp": 1000,
            }
        ],
    }


def test_dialog_logs_deduplicates_delayed_wrapper_event_after_cdp_entry(monkeypatch):
    driver = FakeDriver()

    def fake_extension_command(d, cmd, tab_id=None, timeout=15, token=None, group_status=None):
        return {
            "ok": True,
            "entries": [
                {
                    "type": "alert",
                    "message": "Agent alert!",
                    "defaultPrompt": "",
                    "hasBrowserHandler": True,
                    "timestamp": 1000,
                },
                {
                    "type": "alert",
                    "message": "Agent alert!",
                    "defaultPrompt": "",
                    "hasBrowserHandler": False,
                    "timestamp": 14000,
                },
            ],
        }

    monkeypatch.setattr(actions, "extension_command", fake_extension_command)

    result = actions.dialog_logs(driver, tab_id="tab-1")

    assert result == {
        "status": "success",
        "entries": [
            {
                "type": "alert",
                "message": "Agent alert!",
                "defaultPrompt": "",
                "hasBrowserHandler": True,
                "timestamp": 14000,
            }
        ],
    }


def test_dialog_handle_forwards_accept_flag(monkeypatch):
    driver = FakeDriver()
    calls = []

    def fake_send_cdp(d, tab_id, method, params, **kwargs):
        calls.append({"method": method, "params": params, "tab_id": tab_id})
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.dialog_handle(driver, tab_id="tab-1", accept=False)

    assert result["status"] == "success"
    assert result["handled"] is True
    assert calls == [{"method": "Page.handleJavaScriptDialog", "params": {"accept": False}, "tab_id": "tab-1"}]


def test_dialog_handle_forwards_prompt_text(monkeypatch):
    driver = FakeDriver()
    calls = []

    def fake_send_cdp(d, tab_id, method, params, **kwargs):
        calls.append({"method": method, "params": params, "tab_id": tab_id})
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.dialog_handle(driver, tab_id="tab-1", accept=True, prompt_text="hello")

    assert result["status"] == "success"
    assert result["handled"] is True
    assert calls == [{"method": "Page.handleJavaScriptDialog", "params": {"accept": True, "promptText": "hello"}, "tab_id": "tab-1"}]


def test_dialog_handle_retries_until_dialog_is_showing(monkeypatch):
    driver = FakeDriver()
    calls = []
    sleeps = []

    def fake_send_cdp(d, tab_id, method, params, **kwargs):
        calls.append({"method": method, "params": params, "tab_id": tab_id})
        if len(calls) == 1:
            raise cdp.CdpError('{"code":-32602,"message":"No dialog is showing"}')
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(actions.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = actions.dialog_handle(driver, tab_id="tab-1", accept=True)

    assert result["status"] == "success"
    assert result["handled"] is True
    assert len(calls) == 2
    assert sleeps == [0.1]


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


def test_snapshot_action_registered():
    from omnibot.daemon import ACTION_REGISTRY

    assert "snapshot" in ACTION_REGISTRY


def test_snapshot_action_populates_context_refs_for_followup_click(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    ax_tree = {
        "nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}, "childIds": ["2"]},
            {"nodeId": "2", "role": {"value": "button"}, "name": {"value": "Submit"}, "backendDOMNodeId": 30},
        ]
    }

    def fake_send_cdp(driver_arg, tab_id, method, params, token=None, **kwargs):
        if method == "Accessibility.getFullAXTree":
            return ax_tree
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.snapshot(driver, switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert '@e2 [button] "Submit"' in result["content"]
    assert driver.ctx.refs.get("tab-1", "@e2").backend_node_id == 30


def test_snapshot_enriches_input_type_from_backend_dom_node(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    ax_tree = {
        "nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Login"}, "childIds": ["2"]},
            {"nodeId": "2", "role": {"value": "textbox"}, "name": {"value": ""}, "backendDOMNodeId": 30},
        ]
    }

    def fake_send_cdp(driver_arg, tab_id, method, params, token=None, **kwargs):
        if method == "Accessibility.getFullAXTree":
            return ax_tree
        if method == "DOM.describeNode":
            return {"node": {"nodeName": "INPUT", "attributes": ["id", "userPassword", "type", "password"]}}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.snapshot(driver, switch_tab_id="tab-1")

    assert '@e2 [textbox] [type=password]' in result["content"]
    assert result["refs"]["e2"]["type"] == "password"


def test_snapshot_uses_selected_frame_id_for_accessibility_tree(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.frame_target = "#payment-frame"
    ax_tree = {"nodes": [{"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Child"}}]}
    calls = []

    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: {"id": "payment-frame", "url": "https://example.com/child"})

    def fake_send_cdp(driver_arg, tab_id, method, params, token=None, **kwargs):
        calls.append((method, params))
        if method == "Page.getFrameTree":
            return {"frame": {"id": "root", "url": "https://example.com"}, "childFrames": [{"frame": {"id": "child-id", "url": "https://example.com/child"}}]}
        if method == "Accessibility.getFullAXTree":
            return ax_tree
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.snapshot(driver, switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert ("Accessibility.getFullAXTree", {"frameId": "child-id"}) in calls


def test_snapshot_reports_missing_selected_frame_instead_of_falling_back_to_host(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.frame_target = "iframe.missing"
    calls = []

    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: None)

    def fake_send_cdp(driver_arg, tab_id, method, params, token=None, **kwargs):
        calls.append((method, params))
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "root", "url": "https://example.com"}}}
        if method == "Accessibility.getFullAXTree":
            pytest.fail("host AX tree must not be returned for a missing selected frame")
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.snapshot(driver, switch_tab_id="tab-1")

    assert result == {
        "status": "error",
        "msg": "Selected frame was not found in the current page.",
        "reason": "not_found",
        "frame": "iframe.missing",
    }


def test_click_schedules_tool_created_target_after_done(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    driver.ctx.tool_created_tabs.add("tab-1")
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=True)

    monkeypatch.setattr(interactions, "click", lambda *args, **kwargs: {"clicked": "#button", "x": 1, "y": 2, "navigation": False, "url": "https://example.com"})

    result = actions.click(driver, "#button", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert driver.scheduled == [{"tab_id": "tab-1", "close": True}]


def test_click_schedules_user_owned_target_for_ungroup_only_after_done(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=False)

    monkeypatch.setattr(interactions, "click", lambda *args, **kwargs: {"clicked": "#button", "x": 1, "y": 2, "navigation": False, "url": "https://example.com"})

    result = actions.click(driver, "#button", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert driver.scheduled == [{"tab_id": "tab-1", "close": False}]


def test_mouse_move_broadcasts_status_without_waiting_for_tab_group_ack(monkeypatch):
    driver = FakeDriver()
    driver._raw_tab_id = lambda tab_id, token=None: "101"
    monkeypatch.setattr("omnibot.cua.move", lambda *args, **kwargs: {"x": 10, "y": 20})

    result = actions.mouse_move(driver, 10, 20, switch_tab_id="tab-1", token="tok")

    assert result == {"status": "success", "x": 10, "y": 20}
    assert [event.get("groupStatus") for event in driver.broadcasts] == ["移动中", "已移动"]
    assert all(event.get("statusTabId") == 101 for event in driver.broadcasts)
    assert driver.executed == []
    assert driver.cancelled == []


def test_mouse_click_schedules_new_tab_opened_by_coordinate_action(monkeypatch):
    driver = FakeDriver()
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=False)
    new_tab = {
        "id": 202,
        "openerTabId": 101,
        "browserClientId": "edge-client",
        "url": "https://example.test/article",
        "title": "Article",
    }
    monkeypatch.setattr(
        "omnibot.cua.click",
        lambda *args, **kwargs: {"x": 10, "y": 20, "newTabs": [new_tab]},
    )

    result = actions.mouse_click(driver, 10, 20, switch_tab_id="tab-1", token="tok")

    assert result["status"] == "success"
    assert "edge-client:202" in driver.ctx.tool_created_tabs
    assert driver.scheduled == [
        {"tab_id": "edge-client:202", "close": True},
        {"tab_id": "tab-1", "close": False},
    ]


def test_get_reschedules_tool_created_target_after_done(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.tool_created_tabs.add("tab-1")
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=True)

    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "https://example.com")

    result = actions.get(driver, "url", switch_tab_id="tab-1")

    assert result == {"status": "success", "kind": "url", "selector": None, "value": "https://example.com"}
    assert driver.cancelled == ["tab-1"]
    assert driver.scheduled == [{"tab_id": "tab-1", "close": True}]


def test_get_attr_supports_snapshot_refs(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.refs.add("tab-1", role="link", name="Inspect target link", backend_node_id=42)
    calls = []

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        calls.append({"tab_id": tab_id, "expression": expression})
        return "https://example.com/target"

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)

    result = actions.get(driver, "attr", selector="@e1", attr="href", switch_tab_id="tab-1")

    assert result == {"status": "success", "kind": "attr", "selector": "@e1", "value": "https://example.com/target"}
    assert calls[0]["tab_id"] == "tab-1"
    assert '"Inspect target link"' in calls[0]["expression"]
    assert '"href"' in calls[0]["expression"]


def test_get_reports_missing_element_as_structured_error(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: {"__omnibotElementError": True, "reason": "element_not_found"})

    result = actions.get(driver, "text", selector="#does-not-exist", switch_tab_id="tab-1")

    assert result == {
        "status": "error",
        "msg": "Element not found for text: #does-not-exist",
        "reason": "element_not_found",
        "selector": "#does-not-exist",
    }


def test_fill_reschedules_tool_created_target_after_done(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    driver.ctx.tool_created_tabs.add("tab-1")
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=True)

    monkeypatch.setattr(interactions, "fill", lambda *args, **kwargs: {"filled": "#email", "value": "tester@example.com"})

    result = actions.fill(driver, "#email", "tester@example.com", switch_tab_id="tab-1")

    assert result == {"status": "success", "filled": "#email", "value": "tester@example.com"}
    assert driver.cancelled == ["tab-1"]
    assert driver.scheduled == [{"tab_id": "tab-1", "close": True}]


def test_fill_schedules_user_owned_target_for_ungroup_only_after_done(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    driver.ctx.sessions["tab-1"] = SimpleNamespace(created_by_tool=False)

    monkeypatch.setattr(interactions, "fill", lambda *args, **kwargs: {"filled": "#email", "value": "tester@example.com"})

    result = actions.fill(driver, "#email", "tester@example.com", switch_tab_id="tab-1")

    assert result == {"status": "success", "filled": "#email", "value": "tester@example.com"}
    assert driver.cancelled == ["tab-1"]
    assert driver.scheduled == [{"tab_id": "tab-1", "close": False}]


def test_click_new_tab_schedules_created_tab_after_done(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    monkeypatch.setattr(
        interactions,
        "click_new_tab",
        lambda *args, **kwargs: {"status": "success", "clicked": "@e2", "new_tab": True, "url": "https://example.com/next", "tab": {"id": "new-tab"}},
    )

    result = actions.click(driver, "@e2", switch_tab_id="tab-1", new_tab=True)

    assert result["status"] == "success"
    assert "new-tab" in driver.ctx.tool_created_tabs
    assert driver.scheduled == [
        {"tab_id": "new-tab", "close": True},
        {"tab_id": "tab-1", "close": False},
    ]


def test_click_schedules_tabs_opened_by_normal_click(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    driver.ctx.sessions["edge-client:200"] = SimpleNamespace(created_by_tool=False)
    monkeypatch.setattr(
        interactions,
        "click",
        lambda *args, **kwargs: {
            "clicked": "@e2",
            "x": 10,
            "y": 20,
            "navigation": False,
            "url": "https://example.com",
            "newTabs": [
                {"id": 200, "url": "https://example.com/next", "openerTabId": 101, "browserClientId": "edge-client"}
            ],
        },
    )

    result = actions.click(driver, "@e2", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert "edge-client:200" in driver.ctx.tool_created_tabs
    assert driver.ctx.sessions["edge-client:200"].created_by_tool is True
    assert driver.scheduled == [
        {"tab_id": "edge-client:200", "close": True},
        {"tab_id": "tab-1", "close": False},
    ]


def test_click_does_not_claim_concurrently_opened_user_tab(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    driver.ctx.sessions["edge-client:200"] = SimpleNamespace(created_by_tool=False)
    monkeypatch.setattr(
        interactions,
        "click",
        lambda *args, **kwargs: {
            "clicked": "@e2",
            "x": 10,
            "y": 20,
            "navigation": False,
            "url": "https://example.com",
            "newTabs": [
                {"id": 200, "url": "https://www.bilibili.com/video/example", "openerTabId": 99, "browserClientId": "edge-client"}
            ],
        },
    )

    actions.click(driver, "@e2", switch_tab_id="tab-1")

    assert "edge-client:200" not in driver.ctx.tool_created_tabs
    assert driver.ctx.sessions["edge-client:200"].created_by_tool is False
    assert {"tab_id": "edge-client:200", "close": True} not in driver.scheduled


def test_click_does_not_claim_new_tab_without_opener_evidence(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    monkeypatch.setattr(
        interactions,
        "click",
        lambda *args, **kwargs: {
            "clicked": "@e2",
            "x": 10,
            "y": 20,
            "navigation": False,
            "url": "https://example.com",
            "newTabs": [{"id": 200, "url": "https://example.com/next", "browserClientId": "edge-client"}],
        },
    )

    actions.click(driver, "@e2", switch_tab_id="tab-1")

    assert "edge-client:200" not in driver.ctx.tool_created_tabs
    assert {"tab_id": "edge-client:200", "close": True} not in driver.scheduled


def test_click_claims_noopener_tab_confirmed_by_status_group(monkeypatch):
    from omnibot import interactions

    driver = FakeDriver()
    driver.ctx.sessions["edge-client:200"] = SimpleNamespace(created_by_tool=False)
    monkeypatch.setattr(
        interactions,
        "click",
        lambda *args, **kwargs: {
            "clicked": "@e2",
            "x": 10,
            "y": 20,
            "navigation": False,
            "url": "https://example.com",
            "newTabs": [
                {
                    "id": 200,
                    "url": "https://mp.weixin.qq.com/s/article",
                    "browserClientId": "edge-client",
                    "ownershipReason": "status-group",
                }
            ],
        },
    )

    actions.click(driver, "@e2", switch_tab_id="tab-1")

    assert "edge-client:200" in driver.ctx.tool_created_tabs
    assert driver.ctx.sessions["edge-client:200"].created_by_tool is True
    assert {"tab_id": "edge-client:200", "close": True} in driver.scheduled


class SessionStub:
    def __init__(self, session_id, info):
        self.id = session_id
        self.info = info
        self.tab_id = info.get("tab_id", session_id)
        self.client_id = info.get("client_id")
        self.created_by_tool = False
        self.type = info.get("type", "ext_ws")


class ExecuteJsNewTabsDriver:
    def __init__(self):
        self.multi_user = False
        self.ctx = SimpleNamespace(
            sessions={
                "edge-client:100": SessionStub(
                    "edge-client:100",
                    {
                        "url": "https://www.baidu.com/",
                        "title": "Baidu",
                        "type": "ext_ws",
                        "client_id": "edge-client",
                        "tab_id": "100",
                    },
                ),
                "edge-client:200": SessionStub(
                    "edge-client:200",
                    {
                        "url": "https://news.baidu.com/",
                        "title": "Baidu News",
                        "type": "ext_ws",
                        "client_id": "edge-client",
                        "tab_id": "200",
                    },
                ),
            },
            tool_created_tabs=set(),
            grouped_tabs={},
            grouped_tab_versions={},
            _group_lock=__import__("threading").Lock(),
        )
        self.cancelled = []
        self.scheduled = []
        self.group_calls = []

    def get_context(self, token=None):
        return self.ctx

    def get_all_sessions(self, token=None):
        return self.ctx.get_all_active_sessions() if hasattr(self.ctx, 'get_all_active_sessions') else [
            {"id": s.id, "tab_id": s.tab_id, "url": s.info.get("url", ""), "title": s.info.get("title", ""), "type": s.type, "connected_at": 1}
            for s in self.ctx.sessions.values()
        ]

    def _cancel_tab_close(self, tab_id, token=None):
        self.cancelled.append(tab_id)

    def _raw_tab_id(self, tab_id, token=None):
        raw = str(tab_id)
        if ":" in raw:
            return raw.rsplit(":", 1)[1]
        return raw

    def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=True):
        self.scheduled.append({"tab_id": tab_id, "close": close})

    def update_tab_group(self, tab_id, group_name, token=None):
        self.group_calls.append((tab_id, group_name))


def test_execute_js_schedules_returned_new_tabs_independently(monkeypatch):
    driver = ExecuteJsNewTabsDriver()

    def fake_execute_js_rich(script, driver, no_monitor=False, token=None, group_status=None, session_id=None, status_tab_id=None):
        return {
            "status": "success",
            "js_return": "点击成功",
            "tab_id": "edge-client:100",
            "newTabs": [
                {
                    "id": 200,
                    "url": "https://news.baidu.com/",
                    "title": "Baidu News",
                    "openerTabId": 100,
                    "browserClientId": "edge-client",
                }
            ],
        }

    monkeypatch.setattr(actions.simphtml, "execute_js_rich", fake_execute_js_rich)
    monkeypatch.setattr(actions.importlib, "reload", lambda x: x)

    result = actions.execute_js(driver, "document.querySelector('a').click()", switch_tab_id="edge-client:100")

    assert result["status"] == "success"
    assert "edge-client:200" in driver.ctx.tool_created_tabs
    assert driver.ctx.sessions["edge-client:200"].created_by_tool is True
    assert {"tab_id": "edge-client:200", "close": True} in driver.scheduled


def test_tmwebdriver_execute_js_requires_session_id_for_page_scripts(monkeypatch):
    driver = TMWebDriver.__new__(TMWebDriver)
    driver.multi_user = False
    driver.is_remote = False
    driver._default_ctx = UserContext("__default__")
    ctx = driver._default_ctx

    ctx.tool_created_tabs.add("edge-client:tool-stale")

    sent_payloads = []

    class FakeWs:
        def send_message(self, payload):
            sent_payloads.append(json.loads(payload))

    ctx.sessions["edge-client:chatgpt"] = Session(
        "edge-client:chatgpt",
        {
            "url": "https://chatgpt.com/c/6a24c42b-ad24-83e8-9cf7-f389d1818eac",
            "title": "ChatGPT",
            "type": "ext_ws",
            "client_id": "edge-client",
            "tab_id": "99",
        },
        FakeWs(),
    )
    monkeypatch.setattr(actions.time, "sleep", lambda _: None)

    with pytest.raises(ValueError, match="session_id is required"):
        driver.execute_js("return 1;")

    assert sent_payloads == []


def test_snapshot_appends_dom_popup_controls(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    ax_tree = {"nodes": [{"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}}]}
    evaluations = []

    def fake_send_cdp(driver_arg, tab_id, method, params, token=None, **kwargs):
        if method == "Accessibility.getFullAXTree":
            return ax_tree
        return {}

    def fake_evaluate(driver_arg, tab_id, script, token=None):
        evaluations.append(script)
        if "dom_richtext_controls" in script or "editorSelector" in script:
            return []
        return [{"role": "button", "name": "取消", "selector": ".modal .cancel", "box": {"x": 1, "y": 2, "width": 3, "height": 4}}]

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)

    result = actions.snapshot(driver, switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert "# DOM Popup Controls" in result["content"]
    assert '@e2 [button] "取消"' in result["content"]
    assert driver.ctx.refs.get("tab-1", "@e2").selector == ".modal .cancel"
    assert evaluations


def test_snapshot_collects_dom_popup_controls_before_ax_tree(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    calls = []

    def fake_send_cdp(driver_arg, tab_id, method, params, token=None, **kwargs):
        calls.append(method)
        if method == "Accessibility.getFullAXTree":
            return {"nodes": [{"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}}]}
        return {}

    def fake_evaluate(driver_arg, tab_id, script, token=None):
        calls.append("Runtime.evaluate")
        if "dom_richtext_controls" in script or "editorSelector" in script:
            return []
        return [{"role": "option", "name": "BOT KEY", "selector": "[role=option]:nth-of-type(2)", "box": {"x": 10, "y": 20, "width": 100, "height": 28}}]

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)

    result = actions.snapshot(driver, switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert '@e2 [option] "BOT KEY"' in result["content"]
    assert calls.index("Runtime.evaluate") < calls.index("Accessibility.getFullAXTree")


def test_snapshot_collects_combobox_options_before_ax_tree(monkeypatch):
    from omnibot import cdp, snapshot as snapshot_mod

    driver = FakeDriver()
    calls = []
    ax_tree = {"nodes": [{"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}}]}
    evaluate_count = {"n": 0}

    def fake_send_cdp(driver_arg, tab_id, method, params, token=None, **kwargs):
        calls.append(method)
        if method == "Accessibility.getFullAXTree":
            return ax_tree
        return {}

    def fake_evaluate(driver_arg, tab_id, script, token=None):
        evaluate_count["n"] += 1
        calls.append("Runtime.evaluate")
        if evaluate_count["n"] == 1:
            return []
        if "dom_combobox_options" in script or "controlSelector" in script:
            return [{"role": "option", "name": "OpenAI Chat", "selector": ".protocol [role=option]:nth-of-type(2)", "openerSelector": "#protocol", "box": {"x": 10, "y": 20, "width": 100, "height": 28}}]
        return []

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)

    result = actions.snapshot(driver, switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert '@e2 [option] "OpenAI Chat"' in result["content"]
    assert result["refs"]["e2"]["openerSelector"] == "#protocol"
    assert calls.index("Runtime.evaluate") < calls.index("Accessibility.getFullAXTree")


def test_click_uses_selector_from_ref_when_name_lookup_fails(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.refs.add("tab-1", role="button", name="", selector=".modal-close", box={"x": 10, "y": 20, "width": 30, "height": 40})
    evaluated = []

    def fake_send_cdp(driver_arg, tab_id, method, params, **kwargs):
        if method == "Runtime.evaluate":
            evaluated.append(params["expression"])
            if ".modal-close" in params["expression"]:
                return {"result": {"value": {"x": 10, "y": 20, "width": 30, "height": 40}}}
            return {"result": {"value": None}}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "https://example.com")

    result = actions.click(driver, "@e1", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert result["clicked"] == "@e1"
    assert any(".modal-close" in expression for expression in evaluated)


def test_click_reopens_combobox_for_transient_option_refs(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.refs.add(
        "tab-1",
        role="option",
        name="BOT KEY",
        selector=".popup [role=option]:nth-of-type(2)",
        opener_selector='button[role="combobox"]',
        box={"x": 10, "y": 20, "width": 100, "height": 28},
    )
    evaluated = []

    def fake_send_cdp(driver_arg, tab_id, method, params, **kwargs):
        if method == "Runtime.evaluate":
            expression = params["expression"]
            evaluated.append(expression)
            if "activateTransientOption" in expression:
                return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 28}}}
            return {"result": {"value": None}}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "https://example.com")

    result = actions.click(driver, "@e1", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert any("activateTransientOption" in expression and "BOT KEY" in expression and "combobox" in expression for expression in evaluated)


def test_transient_option_script_uses_native_click_for_base_ui_comboboxes():
    from omnibot import interactions

    script = interactions.activate_transient_option_script('#create-type', '[role="option"]', 'BOT KEY', 1)

    assert '.click()' in script
    assert 'rectOf(option)' in script


def test_click_reopens_transient_option_after_hidden_named_match(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.refs.add(
        "tab-1",
        role="option",
        name="BOT KEY",
        selector=".popup [role=option]:nth-of-type(2)",
        opener_selector="#create-type",
        box={"x": 10, "y": 20, "width": 100, "height": 28},
    )
    evaluations = []

    def fake_send_cdp(driver_arg, tab_id, method, params, **kwargs):
        evaluations.append(method)
        if method == "Runtime.evaluate":
            expression = params["expression"]
            evaluations.append(expression)
            if "activateTransientOption" in expression:
                return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 28}}}
            return {"result": {"value": {"x": 0, "y": 0, "width": 0, "height": 0}}}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "https://example.com")

    result = actions.click(driver, "@e1", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert any("activateTransientOption" in expression for expression in evaluations)
    assert "Input.dispatchMouseEvent" in evaluations


def test_click_transient_option_skips_named_js_click_when_visible(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.refs.add(
        "tab-1",
        role="option",
        name="API KEY",
        selector=".popup [role=option]:nth-of-type(1)",
        opener_selector="#create-type",
        box={"x": 10, "y": 20, "width": 100, "height": 28},
    )
    runtime_expressions = []
    methods = []

    def fake_send_cdp(driver_arg, tab_id, method, params, **kwargs):
        methods.append(method)
        if method == "Runtime.evaluate":
            expression = params["expression"]
            runtime_expressions.append(expression)
            if "activateTransientOption" in expression:
                return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 28}}}
            raise AssertionError("transient option should not use named JS click")
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        if "__omnibotCoordinateClickProbe" in expression:
            return {"clicked": True}
        return "https://example.com"

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)

    result = actions.click(driver, "@e1", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert any("activateTransientOption" in expression for expression in runtime_expressions)
    assert "Input.dispatchMouseEvent" in methods


def test_click_transient_option_uses_saved_box_when_option_lookup_fails(monkeypatch):
    from omnibot import cdp

    driver = FakeDriver()
    driver.ctx.refs.add(
        "tab-1",
        role="option",
        name="API KEY",
        selector=".stale-option",
        opener_selector="#create-type",
        box={"x": 10, "y": 20, "width": 100, "height": 28},
    )
    expressions = []
    methods = []

    def fake_send_cdp(driver_arg, tab_id, method, params, **kwargs):
        methods.append(method)
        if method == "Runtime.evaluate":
            expression = params["expression"]
            expressions.append(expression)
            if "activateTransientOption" in expression:
                return {"result": {"value": None}}
            if "#create-type" in expression:
                return {"result": {"value": True}}
            return {"result": {"value": None}}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "https://example.com")

    result = actions.click(driver, "@e1", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert any("activateTransientOption" in expression for expression in expressions)
    assert any("#create-type" in expression for expression in expressions)
    assert "Input.dispatchMouseEvent" in methods


# ---------------------------------------------------------------------------
# clipboard_read / clipboard_write contract
# ---------------------------------------------------------------------------

class _ClipboardFakeDriver(FakeDriver):
    """FakeDriver variant that captures extension_command calls for clipboard."""

    def __init__(self):
        super().__init__()
        self.ext_commands = []

    def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
        import json as _json
        try:
            cmd = _json.loads(code) if isinstance(code, str) else code
        except Exception:
            cmd = None
        if isinstance(cmd, dict) and cmd.get("cmd") == "clipboard":
            self.ext_commands.append(cmd)
            method = cmd.get("method")
            if method == "readText":
                return {"data": {"text": "hello-clipboard"}}
            if method == "writeText":
                return {"data": {"text": cmd.get("text", "")}}
        return super().execute_js(code, timeout=timeout, session_id=session_id, token=token, group_status=group_status, status_tab_id=status_tab_id)


def test_clipboard_read_uses_extension_command_not_cdp():
    driver = _ClipboardFakeDriver()
    result = actions.clipboard_read(driver, switch_tab_id="tab-1")
    assert result["status"] == "success"
    assert result["text"] == "hello-clipboard"
    assert len(driver.ext_commands) == 1
    assert driver.ext_commands[0]["cmd"] == "clipboard"
    assert driver.ext_commands[0]["method"] == "readText"


def test_clipboard_write_uses_extension_command_not_cdp():
    driver = _ClipboardFakeDriver()
    result = actions.clipboard_write(driver, text="omnibot-test", switch_tab_id="tab-1")
    assert result["status"] == "success"
    assert result["text"] == "omnibot-test"
    assert len(driver.ext_commands) == 1
    assert driver.ext_commands[0]["cmd"] == "clipboard"
    assert driver.ext_commands[0]["method"] == "writeText"
    assert driver.ext_commands[0]["text"] == "omnibot-test"


def test_viewport_set_reports_error_when_requested_css_size_was_not_applied(monkeypatch):
    driver = FakeDriver()
    cdp_calls = []

    def fake_send_cdp(driver_arg, tab_id, method, params=None, **kwargs):
        cdp_calls.append((method, params or {}))
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: {
        "width": 727,
        "height": 545,
        "deviceScaleFactor": 2.2,
    })

    result = actions.viewport_set(driver, width=800, height=600, switch_tab_id="tab-1")

    assert result["status"] == "error"
    assert result["reason"] == "viewport_not_applied"
    assert result["requested"] == {"width": 800, "height": 600}
    assert result["actual"] == {"width": 727, "height": 545}
    assert cdp_calls[0][0] == "Emulation.setDeviceMetricsOverride"


def test_viewport_set_accepts_one_pixel_browser_rounding(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(cdp, "send_cdp", lambda *args, **kwargs: {})
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: {"width": 480, "height": 641})

    result = actions.viewport_set(driver, width=480, height=640, switch_tab_id="tab-1")

    assert result == {
        "status": "success",
        "width": 480,
        "height": 640,
        "actual": {"width": 480, "height": 641},
    }


def test_viewport_set_calibrates_cdp_dimensions_for_browser_zoom(monkeypatch):
    driver = FakeDriver()
    cdp_calls = []
    viewport_reads = iter([
        {"width": 727, "height": 545, "deviceScaleFactor": 2.2},
        {"width": 800, "height": 600, "deviceScaleFactor": 2.2},
    ])

    def fake_send_cdp(driver_arg, tab_id, method, params=None, **kwargs):
        cdp_calls.append((method, params or {}))
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: next(viewport_reads))

    result = actions.viewport_set(driver, width=800, height=600, switch_tab_id="tab-1")

    assert result == {"status": "success", "width": 800, "height": 600}
    assert cdp_calls[1] == (
        "Emulation.setDeviceMetricsOverride",
        {"width": 880, "height": 660, "deviceScaleFactor": 1, "mobile": False},
    )


def test_get_wraps_selector_reads_in_selected_frame(monkeypatch):
    driver = FakeDriver()
    driver.ctx.frame_target = "payment-frame"
    evaluate_calls = []
    send_cdp_calls = []

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        evaluate_calls.append(expression)
        # First (and only) evaluate is the frame-descriptor probe; return a
        # descriptor whose id matches the frame in the fake frame tree below.
        return {"id": "payment-frame", "name": "payment-frame", "title": "", "src": "/pay", "url": "https://example.com/pay"}

    def fake_send_cdp(driver_arg, tab_id, method, params=None, **kwargs):
        send_cdp_calls.append((method, params or {}))
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "payment-frame", "name": "payment-frame", "url": "https://example.com/pay"}, "childFrames": []}}
        if method == "Page.createIsolatedWorld":
            return {"executionContextId": 7}
        if method == "Runtime.evaluate":
            return {"result": {"value": "frame submitted FRAME-42"}}
        return {}

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.get(driver, "text", selector="#frame-status", switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert result["value"] == "frame submitted FRAME-42"
    # The frame-descriptor probe is evaluated once and references the frame target.
    assert len(evaluate_calls) == 1
    assert "payment-frame" in evaluate_calls[0]
    # The user script runs inside the isolated world via Runtime.evaluate.
    assert send_cdp_calls[-1][0] == "Runtime.evaluate"
    assert "#frame-status" in send_cdp_calls[-1][1]["expression"]


def test_get_uses_exact_backend_node_for_ref_inside_selected_frame(monkeypatch):
    driver = FakeDriver()
    driver.ctx.frame_target = "iframe"
    driver.ctx.refs.add("tab-1", role="table", name="", backend_node_id=730)
    calls = []

    def fake_send_cdp(driver_arg, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        if method == "DOM.getOuterHTML":
            assert params == {"backendNodeId": 730}
            return {"outerHTML": "<table><tbody><tr><td>Task A</td></tr></tbody></table>"}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)
    monkeypatch.setattr(cdp, "evaluate_in_frame", lambda *_args, **_kwargs: pytest.fail("semantic frame lookup must not run"))

    result = actions.get(driver, "html", selector="@e1", switch_tab_id="tab-1")

    assert result == {
        "status": "success",
        "kind": "html",
        "selector": "@e1",
        "value": "<tbody><tr><td>Task A</td></tr></tbody>",
    }


def test_get_reports_selected_cross_origin_frame_inaccessible(monkeypatch):
    driver = FakeDriver()
    driver.ctx.frame_target = "remote-payment-frame"

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        # Cross-origin frame: the descriptor probe returns null because the
        # iframe element is not reachable from the top-level document context.
        return None

    def fake_send_cdp(driver_arg, tab_id, method, params=None, **kwargs):
        if method == "Page.getFrameTree":
            return {"frameTree": {"frame": {"id": "top", "url": "https://example.com"}, "childFrames": []}}
        return {}

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.get(driver, "text", selector="#remote-frame-status", switch_tab_id="tab-1")

    assert result["status"] == "error"
    assert result["reason"] == "cross_origin_or_inaccessible"
    assert result["frame"] == "remote-payment-frame"


def test_find_wraps_locator_script_in_selected_frame(monkeypatch):
    driver = FakeDriver()
    driver.ctx.frame_target = "payment-frame"
    expressions = []

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        expressions.append(expression)
        return True

    def fake_fill(driver_arg, selector, value, switch_tab_id="", token=None):
        expressions.append(f"fill:{selector}:{value}:{switch_tab_id}")
        return {"status": "success", "filled": selector, "value": value}

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(actions, "fill", fake_fill)

    result = actions.find(
        driver,
        "label",
        "Frame code",
        action="fill",
        action_value="FRAME-42",
        switch_tab_id="tab-1",
    )

    assert result["status"] == "success"
    assert "contentDocument" in expressions[0]
    assert "payment-frame" in expressions[0]
    assert expressions[1] == "fill:[data-omnibot-located='true']:FRAME-42:tab-1"


def test_find_reports_selected_cross_origin_frame_inaccessible(monkeypatch):
    driver = FakeDriver()
    driver.ctx.frame_target = "remote-payment-frame"

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        return {
            "__omnibotFrameError": True,
            "target": "remote-payment-frame",
            "reason": "cross_origin_or_inaccessible",
            "message": "Selected frame is cross-origin or inaccessible from this page context.",
        }

    monkeypatch.setattr(cdp, "evaluate", fake_evaluate)

    result = actions.find(
        driver,
        "label",
        "Remote frame code",
        action="fill",
        action_value="XFRAME-16",
        switch_tab_id="tab-1",
    )

    assert result["status"] == "error"
    assert result["reason"] == "cross_origin_or_inaccessible"
    assert result["frame"] == "remote-payment-frame"
    assert "cross-origin" in result["msg"]


def test_console_errors_filters_non_error_levels(monkeypatch):
    driver = FakeDriver()
    monkeypatch.setattr(
        actions,
        "console_logs",
        lambda *args, **kwargs: {
            "status": "success",
            "logs": [
                {"level": "log", "text": "ordinary"},
                {"level": "warn", "text": "warning"},
                {"level": "error", "text": "failure"},
            ],
        },
    )

    result = actions.console_errors(driver, tab_id="tab-1")

    assert result == {"status": "success", "logs": [{"level": "error", "text": "failure"}]}
