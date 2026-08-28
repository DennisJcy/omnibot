from types import SimpleNamespace

from omnibot import actions, cdp


class FakeDriver:
    def __init__(self):
        self.ctx = SimpleNamespace(sessions={"tab-1": SimpleNamespace(created_by_tool=False)}, tool_created_tabs=set())

    def get_context(self, token=None):
        return self.ctx

    def get_all_sessions(self, token=None):
        return [{"id": "tab-1", "tab_id": "101"}]

    def _cancel_tab_close(self, tab_id, token=None):
        pass

    def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=True):
        pass


def test_wait_fn_accepts_optional_return_prefix(monkeypatch):
    expressions = []
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: expressions.append(args[2]) or True)

    result = actions.wait(FakeDriver(), fn="return window.ready === true", switch_tab_id="tab-1", timeout=1)

    assert result["status"] == "success"
    assert expressions == ["Boolean(window.ready === true)"]


def test_wait_does_not_treat_evaluation_error_text_as_success(monkeypatch):
    monkeypatch.setattr(cdp, "evaluate", lambda *args, **kwargs: "SyntaxError: Unexpected token 'return'")

    result = actions.wait(FakeDriver(), fn="window.ready", switch_tab_id="tab-1", timeout=0)

    assert result["status"] == "timeout"
    assert result["value"] == "SyntaxError: Unexpected token 'return'"
