import os
import sys
from pathlib import Path


def state_dir() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    path = base / "omnibot"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pid_path() -> Path:
    return state_dir() / "daemon.pid"


def log_path() -> Path:
    return state_dir() / "daemon.log"
