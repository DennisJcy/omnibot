from omnibot import session_commands


class Ctx:
    session_name = ""
    claimed_tabs = set()


def test_name_session_sets_context_name():
    ctx = Ctx()
    assert session_commands.name_session(ctx, "checkout") == {"name": "checkout"}
    assert ctx.session_name == "checkout"


def test_claim_and_release_tab_updates_claimed_tabs():
    ctx = Ctx()
    session_commands.claim_tab(ctx, "tab-1")
    assert "tab-1" in ctx.claimed_tabs
    session_commands.release_tab(ctx, "tab-1")
    assert "tab-1" not in ctx.claimed_tabs
