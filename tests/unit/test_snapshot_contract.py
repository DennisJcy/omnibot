from omnibot.refs import RefMap
from omnibot import snapshot


AX_TREE = {
    "nodes": [
        {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}, "childIds": ["2", "3", "4"]},
        {"nodeId": "2", "role": {"value": "heading"}, "name": {"value": "Welcome"}, "properties": [{"name": "level", "value": {"value": 1}}], "backendDOMNodeId": 20},
        {"nodeId": "3", "role": {"value": "button"}, "name": {"value": "Submit"}, "backendDOMNodeId": 30},
        {"nodeId": "4", "role": {"value": "textbox"}, "name": {"value": "Email"}, "properties": [{"name": "required", "value": {"value": True}}], "backendDOMNodeId": 40},
    ]
}


def test_format_snapshot_assigns_refs_to_actionable_nodes():
    ref_map = RefMap()
    text, refs = snapshot.format_ax_snapshot(AX_TREE, tab_id="123", ref_map=ref_map, interactive=False, compact=False, max_depth=None, include_urls=False)

    assert '@e1 [RootWebArea] "Example"' in text
    assert '@e2 [heading] "Welcome" [level=1]' in text
    assert '@e3 [button] "Submit"' in text
    assert '@e4 [textbox] "Email" [required=true]' in text
    assert refs["e3"] == {"role": "button", "name": "Submit"}


def test_interactive_snapshot_filters_static_content():
    ref_map = RefMap()
    text, refs = snapshot.format_ax_snapshot(AX_TREE, tab_id="123", ref_map=ref_map, interactive=True, compact=True, max_depth=None, include_urls=False)

    assert "Welcome" not in text
    assert '@e1 [button] "Submit"' in text
    assert '@e2 [textbox] "Email" [required=true]' in text
    assert list(refs) == ["e1", "e2"]


def test_snapshot_annotates_textbox_input_types_from_dom_metadata():
    ax_tree = {
        "nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Login"}, "childIds": ["2", "3"]},
            {"nodeId": "2", "role": {"value": "textbox"}, "name": {"value": ""}, "backendDOMNodeId": 20},
            {"nodeId": "3", "role": {"value": "textbox"}, "name": {"value": ""}, "backendDOMNodeId": 30},
        ]
    }
    ref_map = RefMap()

    text, refs = snapshot.format_ax_snapshot(
        ax_tree,
        tab_id="123",
        ref_map=ref_map,
        interactive=True,
        compact=True,
        max_depth=None,
        include_urls=False,
        input_types={20: "text", 30: "password"},
    )

    assert '@e1 [textbox] [type=text]' in text
    assert '@e2 [textbox] [type=password]' in text
    assert refs["e1"]["type"] == "text"
    assert refs["e2"]["type"] == "password"
    assert ref_map.get("123", "@e2").input_type == "password"


def test_interactive_snapshot_keeps_visual_region_refs_for_screenshot():
    ax_tree = {
        "nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}, "childIds": ["2"]},
            {"nodeId": "2", "role": {"value": "article"}, "name": {"value": "A visual post"}, "backendDOMNodeId": 20, "childIds": ["3"]},
            {"nodeId": "3", "role": {"value": "button"}, "name": {"value": "Like"}, "backendDOMNodeId": 30},
        ]
    }
    ref_map = RefMap()

    text, refs = snapshot.format_ax_snapshot(ax_tree, tab_id="123", ref_map=ref_map, interactive=True, compact=True, max_depth=None, include_urls=False)

    assert '@e1 [article] "A visual post" [visual=true]' in text
    assert '@e2 [button] "Like"' in text
    assert refs["e1"] == {"role": "article", "name": "A visual post", "kind": "visual"}
    assert ref_map.get("123", "@e1").kind == "visual"


def test_ignored_container_does_not_hide_actionable_children():
    ax_tree = {
        "nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}, "childIds": ["2"]},
            {"nodeId": "2", "role": {"value": "none"}, "ignored": True, "childIds": ["3"]},
            {"nodeId": "3", "role": {"value": "button"}, "name": {"value": "Submit"}, "backendDOMNodeId": 30},
        ]
    }
    ref_map = RefMap()

    text, refs = snapshot.format_ax_snapshot(ax_tree, tab_id="123", ref_map=ref_map, interactive=False, compact=False, max_depth=None, include_urls=False)

    assert '@e2 [button] "Submit"' in text
    assert refs["e2"] == {"role": "button", "name": "Submit"}


def test_depth_limit_keeps_root_children_within_depth():
    ref_map = RefMap()
    text, refs = snapshot.format_ax_snapshot(AX_TREE, tab_id="123", ref_map=ref_map, interactive=False, compact=False, max_depth=1, include_urls=False)

    assert "Submit" in text
    assert refs["e3"]["role"] == "button"


