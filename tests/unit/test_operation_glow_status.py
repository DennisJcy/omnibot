import json
import unittest

from omnibot.TMWebDriver import TMWebDriver, Session


class UpdateTabGroupGlowStatusTest(unittest.TestCase):
    def test_update_tab_group_forwards_title_as_group_status(self):
        calls = []
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.multi_user = False
        driver._default_ctx = type("Ctx", (), {
            "sessions": {"123": Session("123", {"url": "https://example.com", "title": "", "type": "ext_ws"})},
            "tool_created_tabs": set(),
            "grouped_tabs": {},
            "_group_lock": __import__("threading").Lock(),
            "results": {},
            "acks": {},
        })()

        def fake_execute_js(code, timeout=15, session_id=None, token=None, group_status=None, status_tab_id=None):
            calls.append(
                {
                    "code": code,
                    "timeout": timeout,
                    "session_id": session_id,
                    "token": token,
                    "group_status": group_status,
                }
            )
            return {"data": {"ok": True}}

        driver.execute_js = fake_execute_js

        result = driver.update_tab_group("123", "✅ 已扫描", token="request-token")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["timeout"], 5)
        self.assertEqual(calls[0]["session_id"], "123")
        self.assertEqual(calls[0]["token"], "request-token")
        self.assertEqual(calls[0]["group_status"], "✅ 已扫描")

        payload = json.loads(calls[0]["code"])
        self.assertEqual(payload, {"cmd": "tabGroups", "method": "group", "tabId": 123, "title": "✅ 已扫描"})


if __name__ == "__main__":
    unittest.main()
