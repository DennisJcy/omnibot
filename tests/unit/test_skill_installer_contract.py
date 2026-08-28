from __future__ import annotations

from omnibot import skill_installer


def test_install_official_skills_unchanged(tmp_path, monkeypatch):
    target = tmp_path / "agent-skills"
    result = skill_installer.install(agent="opencode", target_dir=str(target))
    assert result["status"] == "success"
    assert any("omnibot" in p for p in result["installed"])