def test_append_dom_popup_controls_adds_refs_after_ax_nodes():
    ref_map = RefMap()
    text, refs = snapshot.format_ax_snapshot(AX_TREE, tab_id="123", ref_map=ref_map, interactive=True, compact=True, max_depth=None, include_urls=False)

    popup_controls = [
        {"role": "button", "name": "取消", "selector": ".byte-modal .cancel", "box": {"x": 10, "y": 20, "width": 80, "height": 32}},
        {"role": "button", "name": "确定", "selector": ".byte-modal .ok", "disabled": True, "box": {"x": 100, "y": 20, "width": 80, "height": 32}},
    ]

    text, refs = snapshot.append_dom_popup_controls(text, refs, popup_controls, tab_id="123", ref_map=ref_map)

    assert "# DOM Popup Controls" in text
    assert '@e3 [button] "取消"' in text
    assert '@e4 [button] "确定" [disabled=true]' in text
    assert refs["e3"] == {"role": "button", "name": "取消", "box": {"x": 10, "y": 20, "width": 80, "height": 32}}
    assert ref_map.get("123", "@e3").selector == ".byte-modal .cancel"


def test_append_dom_popup_controls_skips_duplicate_backend_nodes():
    ref_map = RefMap()
    text, refs = snapshot.format_ax_snapshot(AX_TREE, tab_id="123", ref_map=ref_map, interactive=False, compact=False, max_depth=None, include_urls=False)

    popup_controls = [
        {"role": "button", "name": "Submit", "selector": "button.submit", "backendNodeId": 30, "box": {"x": 1, "y": 2, "width": 3, "height": 4}},
        {"role": "button", "name": "关闭", "selector": ".modal-close", "box": {"x": 5, "y": 6, "width": 7, "height": 8}},
    ]

    text, refs = snapshot.append_dom_popup_controls(text, refs, popup_controls, tab_id="123", ref_map=ref_map)

    assert text.count("Submit") == 1
    assert '@e5 [button] "关闭"' in text
    assert refs["e5"]["role"] == "button"


def test_popup_controls_script_contains_recall_first_candidates():
    script = snapshot.dom_popup_controls_script(limit=50)

    assert '[role="dialog"]' in script
    assert '[role="alertdialog"]' in script
    assert '[role="listbox"]' in script
    assert '[role="menu"]' in script
    assert 'dialog[open]' in script
    assert '[popover]' in script
    assert 'modal|dialog|popup|popover|drawer|overlay|mask|portal' in script
    assert 'position === \'fixed\'' in script
    assert 'querySelectorAll(controlSelector)' in script
    assert 'closest(\'[role="listbox"], [role="menu"' in script


def test_popup_controls_script_enforces_limit():
    script = snapshot.dom_popup_controls_script(limit=7)

    assert 'const limit = 7;' in script


def test_combobox_options_script_probes_visible_comboboxes_with_limit():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert 'const limit = 8;' in script
    assert '[role="combobox"]' in script
    assert '[aria-haspopup][aria-expanded]' in script
    assert 'slice(0, limit)' in script
    assert 'requestAnimationFrame' in script


def test_combobox_options_script_captures_options_with_openers():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert '[role="option"], [role="menuitem"]' in script
    assert 'openerSelector' in script
    assert 'cssPath(opener)' in script
    assert 'role, name, selector' in script
    assert 'box: {x: rect.left, y: rect.top, width: rect.width, height: rect.height}' in script


def test_combobox_options_script_closes_each_probe():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert 'dismissComboboxWithinOwner(opener)' in script
    assert "opener.closest('[role=\"dialog\"]" in script
    assert "owner.focus({preventScroll: true})" in script
    assert "activeBefore.focus({preventScroll: true})" in script
    assert "opener.getAttribute('aria-expanded') === 'true'" in script


def test_combobox_options_script_clamps_probe_limit():
    assert 'const limit = 0;' in snapshot.dom_combobox_options_script(limit=-1)
    assert 'const limit = 20;' in snapshot.dom_combobox_options_script(limit=999)


def test_combobox_options_script_filters_current_combobox_popup_options_only():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert 'beforeOptions' in script
    assert 'afterOptions' in script
    assert 'newOptions' in script
    assert 'seen.has(key)' in script


def test_combobox_options_script_dispatches_one_mouse_click_sequence():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert "new MouseEvent('mousedown'" in script
    assert "new MouseEvent('mouseup'" in script
    assert "new MouseEvent('click'" in script
    assert "opener.dispatchEvent(new MouseEvent('click', up));\n    opener.click();" not in script


def test_combobox_options_script_skips_menu_haspopup():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert 'isProbeSafeOpener' in script
    assert "['listbox', 'tree', 'grid'].includes(hasPopup)" in script
    assert 'return false' in script


def test_combobox_options_script_does_not_escape_or_scroll_ancestor_ui():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert 'scrollIntoView' not in script
    assert "new KeyboardEvent('keydown'" not in script
    assert 'document.dispatchEvent' not in script


