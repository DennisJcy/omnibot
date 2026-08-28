import json
import threading
import time
import unittest
from types import SimpleNamespace

import omnibot.TMWebDriver as tmwebdriver_module
from omnibot import actions
from omnibot.TMWebDriver import TMWebDriver, Session, UserContext


def fire_serial_countdown(fake_timer, timeout):
    """Run the scheduled 10..1 countdown and its terminal cleanup callback."""
    countdown_timer = next(t for t in fake_timer.instances if t.interval == timeout - 10)
    countdown_timer.function()
    for _ in range(10):
        fake_timer.instances[-1].function()


class TestTransportSessionHelpers(unittest.TestCase):
    """Test that _transport_session_id and get_ext_ws_transport_session_id
    correctly decouple target tab from WebSocket transport."""

    def _make_ctx(self, sessions_map):
        """Build a minimal UserContext-like object."""
        ctx = SimpleNamespace(
            sessions=sessions_map,
            tool_created_tabs=set(),
            results={},
            acks={},
        )
        return ctx

    def _make_session(self, sid, session_type='ext_ws', active=True):
        info = {'url': 'https://example.com', 'title': 'test', 'type': session_type}
        s = Session(sid, info)
        if not active:
            s.mark_disconnected()
        return s

    def test_transport_returns_same_tab_when_target_is_active_ext_ws(self):
        target_session = self._make_session('100', 'ext_ws', active=True)
        ctx = self._make_ctx({'100': target_session})

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def _sessions_context(self, token=None):
                return ctx

        d = FakeDriver()
        d.get_ext_ws_transport_session_id = TMWebDriver.get_ext_ws_transport_session_id.__get__(d)
        d._transport_session_id = TMWebDriver._transport_session_id.__get__(d)
        d._status_managed_tab_ids = TMWebDriver._status_managed_tab_ids

        result = d._transport_session_id('100')
        self.assertEqual(result, '100')

    def test_transport_falls_back_to_other_ext_ws_when_target_not_session(self):
        transport_session = self._make_session('200', 'ext_ws', active=True)
        ctx = self._make_ctx({'200': transport_session})

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def _sessions_context(self, token=None):
                return ctx

        d = FakeDriver()
        d.get_ext_ws_transport_session_id = TMWebDriver.get_ext_ws_transport_session_id.__get__(d)
        d._transport_session_id = TMWebDriver._transport_session_id.__get__(d)
        d._status_managed_tab_ids = TMWebDriver._status_managed_tab_ids

        # Target '999' is NOT in ctx.sessions (e.g. a file:// tab)
        result = d._transport_session_id('999')
        self.assertEqual(result, '200')

    def test_transport_returns_none_when_no_ext_ws_available(self):
        http_session = self._make_session('300', 'http', active=True)
        ctx = self._make_ctx({'300': http_session})

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def _sessions_context(self, token=None):
                return ctx

        d = FakeDriver()
        d.get_ext_ws_transport_session_id = TMWebDriver.get_ext_ws_transport_session_id.__get__(d)
        d._transport_session_id = TMWebDriver._transport_session_id.__get__(d)
        d._status_managed_tab_ids = TMWebDriver._status_managed_tab_ids

        result = d._transport_session_id('999')
        self.assertIsNone(result)

    def test_transport_skips_disconnected_ext_ws(self):
        dead_session = self._make_session('400', 'ext_ws', active=False)
        ctx = self._make_ctx({'400': dead_session})

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def _sessions_context(self, token=None):
                return ctx

        d = FakeDriver()
        d.get_ext_ws_transport_session_id = TMWebDriver.get_ext_ws_transport_session_id.__get__(d)
        d._transport_session_id = TMWebDriver._transport_session_id.__get__(d)
        d._status_managed_tab_ids = TMWebDriver._status_managed_tab_ids

        result = d._transport_session_id('999')
        self.assertIsNone(result)


