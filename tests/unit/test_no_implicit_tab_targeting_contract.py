from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "omnibot"
TESTS_ROOT = REPO_ROOT / "tests"

GUARD_TEST_FILES = {
    "tests/unit/test_no_implicit_tab_targeting_contract.py",
    "tests/unit/test_transport_no_default_session_contract.py",
    "tests/unit/test_packaged_skills_contract.py",
}


def test_no_public_switch_or_focus_tab_references_in_runtime_docs():
    checked_roots = [SRC_ROOT, REPO_ROOT / "AGENTS.md"]
    offenders = []
    for root in checked_roots:
        paths = [root] if root.is_file() else list(root.rglob("*"))
        for path in paths:
            if path.suffix not in {".py", ".md"}:
                continue
            rel = path.relative_to(REPO_ROOT)
            if str(rel).startswith("src/omnibot/skills/"):
                continue
            text = path.read_text(encoding="utf-8")
            if "switch-tab" in text or "focus-tab" in text:
                offenders.append(str(rel))
    assert offenders == []


def test_actions_do_not_use_default_session_for_targeting():
    text = (SRC_ROOT / "actions.py").read_text(encoding="utf-8")
    forbidden = [
        "ctx.default_session_id = resolved_tab_id",
        "ctx.default_session_id = tab_id",
    ]
    found = [pattern for pattern in forbidden if pattern in text]
    assert found == []


def test_no_default_session_id_symbol_in_runtime_sources():
    forbidden = "default_session_id"
    paths = [
        path
        for path in SRC_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    offenders = []
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in GUARD_TEST_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if forbidden in text:
            offenders.append(rel)
    assert offenders == [], f"default_session_id found in: {offenders}"


def test_no_default_session_id_in_test_sources():
    forbidden = "default_session_id"
    paths = [
        path
        for path in TESTS_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
        and "legacy" not in path.parts
        and "reports" not in path.parts
    ]
    offenders = []
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in GUARD_TEST_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if forbidden in text:
            offenders.append(rel)
    assert offenders == [], f"default_session_id found in test files: {offenders}"


def test_execute_js_never_assigns_implicit_page_target():
    text = (SRC_ROOT / "TMWebDriver.py").read_text(encoding="utf-8")
    assert "ctx.default_session_id" not in text
    assert "default_session_id" not in text
    assert "alive_sessions[0]" not in text


def test_actions_execute_js_calls_are_explicitly_targeted():
    text = (SRC_ROOT / "actions.py").read_text(encoding="utf-8")
    lines = text.splitlines()
    offenders = []
    for index, line in enumerate(lines, start=1):
        if "driver.execute_js(" in line and "session_id=" not in line:
            # Check next 5 lines for session_id (multi-line call)
            block = "\n".join(lines[index - 1 : index + 5])
            if "session_id=" not in block:
                offenders.append((index, line.strip()))
    assert offenders == [], f"execute_js calls without session_id: {offenders}"


def test_no_first_tab_fallback_in_test_sources():
    forbidden_patterns = ["tabs[0]", "alive_sessions[0]"]
    paths = [
        path
        for path in TESTS_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
        and "legacy" not in path.parts
        and "reports" not in path.parts
    ]
    offenders = []
    for path in paths:
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in GUARD_TEST_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in text:
                offenders.append((rel, pattern))
    assert offenders == [], f"First-tab fallback found: {offenders}"
