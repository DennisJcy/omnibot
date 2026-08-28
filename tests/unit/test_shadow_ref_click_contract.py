from omnibot import interactions
from omnibot.refs import RefMap


def test_click_converts_navigation_side_effect_into_success_after_activation_error(monkeypatch):
    locations = iter(["https://example.test/start", "https://example.test/target"])
    monkeypatch.setattr(interactions, "_location_href", lambda *args, **kwargs: next(locations))

    def fail_activation(*args, **kwargs):
        raise interactions.InteractionError("Node with given id does not belong to the document")

    monkeypatch.setattr(interactions, "activate_element", fail_activation)

    result = interactions.click(object(), "tab-1", "@e1", RefMap())

    assert result == {"clicked": "@e1", "navigation": True, "url": "https://example.test/target"}


def test_click_resolves_closed_shadow_link_when_pointer_activation_does_not_navigate(monkeypatch):
    class FakeDriver:
        def __init__(self):
            self.jumps = []

        def jump(self, url, timeout=10, token=None, session_id=None):
            self.jumps.append((url, session_id))

    driver = FakeDriver()
    refs = RefMap()
    refs.add("tab-1", role="link", name="Shadow target", backend_node_id=42)
    locations = iter([
        "http://example.test/",
        "http://example.test/",
        "http://example.test/target.html",
    ])
    monkeypatch.setattr(interactions, "_location_href", lambda *args, **kwargs: next(locations))
    monkeypatch.setattr(interactions, "activate_element", lambda *args, **kwargs: (10.0, 20.0, [], {}))
    monkeypatch.setattr(
        interactions.cdp,
        "send_cdp",
        lambda *args, **kwargs: {"node": {"attributes": ["href", "target.html"]}},
    )
    monkeypatch.setattr(interactions.cdp, "evaluate", lambda *args, **kwargs: "http://example.test/")

    result = interactions.click(driver, "tab-1", "@e1", refs)

    assert driver.jumps == [("http://example.test/target.html", "tab-1")]
    assert result["navigation"] is True
    assert result["url"] == "http://example.test/target.html"
