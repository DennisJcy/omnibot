from omnibot import actions, cdp


def test_backend_snapshot_ref_html_returns_inner_html(monkeypatch):
    def fake_send_cdp(driver, tab_id, method, params, **kwargs):
        assert method == "DOM.getOuterHTML"
        assert params == {"backendNodeId": 42}
        return {"outerHTML": '<button data-kind="shadow"><span>Shadow action</span></button>'}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.get_backend_ref_value(object(), "tab-1", 42, "html")

    assert result == '<span>Shadow action</span>'
