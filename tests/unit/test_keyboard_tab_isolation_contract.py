from types import SimpleNamespace

from omnibot import actions


def test_keyboard_modifiers_are_selected_per_tab():
    ctx = SimpleNamespace(
        keyboard_modifiers=0,
        keyboard_modifiers_by_tab={"tab-a": 1},
    )

    assert actions._keyboard_modifiers_for_tab(ctx, "tab-a") == 1
    assert actions._keyboard_modifiers_for_tab(ctx, "tab-b") == 0
