from pathlib import Path
import shlex

import tomllib
import pytest

from omnibot import cli


ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "src" / "omnibot" / "skills"


def test_expected_skill_files_exist():
    path = SKILLS / "omnibot" / "SKILL.md"
    assert path.exists(), path
    text = path.read_text(encoding="utf-8")
    assert "name: omnibot" in text
    assert "slug: omnibot" in text
    assert "displayName:" in text
    assert "license:" in text
    assert "description: Use when" in text
    assert "omnibot" in text


def test_command_reference_lists_all_cli_commands():
    text = (SKILLS / "omnibot" / "references" / "command-reference.md").read_text(encoding="utf-8")
    for command in ["tabs", "read", "execute-js", "batch", "wait", "navigate", "screenshot"]:
        assert command in text
    assert "omnibot full-scan" not in text
    assert "### full-scan" not in text
    assert "omnibot scan" not in text
    assert "### scan" not in text


def test_command_reference_documents_long_read_timeout():
    text = (SKILLS / "omnibot" / "references" / "command-reference.md").read_text(encoding="utf-8")

    assert "omnibot read --screens 5 --timeout 120 --tab-id <TAB_ID>" in text


def _skill_texts() -> list[str]:
    return [
        (SKILLS / "omnibot" / "SKILL.md").read_text(encoding="utf-8"),
        (SKILLS / "omnibot" / "references" / "command-reference.md").read_text(encoding="utf-8"),
    ]


def _omnibot_examples(text: str) -> list[str]:
    examples = []
    top_commands = set()
    for action in cli.build_parser()._actions:
        choices = getattr(action, "choices", None)
        if choices:
            top_commands.update(choices.keys())
            break
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("omnibot "):
            continue
        if "--help" in line:
            continue
        try:
            parts = shlex.split(_normalize_example(line))
        except ValueError:
            continue
        if len(parts) < 2 or parts[1] not in top_commands:
            continue
        examples.append(line)
    return examples


def _normalize_example(line: str) -> str:
    return (
        line.replace("<TAB_ID>", "123")
        .replace("<tab-id>", "123")
        .replace("<script>", "return document.title")
        .replace("<url>", "https://example.com")
        .replace("<json>", '[{"cmd":"snapshot"}]')
    )


@pytest.mark.parametrize("line", [line for text in _skill_texts() for line in _omnibot_examples(text)])
def test_skill_omnibot_examples_parse_with_current_cli(line):
    args = shlex.split(_normalize_example(line))[1:]
    cli.build_parser().parse_args(args)


def test_omnibot_skill_documents_agent_safe_concurrency():
    text = (SKILLS / "omnibot" / "SKILL.md").read_text(encoding="utf-8")

    assert "OMNIBOT_SESSION_TOKEN" in text
    assert "same token" in text or "同一个" in text
    assert "different tokens" in text or "不同" in text


def test_omnibot_skill_documents_tab_scoped_operations():
    text = (SKILLS / "omnibot" / "SKILL.md").read_text(encoding="utf-8")

    assert "tab-scoped" in text
    assert "snapshot -i --tab-id <TAB_ID>" in text
    assert "click --tab-id <TAB_ID> @e" in text
    assert "Do not rely on default tab" in text


def test_omnibot_skill_documents_agent_dispatch_pattern():
    text = (SKILLS / "omnibot" / "SKILL.md").read_text(encoding="utf-8")

    assert "agent dispatch pattern" in text
    assert "token + tab-id" in text
    assert "never reuse `@eN` refs across tabs" in text
    assert "every command that touches page state" in text
    assert "omnibot get value \"input[name=email]\" --tab-id <TAB_ID>" in text
    assert "omnibot find placeholder \"Search\" --action type --action-value \"omnibot\" --tab-id <TAB_ID>" in text
    assert "omnibot dom dblclick n1 --tab-id <TAB_ID>" in text
    assert "omnibot clipboard read --tab-id <TAB_ID>" in text


def test_omnibot_skill_uses_current_find_and_batch_syntax():
    combined = "\n".join(_skill_texts())

    assert "--action click" in combined
    assert "--action-value" in combined
    assert "omnibot batch '[" in combined
    for obsolete in [
        'find role button --name "Submit" click',
        'find label "Email" fill',
        "batch --commands-json",
        "batch open https://example.com snapshot -i",
        "batch --bail open https://example.com snapshot -i",
    ]:
        assert obsolete not in combined


