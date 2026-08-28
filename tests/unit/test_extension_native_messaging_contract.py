import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_does_not_request_native_messaging_permission():
    manifest = json.loads((ROOT / "browser-extension" / "manifest.json").read_text(encoding="utf-8"))

    assert "nativeMessaging" not in manifest.get("permissions", [])


def test_background_never_connects_native_bridge():
    background = (ROOT / "browser-extension" / "background.js").read_text(encoding="utf-8")

    assert "chrome.runtime.connectNative" not in background
    assert "connectNativeBridge" not in background
    assert "nativePort" not in background
    assert "connectWS();" in background


def test_reconnect_resilience_does_not_use_native_messaging():
    background = (ROOT / "browser-extension" / "background.js").read_text(encoding="utf-8")

    assert "async function ensureConnected()" in background
    assert "nativeMessaging" not in background
    assert "chrome.runtime.connectNative" not in background
