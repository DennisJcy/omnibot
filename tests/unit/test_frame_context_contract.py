from omnibot import frame_context


def test_scoped_script_guards_non_selector_frame_targets():
    script = frame_context.scoped_script("return document.title;", "Payment Frame")

    assert "let directFrame = null;" in script
    assert "try { directFrame = globalThis.document.querySelector(target); } catch (_) {}" in script
    assert "directFrame && frames.includes(directFrame) ? directFrame : frames.find(matches)" in script


def test_scoped_script_accepts_tag_selector_that_resolves_to_iframe():
    script = frame_context.scoped_script("return document.title;", "iframe")

    assert "globalThis.document.querySelector(target)" in script
    assert "directFrame && frames.includes(directFrame)" in script


def test_scoped_script_can_return_frame_error_sentinel():
    script = frame_context.scoped_script(
        "return document.title;",
        "Remote Payment Frame",
        missing_value=frame_context.frame_error_value("not_found"),
        inaccessible_value=frame_context.frame_error_value("cross_origin_or_inaccessible"),
    )

    assert "__omnibotFrameError" in script
    assert 'reason: "not_found"' in script
    assert 'reason: "cross_origin_or_inaccessible"' in script


def test_root_frame_aliases_clear_frame_context():
    from types import SimpleNamespace

    for target in ["", "/", "main", "top", "default", "root"]:
        assert frame_context.active_frame_target(SimpleNamespace(frame_target=target)) == ""


def test_select_frame_id_walks_nested_cdp_frame_tree():
    tree = {
        "frame": {"id": "root", "url": "http://host/"},
        "childFrames": [{"frame": {"id": "child", "name": "payment-frame", "url": "http://host/child.html"}}],
    }

    assert frame_context.select_frame_id(tree, {"id": "payment-frame"}) == "child"
    assert frame_context.select_frame_id({"frameTree": tree}, {"id": "payment-frame"}) == "child"


def test_select_frame_id_matches_nested_frame_by_partial_url():
    tree = {
        "frame": {"id": "root", "url": "http://host/main.do"},
        "childFrames": [
            {
                "frame": {"id": "list", "url": "http://host/pages/task/list.jsf"},
                "childFrames": [
                    {
                        "frame": {
                            "id": "detail",
                            "url": "http://host/pages/task/entityTab.jsf?taskId=123",
                        }
                    }
                ],
            }
        ],
    }

    assert frame_context.select_frame_id(tree, {"url": "entityTab.jsf"}) == "detail"
