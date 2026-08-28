import json
import re
import socket
import sys
import time
import unittest
from pathlib import Path

import requests

from omnibot import actions
from omnibot.TMWebDriver import Session, TMWebDriver, UserContext


class _LineCollector:
    """Lazy accessor for stderr-captured log lines."""
    def __init__(self, get_lines):
        self._get = get_lines
    def __iter__(self):
        return iter(self._get())
    def __len__(self):
        return len(self._get())
    def __contains__(self, item):
        return item in "\n".join(self._get())
    def __str__(self):
        return "\n".join(self._get())


ROOT = Path(__file__).resolve().parents[2]
BACKGROUND_JS = ROOT / "browser-extension" / "background.js"


def _free_http_base_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    http_port = sock.getsockname()[1]
    sock.close()
    return http_port - 1, http_port


class ExecuteJsStatusTargetTest(unittest.TestCase):
    def test_execute_js_payload_separates_transport_tab_and_status_tab(self):
        sent_payloads = []

        class FakeWs:
            def send_message(self, payload):
                sent_payloads.append(json.loads(payload))

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        session = Session("200", {"url": "https://transport.example", "title": "", "type": "ext_ws"}, FakeWs())
        driver._default_ctx.sessions["200"] = session

        exec_id_holder = {}

        def fake_time():
            return 1000

        original_time = time.time
        original_sleep = time.sleep
        try:
            time.time = fake_time

            def fake_sleep(_seconds):
                exec_id = sent_payloads[0]["id"]
                exec_id_holder["id"] = exec_id
                driver._default_ctx.results[exec_id] = {"success": True, "data": "ok", "newTabs": []}

            time.sleep = fake_sleep
            result = driver.execute_js(
                "return 1;",
                session_id="200",
                group_status="💤 2s",
                status_tab_id="555",
            )
        finally:
            time.time = original_time
            time.sleep = original_sleep

        self.assertEqual(result, {"data": "ok"})
        self.assertEqual(len(sent_payloads), 1)
        self.assertEqual(sent_payloads[0]["tabId"], 200)
        self.assertEqual(sent_payloads[0]["statusTabId"], 555)
        self.assertEqual(sent_payloads[0]["groupStatus"], "💤 2s")
        self.assertEqual(exec_id_holder["id"], sent_payloads[0]["id"])

    def test_execute_js_group_status_defaults_status_tab_to_session_tab(self):
        sent_payloads = []

        class FakeWs:
            def send_message(self, payload):
                sent_payloads.append(json.loads(payload))

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        session = Session("edge-client:321", {"url": "https://target.example", "title": "", "type": "ext_ws", "client_id": "edge-client", "tab_id": "321"}, FakeWs())
        driver._default_ctx.sessions["edge-client:321"] = session

        original_time = time.time
        original_sleep = time.sleep
        try:
            time.time = lambda: 1000

            def fake_sleep(_seconds):
                exec_id = sent_payloads[0]["id"]
                driver._default_ctx.results[exec_id] = {"success": True, "data": "ok", "newTabs": []}

            time.sleep = fake_sleep
            driver.execute_js(
                "return 1;",
                session_id="edge-client:321",
                group_status="⚡ 执行中",
            )
        finally:
            time.time = original_time
            time.sleep = original_sleep

        self.assertEqual(sent_payloads[0]["tabId"], 321)
        self.assertEqual(sent_payloads[0]["statusTabId"], 321)
        self.assertEqual(sent_payloads[0]["groupStatus"], "⚡ 执行中")

    def test_update_tab_group_uses_target_as_status_tab_when_transport_differs(self):
        calls = []
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        driver._default_ctx.sessions["200"] = Session("200", {"url": "https://transport.example", "title": "", "type": "ext_ws"})

        def fake_transport_session_id(target_tab_id, token=None):
            self.assertEqual(target_tab_id, "555")
            return "200"

        def fake_execute_js(code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
            calls.append({
                "code": code,
                "timeout": timeout,
                "session_id": session_id,
                "token": token,
                "group_status": group_status,
                "status_tab_id": status_tab_id,
            })
            return {"data": {"ok": True}}

        driver._transport_session_id = fake_transport_session_id
        driver.execute_js = fake_execute_js

        result = driver.update_tab_group("555", "💤 2s", token="request-token")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["session_id"], "200")
        self.assertEqual(calls[0]["status_tab_id"], "555")
        self.assertEqual(calls[0]["group_status"], "💤 2s")
        self.assertEqual(calls[0]["token"], "request-token")
        payload = json.loads(calls[0]["code"])
        self.assertEqual(payload, {"cmd": "tabGroups", "method": "group", "tabId": 555, "title": "💤 2s"})


