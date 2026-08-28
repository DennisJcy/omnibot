from omnibot import locators


def test_role_locator_script_filters_name():
    script = locators.locator_script("role", "button", name="Submit", exact=True)
    assert 'role=' in script
    assert "Submit" in script
    assert locators.MARK in script


def test_label_locator_script_targets_labeled_control():
    script = locators.locator_script("label", "Email", exact=True)
    assert "querySelectorAll('label')" in script
    assert "getElementById" in script


def test_nth_locator_uses_selector_and_index():
    script = locators.nth_script(".card", 2)
    assert ".card" in script
    assert "const idx = 2" in script


def test_located_selector_returns_marker_selector():
    assert locators.located_selector() == "[data-omnibot-located='true']"


def test_placeholder_locator_script():
    script = locators.locator_script("placeholder", "Search")
    assert "placeholder" in script


def test_text_locator_script():
    script = locators.locator_script("text", "Sign in", exact=False)
    assert "Sign in" in script
    assert locators.MARK in script


def test_text_locator_prefers_text_node_container_over_ancestor():
    script = locators.locator_script("text", "锚点C", exact=False)
    assert "createTreeWalker" in script
    assert "NodeFilter.SHOW_TEXT" in script
    assert "closestMatchContainer" in script
    assert "other.contains(direct)" in script
