"""Agent configuration logic for omnibot CLI v2."""
import json
import os
import platform
import sys
from pathlib import Path

from .logger import log


SUPPORTED_AGENTS = ("hermes", "opencode", "claude", "codex", "openclaw", "trae")


def get_config_path(agent):
    log(f"get_config_path: agent={agent}")
    if agent == "opencode":
        path = Path.home() / ".config" / "opencode" / "opencode.json"
    elif agent == "hermes":
        if platform.system() == "Windows":
            path = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "config.yaml"
        else:
            path = Path.home() / ".hermes" / "config.yaml"
    elif agent == "codex":
        path = Path.home() / ".codex" / "config.json"
    elif agent == "openclaw":
        path = Path.home() / ".openclaw" / "config.json"
    elif agent == "trae":
        path = Path.home() / ".trae" / "config.json"
    elif agent == "workbuddy":
        path = Path.home() / ".workbuddy" / "config.json"
    elif agent == "claude":
        path = None
    else:
        log(f"get_config_path: unknown agent={agent}")
        raise ValueError(f"Unknown agent: {agent}")

    log(f"get_config_path: resolved path={path}")
    return path


def generate_config_content(agent):
    log(f"generate_config_content: agent={agent}")
    if agent in SUPPORTED_AGENTS:
        return f"omnibot skills install --agent {agent}"
    if agent == "workbuddy":
        config = {
            "mcpServers": {
                "omnibot": {
                    "command": "omnibot",
                    "disabled": False,
                }
            }
        }
        return json.dumps(config, indent=2)
    log(f"generate_config_content: unknown agent={agent}")
    raise ValueError(f"Unknown agent: {agent}")


def get_config_format(agent):
    log(f"get_config_format: agent={agent}")
    if agent in {"hermes", "opencode", "claude", "codex", "openclaw", "trae"}:
        return "command"
    if agent == "workbuddy":
        return "json"
    log(f"get_config_format: unknown agent={agent}")
    raise ValueError(f"Unknown agent: {agent}")
