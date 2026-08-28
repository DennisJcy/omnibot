from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tests" / "e2e" / "feature_matrix_test.py"
SKILL_ROOT = ROOT / "src" / "omnibot" / "skills" / "omnibot"


def test_feature_matrix_script_exists_and_documents_verifiers():
    text = SCRIPT.read_text(encoding="utf-8")

    assert "FEATURE_CASES" in text
    assert "agent_prompt" in text
    assert "playwright" in text
    assert "cdp" in text
    assert "visual" in text
    assert "self_tool" in text


def test_feature_matrix_has_one_case_per_core_subfunction_except_snapshot():
    text = SCRIPT.read_text(encoding="utf-8")

    for feature_id in [
        "click_ref", "dblclick_ref", "fill_ref", "type_selector",
        "find_label", "find_placeholder", "wait_text", "mouse_click",
        "dom_click", "navigation_aliases", "console_capture",
        "network_capture", "read_clean_output", "upload_file_input",
        "screenshot_file", "clipboard_roundtrip", "viewport_resize",
        "assets_list", "session_token_isolation",
    ]:
        assert feature_id in text, f"missing feature case: {feature_id}"
    assert "snapshot_token_content_read" not in text


def test_feature_matrix_enforces_read_tab_id_for_existing_tabs():
    text = SCRIPT.read_text(encoding="utf-8")

    assert '"read"' in text.partition("PAGE_COMMANDS_REQUIRING_TAB")[2].partition("}")[0]
    assert "def _read_creates_temp_tab" in text


def test_omnibot_skill_docs_match_current_command_surface():
    main = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    command_ref = (SKILL_ROOT / "references" / "command-reference.md").read_text(encoding="utf-8")
    operation_patterns = (SKILL_ROOT / "references" / "operation-patterns.md").read_text(encoding="utf-8")
    session_tabs = (SKILL_ROOT / "references" / "session-and-tabs.md").read_text(encoding="utf-8")

    combined = "\n".join([main, command_ref, operation_patterns, session_tabs])

    assert "OMNIBOT_SESSION_TOKEN is a workflow/context token" in main
    assert "Workflow Context + Tab Target" in main
    assert "not a browser session" in session_tabs
    assert "read <URL>" in main

    assert "navigate --same-tab https://example.com" not in combined
    assert "goto https://example.com\n" not in combined
    assert '"cmd":"snapshot"' not in combined
    assert "upload files" not in main
    assert "Upload |" not in main
    assert "currently unavailable" not in operation_patterns
    assert "DOM.setFileInputFiles" in operation_patterns
    assert "visibility launch" in command_ref
    assert "does not launch a browser" in command_ref
    assert "tab focus" in main
