"""Verify defaults.py and state.py are lightweight — they must not pull in
the heavy daemon/browser stack (daemon, actions, TMWebDriver, simphtml,
)."""

import importlib
import sys


def test_defaults_import_isolation():
    """Importing defaults must not trigger imports of heavy modules."""
    heavy_modules = {
        "omnibot.daemon",
        "omnibot.actions",
        "omnibot.TMWebDriver",
        "omnibot.simphtml",
    }
    # Purge any previously loaded heavy modules so the test is meaningful.
    for mod_name in heavy_modules:
        sys.modules.pop(mod_name, None)

    import omnibot.defaults  # noqa: F401

    loaded = set(sys.modules)
    leaking = loaded & heavy_modules
    assert not leaking, f"defaults.py pulled in heavy modules: {leaking}"


def test_state_import_isolation():
    """Importing state must not trigger imports of heavy modules."""
    heavy_modules = {
        "omnibot.daemon",
        "omnibot.actions",
        "omnibot.TMWebDriver",
        "omnibot.simphtml",
    }
    for mod_name in heavy_modules:
        sys.modules.pop(mod_name, None)

    import omnibot.state  # noqa: F401

    loaded = set(sys.modules)
    leaking = loaded & heavy_modules
    assert not leaking, f"state.py pulled in heavy modules: {leaking}"


def test_defaults_values():
    from omnibot.defaults import DEFAULT_API_HOST, DEFAULT_API_PORT, DEFAULT_WS_PORT

    assert DEFAULT_API_HOST == "127.0.0.1"
    assert DEFAULT_API_PORT == 18764
    assert DEFAULT_WS_PORT == 18765


def test_state_dir_returns_path():
    from pathlib import Path

    from omnibot.state import state_dir

    result = state_dir()
    assert isinstance(result, Path)
    assert result.exists()
    assert result.name == "omnibot"
