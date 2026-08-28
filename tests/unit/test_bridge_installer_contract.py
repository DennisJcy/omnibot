import json
from pathlib import Path

import pytest

from omnibot import bridge_installer


def test_manifest_contains_native_host_contract(tmp_path):
    launcher = tmp_path / "omnibot-bridge-host.sh"
    manifest = bridge_installer.build_manifest(launcher_path=launcher, extension_id="abcdef")

    assert manifest == {
        "name": "ai.omnibot.bridge",
        "description": "omnibot native bridge for browser extension communication",
        "path": str(launcher),
        "type": "stdio",
        "allowed_origins": ["chrome-extension://abcdef/"],
    }


def test_write_launcher_uses_bridge_host_subcommand(tmp_path):
    launcher = bridge_installer.write_launcher(tmp_path, executable="/usr/local/bin/omnibot")

    text = launcher.read_text(encoding="utf-8")
    assert "bridge-host" in text
    assert "-m" not in text
    assert "omnibot.bridge_host" not in text


def test_macos_edge_manifest_path_uses_browser_native_hosts(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge_installer.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    path = bridge_installer.browser_manifest_path("edge")

    assert path == tmp_path / "Library" / "Application Support" / "Microsoft Edge" / "NativeMessagingHosts" / "ai.omnibot.bridge.json"


def test_find_extension_id_prefers_matching_browser_session():
    sessions = [
        {"browser": "chrome", "extension_id": "chrome-extension"},
        {"browser": "edge", "extension_id": "edge-extension"},
    ]

    assert bridge_installer.find_extension_id(sessions, "edge") == "edge-extension"


def test_find_extension_id_falls_back_to_browser_client_id():
    sessions = [{"client_id": "edge-dlbiigchkpmpijahmlofleeemiomaneo-5b32dce5"}]

    assert bridge_installer.find_extension_id(sessions, "edge") == "dlbiigchkpmpijahmlofleeemiomaneo"


def test_uninstall_bridge_removes_browser_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge_installer.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    manifest_path = bridge_installer.browser_manifest_path("edge")
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}", encoding="utf-8")

    bridge_installer.uninstall_bridge(browser="edge")

    assert not manifest_path.exists()


def test_install_bridge_refuses_macos_rejected_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge_installer.sys, "platform", "darwin")
    monkeypatch.setattr(bridge_installer, "install_dir", lambda: tmp_path / "native-bridge")
    monkeypatch.setattr(bridge_installer, "browser_manifest_path", lambda browser: tmp_path / "NativeMessagingHosts" / "ai.omnibot.bridge.json")
    monkeypatch.setattr(bridge_installer, "is_executable_accepted_by_gatekeeper", lambda executable: False)

    with pytest.raises(RuntimeError, match="not accepted by macOS Gatekeeper"):
        bridge_installer.install_bridge(extension_id="edge-extension", browser="edge")

    assert not (tmp_path / "NativeMessagingHosts" / "ai.omnibot.bridge.json").exists()