def test_combobox_options_script_preserves_combobox_select_listbox():
    script = snapshot.dom_combobox_options_script(limit=8)

    assert "tag === 'select'" in script
    assert "role === 'combobox'" in script
    assert "filter(isProbeSafeOpener)" in script


def test_richtext_controls_script_targets_contenteditable_editors():
    script = snapshot.dom_richtext_controls_script(limit=12)

    assert 'const limit = 12;' in script
    assert '[contenteditable="true"]' in script
    assert '[role="textbox"][aria-multiline="true"]' in script
    assert 'richtext' in script
    assert '请输入正文' in script
    assert 'box: {x: rect.left, y: rect.top, width: rect.width, height: rect.height}' in script


def test_richtext_controls_script_clamps_limit():
    assert 'const limit = 1;' in snapshot.dom_richtext_controls_script(limit=-5)
    assert 'const limit = 50;' in snapshot.dom_richtext_controls_script(limit=999)


def test_append_dom_richtext_controls_adds_richtext_refs():
    ref_map = RefMap()
    text, refs = snapshot.format_ax_snapshot(
        AX_TREE,
        tab_id="123",
        ref_map=ref_map,
        interactive=True,
        compact=True,
        max_depth=None,
        include_urls=False,
    )

    richtext_controls = [
        {
            "role": "richtext",
            "kind": "richtext",
            "name": "请输入正文",
            "selector": "#article-editor",
            "contenteditable": True,
            "box": {"x": 238, "y": 366, "width": 968, "height": 640},
        }
    ]

    text, refs = snapshot.append_dom_richtext_controls(text, refs, richtext_controls, tab_id="123", ref_map=ref_map)

    assert "# DOM Rich Text Editors" in text
    assert '@e3 [richtext] "请输入正文" [contenteditable=true]' in text
    assert refs["e3"] == {
        "role": "richtext",
        "name": "请输入正文",
        "kind": "richtext",
        "contenteditable": True,
        "box": {"x": 238, "y": 366, "width": 968, "height": 640},
    }
    assert ref_map.get("123", "@e3").selector == "#article-editor"


def test_append_dom_richtext_controls_skips_duplicate_backend_nodes():
    ref_map = RefMap()
    ax_tree = {
        "nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "Example"}, "childIds": ["2"]},
            {"nodeId": "2", "role": {"value": "textbox"}, "name": {"value": "请输入正文"}, "backendDOMNodeId": 77},
        ]
    }
    text, refs = snapshot.format_ax_snapshot(
        ax_tree,
        tab_id="123",
        ref_map=ref_map,
        interactive=True,
        compact=True,
        max_depth=None,
        include_urls=False,
    )

    richtext_controls = [
        {
            "role": "richtext",
            "kind": "richtext",
            "name": "请输入正文",
            "selector": "#article-editor",
            "backendNodeId": 77,
            "contenteditable": True,
            "box": {"x": 1, "y": 2, "width": 3, "height": 4},
        }
    ]

    text, refs = snapshot.append_dom_richtext_controls(text, refs, richtext_controls, tab_id="123", ref_map=ref_map)

    assert "# DOM Rich Text Editors" not in text
    assert text.count("请输入正文") == 1
    assert list(refs) == ["e1"]


def test_snapshot_can_cover_ax_missing_article_body_richtext():
    ref_map = RefMap()
    ax_tree = {
        "nodes": [
            {"nodeId": "1", "role": {"value": "RootWebArea"}, "name": {"value": "头条号"}, "childIds": ["2"]},
            {
                "nodeId": "2",
                "role": {"value": "textbox"},
                "name": {"value": "请输入文章标题（2～30个字）"},
                "backendDOMNodeId": 20,
            },
        ]
    }
    text, refs = snapshot.format_ax_snapshot(
        ax_tree,
        tab_id="mp-tab",
        ref_map=ref_map,
        interactive=True,
        compact=True,
        max_depth=None,
        include_urls=False,
    )

    text, refs = snapshot.append_dom_richtext_controls(
        text,
        refs,
        [
            {
                "role": "richtext",
                "kind": "richtext",
                "name": "请输入正文",
                "selector": "html > body > div.editor [contenteditable=\"true\"]",
                "contenteditable": True,
                "box": {"x": 238, "y": 366, "width": 968, "height": 640},
            }
        ],
        tab_id="mp-tab",
        ref_map=ref_map,
    )

    assert '@e1 [textbox] "请输入文章标题（2～30个字）"' in text
    assert '@e2 [richtext] "请输入正文" [contenteditable=true]' in text
    assert refs["e1"]["role"] == "textbox"
    assert refs["e2"]["role"] == "richtext"
    assert refs["e2"]["kind"] == "richtext"
    assert refs["e2"]["contenteditable"] is True
