"""Compatibility shim for omnibot v2.

omnibot v2 removes the MCP runtime surface. This module now delegates
behavioral helpers to `omnibot.actions` so existing behavioral tests can
continue exercising the same contracts while the CLI layer replaces MCP tools.
"""

from . import actions, simphtml
from .actions import (
    STATUS_MAP,
    ensure_sessions,
    extension_command,
    infer_or_default_js_status,
    navigate_new_tab,
    normalize_tab_id,
    resolve_session_id,
    update_group_status,
)

_resolve_session_id = resolve_session_id
_extension_command = extension_command
_update_group_status = update_group_status
_navigate_new_tab = navigate_new_tab


def main() -> None:
    raise RuntimeError("omnibot v2 no longer exposes MCP tools. Use `omnibot --help`.")
