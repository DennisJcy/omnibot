from omnibot import browser_commands


def test_get_script_for_text_uses_text_content():
    script = browser_commands.get_script("text", "#title")
    assert "textContent" in script
    assert "#title" in script
    assert "__omnibotElementError" in script


def test_is_script_for_visible_checks_layout_and_style():
    script = browser_commands.is_script("visible", "#submit")
    assert "getBoundingClientRect" in script


def test_is_script_for_hidden_checks_layout_and_style():
    script = browser_commands.is_script("hidden", "#target")
    assert "display === 'none'" in script
    assert "visibility === 'hidden'" in script
    assert "visibility" in script


def test_get_script_for_title_does_not_require_selector():
    assert browser_commands.get_script("title", None) == "document.title"


def test_get_script_for_attr_reads_named_attribute():
    script = browser_commands.get_script("attr", "a.login", attr="href")
    assert "getAttribute" in script
    assert "href" in script


def test_get_script_for_url():
    assert browser_commands.get_script("url") == "location.href"


def test_get_script_for_count():
    script = browser_commands.get_script("count", ".items")
    assert "querySelectorAll" in script
    assert ".items" in script


def test_is_script_for_enabled():
    script = browser_commands.is_script("enabled", "#submit")
    assert "disabled" in script


def test_is_script_for_checked():
    script = browser_commands.is_script("checked", "#agree")
    assert "checked" in script


def test_wait_condition_script_supports_text_and_hidden_state():
    assert "innerText.includes" in browser_commands.wait_condition_script(target=None, text="Welcome", url=None, load=None, fn=None, state="visible")
    hidden = browser_commands.wait_condition_script(target="#spinner", text=None, url=None, load=None, fn=None, state="hidden")
    assert hidden.startswith("Boolean(document.querySelector")
    assert "&& !(" in hidden


def test_looks_like_js_condition_detects_document_expression():
    assert browser_commands.looks_like_js_condition("return document.readyState === 'complete'") is True
    assert browser_commands.looks_like_js_condition("#submit") is False


def test_tab_alias_helpers_assign_and_resolve():
    class Ctx:
        tab_aliases = {}
        next_tab_alias_number = 1

    ctx = Ctx()
    assert browser_commands.assign_tab_alias(ctx, "tab-1") == "t1"
    assert browser_commands.resolve_tab_alias(ctx, "t1") == "tab-1"


def test_tab_alias_helpers_use_label():
    class Ctx:
        tab_aliases = {}
        next_tab_alias_number = 1

    ctx = Ctx()
    assert browser_commands.assign_tab_alias(ctx, "tab-1", label="docs") == "docs"
    assert browser_commands.resolve_tab_alias(ctx, "docs") == "tab-1"


def test_viewport_script_returns_dimensions():
    assert "innerWidth" in browser_commands.viewport_get_script()