def _all_skill_markdown() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in SKILLS.rglob("*.md")}


def test_omnibot_skill_docs_do_not_reference_removed_tab_commands_as_usable():
    combined = "\n".join(_all_skill_markdown().values())

    for line in combined.splitlines():
        line_lower = line.lower().strip()
        if any(removed in line_lower for removed in ["removed", "unavailable", "no longer", "not available", "prohibited"]):
            continue
        for removed in ["switch-tab", "focus-tab"]:
            assert removed not in line_lower, f"removed command '{removed}' appears in non-warning context: {line}"


def test_omnibot_skill_docs_warn_against_first_tab_fallbacks():
    combined = "\n".join(_all_skill_markdown().values()).lower()

    assert "tabs[0]" in combined
    assert "first tab" in combined or "第一个标签" in combined
    assert "transport" in combined
    assert "target" in combined
    assert "tool-created" in combined or "tool created" in combined or "工具创建" in combined


def test_omnibot_skill_docs_require_explicit_tab_id_for_page_state_commands():
    combined = "\n".join(_all_skill_markdown().values())
    page_commands = [
        "snapshot", "click", "dblclick", "execute-js",
        "get", "is", "find", "fill", "type", "press", "hover", "focus",
        "select", "check", "uncheck", "scroll", "scrollintoview", "drag",
        "wait", "screenshot", "cdp", "dom", "mouse", "console", "network",
        "clipboard", "viewport", "assets", "goto", "back", "forward", "reload",
    ]

    assert "Every page-state command requires explicit `--tab-id`" in combined or "Every page command requires explicit `--tab-id`" in combined
    for command in page_commands:
        assert f"omnibot {command}" in combined


def test_pyproject_packages_skill_markdown():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package_data = data["tool"]["setuptools"]["package-data"]["omnibot"]
    assert "skills/*/SKILL.md" in package_data
    assert "skills/*/references/*.md" in package_data


def test_omnibot_skill_docs_do_not_present_full_scan_as_cli_command():
    combined = "\n".join(_all_skill_markdown().values())
    assert "omnibot full-scan" not in combined
    assert "### full-scan" not in combined
    assert "full_scan" not in combined


def test_omnibot_skill_docs_do_not_present_scan_as_cli_command():
    combined = "\n".join(_all_skill_markdown().values())
    assert "omnibot scan" not in combined
    assert "### scan" not in combined


def test_omnibot_skill_docs_do_not_reference_removed_scan_interfaces():
    combined = "\n".join(_all_skill_markdown().values())

    removed_terms = [
        "omnibot scan",
        "omnibot full-scan",
        "browser_scan",
        "browser_full_scan",
        "full_scan",
    ]
    for term in removed_terms:
        assert term not in combined


def test_omnibot_skill_docs_cover_css_only_dropdown_fallback():
    combined = "\n".join(_all_skill_markdown().values()).lower()

    assert "css-only dropdown" in combined or "css-only" in combined
    assert "accessibility tree" in combined
    assert "snapshot -i" in combined
    assert "hidden `<div>`" in combined or "hidden div" in combined
    assert "execute-js" in combined
    assert "trigger" in combined
    assert "option" in combined
    assert "verify" in combined or "verification" in combined


def test_omnibot_skill_docs_require_evidence_before_css_dropdown_javascript():
    combined = "\n".join(_all_skill_markdown().values()).lower()

    assert "do not use `execute-js` first" in combined
    assert "trigger clicked" in combined or "trigger exists" in combined
    assert "options are absent" in combined or "options remain absent" in combined or "option nodes are absent" in combined
    assert "higher tiers" in combined
    assert "selected label" in combined or "sorted result" in combined or "result order" in combined


