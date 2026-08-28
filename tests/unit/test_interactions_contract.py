import pytest

from omnibot import interactions
from omnibot.refs import RefMap


class FakeCdp:
    def __init__(self):
        self.calls = []

    def __call__(self, driver, tab_id, method, params=None, **kwargs):
        self.calls.append((method, params or {}))
        if method == "DOM.getBoxModel":
            return {"model": {"content": [10, 20, 110, 20, 110, 70, 10, 70]}}
        if method == "Runtime.evaluate":
            return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 50}}}
        return {}


def test_box_model_center_uses_content_quad_center():
    assert interactions.box_model_center({"content": [10, 20, 110, 20, 110, 70, 10, 70]}) == (60.0, 45.0)


def test_resolve_ref_center_prefers_backend_node(monkeypatch):
    fake = FakeCdp()
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake)
    ref_map = RefMap()
    ref_map.add("123", role="button", name="Submit", backend_node_id=30)

    assert interactions.resolve_center(object(), "123", "@e1", ref_map) == (60.0, 45.0)
    assert fake.calls[0] == ("DOM.getBoxModel", {"backendNodeId": 30})


def test_resolve_selector_center_uses_runtime_fallback(monkeypatch):
    fake = FakeCdp()
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake)

    assert interactions.resolve_center(object(), "123", "#submit", RefMap()) == (60.0, 45.0)
    assert fake.calls[0][0] == "Runtime.evaluate"


def test_dispatch_click_dispatches_mouse_move_press_release(monkeypatch):
    calls = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        if method == "Runtime.evaluate":
            return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 50}}}
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    interactions.dispatch_click(object(), "123", 60.0, 45.0)

    mouse_calls = [(m, p) for m, p in calls if m == "Input.dispatchMouseEvent"]
    assert mouse_calls[0] == ("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": 60.0, "y": 45.0})
    assert mouse_calls[1] == ("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 60.0, "y": 45.0, "button": "left", "buttons": 1, "clickCount": 1})
    assert mouse_calls[2] == ("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": 60.0, "y": 45.0, "button": "left", "buttons": 0, "clickCount": 1})


def test_drag_dispatches_html5_datatransfer_fallback(monkeypatch):
    calls = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        if method == "Runtime.evaluate":
            return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 50}}}
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    result = interactions.drag(object(), "123", "#drag-source", "#dropzone", RefMap())

    assert result["dragged"] == "#drag-source"
    assert result["target"] == "#dropzone"
    mouse_events = [params["type"] for method, params in calls if method == "Input.dispatchMouseEvent"]
    assert mouse_events == ["mouseMoved", "mousePressed", "mouseMoved", "mouseReleased"]
    fallback_scripts = [params["expression"] for method, params in calls if method == "Runtime.evaluate" and "new DataTransfer" in params.get("expression", "")]
    assert fallback_scripts
    assert "document.elementFromPoint(60.0, 45.0)" in fallback_scripts[0]
    assert "document.querySelector(\"#drag-source\")" not in fallback_scripts[0]
    assert "new DragEvent('dragstart'" in fallback_scripts[0]
    assert "new DragEvent('drop'" in fallback_scripts[0]


def test_click_activates_dom_element_and_reports_navigation(monkeypatch):
    evaluations = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        evaluations.append(params.get("expression", ""))
        return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 50}}}

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        evaluations.append(expression)
        if expression == "location.href":
            return "https://example.test/start" if len(evaluations) == 1 else "https://example.test/next"
        raise AssertionError(f"unexpected evaluate expression: {expression}")

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    result = interactions.click(object(), "123", "#submit", RefMap())

    assert result == {"clicked": "#submit", "x": 60.0, "y": 45.0, "navigation": True, "url": "https://example.test/next"}
    assert any("document.querySelector" in expression and "deferElementClick(el)" in expression for expression in evaluations)


def test_click_activation_scripts_defer_single_clicks_to_avoid_dialog_blocking():
    named = interactions.named_element_script("button", "Open confirm", None, 1)
    selector = interactions.activate_selector_script("#confirm", 1)

    assert "function deferElementClick" in named
    assert "function deferElementClick" in selector
    assert "el.click();" in named
    assert "el.click();" in selector


def test_click_post_activation_href_uses_short_timeout_when_dialog_blocks(monkeypatch):
    evaluate_calls = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 50}}}

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        evaluate_calls.append((expression, kwargs))
        if len(evaluate_calls) == 1:
            return "https://example.test/start"
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    result = interactions.click(object(), "123", "#opens-dialog", RefMap())

    assert result == {"clicked": "#opens-dialog", "x": 60.0, "y": 45.0, "navigation": False, "url": "https://example.test/start"}
    assert evaluate_calls[1][1]["timeout"] == 0.5


