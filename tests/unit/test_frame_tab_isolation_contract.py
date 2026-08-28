from types import SimpleNamespace

from omnibot import actions


def test_active_frame_target_is_selected_per_tab():
    ctx = SimpleNamespace(
        frame_target="",
        frame_targets={"tab-a": "#payment-frame"},
    )

    assert actions._active_frame_target(ctx, "tab-a") == "#payment-frame"
    assert actions._active_frame_target(ctx, "tab-b") == ""


def test_active_frame_target_accepts_raw_tab_alias():
    ctx = SimpleNamespace(frame_target="", frame_targets={"123": "#payment-frame"})

    assert actions._active_frame_target(ctx, "edge-client:123") == "#payment-frame"


def test_active_frame_target_keeps_each_tab_state_after_switching_tabs():
    ctx = SimpleNamespace(
        frame_target="#payment-frame",
        frame_target_tab_id="tab-b",
        frame_targets={"tab-a": "#payment-frame", "tab-b": "main"},
    )

    assert actions._active_frame_target(ctx, "tab-a") == "#payment-frame"
    assert actions._active_frame_target(ctx, "tab-b") == ""
