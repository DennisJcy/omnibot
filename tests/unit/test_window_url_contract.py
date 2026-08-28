from types import SimpleNamespace

from omnibot import actions, cli


def test_window_new_parser_accepts_start_url():
    args = cli.build_parser().parse_args(["window", "new", "https://example.test/start"])

    assert args.window_command == "new"
    assert args.url == "https://example.test/start"


def test_window_new_forwards_start_url_to_browser_window():
    class FakeDriver:
        def __init__(self):
            self.ctx = SimpleNamespace(tool_created_tabs=set(), sessions={})
            self.created_url = None

        def get_context(self, token=None):
            return self.ctx

        def get_all_sessions(self, token=None):
            return [{"tab_id": "123", "url": "https://example.test/start", "title": "Start"}]

        def new_window(self, url, timeout=15, token=None):
            self.created_url = url
            return {"windowId": 99, "tab": {"id": "client:123", "tab_id": "123", "url": url, "title": ""}}

        def _cancel_tab_close(self, tab_id, token=None):
            pass

        def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=True):
            pass

        def update_tab_group(self, *args, **kwargs):
            pass

        def remove_tab_group(self, *args, **kwargs):
            pass

    driver = FakeDriver()
    result = actions.window(driver, "new", url="https://example.test/start")

    assert driver.created_url == "https://example.test/start"
    assert result["status"] == "success"
    assert result["window_id"] == 99
    assert result["tab"]["url"] == "https://example.test/start"
    assert result["tab"]["title"] == "Start"