def test_click_text_ref_prefers_labeled_radio_or_checkbox_control(monkeypatch):
    evaluations = []
    ref_map = RefMap()
    ref_map.add("123", role="StaticText", name="不投放广告")

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        evaluations.append(params.get("expression", ""))
        return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 50}}}

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        evaluations.append(expression)
        if expression == "location.href":
            return "https://example.test/start"
        raise AssertionError(f"unexpected evaluate expression: {expression}")

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    result = interactions.click(object(), "123", "@e1", ref_map)

    assert result == {"clicked": "@e1", "x": 60.0, "y": 45.0, "navigation": False, "url": "https://example.test/start"}
    assert any('input[type="radio"],input[type="checkbox"]' in expression for expression in evaluations)
    assert any("labelText(control) === name" in expression for expression in evaluations)


def test_activate_element_requests_new_tab_watch_for_click_cdp(monkeypatch):
    calls = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}, kwargs))
        return {"result": {"value": {"x": 10, "y": 20, "width": 100, "height": 50}}}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    interactions.activate_element(object(), "123", "#submit", RefMap())

    assert any(method == "Runtime.evaluate" and kwargs.get("watch_new_tabs") is True for method, _params, kwargs in calls)


def test_frame_click_visual_uses_top_viewport_coordinates_without_duplicate_activation(monkeypatch):
    ref_map = RefMap()
    ref_map.add("123", role="link", name="Current task")
    frame_activations = []
    visuals = []

    def fake_evaluate_in_frame(_driver, _tab_id, _frame_target, expression, **_kwargs):
        frame_activations.append(expression)
        return {"x": 20, "y": 30, "width": 100, "height": 40}

    def fake_evaluate(_driver, _tab_id, expression, **_kwargs):
        assert "frame.getBoundingClientRect" in expression
        return {"x": 10, "y": 90}

    monkeypatch.setattr(interactions.cdp, "evaluate_in_frame", fake_evaluate_in_frame)
    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(
        interactions.cua,
        "broadcast_mouse_visual",
        lambda _driver, _tab_id, event, **kwargs: visuals.append((event, kwargs["x"], kwargs["y"])),
    )
    monkeypatch.setattr(
        interactions.cdp,
        "send_cdp",
        lambda *_args, **_kwargs: pytest.fail("successful frame activation must not be repeated"),
    )

    result = interactions.activate_element(object(), "123", "@e1", ref_map, frame_target="iframe")

    assert len(frame_activations) == 1
    assert result == (80.0, 140.0, [], {})
    assert visuals == [("release", 80.0, 140.0)]


def test_click_new_tab_normalizes_browser_client_session_id(monkeypatch):
    class Driver:
        def _raw_tab_id(self, tab_id, token=None):
            return str(tab_id).rsplit(":", 1)[-1]

        def execute_js(self, *args, **kwargs):
            return {
                "data": {"id": 456, "url": "https://example.test/next"},
                "browserClientId": "edge-client",
            }

    monkeypatch.setattr(interactions.cdp, "evaluate", lambda *args, **kwargs: "https://example.test/next")

    result = interactions.click_new_tab(Driver(), "edge-client:123", "a", RefMap())

    assert result["tab"]["id"] == "edge-client:456"
    assert result["tab"]["tab_id"] == "456"
    assert result["tab"]["browserClientId"] == "edge-client"


def test_activate_element_prefers_backend_node_for_shadow_dom_refs(monkeypatch):
    calls = []
    ref_map = RefMap()
    ref_map.add("123", role="button", name="Shadow action", backend_node_id=42)

    def fake_backend(driver, tab_id, backend_node_id, click_count, **kwargs):
        calls.append((tab_id, backend_node_id, click_count))
        return {"x": 5, "y": 10, "width": 80, "height": 30}

    def unexpected_send(*args, **kwargs):
        return {"result": {"value": None}}

    monkeypatch.setattr(interactions, "activate_backend_node", fake_backend)
    monkeypatch.setattr(interactions.cdp, "send_cdp", unexpected_send)

    result = interactions.activate_element(object(), "123", "@e1", ref_map)

    assert result == (45.0, 25.0, [], {})
    assert calls == [("123", 42, 1)]


