from omnibot.refs import RefEntry, RefMap, parse_ref


def test_parse_ref_accepts_agent_browser_style_refs():
    assert parse_ref("@e12") == "e12"
    assert parse_ref("e12") == "e12"
    assert parse_ref("ref=e12") == "e12"
    assert parse_ref("#submit") is None


def test_ref_map_stores_entries_per_tab():
    ref_map = RefMap()
    ref_map.clear_tab("tab-a")
    ref_id = ref_map.add("tab-a", role="button", name="Submit", backend_node_id=42, selector=None, frame_id=None, nth=0, box={"x": 1, "y": 2, "width": 3, "height": 4})

    assert ref_id == "e1"
    assert ref_map.get("tab-a", "@e1") == RefEntry(
        ref_id="e1",
        role="button",
        name="Submit",
        backend_node_id=42,
        selector=None,
        frame_id=None,
        nth=0,
        box={"x": 1, "y": 2, "width": 3, "height": 4},
    )
    assert ref_map.get("tab-b", "@e1") is None


def test_ref_map_resets_numbers_per_tab():
    ref_map = RefMap()
    assert ref_map.add("tab-a", role="button", name="A") == "e1"
    assert ref_map.add("tab-a", role="button", name="B") == "e2"
    ref_map.clear_tab("tab-a")
    assert ref_map.add("tab-a", role="button", name="C") == "e1"
