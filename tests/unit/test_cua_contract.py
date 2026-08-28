from omnibot import cua


class FakeDriver:
    def __init__(self):
        self.calls = []
        self.visual_events = []

    def _raw_tab_id(self, tab_id, token=None):
        return "42"

    def broadcast_extension_event(self, payload, token=None):
        self.visual_events.append(payload)


def test_mouse_click_dispatches_cdp_mouse_events(monkeypatch):
    driver = FakeDriver()

    def fake_send(driver_arg, tab_id, method, params=None, token=None, **kwargs):
        driver_arg.calls.append((method, params))
        return {}

    monkeypatch.setattr("omnibot.cdp.send_cdp", fake_send)
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"clicked": True})
    result = cua.click(driver, "tab-1", 10, 20, token="tok")
    assert result == {"x": 10, "y": 20, "button": "left", "click_count": 1}
    assert [call[1]["type"] for call in driver.calls[:3]] == ["mouseMoved", "mousePressed", "mouseReleased"]
    assert [event["event"]["type"] for event in driver.visual_events] == ["move", "press", "release"]


def test_mouse_click_returns_new_tabs_created_by_mouse_release(monkeypatch):
    driver = FakeDriver()
    watched = []
    new_tab = {
        "id": 84,
        "openerTabId": 42,
        "browserClientId": "edge-client",
        "url": "https://example.test/article",
        "title": "Article",
    }

    def fake_send(driver_arg, tab_id, method, params=None, token=None, **kwargs):
        if params and params.get("type") == "mouseReleased":
            watched.append(kwargs.get("watch_new_tabs"))
            return {"_omnibot_newTabs": [new_tab]}
        return {}

    monkeypatch.setattr("omnibot.cdp.send_cdp", fake_send)
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"clicked": True})

    result = cua.click(driver, "tab-1", 10, 20, token="tok")

    assert watched == [True]
    assert result["newTabs"] == [new_tab]


def test_mouse_click_skips_dom_fallback_when_cdp_click_was_observed(monkeypatch):
    driver = FakeDriver()
    expressions = []

    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: {})

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        expressions.append(expression)
        if "__omnibotCoordinateClickProbe" in expression and "delete window" in expression:
            return {"clicked": True, "target": {"id": "coordinate-target"}}
        return {"id": "coordinate-target"}

    monkeypatch.setattr("omnibot.cdp.evaluate", fake_evaluate)

    result = cua.click(driver, "tab-1", 10, 20)

    assert result["target"] == {"id": "coordinate-target"}
    assert not any("dispatchEvent(new MouseEvent('click'" in expression for expression in expressions)


def test_mouse_click_runs_dom_fallback_when_cdp_click_was_not_observed(monkeypatch):
    driver = FakeDriver()
    expressions = []
    fallback_watch = []
    new_tab = {"id": 85, "openerTabId": 42, "browserClientId": "edge-client"}

    def fake_send(driver_arg, tab_id, method, params=None, **kwargs):
        if method == "Runtime.evaluate":
            expressions.append(params["expression"])
            fallback_watch.append(kwargs.get("watch_new_tabs"))
            return {
                "result": {"value": {"id": "coordinate-target"}},
                "_omnibot_newTabs": [new_tab],
            }
        return {}

    monkeypatch.setattr("omnibot.cdp.send_cdp", fake_send)

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        expressions.append(expression)
        if "__omnibotCoordinateClickProbe" in expression and "delete window" in expression:
            return {"clicked": False, "target": {"id": "coordinate-target"}}
        return {"id": "coordinate-target"}

    monkeypatch.setattr("omnibot.cdp.evaluate", fake_evaluate)

    result = cua.click(driver, "tab-1", 10, 20)

    assert result["target"] == {"id": "coordinate-target"}
    assert result["newTabs"] == [new_tab]
    assert fallback_watch == [True]
    assert any("dispatchEvent(new MouseEvent('click'" in expression for expression in expressions)