def test_backend_ref_click_scrolls_stabilizes_reboxes_and_hit_tests(monkeypatch):
    calls = []
    box_calls = 0
    metrics_calls = 0

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        nonlocal box_calls, metrics_calls
        calls.append((method, params or {}))
        if method == "Page.getLayoutMetrics":
            metrics_calls += 1
            return {"cssVisualViewport": {"pageX": 0, "pageY": 1100, "clientWidth": 1200, "clientHeight": 800}}
        if method == "DOM.getBoxModel":
            box_calls += 1
            y = 1400 if box_calls == 1 else 300
            return {"model": {"content": [10, y, 110, y, 110, y + 50, 10, y + 50]}}
        if method == "DOM.describeNode":
            return {"node": {"attributes": []}}
        if method == "DOM.getNodeForLocation":
            return {"backendNodeId": 42}
        return {"result": {"value": True}}

    clicked = []
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions, "dispatch_verified_click", lambda _driver, _tab_id, x, y, **kwargs: clicked.append((x, y)))

    result = interactions.activate_backend_node(object(), "123", 42, 1)

    assert ("DOM.scrollIntoViewIfNeeded", {"backendNodeId": 42}) in calls
    assert [method for method, _params in calls].count("DOM.getBoxModel") == 3
    assert "Runtime.evaluate" not in [method for method, _params in calls]
    assert clicked == [(60.0, 325.0)]
    assert result["auto_scrolled"] is True
    assert result["before_box"]["y"] == 1400
    assert result["clicked_box"]["y"] == 300
    assert result["hit_test"] is True
    assert result["hit_backend_node_id"] == 42


def test_backend_ref_click_rejects_covered_target(monkeypatch):
    methods = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        methods.append(method)
        if method == "Page.getLayoutMetrics":
            return {"cssVisualViewport": {"pageX": 0, "pageY": 0, "clientWidth": 1200, "clientHeight": 800}}
        if method == "DOM.getBoxModel":
            return {"model": {"content": [10, 300, 110, 300, 110, 350, 10, 350]}}
        if method == "DOM.describeNode":
            return {"node": {"attributes": []}}
        if method == "DOM.getNodeForLocation":
            return {"backendNodeId": 99}
        return {"result": {"value": True}}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions, "dispatch_verified_click", lambda *args, **kwargs: pytest.fail("covered target must not be clicked"))

    with pytest.raises(interactions.InteractionError, match="covered"):
        interactions.activate_backend_node(object(), "123", 42, 1)

    assert "Input.dispatchMouseEvent" not in methods


def test_backend_hit_test_accepts_target_descendant(monkeypatch):
    monkeypatch.setattr(
        interactions.cdp,
        "send_cdp",
        lambda *args, **kwargs: {
            "node": {
                "backendNodeId": 42,
                "children": [{"backendNodeId": 43, "children": [{"backendNodeId": 44}]}],
            }
        },
    )

    assert interactions._backend_contains_node(object(), "123", 42, 44) is True


def test_press_key_dispatches_keydown_and_keyup(monkeypatch):
    calls = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        if method == "Runtime.evaluate":
            return {"result": {"value": ""}}
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    result = interactions.press_key(object(), "123", "Enter")

    assert result == {"key": "Enter", "event": "press"}
    assert calls[0] == ("Page.bringToFront", {})
    assert calls[1][1]["type"] == "keyDown"
    assert calls[2][1]["type"] == "keyUp"


def test_press_key_uses_raw_keydown_for_modifiers(monkeypatch):
    calls = []

    monkeypatch.setattr(
        interactions.cdp,
        "send_cdp",
        lambda driver, tab_id, method, params=None, **kwargs: calls.append((method, params or {})) or {},
    )

    interactions.press_key(object(), "123", "Shift", event_type="down")

    key_event = next(params for method, params in calls if method == "Input.dispatchKeyEvent")
    assert key_event["type"] == "rawKeyDown"
    assert key_event["modifiers"] == 8


def test_active_element_focus_helpers_restore_focus(monkeypatch):
    expressions = []

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        expressions.append(expression)
        return True

    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    assert interactions.save_active_element(object(), "123") is True
    assert interactions.restore_saved_active_element(object(), "123") is True
    assert "__omnibotKeyboardFocus" in expressions[0]
    assert "delete window.__omnibotKeyboardFocus" in expressions[1]


def test_select_option_rejects_missing_option_without_mutating(monkeypatch):
    calls = []

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        calls.append(expression)
        return {"ok": False, "reason": "option_not_found"}

    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    with pytest.raises(interactions.InteractionError, match="Select option not found"):
        interactions.select_option(object(), "123", "#mode", "missing")

    assert len(calls) == 1