def test_omnibot_skill_documents_auto_probed_combobox_options():
    root = Path("src/omnibot/skills/omnibot")
    combined = "\n".join(
        [
            (root / "SKILL.md").read_text(encoding="utf-8"),
            (root / "references" / "operation-patterns.md").read_text(encoding="utf-8"),
            (root / "references" / "command-reference.md").read_text(encoding="utf-8"),
            (root / "references" / "fallback-operations.md").read_text(encoding="utf-8"),
            (root / "references" / "anti-patterns.md").read_text(encoding="utf-8"),
        ]
    )

    assert "auto-probed combobox" in combined
    assert "openerSelector" in combined
    assert "snapshot -i" in combined
    assert "@option" in combined
    assert "CSS-only dropdown JavaScript fallback" in combined


def test_omnibot_skill_keeps_dropdown_fallback_after_snapshot_refs():
    operation_patterns = Path("src/omnibot/skills/omnibot/references/operation-patterns.md").read_text(encoding="utf-8")
    fallback_operations = Path("src/omnibot/skills/omnibot/references/fallback-operations.md").read_text(encoding="utf-8")
    anti_patterns = Path("src/omnibot/skills/omnibot/references/anti-patterns.md").read_text(encoding="utf-8")

    assert "Use `snapshot -i` first; visible comboboxes may include auto-probed option refs" in operation_patterns
    assert "Do not manually reopen a dropdown just to discover options if `snapshot -i` already lists them" in anti_patterns
    assert "Use CSS-only dropdown JavaScript fallback only after auto-probed refs are absent or fail verification" in fallback_operations


def test_omnibot_skill_uses_installed_cli_runtime():
    text = Path("src/omnibot/skills/omnibot/SKILL.md").read_text(encoding="utf-8")
    assert "Run `omnibot <command> --help` before using uncommon or newly introduced commands" in text
    assert "command -v omnibot" in text
    assert "omnibot --version" in text
    assert 'OMNIBOT_BIN="$(command -v omnibot)"' in text
    assert "command not found" in text
    assert "lowercase `path` is a special array tied to `PATH`" in text
    assert "source\ncheckout" in text
    assert "uv run" not in text
    assert "Form terminal-timeout rule" in text


def test_omnibot_skill_documents_runtime_reliability_contracts():
    root = Path("src/omnibot/skills/omnibot")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.md"))

    assert "wait --load --tab-id <TAB_ID>" in text
    assert "Bare `--load` defaults to the `load` lifecycle state" in text
    assert "`status: error` and `status: timeout` exit non-zero" in text
    assert "`EXTENSION_DISCONNECTED`" in text
    assert "`DAEMON_DISCONNECTED` / `DAEMON_TIMEOUT`" in text
    assert "same-tab `goto`" in text
    assert "does not replay clicks, fills, new-tab creation" in text
    assert "`url`, `title`, `viewport`, and `bytes`" in text
    assert "`bytes > 0`" in text
    assert "`/usr/bin/wc`" in text
    assert "Use `route_path` or `page_path`" in text
    assert "redirecting Omnibot output to `/dev/null`" in text


def test_omnibot_skill_documents_network_capture_workflow():
    root = Path("src/omnibot/skills/omnibot")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.md"))
    text_lower = text.lower()
    assert "network clear" in text_lower
    assert "network start" in text_lower
    assert "network stop" in text_lower
    assert "network logs" in text_lower
    assert "raw `cdp` calls are one-shot" in text_lower


def test_omnibot_skill_documents_legacy_jsf_and_nested_frame_workflows():
    root = Path("src/omnibot/skills/omnibot")
    main = (root / "SKILL.md").read_text(encoding="utf-8")
    operations = (root / "references" / "operation-patterns.md").read_text(encoding="utf-8")
    debugging = (root / "references" / "debugging-and-evidence.md").read_text(encoding="utf-8")

    assert "[textbox] [type=password]" in main
    assert "frame main` is the reserved return-to-host command" in main
    assert "Legacy Java/JSF pages may contain multiple `body` elements" in operations
    assert "Frame selection is absolute for the tab" in operations
    assert "get attr @eN src" in operations
    assert "browser mouse-visual-state --tab-id <TAB_ID>" in debugging


def test_omnibot_skill_has_checkout_safety_rules():
    root = Path("src/omnibot/skills/omnibot")
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.md"))
    assert "Do not click final submit/pay/place-order controls" in text
    assert "Do not reveal cookies, auth headers" in text


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
