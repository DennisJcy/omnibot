"""Contract tests for the npm platform packages.

The CLI launcher (``bin/omnibot.js``) and each platform package.json
must agree on the standalone layout: ``bin/omnibot-<platform>/<binary>``.
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NPM_ROOT = REPO_ROOT / "npm-packages"

CLI_LAUNCHER = (NPM_ROOT / "cli" / "bin" / "omnibot.js").read_text(encoding="utf-8")

PLATFORM_PACKAGES = {
    "win-x64": {
        "pkg": "@omniaibot/win-x64",
        "dir_name": "omnibot-windows-x64",
        "binary": "omnibot-windows-x64.exe",
        "os": "win32",
        "arch": "x64",
    },
    "linux-x64": {
        "pkg": "@omniaibot/linux-x64",
        "dir_name": "omnibot-linux-x64",
        "binary": "omnibot-linux-x64",
        "os": "linux",
        "arch": "x64",
    },
    "macos-arm64": {
        "pkg": "@omniaibot/macos-arm64",
        "dir_name": "omnibot-macos-arm64",
        "binary": "omnibot-macos-arm64",
        "os": "darwin",
        "arch": "arm64",
    },
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_cli_launcher_resolves_standalone_binary_per_platform():
    for info in PLATFORM_PACKAGES.values():
        assert f'pkg = "{info["pkg"]}"' in CLI_LAUNCHER, info["pkg"]
        assert f'dirName = "{info["dir_name"]}"' in CLI_LAUNCHER, info["dir_name"]
        assert f'binName = "{info["binary"]}"' in CLI_LAUNCHER, info["binary"]
        assert 'path.join(pkgDir, "bin", dirName, binName)' in CLI_LAUNCHER


def test_cli_optional_dependencies_match_platform_packages():
    cli_pkg = _load_json(NPM_ROOT / "cli" / "package.json")
    expected = {info["pkg"]: cli_pkg["version"] for info in PLATFORM_PACKAGES.values()}
    assert cli_pkg["optionalDependencies"] == expected


def test_platform_packages_use_standalone_layout():
    for folder, info in PLATFORM_PACKAGES.items():
        pkg = _load_json(NPM_ROOT / folder / "package.json")
        assert pkg["name"] == info["pkg"]
        assert pkg["os"] == [info["os"]]
        assert pkg["cpu"] == [info["arch"]]
        assert pkg["bin"] == {"omnibot": f"bin/{info['dir_name']}/{info['binary']}"}
        assert pkg["files"] == ["bin/"]


def test_cli_launcher_does_not_reference_legacy_onefile_paths():
    assert 'path.join(pkgDir, "bin", binName)' not in CLI_LAUNCHER
    assert 'os === "win32" ? "omnibot.exe" : "omnibot"' not in CLI_LAUNCHER