class TestExtensionCommandTransport(unittest.TestCase):
    """Test that extension_command correctly uses transport session
    when the target tab is not itself an active ext_ws session."""

    def test_extension_command_uses_transport_session_for_non_session_target(self):
        transport_session = Session('200', {'url': 'https://transport.example', 'title': '', 'type': 'ext_ws'})
        ctx = SimpleNamespace(
            sessions={'200': transport_session},
            tool_created_tabs=set(),
            results={},
            acks={},
        )

        executed_with = []

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def get_ext_ws_transport_session_id(self, token=None, client_id=None):
                return '200'

            def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
                executed_with.append({'code': code, 'session_id': session_id})
                return {'data': {'result': 'ok'}}

        d = FakeDriver()
        cmd = {"cmd": "cdp", "method": "Page.captureScreenshot", "params": {"format": "png"}}
        actions.extension_command(d, cmd, tab_id='999', timeout=15, token=None)

        self.assertEqual(len(executed_with), 1)
        call = executed_with[0]
        parsed = json.loads(call['code'])
        # The CDP command must carry the target tabId
        self.assertEqual(parsed['tabId'], 999)
        # But the transport session should be the connected ext_ws session, not '999'
        self.assertEqual(call['session_id'], '200')

    def test_extension_command_uses_target_as_transport_when_it_is_active_ext_ws(self):
        target_session = Session('100', {'url': 'https://target.example', 'title': '', 'type': 'ext_ws'})
        ctx = SimpleNamespace(
            sessions={'100': target_session},
            tool_created_tabs=set(),
            results={},
            acks={},
        )

        executed_with = []

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def get_ext_ws_transport_session_id(self, token=None, client_id=None):
                for s in ctx.sessions.values():
                    if s.is_active() and s.type == 'ext_ws':
                        return s.id
                return None

            def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
                executed_with.append({'code': code, 'session_id': session_id})
                return {'data': {'result': 'ok'}}

        d = FakeDriver()
        cmd = {"cmd": "cdp", "method": "Page.captureScreenshot", "params": {"format": "png"}}
        actions.extension_command(d, cmd, tab_id='100', timeout=15, token=None)

        self.assertEqual(len(executed_with), 1)
        call = executed_with[0]
        self.assertEqual(call['session_id'], '100')

    def test_extension_command_no_tab_id_passes_none_session(self):
        ctx = SimpleNamespace(
            sessions={},
            tool_created_tabs=set(),
            results={},
            acks={},
        )

        executed_with = []

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
                executed_with.append({'session_id': session_id})
                return {'data': 'ok'}

        d = FakeDriver()
        cmd = {"cmd": "tabs", "method": "list"}
        actions.extension_command(d, cmd, tab_id=None, timeout=15, token=None)

        self.assertEqual(executed_with[0]['session_id'], None)


