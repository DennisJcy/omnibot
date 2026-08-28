import socket
import time
import unittest

import requests

from omnibot.TMWebDriver import TMWebDriver, UserContext


def _free_http_base_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    http_port = sock.getsockname()[1]
    sock.close()
    return http_port - 1, http_port


class RemoteExecuteJsGroupStatusTest(unittest.TestCase):
    def test_link_route_forwards_group_status_to_execute_js(self):
        base_port, http_port = _free_http_base_port()
        driver = TMWebDriver.__new__(TMWebDriver)
        driver.host = "127.0.0.1"
        driver.port = base_port
        driver.multi_user = False
        driver._default_ctx = UserContext("__default__")
        calls = []

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
                        "sessionId": "123",
                        "code": "return 1;",
                        "timeout": "7",
                        "groupStatus": "⚡ 执行中",
                    },
                    timeout=1,
                )
                if response.status_code == 200:
                    break
            except requests.RequestException as exc:
                last_error = exc
            time.sleep(0.05)
        else:
            raise AssertionError(f"HTTP server did not start: {last_error}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["session_id"], "123")
        self.assertEqual(calls[0]["timeout"], 7.0)
        self.assertEqual(calls[0]["group_status"], "⚡ 执行中")


if __name__ == "__main__":
    unittest.main()
