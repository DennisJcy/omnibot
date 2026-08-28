import json
import re
import shutil
import subprocess
import time
import unittest
from pathlib import Path

from omnibot import actions, server
from omnibot.TMWebDriver import Session, TMWebDriver, UserContext


ROOT = Path(__file__).resolve().parents[2]
BACKGROUND_JS = ROOT / "browser-extension" / "background.js"


class BackgroundBrowserClientContractTest(unittest.TestCase):
    def test_background_persists_browser_client_id(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        self.assertIn("browserClientId", source)
        self.assertIn("ensureBrowserClientId", source)
        self.assertRegex(source, r"chrome\.storage\.local\.get\([^)]*browserClientId")
        self.assertRegex(source, r"chrome\.storage\.local\.set\([^)]*browserClientId")

    def test_ext_ready_and_tabs_update_include_browser_identity(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        ext_ready_block = re.search(
            r"const msg = \{ type: 'ext_ready'.*?\};",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(ext_ready_block, "ext_ready message block not found")
        self.assertIn("browserClientId", ext_ready_block.group(0))
        self.assertIn("extensionId", ext_ready_block.group(0))
        self.assertIn("browser", ext_ready_block.group(0))

        tabs_update_block = re.search(
            r"const msg = \{\s*type: 'tabs_update'.*?\};",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(tabs_update_block, "tabs_update message block not found")
        self.assertIn("browserClientId", tabs_update_block.group(0))
        self.assertIn("extensionId", tabs_update_block.group(0))
        self.assertIn("browser", tabs_update_block.group(0))

    def test_execution_results_include_browser_client_id(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        self.assertIn("browserClientId", source)
        self.assertRegex(source, r"type: 'result'.*browserClientId")
        self.assertRegex(source, r"type: 'error'.*browserClientId")

    def test_daemon_records_extension_version_on_live_client(self):
        source = (ROOT / "src" / "omnibot" / "TMWebDriver.py").read_text(encoding="utf-8")

        self.assertIn("self.extension_version = extension_version or ''", source)


class BackgroundNewTabStabilizationContractTest(unittest.TestCase):
    def test_background_waits_for_scriptable_new_tabs(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        self.assertIn("waitForScriptableTab", source)
        self.assertIn("isScriptable(t.url)", source)

    def test_cdp_commands_can_watch_and_return_new_tabs(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        handle_cdp = re.search(
            r"async function handleCDP\(msg, sender\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(handle_cdp, "handleCDP function not found")
        body = handle_cdp.group("body")

        self.assertIn("watchNewTabs", body)
        self.assertIn("chrome.tabs.onCreated.addListener", body)
        self.assertIn("newTabs", body)
        self.assertRegex(source, r"newTabs:\s*res\.newTabs")

    def test_new_tab_watch_requires_matching_opener(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        self.assertIn("tab.openerTabId === Number(openerTabId)", source)
        self.assertIn("tab.openerTabId === Number(tabId)", source)
        self.assertIn("openerTabId: t.openerTabId", source)

    def test_cdp_new_tab_watch_does_not_fixed_sleep_every_click(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        handle_cdp = re.search(
            r"async function handleCDP\(msg, sender\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(handle_cdp, "handleCDP function not found")

        self.assertNotRegex(
            handle_cdp.group("body"),
            r"if\s*\(watchNewTabs\)\s*await\s+new\s+Promise\([^;]+1800",
        )
        self.assertIn("waitForNewTabIds", source)

    def test_cdp_key_events_drain_before_debugger_detach(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        handle_cdp = re.search(
            r"async function handleCDP\(msg, sender\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(handle_cdp, "handleCDP function not found")
        body = handle_cdp.group("body")
        self.assertIn("msg.method === 'Input.dispatchKeyEvent'", body)
        self.assertIn("setTimeout(resolve, 50)", body)


class BackgroundReconnectContractTest(unittest.TestCase):
    def test_background_defines_ensure_connected(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        self.assertIn("async function ensureConnected()", source)
        self.assertIn("connectWS()", source)
        self.assertIn("WebSocket.OPEN", source)

    def test_tab_update_events_wake_reconnect_before_tabs_update(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        fn = re.search(
            r"async function sendTabsUpdate\(\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(fn, "sendTabsUpdate function not found")
        body = fn.group("body")

        self.assertIn("await ensureConnected()", body)
        self.assertIn("chrome.tabs.onUpdated.addListener", source)
        self.assertIn("chrome.tabs.onCreated.addListener", source)
        self.assertIn("chrome.tabs.onActivated.addListener", source)

    def test_background_starts_offscreen_keepalive_for_mv3_worker(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        self.assertIn("async function ensureOffscreenDocument()", source)
        self.assertIn("chrome.offscreen.createDocument", source)
        self.assertIn("offscreen.html", source)
        self.assertRegex(source, r"connectWS\(\);\s*ensureOffscreenDocument\(\);")

    def test_offscreen_ping_reuses_reconnect_path(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        handler = re.search(
            r"async function handleExtMessage\(msg, sender\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(handler, "handleExtMessage function not found")
        body = handler.group("body")

        self.assertIn("offscreen_ping", body)
        self.assertIn("ensureConnected()", body)

    def test_stale_socket_close_cannot_clear_replacement(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        helper = re.search(
            r"function handleWebSocketClose\(socket\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(helper, "handleWebSocketClose function not found")
        self.assertIn("if (ws !== socket) return", helper.group("body"))

        node = shutil.which("node")
        if not node:
            self.skipTest("node is required for the WebSocket close race regression test")
        script = f"""
let ws = null;
let connecting = false;
let connectionGeneration = 0;
let currentPort = null;
let probes = 0;
function scheduleProbe() {{ probes += 1; }}
function handleWebSocketClose(socket) {{{helper.group('body')}\n}}
const oldSocket = {{ name: 'old' }};
const newSocket = {{ name: 'new' }};
ws = oldSocket;
ws = newSocket;
handleWebSocketClose(oldSocket);
if (ws !== newSocket || probes !== 0 || connectionGeneration !== 0) process.exit(1);
handleWebSocketClose(newSocket);
if (ws !== null || probes !== 1 || connectionGeneration !== 1) process.exit(2);
"""
        result = subprocess.run([node, "-e", script], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


class BackgroundConsoleCaptureContractTest(unittest.TestCase):
    def test_console_clear_clears_devtools_messages(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        handle_console_capture = re.search(
            r"async function handleConsoleCapture\(msg, sender\) \{(?P<body>.*?)\n\}",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(handle_console_capture, "handleConsoleCapture function not found")
        body = handle_console_capture.group("body")

        self.assertIn("Console.clearMessages", body)


class BrowserClientSessionIsolationTest(unittest.TestCase):
    def test_session_stores_client_id_from_info(self):
        session = Session("123", {"url": "https://example.com", "title": "", "type": "ext_ws", "client_id": "edge-client"})

        self.assertEqual(session.client_id, "edge-client")

    def test_duplicate_tab_ids_from_different_clients_are_distinct_sessions(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")

        class FakeClient:
            pass

        driver._register_client(
            "edge-client:123",
            FakeClient(),
            {"url": "https://edge.example", "title": "Edge", "type": "ext_ws", "client_id": "edge-client", "tab_id": "123"},
        )
        driver._register_client(
            "chrome-client:123",
            FakeClient(),
            {"url": "https://chrome.example", "title": "Chrome", "type": "ext_ws", "client_id": "chrome-client", "tab_id": "123"},
        )

        self.assertIn("edge-client:123", driver._default_ctx.sessions)
        self.assertIn("chrome-client:123", driver._default_ctx.sessions)
        self.assertEqual(driver._default_ctx.sessions["edge-client:123"].client_id, "edge-client")
        self.assertEqual(driver._default_ctx.sessions["chrome-client:123"].client_id, "chrome-client")


class BrowserClientTransportSelectionTest(unittest.TestCase):
    def test_transport_uses_same_client_as_target_session(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        edge_target = Session("edge-client:123", {"url": "https://edge.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "123"})
        chrome_transport = Session("chrome-client:456", {"url": "https://chrome.example", "title": "", "type": "ext_ws", "client_id": "chrome-client", "tab_id": "456"})
        edge_transport = Session("edge-client:789", {"url": "https://edge2.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "789"})
        driver._default_ctx.sessions = {
            "chrome-client:456": chrome_transport,
            "edge-client:123": edge_target,
            "edge-client:789": edge_transport,
        }

        self.assertEqual(driver._transport_session_id("edge-client:123"), "edge-client:123")

    def test_transport_fallback_prefers_requested_client(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        chrome_transport = Session("chrome-client:456", {"url": "https://chrome.example", "title": "", "type": "ext_ws", "client_id": "chrome-client", "tab_id": "456"})
        edge_transport = Session("edge-client:789", {"url": "https://edge.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "789"})
        driver._default_ctx.sessions = {
            "chrome-client:456": chrome_transport,
            "edge-client:789": edge_transport,
        }

        self.assertEqual(driver.get_ext_ws_transport_session_id(token=None, client_id="edge-client"), "edge-client:789")


class BrowserClientResultMetadataTest(unittest.TestCase):
    def test_execute_js_returns_browser_client_id_from_result(self):
        sent_payloads = []

        class FakeWs:
            def send_message(self, payload):
                sent_payloads.append(json.loads(payload))

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        session = Session("edge-client:200", {"url": "https://edge.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "200"}, FakeWs())
        driver._default_ctx.sessions["edge-client:200"] = session

        original_sleep = time.sleep
        try:
            def fake_sleep(_seconds):
                exec_id = sent_payloads[0]["id"]
                driver._default_ctx.results[exec_id] = {"success": True, "data": "ok", "newTabs": [], "browserClientId": "edge-client"}

            time.sleep = fake_sleep
            result = driver.execute_js("return 1;", session_id="edge-client:200")
        finally:
            time.sleep = original_sleep

        self.assertEqual(result["browserClientId"], "edge-client")


class BrowserClientNewTabTargetTest(unittest.TestCase):
    def test_new_tab_returns_composite_id_when_browser_client_id_present(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")

        def fake_execute_js(code, timeout=15, token=None):
            return {
                "data": {
                    "id": 321,
                    "url": "https://www.baidu.com/",
                    "title": "百度一下",
                },
                "browserClientId": "edge-client",
            }

        driver.execute_js = fake_execute_js
        result = driver.new_tab("https://www.baidu.com/", token="request-token")

        self.assertEqual(result["id"], "edge-client:321")
        self.assertEqual(result["tab_id"], "321")
        self.assertEqual(result["browserClientId"], "edge-client")
        self.assertIn("edge-client:321", driver._default_ctx.tool_created_tabs)
        self.assertNotIn("321", driver._default_ctx.tool_created_tabs)

    def test_new_tab_marks_existing_composite_session_as_tool_created(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        session = Session(
            "edge-client:321",
            {
                "url": "https://www.baidu.com/",
                "title": "百度一下",
                "type": "ext_ws",
                "client_id": "edge-client",
                "tab_id": "321",
            },
        )
        driver._default_ctx.sessions["edge-client:321"] = session

        def fake_execute_js(code, timeout=15, token=None):
            return {
                "data": {
                    "id": 321,
                    "url": "https://www.baidu.com/",
                    "title": "百度一下",
                },
                "browserClientId": "edge-client",
            }

        driver.execute_js = fake_execute_js
        result = driver.new_tab("https://www.baidu.com/", token="request-token")

        self.assertEqual(result["id"], "edge-client:321")
        self.assertTrue(driver._default_ctx.sessions["edge-client:321"].created_by_tool)


class BrowserNavigateNewTabTargetTest(unittest.TestCase):
    def test_browser_navigate_uses_composite_new_tab_id_as_target(self):
        ctx = UserContext("__default__")
        old_session = Session(
            "edge-client:100",
            {
                "url": "https://mp.weixin.qq.com/",
                "title": "公众号",
                "type": "ext_ws",
                "client_id": "edge-client",
                "tab_id": "100",
            },
        )
        new_session = Session(
            "edge-client:321",
            {
                "url": "https://www.baidu.com/",
                "title": "百度一下",
                "type": "ext_ws",
                "client_id": "edge-client",
                "tab_id": "321",
            },
        )
        ctx.sessions = {
            "edge-client:100": old_session,
            "edge-client:321": new_session,
        }

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def get_all_sessions(self, token=None):
                return ctx.get_all_active_sessions()

            def new_tab(self, url, timeout=15, token=None):
                return {
                    "id": "edge-client:321",
                    "tab_id": "321",
                    "url": url,
                    "title": "百度一下",
                    "browserClientId": "edge-client",
                }

            def _cancel_tab_close(self, tab_id, token=None):
                self.cancelled_tab_id = tab_id

            def _schedule_tab_close(self, tab_id, token=None):
                self.scheduled_tab_id = tab_id

        driver = FakeDriver()
        original_update_group_status = actions.update_group_status
        try:
            actions.update_group_status = lambda d, tab_id, status, phase, token=None: None
            result = actions.navigate_new_tab(driver, "https://www.baidu.com/", token="request-token")
        finally:
            actions.update_group_status = original_update_group_status

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tab"]["id"], "edge-client:321")
        self.assertEqual(driver.cancelled_tab_id, "edge-client:321")
        self.assertEqual(driver.scheduled_tab_id, "edge-client:321")


class BrowserTabIdentifierResolutionTest(unittest.TestCase):
    def test_resolve_session_id_accepts_canonical_session_id(self):
        ctx = UserContext("__default__")
        ctx.sessions = {
            "edge-client:321": Session(
                "edge-client:321",
                {
                    "url": "https://www.baidu.com/",
                    "title": "百度一下",
                    "type": "ext_ws",
                    "client_id": "edge-client",
                    "tab_id": "321",
                },
            )
        }

        class FakeDriver:
            def get_all_sessions(self, token=None):
                return ctx.get_all_active_sessions()

        self.assertEqual(actions.resolve_session_id(FakeDriver(), "edge-client:321"), "edge-client:321")

    def test_resolve_session_id_accepts_unique_raw_tab_id(self):
        ctx = UserContext("__default__")
        ctx.sessions = {
            "edge-client:321": Session(
                "edge-client:321",
                {
                    "url": "https://www.baidu.com/",
                    "title": "百度一下",
                    "type": "ext_ws",
                    "client_id": "edge-client",
                    "tab_id": "321",
                },
            )
        }

        class FakeDriver:
            def get_all_sessions(self, token=None):
                return ctx.get_all_active_sessions()

        self.assertEqual(actions.resolve_session_id(FakeDriver(), "321"), "edge-client:321")

    def test_resolve_session_id_rejects_ambiguous_raw_tab_id(self):
        ctx = UserContext("__default__")
        ctx.sessions = {
            "edge-client:321": Session(
                "edge-client:321",
                {"url": "https://edge.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "321"},
            ),
            "chrome-client:321": Session(
                "chrome-client:321",
                {"url": "https://chrome.example", "title": "", "type": "ext_ws", "client_id": "chrome-client", "tab_id": "321"},
            ),
        }

        class FakeDriver:
            def get_all_sessions(self, token=None):
                return ctx.get_all_active_sessions()

        self.assertIsNone(actions.resolve_session_id(FakeDriver(), "321"))

    def test_extension_command_accepts_canonical_session_id_and_sends_raw_tab_id(self):
        ctx = UserContext("__default__")
        ctx.sessions = {
            "edge-client:321": Session(
                "edge-client:321",
                {"url": "https://www.baidu.com/", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "321"},
            )
        }
        calls = []

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def get_all_sessions(self, token=None):
                return ctx.get_all_active_sessions()

            def execute_js(self, code, timeout=15, token=None, group_status=None, session_id=None, status_tab_id=None):
                calls.append({"code": json.loads(code), "session_id": session_id, "status_tab_id": status_tab_id})
                return {"data": "ok"}

        result = actions.extension_command(FakeDriver(), {"cmd": "tabs", "method": "switch"}, tab_id="edge-client:321")

        self.assertEqual(result, "ok")
        self.assertEqual(calls[0]["code"]["tabId"], 321)
        self.assertEqual(calls[0]["session_id"], "edge-client:321")
        self.assertEqual(calls[0]["status_tab_id"], "321")

    def test_extension_command_uses_resolved_session_from_fallback_context(self):
        default_ctx = UserContext("__default__")
        token_ctx = UserContext("agent-token")
        default_ctx.sessions = {
            "edge-client:321": Session(
                "edge-client:321",
                {"url": "https://fixture.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "321"},
            ),
            "edge-client:100": Session(
                "edge-client:100",
                {"url": "https://first.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "100"},
            ),
        }
        calls = []

        class FakeDriver:
            def get_context(self, token=None):
                return token_ctx if token == "agent-token" else default_ctx

            def get_all_sessions(self, token=None):
                return default_ctx.get_all_active_sessions()

            def get_ext_ws_transport_session_id(self, token=None, client_id=None):
                return "edge-client:100"

            def execute_js(self, code, timeout=15, token=None, group_status=None, session_id=None, status_tab_id=None):
                calls.append({"code": json.loads(code), "session_id": session_id, "status_tab_id": status_tab_id})
                return {"data": "ok"}

        result = actions.extension_command(
            FakeDriver(),
            {"cmd": "tabs", "method": "close"},
            tab_id="edge-client:321",
            token="agent-token",
        )

        self.assertEqual(result, "ok")
        self.assertEqual(calls[0]["code"]["tabId"], 321)
        self.assertEqual(calls[0]["status_tab_id"], "321")

    def test_extension_command_falls_back_to_normalize_for_unknown_tab_identifier(self):
        ctx = UserContext("__default__")
        calls = []

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def get_all_sessions(self, token=None):
                return []

            def get_ext_ws_transport_session_id(self, token=None, client_id=None):
                return None

            def execute_js(self, code, timeout=15, token=None, group_status=None, session_id=None, status_tab_id=None):
                calls.append({"code": json.loads(code), "session_id": session_id, "status_tab_id": status_tab_id})
                return {"data": "ok"}

        result = actions.extension_command(FakeDriver(), {"cmd": "tabs", "method": "switch"}, tab_id="999")

        self.assertEqual(result, "ok")
        self.assertEqual(calls[0]["code"]["tabId"], 999)
        self.assertEqual(calls[0]["status_tab_id"], "999")


if __name__ == "__main__":
    unittest.main()