class TestScreenshotTargetsCorrectTab(unittest.TestCase):
    """Test that screenshot sends CDP to the correct tab
    even when the target tab is not an active ext_ws session (e.g. file://)."""

    def test_screenshot_after_navigate_file_uses_new_tab_as_target(self):
        # Simulate: tab 555 is registered but NOT an active ext_ws session (e.g. file://),
        # so transport falls back to the connected ext_ws tab 200.
        transport_session = Session('200', {'url': 'https://other.example', 'title': '', 'type': 'ext_ws'})
        file_session = Session('555', {'url': 'file:///tmp/page.html', 'title': '', 'type': 'http'})
        ctx = SimpleNamespace(
            sessions={'200': transport_session, '555': file_session},
            tool_created_tabs={'555'},
            results={},
            acks={},
            _group_lock=__import__('threading').Lock(),
            grouped_tabs={},
        )

        executed_with = []

        class FakeDriver:
            def get_context(self, token=None):
                return ctx

            def get_all_sessions(self, token=None):
                return [{'id': '200', 'url': 'https://other.example', 'title': ''}, {'id': '555', 'url': 'file:///tmp/page.html', 'title': ''}]

            def get_ext_ws_transport_session_id(self, token=None, client_id=None):
                return '200'

            def _transport_session_id(self, target_tab_id, token=None):
                session = ctx.sessions.get(str(target_tab_id))
                if session and session.is_active() and session.type == 'ext_ws':
                    return str(target_tab_id)
                return self.get_ext_ws_transport_session_id(token=token)

            def execute_js(self, code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
                executed_with.append({'code': code, 'session_id': session_id})
                return {'data': {'data': 'base64png'}}

            def _cancel_tab_close(self, tab_id, token=None):
                pass

            def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=False):
                pass

            def update_tab_group(self, tab_id, name, token=None):
                pass

            def broadcast_extension_event(self, payload, token=None):
                pass

        driver = FakeDriver()
        result = actions.screenshot(driver, tab_id='555')

        self.assertEqual(result['status'], 'success')
        self.assertEqual(len(executed_with), 1)
        call = executed_with[0]
        parsed = json.loads(call['code'])
        # The CDP command must target tab 555 (the file:// tab)
        self.assertEqual(parsed['tabId'], 555)
        # The transport must be tab 200 (the connected ext_ws session)
        self.assertEqual(call['session_id'], '200')

    def test_schedule_tab_close_updates_waiting_and_closes_composite_session(self):
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
        driver._default_ctx.tool_created_tabs.add("edge-client:321")
        calls = []

        def fake_update_tab_group(tab_id, group_name, token=None):
            calls.append(("group", tab_id, group_name))

        def fake_remove_tab_group(tab_id, token=None):
            calls.append(("ungroup", tab_id))

        def fake_close_tab(tab_id, token=None):
            calls.append(("close", tab_id))

        driver.update_tab_group = fake_update_tab_group
        driver.remove_tab_group = fake_remove_tab_group
        driver.close_tab = fake_close_tab

        driver._schedule_tab_close("edge-client:321", timeout=0.2)
        time.sleep(0.4)

        self.assertIn(("close", "edge-client:321"), calls)
        self.assertNotIn("edge-client:321", driver._default_ctx.tool_created_tabs)

    def test_schedule_tab_close_retains_tool_marker_and_retries_when_close_fails(self):
        class FakeTimer:
            instances = []

            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.cancelled = False
                self.started = False
                self.daemon = False
                FakeTimer.instances.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        driver._default_ctx.tool_created_tabs.add("edge-client:321")
        close_calls = []
        driver.update_tab_group = lambda tab_id, group_name, token=None: None
        driver.remove_tab_group = lambda tab_id, token=None: None
        driver.close_tab = lambda tab_id, token=None: close_calls.append(tab_id) or False

        original_timer = tmwebdriver_module.Timer
        tmwebdriver_module.Timer = FakeTimer
        try:
            driver._schedule_tab_close("edge-client:321", timeout=60)
            fire_serial_countdown(FakeTimer, 60)
        finally:
            tmwebdriver_module.Timer = original_timer

        self.assertEqual(close_calls, ["edge-client:321"])
        self.assertIn("edge-client:321", driver._default_ctx.tool_created_tabs)
        self.assertIn("edge-client:321", driver._default_ctx.grouped_tabs)
        self.assertTrue(any(t.interval == 5 for t in FakeTimer.instances))

    def test_schedule_tab_close_clears_tool_marker_when_close_succeeds(self):
        class FakeTimer:
            instances = []

            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.cancelled = False
                self.started = False
                self.daemon = False
                FakeTimer.instances.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        driver._default_ctx.tool_created_tabs.add("edge-client:321")
        driver.update_tab_group = lambda tab_id, group_name, token=None: None
        driver.remove_tab_group = lambda tab_id, token=None: None
        driver.close_tab = lambda tab_id, token=None: True

        original_timer = tmwebdriver_module.Timer
        tmwebdriver_module.Timer = FakeTimer
        try:
            driver._schedule_tab_close("edge-client:321", timeout=60)
            fire_serial_countdown(FakeTimer, 60)
        finally:
            tmwebdriver_module.Timer = original_timer

        self.assertNotIn("edge-client:321", driver._default_ctx.tool_created_tabs)

    def test_close_timer_removes_grouped_tab_entry(self):
        class FakeTimer:
            instances = []

            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.cancelled = False
                self.started = False
                self.daemon = False
                FakeTimer.instances.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        driver._default_ctx.tool_created_tabs.add("edge-client:321")
        group_calls = []

        def fake_update_tab_group(tab_id, group_name, token=None):
            group_calls.append((tab_id, group_name))

        driver.update_tab_group = fake_update_tab_group
        driver.remove_tab_group = lambda tab_id, token=None: None
        driver.close_tab = lambda tab_id, token=None: None

        original_timer = tmwebdriver_module.Timer
        tmwebdriver_module.Timer = FakeTimer
        try:
            driver._schedule_tab_close("edge-client:321", timeout=16)
            fire_serial_countdown(FakeTimer, 16)
        finally:
            tmwebdriver_module.Timer = original_timer

        self.assertNotIn("edge-client:321", driver._default_ctx.grouped_tabs)

    def test_stale_close_callback_does_not_close_after_reschedule(self):
        class FakeTimer:
            instances = []

            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.cancelled = False
                self.started = False
                self.daemon = False
                FakeTimer.instances.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        calls = []
        driver.update_tab_group = lambda tab_id, group_name, token=None: None
        driver.remove_tab_group = lambda tab_id, token=None: calls.append(("ungroup", tab_id))
        driver.close_tab = lambda tab_id, token=None: calls.append(("close", tab_id))

        original_timer = tmwebdriver_module.Timer
        tmwebdriver_module.Timer = FakeTimer
        try:
            driver._schedule_tab_close("edge-client:321", timeout=11)
            stale_countdown_timer = next(t for t in FakeTimer.instances if t.interval == 1)
            driver._schedule_tab_close("edge-client:321", timeout=11)

            stale_countdown_timer.function()
        finally:
            tmwebdriver_module.Timer = original_timer

        self.assertEqual(calls, [])

    def test_schedule_tab_close_does_not_close_non_tool_created_tab(self):
        class FakeTimer:
            instances = []

            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.cancelled = False
                self.started = False
                self.daemon = False
                FakeTimer.instances.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        calls = []
        driver.update_tab_group = lambda tab_id, group_name, token=None: None
        driver.remove_tab_group = lambda tab_id, token=None: calls.append(("ungroup", tab_id))
        driver.close_tab = lambda tab_id, token=None: calls.append(("close", tab_id))

        original_timer = tmwebdriver_module.Timer
        tmwebdriver_module.Timer = FakeTimer
        try:
            driver._schedule_tab_close("edge-client:user-tab", timeout=60, close=True)
            fire_serial_countdown(FakeTimer, 60)
        finally:
            tmwebdriver_module.Timer = original_timer

        self.assertIn(("ungroup", "edge-client:user-tab"), calls)
        self.assertNotIn(("close", "edge-client:user-tab"), calls)

    def test_schedule_tab_close_ungroups_non_tool_tab_when_close_false(self):
        class FakeTimer:
            instances = []

            def __init__(self, interval, function):
                self.interval = interval
                self.function = function
                self.cancelled = False
                self.started = False
                self.daemon = False
                FakeTimer.instances.append(self)

            def start(self):
                self.started = True

            def cancel(self):
                self.cancelled = True

        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        calls = []
        driver.update_tab_group = lambda tab_id, group_name, token=None: calls.append(("group", tab_id, group_name))
        driver.remove_tab_group = lambda tab_id, token=None: calls.append(("ungroup", tab_id))
        driver.close_tab = lambda tab_id, token=None: calls.append(("close", tab_id))

        original_timer = tmwebdriver_module.Timer
        tmwebdriver_module.Timer = FakeTimer
        try:
            driver._schedule_tab_close("edge-client:user-tab", timeout=60, close=False)
            for timer in list(FakeTimer.instances):
                timer.function()
        finally:
            tmwebdriver_module.Timer = original_timer

        self.assertNotIn(("group", "edge-client:user-tab", "💤 等待中"), calls)
        self.assertNotIn(("group", "edge-client:user-tab", "💤 10s"), calls)
        self.assertIn(("ungroup", "edge-client:user-tab"), calls)
        self.assertNotIn(("close", "edge-client:user-tab"), calls)


if __name__ == '__main__':
    unittest.main()
