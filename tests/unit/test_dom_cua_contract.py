from omnibot import dom_cua


def test_visible_dom_script_marks_interactive_nodes():
    script = dom_cua.visible_dom_script(limit=20)
    assert "querySelectorAll" in script
    assert "data-omnibot-node-id" in script
    assert "button" in script


def test_node_selector_uses_node_id_attribute():
    assert dom_cua.node_selector("n7") == "[data-omnibot-node-id='n7']"
