from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_primary_docs_do_not_instruct_native_bridge_install():
    paths = [
        ROOT / "README.md",
        ROOT / "AGENTS.md",
        ROOT / "src" / "omnibot" / "skills" / "omnibot" / "SKILL.md",
    ]

    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "omnibot install-bridge" not in text
        assert "Native Bridge" not in text
        assert "native bridge" not in text


def test_primary_docs_describe_websocket_daemon_auto_start():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "omnibot doctor" in readme
    assert "omnibot tabs" in readme
    assert "omnibot snapshot" in readme
    assert "daemon" in readme
