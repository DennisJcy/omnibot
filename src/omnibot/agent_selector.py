"""Interactive agent selection UI using prompt_toolkit."""
import sys
from typing import Optional

from prompt_toolkit import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout, HSplit
from prompt_toolkit.layout.containers import Window, WindowAlign
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from .logger import log


AGENTS = [
    ("opencode", "OpenCode"),
    ("hermes", "Hermes"),
    ("claude", "Claude Code"),
    ("codex", "Codex"),
    ("workbuddy", "Workbuddy"),
]


def select_agent() -> Optional[str]:
    """Show interactive agent selection dialog.

    Navigation: Up/Down arrows to move, Space/Enter to confirm selection.
    Returns:
        str: Selected agent name, or None if cancelled.
    """
    log("select_agent: showing agent selection dialog")

    selected_index = [0]

    def get_menu_text():
        lines = [
            "<title>omnibot - Agent Configuration</title>",
            "",
            "<subtitle>Select an AI agent to configure:</subtitle>",
            "",
        ]
        for i, (value, label) in enumerate(AGENTS):
            if i == selected_index[0]:
                lines.append(f"  <selected> ● {label} </selected>")
            else:
                lines.append(f"    ○ {label}")
        lines.append("")
        lines.append("<hint> ↑↓: navigate   Enter/Space: confirm   Ctrl-C: cancel </hint>")
        return HTML("\n".join(lines))

    control = FormattedTextControl(get_menu_text)

    style = Style.from_dict({
        "title": "bold cyan",
        "subtitle": "white",
        "selected": "bold white bg:#005f5f",
        "hint": "#888888",
    })

    root = HSplit([
        Window(content=control, align=WindowAlign.LEFT),
    ])

    bindings = KeyBindings()

    @bindings.add(Keys.Up)
    def _(event):
        selected_index[0] = max(0, selected_index[0] - 1)

    @bindings.add(Keys.Down)
    def _(event):
        selected_index[0] = min(len(AGENTS) - 1, selected_index[0] + 1)

    @bindings.add(" ")
    def _(event):
        event.app.exit(result=AGENTS[selected_index[0]][0])

    @bindings.add(Keys.Enter)
    def _(event):
        event.app.exit(result=AGENTS[selected_index[0]][0])

    @bindings.add(Keys.ControlC)
    def _(event):
        event.app.exit(result=None)

    app = Application(
        layout=Layout(root),
        key_bindings=bindings,
        style=style,
        full_screen=False,
    )
    result = app.run()

    log(f"select_agent: user selected={result}")
    return result