class ExtensionCommandStatusTargetTest(unittest.TestCase):
    def test_extension_command_passes_target_as_status_tab_when_using_transport(self):
        transport_session = Session("200", {"url": "https://transport.example", "title": "", "type": "ext_ws"})
        ctx = type("Ctx", (), {
            "sessions": {"200": transport_session},
        })()
        calls = []

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def get_ext_ws_transport_session_id(self, token=None, client_id=None):
                return "200"

            def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
                calls.append({
                    "code": code,
                    "session_id": session_id,
                    "group_status": group_status,
                    "status_tab_id": status_tab_id,
                })
                return {"data": {"ok": True}}

        cmd = {"cmd": "tabGroups", "method": "group", "tabId": 555, "title": "💤 2s"}
        result = actions.extension_command(
            FakeDriver(),
            cmd,
            tab_id="555",
            group_status="💤 2s",
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["session_id"], "200")
        self.assertEqual(calls[0]["status_tab_id"], "555")
        self.assertEqual(calls[0]["group_status"], "💤 2s")
        payload = json.loads(calls[0]["code"])
        self.assertEqual(payload["tabId"], 555)


class CompositeTabIdResolutionTest(unittest.TestCase):
    def test_raw_tab_id_from_canonical_session_id(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        session = Session(
            "edge-client:321",
            {
                "url": "https://openai.com/",
                "title": "OpenAI",
                "type": "ext_ws",
                "client_id": "edge-client",
                "tab_id": "321",
            },
        )
        driver._default_ctx.sessions["edge-client:321"] = session

        self.assertEqual(driver._raw_tab_id("edge-client:321"), "321")

    def test_raw_tab_id_accepts_plain_numeric_id(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")

        self.assertEqual(driver._raw_tab_id("321"), "321")

    def test_raw_tab_id_accepts_int_id(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")

        self.assertEqual(driver._raw_tab_id(321), "321")

    def test_update_tab_group_uses_raw_tab_id_for_canonical_session(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        session = Session(
            "edge-client:321",
            {
                "url": "https://openai.com/",
                "title": "OpenAI",
                "type": "ext_ws",
                "client_id": "edge-client",
                "tab_id": "321",
            },
        )
        driver._default_ctx.sessions["edge-client:321"] = session
        calls = []

        def fake_execute_js(code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
            calls.append({
                "code": json.loads(code),
                "session_id": session_id,
                "group_status": group_status,
                "status_tab_id": status_tab_id,
            })
            return {"data": {"ok": True}}

        driver.execute_js = fake_execute_js

        result = driver.update_tab_group("edge-client:321", "💤 等待中")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(calls[0]["code"]["tabId"], 321)
        self.assertEqual(calls[0]["status_tab_id"], "321")
        self.assertEqual(calls[0]["group_status"], "💤 等待中")

    def test_remove_tab_group_uses_raw_tab_id_for_canonical_session(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        session = Session(
            "edge-client:321",
            {
                "url": "https://openai.com/",
                "title": "OpenAI",
                "type": "ext_ws",
                "client_id": "edge-client",
                "tab_id": "321",
            },
        )
        driver._default_ctx.sessions["edge-client:321"] = session
        calls = []

        def fake_execute_js(code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
            calls.append({"code": json.loads(code), "session_id": session_id, "group_status": group_status, "status_tab_id": status_tab_id})
            return {"data": {"ok": True}}

        driver.execute_js = fake_execute_js

        driver.remove_tab_group("edge-client:321")

        self.assertEqual(calls[0]["code"]["tabId"], 321)
        self.assertIsNone(calls[0]["group_status"])
        self.assertIsNone(calls[0]["status_tab_id"])

    def test_close_tab_uses_raw_tab_id_for_canonical_session(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        session = Session(
            "edge-client:321",
            {
                "url": "https://openai.com/",
                "title": "OpenAI",
                "type": "ext_ws",
                "client_id": "edge-client",
                "tab_id": "321",
            },
        )
        driver._default_ctx.sessions["edge-client:321"] = session
        calls = []

        def fake_execute_js(code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
            calls.append({"code": json.loads(code), "session_id": session_id})
            return {"data": {"ok": True}}

        driver.execute_js = fake_execute_js

        driver.close_tab("edge-client:321")

        self.assertEqual(calls[0]["code"]["tabId"], 321)


class RemoteExecuteJsStatusTargetTest(unittest.TestCase):
    def test_link_route_forwards_status_tab_id_to_execute_js(self):
        base_port, http_port = _free_http_base_port()
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.host = "127.0.0.1"
        driver.port = base_port
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        calls = []

        def fake_execute_js(code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
            calls.append({
                "code": code,
                "timeout": timeout,
                "session_id": session_id,
                "token": token,
                "group_status": group_status,
                "status_tab_id": status_tab_id,
            })
            return {"data": "ok"}

        driver.execute_js = fake_execute_js
        driver.start_http_server()

        deadline = time.time() + 3
        last_error = None
        while time.time() < deadline:
            try:
                response = requests.post(
                    f"http://127.0.0.1:{http_port}/link",
                    json={
                        "cmd": "execute_js",
                        "sessionId": "200",
                        "code": "return 1;",
                        "timeout": "7",
                        "groupStatus": "💤 2s",
                        "statusTabId": "555",
                    },
                    timeout=1,
                )
                if response.status_code == 200:
                    break
                last_error = RuntimeError(f"unexpected status {response.status_code}")
                time.sleep(0.05)
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(0.05)
        else:
            raise AssertionError(f"HTTP server did not start: {last_error}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["session_id"], "200")
        self.assertEqual(calls[0]["group_status"], "💤 2s")
        self.assertEqual(calls[0]["status_tab_id"], "555")


class BackgroundStatusTargetContractTest(unittest.TestCase):
    def test_background_uses_status_tab_id_for_group_status_ui(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        start = source.find("if (data.groupStatus && data.tabId) {")
        end = source.find("if (data.id && data.code) {", start)

        self.assertNotEqual(start, -1, "groupStatus handling block not found")
        self.assertNotEqual(end, -1, "next websocket code block not found")
        body = source[start:end]
        self.assertIn("data.statusTabId", body)
        self.assertIn("statusTabId", body)
        self.assertIn("handleExtMessage({cmd:'tabGroups', method:'group', tabId: statusTabId", body)
        self.assertIn("sendOperationGlow(statusTabId", body)

    def test_background_ungroups_only_target_tab_before_auto_close(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        ungroup_block = re.search(
            r"else if \(msg\.method === 'ungroup'\) \{(?P<body>.*?)\n\s*\}",
            source,
            re.DOTALL,
        )

        self.assertIsNotNone(ungroup_block, "tabGroups ungroup block not found")
        body = ungroup_block.group("body")
        self.assertIn("await cleanupTabStatus(tabId)", body)
        self.assertIn("await chrome.tabs.ungroup(tabId)", source)
        self.assertNotIn("chrome.tabs.query({ groupId: tab.groupId, windowId: tab.windowId })", body)
        self.assertNotIn("tabs.map(t => t.id)", body)

    def test_background_isolates_target_tab_before_group_status_update(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        group_block = re.search(
            r"if \(msg\.method === 'group'\) \{(?P<body>.*?)\n\s*\} else if \(msg\.method === 'ungroup'\)",
            source,
            re.DOTALL,
        )

        self.assertIsNotNone(group_block, "tabGroups group block not found")
        body = group_block.group("body")
        self.assertIn("callChromeApi(chrome.tabs.query, [{ groupId: tab.groupId, windowId: tab.windowId }], chrome.tabs)", body)
        self.assertIn("groupTabs.length > 1", body)
        self.assertIn("await callChromeApi(chrome.tabs.ungroup, [tabId], chrome.tabs)", body)
        self.assertIn("isOmnibotStatusTitle(group.title)", body)
        self.assertIn("groupTabs.map(item => item.id)", body)
        self.assertIn("await callChromeApi(chrome.tabs.group, [{ tabIds: [tabId] }], chrome.tabs)", body)

    def test_background_ungroup_hides_operation_glow_without_regrouping(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")

        ungroup_block = re.search(
            r"else if \(msg\.method === 'ungroup'\) \{(?P<body>.*?)\n\s*\}\n\s*return \{ ok: false",
            source,
            re.DOTALL,
        )

        self.assertIsNotNone(ungroup_block, "tabGroups ungroup block not found")
        body = ungroup_block.group("body")
        self.assertIn("await cleanupTabStatus(tabId)", body)
        self.assertIn("await chrome.tabs.ungroup(tabId)", source)
        self.assertIn("sendOperationGlow(tabId, 'hide'", source)
        self.assertNotIn("method:'group'", body)
        self.assertNotIn('method: "group"', body)

    def test_background_status_tab_id_takes_precedence_over_transport_tab_id(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        start = source.find("if (data.groupStatus && data.tabId) {")
        end = source.find("if (data.id && data.code) {", start)
        self.assertNotEqual(start, -1, "groupStatus handling block not found")
        self.assertNotEqual(end, -1, "next websocket code block not found")
        body = source[start:end]

        # The status target MUST be derived from statusTabId with tabId only as fallback,
        # so that when Python pins statusTabId the badge lands on the target, not the transport.
        self.assertIn("data.statusTabId ?? data.tabId", body,
                      "background.js must compute statusTabId as `data.statusTabId ?? data.tabId` "
                      "(target wins; transport tab id is fallback only)")


class ScheduleTabCleanupTest(unittest.TestCase):
    def test_transient_status_title_detection_covers_operation_and_countdown(self):
        self.assertTrue(TMWebDriver._is_transient_tab_status_title("执行中"))
        self.assertTrue(TMWebDriver._is_transient_tab_status_title("⚡ 执行中"))
        self.assertTrue(TMWebDriver._is_transient_tab_status_title("3s"))
        self.assertFalse(TMWebDriver._is_transient_tab_status_title("工作资料"))

    def test_ext_ready_reconciliation_cleans_only_orphaned_status_groups(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        for raw_id in ("101", "102", "103"):
            sid = f"edge-client:{raw_id}"
            driver._default_ctx.sessions[sid] = Session(
                sid,
                {
                    "url": f"https://example.com/{raw_id}",
                    "title": "",
                    "type": "ext_ws",
                    "client_id": "edge-client",
                    "tab_id": raw_id,
                },
                object(),
            )
        driver._default_ctx.status_cleanup_deadlines["edge-client:102"] = time.time() + 60
        titles = {"101": "执行中", "102": "点击中", "103": "工作资料"}
        cleaned = []

        def fake_execute_js(code, **kwargs):
            raw_id = str(json.loads(code)["tabId"])
            return {"data": {"grouped": True, "title": titles[raw_id]}}

        driver.execute_js = fake_execute_js
        driver.cleanup_tab_status = lambda tab_id, token=None: cleaned.append(tab_id)

        driver._reconcile_stale_status_tabs(
            [
                {"id": 101, "groupId": 11},
                {"id": 102, "groupId": 12},
                {"id": 103, "groupId": 13},
                {"id": 104, "groupId": -1},
            ],
            "edge-client",
            token="__default__",
        )

        self.assertEqual(cleaned, ["edge-client:101"])

    def test_cleanup_tab_status_sends_unified_cleanup_command(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        calls = []

        def fake_execute_js(code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
            calls.append({
                "code": json.loads(code),
                "timeout": timeout,
                "session_id": session_id,
                "group_status": group_status,
                "status_tab_id": status_tab_id,
            })
            return {"data": {"ok": True}}

        driver.execute_js = fake_execute_js
        driver._transport_session_id = lambda tab_id, token=None: "edge-client:321"

        driver.cleanup_tab_status("edge-client:555", token="request-token")

        self.assertEqual(calls, [{
            "code": {"cmd": "tabStatus", "method": "cleanup", "tabId": 555},
            "timeout": 5,
            "session_id": "edge-client:321",
            "group_status": None,
            "status_tab_id": None,
        }])

    def test_cleanup_tab_status_keeps_retry_deadline_when_command_times_out(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        tab_id = "edge-client:555"
        driver._default_ctx.status_cleanup_deadlines[tab_id] = 123.0

        def fake_execute_js(
            code,
            timeout=15,
            session_id=None,
            token=None,
            group_status=None,
            status_tab_id=None,
        ):
            return {"result": "No response data in 5s (no ACK, script may not have been delivered)"}

        driver.execute_js = fake_execute_js
        driver._transport_session_id = lambda tab_id, token=None: "edge-client:321"

        driver.cleanup_tab_status(tab_id, token="request-token")

        self.assertIn(tab_id, driver._default_ctx.status_cleanup_deadlines)

    def test_status_sweeper_does_not_expire_tab_owned_by_close_schedule(self):
        ctx = UserContext("__default__")
        ctx.status_cleanup_deadlines["managed-tab"] = 10.0
        ctx.status_cleanup_deadlines["orphan-tab"] = 10.0
        ctx.grouped_tabs["managed-tab"] = []

        self.assertEqual(TMWebDriver._expired_status_tabs(ctx, 11.0), ["orphan-tab"])

    def test_close_tab_treats_already_gone_as_success(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        driver._raw_tab_id = lambda tab_id, token=None: "555"
        driver._transport_session_id = lambda tab_id, token=None: "edge-client:321"

        def fake_execute_js(*args, **kwargs):
            raise Exception("No tab with id: 555.")

        driver.execute_js = fake_execute_js

        self.assertTrue(driver.close_tab("edge-client:555"))

    def test_schedule_cleanup_uses_shorter_timeout_for_existing_tabs(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        scheduled = []

        driver._schedule_tab_close = lambda tab_id, timeout=60, token=None, close=True: scheduled.append({
            "tab_id": tab_id,
            "timeout": timeout,
            "close": close,
        })

        actions._schedule_tab_cleanup_after_operation(driver, driver._default_ctx, "existing-tab")

        self.assertEqual(scheduled, [{"tab_id": "existing-tab", "timeout": 8, "close": False}])

    def test_schedule_tab_close_with_close_false_ungroups_without_closing(self):
        callbacks = []

        class FakeTimer:
            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.cancelled = False
                self.daemon = False

            def start(self):
                callbacks.append(self)

            def cancel(self):
                self.cancelled = True

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        driver._default_ctx.tool_created_tabs.add("user-tab")
        cleaned = []
        closed = []

        driver.cleanup_tab_status = lambda tab_id, token=None: cleaned.append(tab_id)
        driver.close_tab = lambda tab_id, token=None: closed.append(tab_id)
        driver.update_tab_group = lambda tab_id, group_name, token=None: None

        timer_globals = driver._schedule_tab_close.__globals__
        original_timer = timer_globals["Timer"]
        try:
            timer_globals["Timer"] = FakeTimer
            driver._schedule_tab_close("user-tab", timeout=8, close=False)
        finally:
            timer_globals["Timer"] = original_timer

        self.assertEqual([timer.interval for timer in callbacks], [8])

        callbacks[-1].function()

        self.assertEqual(cleaned, ["user-tab"])
        self.assertEqual(closed, [])
        self.assertIn("user-tab", driver._default_ctx.tool_created_tabs)

    def test_tabs_update_does_not_cancel_tool_created_tab_close_timers(self):
        source = (ROOT / "src" / "omnibot" / "TMWebDriver.py").read_text(encoding="utf-8")
        disconnected_block = source[source.find("if sess.type == 'ext_ws'"):source.find("if disconnected:")]

        self.assertIn("if sid not in ctx.tool_created_tabs:", disconnected_block)
        self.assertIn("driver._cancel_tab_status_timers(sid, token=token)", disconnected_block)


class SimphtmlStatusTargetTest(unittest.TestCase):
    def test_get_main_block_forwards_status_tab_id_to_execute_js(self):
        from omnibot import simphtml

        calls = []

        class FakeDriver:
            def execute_js(self, code, timeout=15, session_id=None, token=None,
                           group_status=None, status_tab_id=None):
                calls.append({
                    "session_id": session_id,
                    "group_status": group_status,
                    "status_tab_id": status_tab_id,
                })
                return {"data": "<html></html>"}

        simphtml.get_main_block(
            FakeDriver(),
            group_status="读取中",
            session_id="edge-client:321",
            status_tab_id="321",
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["session_id"], "edge-client:321")
        self.assertEqual(calls[0]["group_status"], "读取中")
        self.assertEqual(calls[0]["status_tab_id"], "321")

    def test_get_html_forwards_status_tab_id_into_get_main_block(self):
        from omnibot import simphtml

        calls = []

        class FakeDriver:
            def execute_js(self, code, timeout=15, session_id=None, token=None,
                           group_status=None, status_tab_id=None):
                calls.append({"status_tab_id": status_tab_id})
                if "findMainList" in code:
                    return {"data": []}
                return {"data": "<html></html>"}

        simphtml.get_html(
            FakeDriver(),
            group_status="读取中",
            session_id="edge-client:321",
            status_tab_id="321",
        )

        self.assertTrue(calls, "get_html did not call execute_js")
        self.assertTrue(all(c["status_tab_id"] == "321" for c in calls),
                        f"expected all calls to carry status_tab_id=321, got {calls}")

    def test_execute_js_rich_forwards_status_tab_id_to_main_execute_js_call(self):
        import omnibot.simphtml as simphtml
        from omnibot.simphtml import execute_js_rich

        calls = []

        class FakeDriver:
            def __init__(self):
                self.multi_user = False

            def get_context(self, token=None):
                return None

            def get_session_dict(self, token=None):
                return {}

            def execute_js(self, code, timeout=15, session_id=None, token=None,
                           group_status=None, status_tab_id=None):
                calls.append({
                    "group_status": group_status,
                    "status_tab_id": status_tab_id,
                    "is_main": "return" in code and "optHTML" not in code,
                })
                return {"data": "ok"}

        rr = execute_js_rich(
            "return document.title;",
            FakeDriver(),
            no_monitor=True,
            group_status="执行中",
            session_id="edge-client:321",
            status_tab_id="321",
        )

        main_calls = [c for c in calls if c["is_main"]]
        self.assertTrue(main_calls, "execute_js_rich did not issue a main execute_js call")
        self.assertEqual(main_calls[0]["group_status"], "执行中")
        self.assertEqual(main_calls[0]["status_tab_id"], "321",
                         "execute_js_rich must pin status_tab_id to the target, not the transport")


class ActionsStatusTargetTest(unittest.TestCase):
    def test_execute_js_action_passes_target_status_tab_id_to_execute_js_rich(self):
        # NOTE: actions.execute_js calls `importlib.reload(simphtml)` right before
        # invoking execute_js_rich, which re-executes the module body and resets
        # any monkeypatch on `simphtml.execute_js_rich`. So we cannot spy on
        # execute_js_rich directly. Instead we capture at FakeDriver.execute_js —
        # the downstream call that execute_js_rich forwards `status_tab_id` to
        # (wired in Task 3). The main user-script call is filtered by matching
        # the script text, and we assert the pinned status_tab_id flows through.
        from omnibot.actions import execute_js as execute_js_action

        USER_SCRIPT = "return document.title;"
        main_calls = []

        class FakeSession:
            def __init__(self, tab_id, client_id):
                self.tab_id = tab_id
                self.client_id = client_id
                self.type = "ext_ws"
                self.created_by_tool = False
                self.info = {"url": "https://target.example"}
            def is_active(self):
                return True

        class FakeDriver:
            def __init__(self):
                self.multi_user = False
                self._default_ctx = UserContext("__default__")
                self._default_ctx.sessions["edge-client:321"] = FakeSession("321", "edge-client")
            def get_context(self, token=None):
                return self._default_ctx
            def get_all_sessions(self, token=None):
                return [{"id": "edge-client:321", "tab_id": "321", "client_id": "edge-client", "type": "ext_ws"}]
            def get_session_dict(self, token=None):
                return {}
            def _cancel_tab_close(self, tab_id, token=None):
                pass
            def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=True):
                pass
            def _raw_tab_id(self, tab_id, token=None):
                raw = str(tab_id)
                session = self._default_ctx.sessions.get(raw)
                if session:
                    return session.tab_id
                if ":" in raw:
                    return raw.rsplit(":", 1)[1]
                return raw
            def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
                if code == USER_SCRIPT:
                    main_calls.append({
                        "session_id": session_id,
                        "group_status": group_status,
                        "status_tab_id": status_tab_id,
                    })
                return {"data": "ok", "newTabs": []}

        rr = execute_js_action(FakeDriver(), USER_SCRIPT, switch_tab_id="edge-client:321")

        self.assertTrue(main_calls, "execute_js_rich did not issue the main execute_js call for the user script")
        self.assertEqual(main_calls[0]["session_id"], "edge-client:321")
        self.assertIsNotNone(main_calls[0]["status_tab_id"],
                             "actions.execute_js must pin status_tab_id so the badge targets the operated tab, not the transport")
        self.assertEqual(main_calls[0]["status_tab_id"], "321")

    def test_read_action_executes_with_status_tab_id_pinned_to_target(self):
        import omnibot.actions as actions
        from omnibot.actions import read as read_action

        class FakeSession:
            def __init__(self, tab_id, client_id):
                self.tab_id = tab_id
                self.client_id = client_id
                self.type = "ext_ws"
                self.created_by_tool = False
                self.info = {"url": "https://target.example"}
            def is_active(self):
                return True

        calls = []
        class FakeDriver:
            def __init__(self):
                self.multi_user = False
                self._default_ctx = UserContext("__default__")
                self._default_ctx.sessions["edge-client:321"] = FakeSession("321", "edge-client")
            def get_context(self, token=None):
                return self._default_ctx
            def get_all_sessions(self, token=None):
                return [{"id": "edge-client:321", "tab_id": "321", "client_id": "edge-client", "type": "ext_ws"}]
            def _cancel_tab_close(self, tab_id, token=None):
                pass
            def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=True):
                pass
            def _raw_tab_id(self, tab_id, token=None):
                return "321"
            def update_tab_group(self, tab_id, name, token=None):
                pass
            def execute_js(self, code, timeout=15, session_id=None, token=None,
                           group_status=None, status_tab_id=None):
                calls.append({"group_status": group_status, "status_tab_id": status_tab_id})
                return {"data": "<html><body>x</body></html>"}

        read_action(FakeDriver(), switch_tab_id="edge-client:321", screens=1)

        self.assertTrue(calls, "read did not call execute_js")
        # Even when group_status is None (no badge during read), the target pin must be present
        # so a future in-progress badge cannot leak to the transport tab.
        self.assertTrue(all(c["status_tab_id"] == "321" for c in calls),
                        f"read must pin status_tab_id=321 on every execute_js call, got {calls}")


class TransportSelectionStabilityTest(unittest.TestCase):
    def _build_driver(self, sessions):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        for sid, info in sessions.items():
            driver._default_ctx.sessions[sid] = Session(sid, info)
        return driver

    def test_transport_selection_prefers_target_session_when_active_ext_ws(self):
        sessions = {
            "clientA:111": {"url": "https://unrelated.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "111"},
            "clientA:222": {"url": "https://target.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "222"},
        }
        driver = self._build_driver(sessions)
        # Target is itself an active ext_ws session -> must be used directly.
        self.assertEqual(driver._transport_session_id("clientA:222"), "clientA:222")

    def test_transport_selection_avoids_tab_under_active_status_management(self):
        sessions = {
            # tokenmp tab — earliest inserted, currently being badged by another operation.
            "clientA:111": {"url": "https://tokenmp.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "111"},
            # a neutral background tab, inserted later.
            "clientA:333": {"url": "https://neutral.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "333"},
        }
        driver = self._build_driver(sessions)
        # Simulate tokenmp being under active status management.
        driver._default_ctx.status_cleanup_deadlines["clientA:111"] = time.time() + 60

        # Target is the JD tab (not connected as ext_ws here) — must NOT route through tokenmp (111).
        chosen = driver._transport_session_id("clientA:999")
        self.assertEqual(chosen, "clientA:333",
                         "transport selection must avoid tabs under active status management; "
                         f"got {chosen}")

    def test_transport_selection_avoids_tab_under_countdown_timer(self):
        sessions = {
            "clientA:111": {"url": "https://tokenmp.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "111"},
            "clientA:333": {"url": "https://neutral.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "333"},
        }
        driver = self._build_driver(sessions)
        # tokenmp has a live countdown timer.
        driver._default_ctx.grouped_tabs["clientA:111"] = ["placeholder-timer"]

        chosen = driver._transport_session_id("clientA:999")
        self.assertEqual(chosen, "clientA:333",
                         f"transport selection must avoid tabs with active countdown timers; got {chosen}")

    def test_transport_selection_prefers_same_client_transport_when_target_has_client_id(self):
        sessions = {
            # Target is a known session but NOT ext_ws (http type) — so it can't be a transport.
            "clientA:999": {"url": "https://target.example", "type": "http", "client_id": "clientA", "tab_id": "999"},
            # Same-client transport, but under status management (should be avoided).
            "clientA:111": {"url": "https://tokenmp.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "111"},
            # Same-client transport, neutral.
            "clientA:222": {"url": "https://neutral-a.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "222"},
            # Different-client transport, neutral.
            "clientB:333": {"url": "https://neutral-b.example", "type": "ext_ws", "client_id": "clientB", "tab_id": "333"},
        }
        driver = self._build_driver(sessions)
        driver._default_ctx.status_cleanup_deadlines["clientA:111"] = time.time() + 60

        chosen = driver._transport_session_id("clientA:999")
        # Must pick the same-client neutral transport (222), not the avoided one (111),
        # and not the different-client one (333).
        self.assertEqual(chosen, "clientA:222",
                         f"transport selection must prefer same-client non-avoided transport; got {chosen}")

    def test_transport_selection_falls_back_to_any_client_ignoring_avoid_as_last_resort(self):
        sessions = {
            # Target is a known http session with clientA.
            "clientA:999": {"url": "https://target.example", "type": "http", "client_id": "clientA", "tab_id": "999"},
            # The ONLY ext_ws transport is a different client, and it's under status management.
            "clientB:111": {"url": "https://only-transport.example", "type": "ext_ws", "client_id": "clientB", "tab_id": "111"},
        }
        driver = self._build_driver(sessions)
        driver._default_ctx.status_cleanup_deadlines["clientB:111"] = time.time() + 60

        chosen = driver._transport_session_id("clientA:999")
        # No same-client transport exists; the only transport is avoided. Last resort must
        # still return it (better to route through an avoided tab than fail the command entirely).
        self.assertEqual(chosen, "clientB:111",
                         f"last-resort fallback must return any available transport; got {chosen}")


class CdpStatusTargetContractTest(unittest.TestCase):
    def test_send_cdp_pins_status_tab_id_to_target_raw_tab_id(self):
        from omnibot import cdp

        calls = []
        class FakeDriver:
            def _raw_tab_id(self, tab_id, token=None):
                return "555"
            def execute_js(self, payload, timeout=15, session_id=None, token=None,
                           group_status=None, status_tab_id=None):
                calls.append({
                    "payload": payload,
                    "group_status": group_status,
                    "status_tab_id": status_tab_id,
                })
                return {"data": {"ok": True, "data": {}}}

        cdp.send_cdp(FakeDriver(), "edge-client:555", "Page.captureScreenshot",
                     {}, group_status="截图中")

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["payload"]["tabId"], 555)
        self.assertEqual(calls[0]["status_tab_id"], 555,
                         "send_cdp must pin status_tab_id to the target raw tab id, not the transport")
        self.assertEqual(calls[0]["group_status"], "截图中")


class RoutingObservabilityTest(unittest.TestCase):
    def _capture_tlog(self):
        """Capture _tlog output by redirecting stderr.

        Previous versions patched the module-level _tlog function, but that
        breaks when earlier tests cause module reimports that leave the
        TMWebDriver class with stale __globals__ references.  Redirecting
        stderr is immune to that class of pollution.
        """
        import io
        import omnibot.TMWebDriver as tm

        buf = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = buf
        original_tlog = tm._tlog

        def restore():
            sys.stderr = original_stderr
            tm._tlog = original_tlog

        def get_lines():
            sys.stderr = original_stderr
            raw = buf.getvalue()
            sys.stderr = buf
            return [ln for ln in raw.splitlines() if ln.strip()]

        return _LineCollector(get_lines), restore

    def _assert_in_log(self, needle, collector, label):
        lines = collector()
        joined = str(lines)
        self.assertIn(needle, joined, f"{label}; log was:\n{joined}")

    def test_execute_js_logs_transport_and_status_target_when_group_status_set(self):
        import omnibot.TMWebDriver as tm

        class FakeWs:
            def __init__(self):
                self.captured_id = None
            def send_message(self, payload):
                self.captured_id = json.loads(payload)["id"]

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        fake_ws = FakeWs()
        driver._default_ctx.sessions["200"] = Session(
            "200", {"url": "https://transport.example", "type": "ext_ws", "tab_id": "200"}, fake_ws)

        original_time = time.time
        original_sleep = time.sleep
        lines, restore = self._capture_tlog()
        try:
            time.time = lambda: 1000
            def seed_result(_s):
                driver._default_ctx.results[fake_ws.captured_id] = {"success": True, "data": "ok", "newTabs": []}
            time.sleep = seed_result
            driver.execute_js("return 1;", session_id="200",
                              group_status="执行中", status_tab_id="555")
        finally:
            time.time = original_time
            time.sleep = original_sleep
            restore()

        joined = str(lines)
        self.assertIn("transport=200", joined,
                       f"execute_js must log the chosen transport session; log was:\n{joined}")
        self.assertIn("status_target=555", joined,
                       f"execute_js must log the status target so badge routing is diagnosable; log was:\n{joined}")
        self.assertIn("group_status=执行中", joined,
                       f"execute_js must log the group_status label; log was:\n{joined}")

    def test_update_tab_group_logs_success_with_target_and_label(self):
        import omnibot.TMWebDriver as tm

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        driver._default_ctx.sessions["200"] = Session(
            "200", {"url": "https://transport.example", "type": "ext_ws", "tab_id": "200"})

        driver._transport_session_id = lambda tab_id, token=None: "200"
        driver._raw_tab_id = lambda tab_id, token=None: "555"
        def fake_execute_js(code, timeout=15, session_id=None, token=None,
                            group_status=None, status_tab_id=None):
            return {"data": {"ok": True}}
        driver.execute_js = fake_execute_js

        lines, restore = self._capture_tlog()
        try:
            driver.update_tab_group("555", "读取中", token="jd")
        finally:
            restore()

        joined = str(lines)
        self.assertIn("status_target=555", joined,
                      f"update_tab_group must log the status target on success; log was:\n{joined}")
        self.assertIn("label=读取中", joined,
                      f"update_tab_group must log the badge label on success; log was:\n{joined}")
        self.assertIn("transport=", joined,
                      f"update_tab_group must log the transport identifier on success; log was:\n{joined}")
        self.assertNotIn("update_tab_group failed", joined,
                         "a successful call must not log the failure line")

    def test_execute_js_does_not_log_routing_when_group_status_is_none(self):
        import omnibot.TMWebDriver as tm

        class FakeWs:
            def __init__(self):
                self.captured_id = None
            def send_message(self, payload):
                self.captured_id = json.loads(payload)["id"]

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        fake_ws = FakeWs()
        driver._default_ctx.sessions["200"] = Session(
            "200", {"url": "https://transport.example", "type": "ext_ws", "tab_id": "200"}, fake_ws)

        original_time = time.time
        original_sleep = time.sleep
        lines, restore = self._capture_tlog()
        try:
            time.time = lambda: 1000
            def seed_result(_s):
                driver._default_ctx.results[fake_ws.captured_id] = {"success": True, "data": "ok", "newTabs": []}
            time.sleep = seed_result
            driver.execute_js("return 1;", session_id="200")  # no group_status
        finally:
            time.time = original_time
            time.sleep = original_sleep
            restore()

        joined = str(lines)
        self.assertNotIn("execute_js routing", joined,
                         f"execute_js must NOT log routing when group_status is None; log was:\n{joined}")


class DuplicateClientRegistrationTest(unittest.TestCase):
    def test_tabs_update_disconnects_other_client_session_for_same_raw_tab_id(self):
        # We test the pure-Python reconciliation helper directly to avoid spinning up
        # a real WebSocket server.
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        # Client A already has the JD tab.
        driver._default_ctx.sessions["clientA:555"] = Session(
            "clientA:555",
            {"url": "https://jd.example", "type": "ext_ws", "client_id": "clientA", "tab_id": "555"},
        )
        # Client B now reports the same raw tab id 555.
        driver._reconcile_cross_client_duplicates(
            reporting_client_id="clientB",
            raw_tab_ids={"555"},
            token="__default__",
        )
        sess_a = driver._default_ctx.sessions["clientA:555"]
        self.assertFalse(sess_a.is_active(),
                         "When two extensions report the same raw tab id, the older client's "
                         "session must be demoted so transport selection is deterministic.")


if __name__ == "__main__":
    unittest.main()