def test_fill_clicks_and_inserts_text(monkeypatch):
    calls = []

    def fake_click(driver, tab_id, selector, ref_map, **kwargs):
        calls.append(("click", selector))
        return {"clicked": selector, "x": 1, "y": 2, "navigation": False, "url": "https://example.com"}

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        return {}

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        calls.append(("evaluate", expression))
        return True

    monkeypatch.setattr(interactions, "click", fake_click)
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions.cdp, "evaluate", lambda *args, **kwargs: True)
    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    result = interactions.fill(object(), "123", "#email", "a@b.com", RefMap())

    assert result == {"filled": "#email", "value": "a@b.com"}
    assert ("click", "#email") in calls
    assert ("Input.insertText", {"text": "a@b.com"}) in calls


def test_fill_reconciles_form_value_after_cdp_insertion(monkeypatch):
    expressions = []

    monkeypatch.setattr(interactions, "click", lambda *args, **kwargs: {"clicked": "#email"})
    monkeypatch.setattr(interactions.cdp, "send_cdp", lambda *args, **kwargs: {})

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        expressions.append(expression)
        return True

    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    interactions.fill(object(), "123", "#email", "a@b.com", RefMap())

    assert any("HTMLInputElement.prototype" in expression for expression in expressions)
    assert any("dispatchEvent(new Event('input'" in expression for expression in expressions)
    assert any("dispatchEvent(new Event('change'" in expression for expression in expressions)


def test_fill_selects_without_dispatching_ctrl_a_key_events(monkeypatch):
    calls = []
    monkeypatch.setattr(interactions, "click", lambda *args, **kwargs: {"clicked": "#email"})
    monkeypatch.setattr(interactions.cdp, "send_cdp", lambda _d, _t, method, params=None, **_k: calls.append((method, params or {})) or {})
    monkeypatch.setattr(interactions.cdp, "evaluate", lambda _d, _t, expression, **_k: calls.append(("evaluate", expression)) or True)

    interactions.fill(object(), "123", "#email", "a@b.com", RefMap())

    assert not any(method == "Input.dispatchKeyEvent" for method, _params in calls)
    assert any(method == "Input.insertText" for method, _params in calls)
    assert any(method == "evaluate" and "select()" in expression for method, expression in calls)


def test_fill_rejects_noneditable_target(monkeypatch):
    monkeypatch.setattr(interactions, "click", lambda *args, **kwargs: {"clicked": "#status"})

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        if "tag === 'input'" in expression:
            return False
        return True

    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    with pytest.raises(interactions.InteractionError, match="Element is not editable"):
        interactions.fill(object(), "123", "#status", "SHOULD-FAIL", RefMap())


def test_fill_focuses_selectorless_textbox_ref_semantically(monkeypatch):
    calls = []
    ref_map = RefMap()
    ref_map.add("123", role="textbox", name="Message")

    monkeypatch.setattr(interactions, "click", lambda *args, **kwargs: calls.append(("click", args[2])))
    monkeypatch.setattr(interactions.cdp, "send_cdp", lambda *args, **kwargs: calls.append(("send", args[2])))

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        calls.append(("evaluate", expression))
        return True

    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)

    result = interactions.fill(object(), "123", "@e1", "alpha", ref_map)

    assert result == {"filled": "@e1", "value": "alpha"}
    assert not any(kind == "click" for kind, _value in calls)
    assert any(kind == "evaluate" and "Message" in value for kind, value in calls)


def test_fill_uses_exact_backend_node_and_verifies_reconciled_value(monkeypatch):
    calls = []
    ref_map = RefMap()
    ref_map.add("123", role="textbox", name="", backend_node_id=197, input_type="password")

    def fake_send(_driver, _tab_id, method, params=None, **_kwargs):
        calls.append((method, params or {}))
        if method == "DOM.resolveNode":
            assert params == {"backendNodeId": 197}
            return {"object": {"objectId": "password-object"}}
        if method == "Runtime.callFunctionOn":
            if params.get("arguments"):
                return {"result": {"value": {"ok": True, "value": "secret"}}}
            return {"result": {"value": {"ok": True, "value": ""}}}
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions.cdp, "evaluate", lambda *_args, **_kwargs: pytest.fail("semantic lookup must not run"))

    result = interactions.fill(object(), "123", "@e1", "secret", ref_map)

    assert result == {"filled": "@e1", "value": "secret"}
    assert ("Input.insertText", {"text": "secret"}) in calls
    assert sum(method == "DOM.resolveNode" for method, _params in calls) == 2
    assert any(
        method == "Runtime.callFunctionOn" and params.get("arguments") == [{"value": "secret"}]
        for method, params in calls
    )


