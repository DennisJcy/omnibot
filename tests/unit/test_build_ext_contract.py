import importlib.util
import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


def _load_build_ext():
    spec = importlib.util.spec_from_file_location("build_ext", ROOT / "build_ext.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pyinstaller_entrypoint_bootstraps_package_main():
    entrypoint = ROOT / "build-config" / "_entry.py"
    source = entrypoint.read_text()

    assert entrypoint.exists()
    assert "from omnibot import main" in source
    assert "from ." not in source
    assert "main()" in source


def test_extension_no_longer_injects_native_dialog_override():
    build_ext = _load_build_ext()
    manifest_path = ROOT / "browser-extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    assert "disable_dialogs.js" not in build_ext.JS_FILES
    scripts = [script for entry in manifest.get("content_scripts", []) for script in entry.get("js", [])]
    assert "disable_dialogs.js" not in scripts


def test_extension_captures_native_dialogs_without_blocking_them():
    build_ext = _load_build_ext()
    script_path = ROOT / "browser-extension" / "native_dialogs.js"
    source = script_path.read_text()

    assert "native_dialogs.js" in build_ext.JS_FILES
    assert "const nativeConfirm = window.confirm.bind(window)" in source
    assert "source: 'omnibot-native-dialog'" in source
    assert "document.dispatchEvent" in source
    assert "data-omnibot-last-dialog" in source
    assert "return nativeConfirm(message)" in source
    assert "return true" not in source
    assert "Blocked Confirm" not in source


def test_extension_deduplicates_multi_source_dialog_events():
    source = (ROOT / "browser-extension" / "background.js").read_text()

    assert "dialogEntryKey" in source
    assert "state.entries[state.entries.length - 1]" in source
    assert "hasBrowserHandler: previous.hasBrowserHandler || entry.hasBrowserHandler" in source


def test_content_bridge_forwards_dialog_prompt_text():
    source = (ROOT / "browser-extension" / "content.js").read_text()

    assert "promptText: req.promptText" in source


def test_extension_contains_mouse_visualization_bridge():
    background = (ROOT / "browser-extension" / "background.js").read_text()
    content = (ROOT / "browser-extension" / "content.js").read_text()

    assert "data.type === 'mouse_visual'" in background
    assert "cmd: 'mouse-visual'" in background
    assert "mouse-visual-ready" in background
    assert "omnibot-mouse-visual" in content
    assert "class=\"pointer\"" in content
    assert "className = 'trail'" in content
    assert "className = 'pulse'" in content
    assert "clip-path: polygon" in content
    assert "background: #050505" in content
    assert "window.__omnibotMouseVisualLegacy" in content
    assert "transform: none" in content
    assert "TIP_OFFSET_X = 0" in content
    assert "TIP_OFFSET_Y = 0" in content
    assert "drop-shadow(0 0 4px rgba(51,156,255,.95))" in content
    assert ".pointer.visible" in content
    assert "setTimeout(() => pointer.classList.remove('visible'), 1200)" in content
    assert (ROOT / "browser-extension" / "cursor-chat.png").exists()


def test_child_frame_ready_does_not_replay_stale_mouse_event():
    background = (ROOT / "browser-extension" / "background.js").read_text()
    content = (ROOT / "browser-extension" / "content.js").read_text()

    assert "if (window.self === window.top)" in content
    assert "{ event, receivedAt: Date.now() }" in background
    assert "sender.frameId == null || sender.frameId === 0" in background
    assert "Date.now() - pending.receivedAt <= 1500" in background
    assert "event: pending.event" in background


def test_extension_reinjects_visual_bridge_for_existing_tabs():
    source = (ROOT / "browser-extension" / "background.js").read_text()

    assert "ensureMouseVisualContentScript" in source
    assert "func: installMouseVisualBridge" in source
    assert "function installMouseVisualBridge()" in source
    assert "mouse_visual broadcast targets=" in (ROOT / "src/omnibot/TMWebDriver.py").read_text()
    assert "setTimeout(deliver, 120)" in source
    assert "setTimeout(deliver, 600)" in source
    assert "Existing tabs do not receive content_scripts again after an extension" in source
    assert "window.__omnibotMouseVisualRender" in source


def test_extension_declares_standalone_mouse_visual_content_script():
    manifest = json.loads((ROOT / "browser-extension" / "manifest.json").read_text())
    scripts = [script for entry in manifest.get("content_scripts", []) for script in entry.get("js", [])]
    assert "mouse_visual.js" in scripts
    assert "mouse_visual.js" in _load_build_ext().JS_FILES
    source = (ROOT / "browser-extension" / "mouse_visual.js").read_text()
    assert "omnibot-mouse-visual" in source
    assert "cursor-chat.png" in source
    assert "width:23px;height:24px" in source
    assert "translate3d(12px,-2.5px,0)" in source
    assert "rotate(44deg) scale(1)" in source
    assert "msg.cmd !== 'mouse-visual'" in source
    assert "window.__omnibotStandaloneMouseVisual" in source
    assert "root.querySelector('.pointer-asset')" in source
    assert "pointer.style.opacity = '0'" in source
    assert "setTimeout(() => { pointer.style.opacity = '0'; }, 4500)" in source
    assert "translate3d(${x - 12}px,${y - 12}px,0) rotate(-44deg)" in source
    assert "x - 14.5" not in source
    assert "mouse-visual-ready" in source


def test_extension_packages_offscreen_keepalive_document():
    build_ext = _load_build_ext()
    manifest_path = ROOT / "browser-extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())

    assert "offscreen" in manifest.get("permissions", [])
    assert any("cursor-chat.png" in item.get("resources", []) for item in manifest.get("web_accessible_resources", []))
    assert "offscreen.js" in build_ext.JS_FILES
    assert (ROOT / "browser-extension" / "offscreen.html").exists()
    assert (ROOT / "browser-extension" / "offscreen.js").exists()


def test_extension_claims_clipboard_permissions_and_offscreen_handler():
    manifest_path = ROOT / "browser-extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert "clipboardRead" in manifest.get("permissions", [])
    assert "clipboardWrite" in manifest.get("permissions", [])

    bg_source = (ROOT / "browser-extension" / "background.js").read_text()
    assert "handleClipboard" in bg_source
    assert "msg.cmd === 'clipboard'" in bg_source
    assert "ensureOffscreenDocument" in bg_source

    offscreen_source = (ROOT / "browser-extension" / "offscreen.js").read_text()
    assert "navigator.clipboard.readText" in offscreen_source
    assert "navigator.clipboard.writeText" in offscreen_source


def test_extension_declares_windows_permission_and_create_handler():
    manifest_path = ROOT / "browser-extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert "windows" in manifest.get("permissions", [])

    source = (ROOT / "browser-extension" / "background.js").read_text()
    assert "msg.cmd === 'windows'" in source
    assert "chrome.windows.create" in source
    assert "windowId: win.id" in source


def test_extension_tab_groups_use_promise_callback_compatibility_bridge():
    source = (ROOT / "browser-extension" / "background.js").read_text()

    assert "msg.cmd === 'tabGroups'" in source
    assert "callChromeApi(chrome.tabs.group" in source
    assert "callChromeApi(chrome.tabGroups.update" in source
    assert "Older workers return the tab-group object directly" in (ROOT / "src/omnibot/actions.py").read_text()


def test_extension_content_settings_supports_read_only_get():
    source = (ROOT / "browser-extension" / "background.js").read_text()

    assert "msg.cmd === 'contentSettings'" in source
    assert "msg.method === 'get'" in source
    assert "contentSettings[type].get" in source
    assert "primaryUrl" in source


def test_extension_declares_browser_data_permissions_for_history_bookmarks_and_downloads():
    manifest_path = ROOT / "browser-extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    permissions = manifest.get("permissions", [])
    for permission in ("history", "bookmarks", "downloads", "sessions", "topSites"):
        assert permission in permissions


def test_extension_routes_browser_commands_from_websocket_exec_to_background_api():
    source = (ROOT / "browser-extension" / "background.js").read_text()
    assert "const commands = new Set" in source
    assert "handleExtMessage(extensionCommand, {})" in source
    assert "commands.has(parsed.cmd)" in source
    exec_source = source[source.index("async function handleWsExec(data, socket = ws)"):]
    assert exec_source.index("socket.send(JSON.stringify({ type: 'ack', id: data.id }))") < exec_source.index("const browserClientId = await ensureBrowserClientId()")
    assert "result: res, browserClientId" in exec_source


def test_extension_handshake_reports_manifest_version():
    source = (ROOT / "browser-extension" / "background.js").read_text()
    assert "const extensionVersion = chrome.runtime.getManifest().version || ''" in source
    assert "extensionVersion" in source


def test_extension_does_not_send_on_closed_async_websocket():
    source = (ROOT / "browser-extension" / "background.js").read_text()
    assert "const socket = ws" in source
    assert "handleWsExec(data, socket)" in source
    assert "socket.readyState === WebSocket.OPEN" in source


def test_extension_tabs_update_recaptures_websocket_after_async_work():
    source = (ROOT / "browser-extension" / "background.js").read_text()
    body = source[source.index("async function sendTabsUpdate()") :]
    body = body[: body.index("chrome.tabs.onUpdated.addListener")]

    tabs_query = body.index("await chrome.tabs.query({})")
    socket_capture = body.index("const socket = ws", tabs_query)
    readiness_check = body.index("if (!socket || socket.readyState !== WebSocket.OPEN) return", socket_capture)
    send = body.index("socket.send(JSON.stringify(msg))", readiness_check)

    assert tabs_query < socket_capture < readiness_check < send
    assert "ws.send(JSON.stringify(msg))" not in body
    assert "tabs update skipped:" in body


def test_extension_cdp_reuses_per_tab_debugger_lease_until_idle():
    source = (ROOT / "browser-extension" / "background.js").read_text()

    assert "const DEBUGGER_IDLE_TTL_MS = 30_000" in source
    assert "const debuggerSessionsByTab = new Map()" in source
    assert "async function withDebugger(tabId, callback)" in source
    assert "session.inFlight += 1" in source
    assert "session.expiresAt = Date.now() + DEBUGGER_IDLE_TTL_MS" in source
    assert "async function cleanupDebuggerSession(tabId)" in source
    assert "chrome.debugger.onDetach.addListener" in source
    assert "refreshDebuggerSessionIfAttached(tabId)" in source

    cdp_body = source[source.index("async function handleCDP(msg, sender)") :]
    cdp_body = cdp_body[: cdp_body.index("const isScriptable")]
    assert "withDebugger(tabId" in cdp_body
    assert "chrome.debugger.attach" not in cdp_body
    assert "chrome.debugger.detach" not in cdp_body

    assert source.count("chrome.debugger.attach") == 1
    assert source.count("chrome.debugger.detach") == 1


def test_extension_default_locale_uses_chrome_supported_locale_directory():
    manifest_path = ROOT / "browser-extension" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    default_locale = manifest.get("default_locale")

    assert default_locale == "zh_CN"
    assert (ROOT / "browser-extension" / "_locales" / default_locale / "messages.json").exists()
    assert not (ROOT / "browser-extension" / "_locales" / "zh" / "messages.json").exists()
