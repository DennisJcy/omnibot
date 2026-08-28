import shutil
from importlib import resources
from pathlib import Path
from typing import Any


def packaged_skills_dir() -> Path:
    return Path(str(resources.files("omnibot") / "skills"))


def _packaged_skill_names() -> list[str]:
    skills_root = packaged_skills_dir()
    return sorted(p.name for p in skills_root.iterdir() if p.is_dir())


def default_target_dir(agent: str) -> Path:
    home = Path.home()
    if agent == "hermes":
        return home / ".hermes" / "skills"
    if agent == "opencode":
        return home / ".config" / "opencode" / "skills"
    if agent == "claude":
        return home / ".claude" / "skills"
    if agent == "codex":
        return home / ".codex" / "skills"
    if agent == "openclaw":
        return home / ".openclaw" / "skills"
    if agent == "workbuddy":
        return home / ".workbuddy" / "skills"
    if agent == "trae":
        return home / ".trae" / "skills"
    raise ValueError(f"Unsupported agent: {agent}")


def hermes_profile_dir(profile: str) -> Path:
    return Path.home() / ".hermes" / "profiles" / profile / "skills"


def hermes_profile_dirs() -> list[Path]:
    profiles = Path.home() / ".hermes" / "profiles"
    if not profiles.exists():
        return []
    return [path / "skills" for path in profiles.iterdir() if path.is_dir()]


def copy_skills(target_dir: Path) -> list[str]:
    source_root = packaged_skills_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in _packaged_skill_names():
        src = source_root / name
        dst = target_dir / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        copied.append(str(dst))
    return copied


def install(agent: str, profile: str | None = None, all_profiles: bool = False, target_dir: str | None = None) -> dict[str, Any]:
    targets: list[Path]
    if target_dir:
        targets = [Path(target_dir)]
    elif agent == "hermes" and profile:
        targets = [hermes_profile_dir(profile)]
    elif agent == "hermes" and all_profiles:
        targets = hermes_profile_dirs()
    else:
        targets = [default_target_dir(agent)]
    installed = []
    for target in targets:
        installed.extend(copy_skills(target))
    return {"status": "success", "agent": agent, "installed": installed}