def test_fill_rejects_backend_ref_when_exact_value_does_not_change(monkeypatch):
    ref_map = RefMap()
    ref_map.add("123", role="textbox", name="", backend_node_id=197)

    def fake_send(_driver, _tab_id, method, params=None, **_kwargs):
        if method == "DOM.resolveNode":
            return {"object": {"objectId": "password-object"}}
        if method == "Runtime.callFunctionOn":
            if params.get("arguments"):
                return {"result": {"value": {"ok": False, "value": ""}}}
            return {"result": {"value": {"ok": True, "value": ""}}}
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    with pytest.raises(interactions.InteractionError, match="value was not updated"):
        interactions.fill(object(), "123", "@e1", "secret", ref_map)


def test_named_textbox_lookup_does_not_match_empty_label_checkbox():
    script = interactions.named_element_script("textbox", "", 1, 1)

    assert "['checkbox', 'radio'].includes(role)" in script
    assert "control.type === role" in script


def test_select_option_resolves_selectorless_combobox_ref(monkeypatch):
    ref_map = RefMap()
    ref_map.add("123", role="combobox", name="Mode")
    expressions = []

    monkeypatch.setattr(interactions.cdp, "evaluate", lambda _d, _t, expression, **_k: expressions.append(expression) or {"ok": True, "value": "gamma"})

    assert interactions.select_option(object(), "123", "@e1", "gamma", ref_map) == {"selected": "@e1", "value": "gamma"}
    assert any("Mode" in expression and "combobox" in expression for expression in expressions)


def test_set_checked_resolves_selectorless_checkbox_ref(monkeypatch):
    ref_map = RefMap()
    ref_map.add("123", role="checkbox", name="I agree")
    expressions = []

    monkeypatch.setattr(interactions.cdp, "evaluate", lambda _d, _t, expression, **_k: expressions.append(expression) or {"ok": True})

    assert interactions.set_checked(object(), "123", "@e1", ref_map, True) == {"checked": True, "selector": "@e1"}
    assert any("I agree" in expression and "input[type=\"checkbox\"]" in expression for expression in expressions)


def test_set_checked_rejects_noncheckable_target(monkeypatch):
    monkeypatch.setattr(
        interactions.cdp,
        "evaluate",
        lambda *args, **kwargs: {"ok": False, "reason": "not_checkable"},
    )

    with pytest.raises(interactions.InteractionError, match="Element is not checkable"):
        interactions.set_checked(object(), "123", "#email", RefMap(), True)


def test_ref_get_script_normalizes_ax_label_whitespace():
    from omnibot.actions import ref_get_script

    script = ref_get_script("checkbox", " I agree to automation testing", 0, "checked")

    assert 'const name = "I agree to automation testing"' in script


def test_type_text_dispatches_printable_key_events(monkeypatch):
    calls = []

    def fake_click(driver, tab_id, selector, ref_map, **kwargs):
        calls.append(("click", selector))
        return {"clicked": selector, "x": 1, "y": 2, "navigation": False, "url": "https://example.com"}

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        return {}

    monkeypatch.setattr(interactions, "click", fake_click)
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)
    monkeypatch.setattr(interactions.cdp, "evaluate", lambda *args, **kwargs: True)

    result = interactions.type_text(object(), "123", "body", "ab", RefMap())

    assert result == {"typed": "body", "text": "ab"}
    assert ("click", "body") in calls
    key_events = [params for method, params in calls if method == "Input.dispatchKeyEvent"]
    assert key_events[0]["type"] == "rawKeyDown"
    assert key_events[0]["key"] == "a"
    assert key_events[0]["text"] == "a"
    assert key_events[2]["type"] == "rawKeyDown"
    assert key_events[2]["key"] == "b"
    assert not any(method == "Input.insertText" for method, _params in calls)