def test_scroll_dispatches_mouse_wheel_event(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    result = cua.scroll(driver, "tab-1", 100, 200, 0, 500)
    assert result["scrollY"] == 500
    assert calls[0]["type"] == "mouseWheel"
    assert driver.visual_events[0]["event"] == {"type": "move", "x": 100.0, "y": 200.0}


def test_move_dispatches_mouse_moved_event(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    result = cua.move(driver, "tab-1", 50, 60)
    assert result == {"x": 50, "y": 60}
    assert calls[0]["type"] == "mouseMoved"
    assert driver.visual_events[0]["event"] == {"type": "move", "x": 50.0, "y": 60.0}


def test_drag_fast_dispatches_four_events(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"dropped": True})
    result = cua.drag(driver, "tab-1", 10, 20, 100, 200, fast=True)
    assert result == {"from": {"x": 10, "y": 20}, "to": {"x": 100, "y": 200}}
    assert [c["type"] for c in calls] == ["mouseMoved", "mousePressed", "mouseMoved", "mouseReleased"]
    assert [event["event"]["type"] for event in driver.visual_events] == ["move", "press", "drag", "release"]


def test_drag_default_dispatches_multi_step_trajectory(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"dropped": True})
    monkeypatch.setattr("omnibot.cua.time.sleep", lambda *_a, **_k: None)
    cua.drag(driver, "tab-1", 10, 20, 100, 200)
    moved = [c for c in calls if c["type"] == "mouseMoved"]
    pressed = [c for c in calls if c["type"] == "mousePressed"]
    released = [c for c in calls if c["type"] == "mouseReleased"]
    assert len(pressed) == 1
    assert len(released) == 1
    # Realistic trajectory must have many more move events than the fast 4-step path.
    assert len(moved) >= 30


def test_drag_default_first_move_starts_at_origin_and_press_follows(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"dropped": True})
    monkeypatch.setattr("omnibot.cua.time.sleep", lambda *_a, **_k: None)
    cua.drag(driver, "tab-1", 10, 20, 100, 200)
    types = [c["type"] for c in calls]
    # Sequence: hover move -> press -> many moves -> release
    assert types[0] == "mouseMoved"
    assert types[1] == "mousePressed"
    assert types[-1] == "mouseReleased"
    assert calls[0]["x"] == 10 and calls[0]["y"] == 20


def test_drag_default_release_lands_near_target(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"dropped": True})
    monkeypatch.setattr("omnibot.cua.time.sleep", lambda *_a, **_k: None)
    cua.drag(driver, "tab-1", 10, 20, 100, 200)
    release = next(c for c in calls if c["type"] == "mouseReleased")
    assert abs(release["x"] - 100) < 1.0
    assert abs(release["y"] - 200) < 1.0


def test_drag_overshoot_goes_past_target_then_settles(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"dropped": True})
    monkeypatch.setattr("omnibot.cua.time.sleep", lambda *_a, **_k: None)
    cua.drag(driver, "tab-1", 0, 0, 100, 0, overshoot=6.0)
    moved = [c for c in calls if c["type"] == "mouseMoved" and c.get("buttons") == 1]
    max_x = max(c["x"] for c in moved)
    # Overshoot should push the trajectory strictly past the target x.
    assert max_x > 100


def test_drag_jitter_adds_y_variation(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"dropped": True})
    monkeypatch.setattr("omnibot.cua.time.sleep", lambda *_a, **_k: None)
    cua.drag(driver, "tab-1", 0, 100, 200, 100, jitter=3.0)
    moved = [c for c in calls if c["type"] == "mouseMoved" and c.get("buttons") == 1]
    ys = {round(c["y"], 3) for c in moved}
    # A horizontal drag with jitter should not stay perfectly on y=100 the whole way.
    assert len(ys) > 3


def test_drag_respects_steps_parameter(monkeypatch):
    driver = FakeDriver()
    calls = []
    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: calls.append(args[3]) or {})
    monkeypatch.setattr("omnibot.cdp.evaluate", lambda *args, **kwargs: {"dropped": True})
    monkeypatch.setattr("omnibot.cua.time.sleep", lambda *_a, **_k: None)
    cua.drag(driver, "tab-1", 0, 0, 50, 0, steps=40)
    moved = [c for c in calls if c["type"] == "mouseMoved" and c.get("buttons") == 1]
    # Main trajectory points + overshoot/settle tail (3) should be in the right ballpark.
    assert 38 <= len(moved) <= 60


def test_drag_uses_coordinate_html5_fallback_when_native_drop_is_not_observed(monkeypatch):
    driver = FakeDriver()
    expressions = []

    monkeypatch.setattr("omnibot.cdp.send_cdp", lambda *args, **kwargs: {})

    def fake_evaluate(driver_arg, tab_id, expression, **kwargs):
        expressions.append(expression)
        if "__omnibotCoordinateDragProbe" in expression and "delete window" in expression:
            return {"dropped": False}
        return True

    monkeypatch.setattr("omnibot.cdp.evaluate", fake_evaluate)
    cua.drag(driver, "tab-1", 10, 20, 100, 200, fast=True)

    assert any("new DataTransfer" in expression for expression in expressions)
    assert any("new DragEvent('drop'" in expression for expression in expressions)
