"""Verify that lightweight CLI commands do not pull in the heavy
daemon/browser stack (daemon, actions, TMWebDriver, simphtml,
, bs4, cryptography)."""
import json
import subprocess
import sys
import textwrap


HEAVY_MODULES = [
    "omnibot.daemon",
    "omnibot.actions",
    "omnibot.TMWebDriver",
    "omnibot.simphtml",
    "bs4",
    "cryptography",
]


def _run_probe(code: str) -> dict[str, bool]:
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_help_does_not_import_daemon_or_browser_stack():
    heavy = list(HEAVY_MODULES)
    loaded = _run_probe(
        """
        import contextlib
        import io
        import json
        import sys

        from omnibot.cli import main

        with contextlib.redirect_stdout(io.StringIO()):
            result = main(["--help"])

        assert result == 0
        print(json.dumps({name: name in sys.modules for name in %r}))
        """
        % heavy
    )
    assert loaded == {name: False for name in heavy}


def test_daemon_status_does_not_import_daemon_or_browser_stack():
    heavy = list(HEAVY_MODULES)
    loaded = _run_probe(
        """
        import contextlib
        import io
        import json
        import sys

        from omnibot.cli import main

        with contextlib.redirect_stdout(io.StringIO()):
            result = main(["daemon", "status"])

        assert result == 0
        print(json.dumps({name: name in sys.modules for name in %r}))
        """
        % heavy
    )
    assert loaded == {name: False for name in heavy}
