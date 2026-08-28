import json
import re
from types import SimpleNamespace
import unittest
from pathlib import Path

import pytest

from omnibot import actions
from omnibot.TMWebDriver import TMWebDriver, UserContext, Session


ROOT = Path(__file__).resolve().parents[2]
BACKGROUND_JS = ROOT / "browser-extension" / "background.js"
ACTIONS_PY = ROOT / "src" / "omnibot" / "actions.py"


class BackgroundNavigationContractTests(unittest.TestCase):
    def test_extension_creates_navigate_tabs_in_background(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        create_block = re.search(
            r"msg\.method\s*===\s*['\"]create['\"]\)\s*\{(?P<body>.*?)\}\s*else",
            source,
            re.DOTALL,
        )

        self.assertIsNotNone(create_block, "tabs/create branch not found in background.js")
        body = create_block.group("body")
        self.assertIn("chrome.tabs.create", body)
        self.assertRegex(body, r"active\s*:\s*false")
        self.assertNotRegex(body, r"active\s*:\s*true")

    def test_extension_waits_for_created_tab_metadata(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        create_block = re.search(
            r"msg\.method\s*===\s*['\"]create['\"]\)\s*\{(?P<body>.*?)\}\s*else",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(create_block, "tabs/create branch not found in background.js")
        body = create_block.group("body")
        self.assertIn("waitForScriptableTab(tab.id)", body)
        self.assertIn("metadata.url", body)

    def test_cdp_new_tab_watcher_filters_opener_after_tab_metadata_is_available(self):
        source = BACKGROUND_JS.read_text(encoding="utf-8")
        handle_cdp = source[source.index("async function handleCDP"):source.index("const isScriptable")]

        self.assertIn("candidateTabIds.add(tab.id)", handle_cdp)
        self.assertNotIn("if (tab.openerTabId === Number(tabId))", handle_cdp)
        self.assertIn("sourceStatusGroupId", handle_cdp)
        self.assertIn("waitForOwnedNewTabs(candidateTabIds, tabId, sourceStatusGroupId, sourceWindowId)", handle_cdp)

        owned_watcher = source[source.index("async function waitForOwnedNewTabs"):source.index("async function waitForScriptableTab")]
        self.assertIn("tab.openerTabId === Number(openerTabId)", owned_watcher)
        self.assertIn("tab.groupId === sourceStatusGroupId", owned_watcher)
        self.assertIn("ownershipReason: openerMatches ? 'opener' : 'status-group'", owned_watcher)
        self.assertIn("isScriptable(tab.url)", owned_watcher)

    def test_navigate_new_tab_schedules_close(self):
        source = ACTIONS_PY.read_text(encoding="utf-8")

        self.assertIn("driver._schedule_tab_close(tab_id, token=token)", source)
        self.assertIn("if new_tab:", source)

    def test_page_script_requires_session_id(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        session = Session("transport:1", {"url": "https://example.com", "title": "", "type": "ext_ws", "client_id": "transport", "tab_id": "1"})
        driver._default_ctx.sessions["transport:1"] = session
        driver._default_ctx.latest_session_id = "transport:1"

        with self.assertRaises(ValueError) as ctx:
            driver.execute_js("return location.href")
        self.assertIn("session_id is required", str(ctx.exception))

    def test_extension_command_uses_transport_when_no_session_id(self):
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver.is_remote = False
        driver._default_ctx = UserContext("__default__")
        sent = []

        class FakeWs:
            def send_message(self, payload):
                sent.append(json.loads(payload))
                exec_id = sent[-1]["id"]
                driver._default_ctx.acks[exec_id] = True
                driver._default_ctx.results[exec_id] = {"success": True, "data": {"id": 999}, "newTabs": []}

        session = Session("transport:1", {"url": "https://example.com", "title": "", "type": "ext_ws", "client_id": "transport", "tab_id": "1"}, FakeWs())
        driver._default_ctx.sessions["transport:1"] = session
        driver._default_ctx.latest_session_id = "transport:1"

        result = driver.execute_js('{"cmd":"tabs","method":"create","url":"https://new.example"}')
        self.assertEqual(result["data"]["id"], 999)
        self.assertEqual(sent[0]["tabId"], 1)

    def test_navigate_new_tab_does_not_use_default_session(self):
        calls = []

        class FakeDriver:
            def get_context(self, token=None):
                return SimpleNamespace(sessions={}, tool_created_tabs=set(), latest_session_id=None)

            def get_all_sessions(self, token=None):
                return [{"id": "connected-transport", "url": "https://transport.example"}]

            def new_tab(self, url, timeout=15, token=None):
                calls.append({"url": url})
                return {"id": 123, "url": url, "title": ""}

            def _cancel_tab_close(self, tab_id, token=None):
                calls.append({"cancel": tab_id})

            def _schedule_tab_close(self, tab_id, token=None):
                calls.append({"schedule": tab_id})

            def update_tab_group(self, tab_id, name, token=None):
                calls.append({"group": tab_id, "name": name})

        result = actions.navigate_new_tab(FakeDriver(), "https://www.baidu.com/s?wd=AI")

        self.assertEqual(result["status"], "success")
        self.assertEqual(calls[0], {"url": "https://www.baidu.com/s?wd=AI"})

    def test_navigate_new_tab_allowed_when_no_web_tabs_connected(self):
        calls = []

        class FakeDriver:
            def get_context(self, token=None):
                return SimpleNamespace(sessions={}, tool_created_tabs=set(), latest_session_id=None)

            def get_all_sessions(self, token=None):
                return []

            def new_tab(self, url, timeout=15, token=None):
                calls.append({"url": url})
                return {"id": "client:456", "tab_id": "456", "url": url, "title": ""}

            def _cancel_tab_close(self, tab_id, token=None):
                calls.append({"cancel": tab_id})

            def _schedule_tab_close(self, tab_id, token=None):
                calls.append({"schedule": tab_id})

            def update_tab_group(self, tab_id, name, token=None):
                calls.append({"group": tab_id, "name": name})

        result = actions.navigate(FakeDriver(), "https://example.test", new_tab=True)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tab"]["id"], "client:456")
        self.assertEqual(calls[0], {"url": "https://example.test"})

    def test_tab_new_propagates_create_failure(self):
        class FakeDriver:
            def get_context(self, token=None):
                return SimpleNamespace(tab_aliases={}, next_tab_alias_number=1)

            def new_tab(self, url, timeout=15, token=None):
                raise ValueError("no extension transport")

        result = actions.tab(FakeDriver(), tab_command="new", url="https://example.test")

        self.assertEqual(result["status"], "error")
        self.assertIn("no extension transport", result["msg"])

if __name__ == "__main__":
    unittest.main()
