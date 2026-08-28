from __future__ import annotations

from pathlib import Path

VISIBILITY_MODES = ["visible", "background", "dedicated-profile", "headless"]


def normalize_mode(mode: str | None) -> str:
    value = (mode or "visible").strip().lower()
    if value not in VISIBILITY_MODES:
        raise ValueError(f"Unsupported visibility mode: {mode}. Expected one of: {', '.join(VISIBILITY_MODES)}")
    return value


def mode_capabilities(mode: str | None) -> dict:
    value = normalize_mode(mode)
    if value == "visible":
        return {"mode": value, "uses_user_current_browser": True, "requires_dedicated_profile": False, "can_be_headless": False, "warnings": []}
    if value == "background":
        return {"mode": value, "uses_user_current_browser": True, "requires_dedicated_profile": False, "can_be_headless": False, "warnings": ["browser window may still be visible to the OS and user"]}
    if value == "dedicated-profile":
        return {"mode": value, "uses_user_current_browser": False, "requires_dedicated_profile": True, "can_be_headless": False, "warnings": ["does not share the user's current login state unless profile data is explicitly configured"]}
    return {"mode": value, "uses_user_current_browser": False, "requires_dedicated_profile": True, "can_be_headless": True, "warnings": ["extension support depends on Chromium headless extension behavior", "does not control the user's already-open browser tabs"]}


def dedicated_profile_args(executable: str, user_data_dir: str | Path, remote_debugging_port: int | None = None) -> list[str]:
    args = [executable, f"--user-data-dir={Path(user_data_dir)}", "--no-first-run", "--no-default-browser-check"]
    if remote_debugging_port:
        args.append(f"--remote-debugging-port={remote_debugging_port}")
    return args


def headless_launch_args(executable: str, user_data_dir: str | Path, remote_debugging_port: int) -> list[str]:
    return dedicated_profile_args(executable, user_data_dir, remote_debugging_port) + ["--headless=new", "--disable-gpu"]