def test_type_text_refocuses_target_after_activation_before_dispatching_keys(monkeypatch):
    calls = []

    def fake_click(driver, tab_id, selector, ref_map, **kwargs):
        calls.append(("click", selector))
        return {"clicked": selector}

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        calls.append(("evaluate", expression))
        return True

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        return {}

    monkeypatch.setattr(interactions, "click", fake_click)
    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    interactions.type_text(object(), "123", "#search", "keyboard", RefMap())

    focus_calls = [expression for method, expression in calls if method == "evaluate" and ".focus()" in expression]
    assert focus_calls, "type must restore target focus before dispatching printable keys"
    assert calls.index(("evaluate", focus_calls[0])) < next(i for i, call in enumerate(calls) if call[0] == "Input.dispatchKeyEvent")


def test_type_text_falls_back_to_insert_text_when_key_events_do_not_update_control(monkeypatch):
    calls = []

    def fake_click(driver, tab_id, selector, ref_map, **kwargs):
        calls.append(("click", selector))
        return {"clicked": selector}

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        calls.append(("evaluate", expression))
        if ".focus()" in expression:
            return True
        if "activeElement" in expression:
            return ""
        return True

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        return {}

    monkeypatch.setattr(interactions, "click", fake_click)
    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    interactions.type_text(object(), "123", "#search", "keyboard", RefMap())

    assert ("Input.insertText", {"text": "keyboard"}) in calls


def test_keyboard_insert_text_uses_insert_text_without_key_events(monkeypatch):
    calls = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    result = interactions.keyboard_insert_text(object(), "123", "ab")

    assert result == {"inserted": "ab"}
    assert calls[0][0] == "Runtime.evaluate"
    assert ("Page.bringToFront", {}) in calls
    assert ("Input.insertText", {"text": "ab"}) in calls
    assert not any(method == "Input.dispatchKeyEvent" for method, _params in calls)


def test_keyboard_type_dispatches_key_events(monkeypatch):
    calls = []

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        if method == "Runtime.evaluate":
            return {"result": {"value": ""}}
        return {}

    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    result = interactions.keyboard_type(object(), "123", "ab")

    assert result == {"typed": "ab"}
    key_events = [params for method, params in calls if method == "Input.dispatchKeyEvent"]
    assert [event["key"] for event in key_events if event["type"] == "rawKeyDown"] == ["a", "b"]
    assert ("Input.insertText", {"text": "ab"}) in calls
    assert any("Object.getOwnPropertyDescriptor" in params.get("expression", "") for method, params in calls if method == "Runtime.evaluate")


def test_named_element_script_maps_richtext_to_contenteditable():
    script = interactions.named_element_script("richtext", "请输入正文", None, 1)

    assert 'richtext' in script
    assert '[contenteditable="true"]' in script
    assert '[role="textbox"][aria-multiline="true"]' in script


def test_activate_selector_script_can_target_contenteditable_selector():
    script = interactions.activate_selector_script('[contenteditable="true"]', 1)

    assert 'document.querySelector(selector)' in script
    assert 'if (el.focus) el.focus();' in script


def test_activate_selector_script_clicks_located_text_match_range():
    script = interactions.activate_selector_script("[data-omnibot-located='true']", 1)

    assert "data-omnibot-text-offset" in script
    assert "Range" in script
    assert "setStart" in script
    assert "getClientRects" in script
    assert "deferElementClick(el)" in script
    assert "return matchPoint ||" in script


def test_fill_richtext_script_sets_contenteditable_text_and_events():
    script = interactions.fill_richtext_script('#article-editor', '第一段\n\n第二段')

    assert "document.querySelector(selector)" in script
    assert "el.isContentEditable" in script
    assert "innerHTML" in script
    assert "dispatchEvent(new InputEvent('input'" in script
    assert "dispatchEvent(new Event('change'" in script
    assert "第一段" in script
    assert "第二段" in script


def test_fill_uses_richtext_path_for_richtext_ref(monkeypatch):
    calls = []
    ref_map = RefMap()
    ref_map.add(
        "123",
        role="richtext",
        name="请输入正文",
        selector="#article-editor",
        kind="richtext",
        contenteditable=True,
    )

    def fake_evaluate(driver, tab_id, expression, **kwargs):
        calls.append(("evaluate", expression))
        return True

    def fake_send(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params or {}))
        return {}

    monkeypatch.setattr(interactions.cdp, "evaluate", fake_evaluate)
    monkeypatch.setattr(interactions.cdp, "send_cdp", fake_send)

    result = interactions.fill(object(), "123", "@e1", "正文内容", ref_map)

    assert result == {"filled": "@e1", "value": "正文内容"}
    assert any(call[0] == "evaluate" and "#article-editor" in call[1] and "正文内容" in call[1] for call in calls)
    assert not any(call[0] == "Input.insertText" for call in calls)
