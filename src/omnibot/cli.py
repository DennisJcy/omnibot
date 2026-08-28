import argparse
import json
import os
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

from . import daemon_client
from .defaults import DEFAULT_API_PORT, DEFAULT_WS_PORT


COMMANDS = [
    ("daemon", "Manage the local omnibot daemon."),
    ("tabs", "List connected browser tabs."),
    ("read", "Read a page as clean text; opens URL in a temporary tab when provided."),
    ("snapshot", "Accessibility tree snapshot with @eN refs; text output by default."),
    ("click", "Click an element by selector or @eN ref."),
    ("dblclick", "Double-click an element by selector or @eN ref."),
    ("execute-js", "Run JavaScript or extension/CDP commands in a tab."),
    ("get", "Read page or element state."),
    ("is", "Check element state."),
    ("find", "Find element by semantic locator."),
    ("fill", "Replace an input value by selector or @eN ref."),
    ("type", "Type text into an element by selector or @eN ref."),
    ("press", "Press a key in the active tab."),
    ("keyboard", "Send keyboard text input to a tab."),
    ("keydown", "Dispatch a keydown event in a tab."),
    ("keyup", "Dispatch a keyup event in a tab."),
    ("hover", "Hover over an element by selector or @eN ref."),
    ("focus", "Focus an element by selector or @eN ref."),
    ("select", "Select an option in a dropdown."),
    ("check", "Check a checkbox."),
    ("uncheck", "Uncheck a checkbox."),
    ("scroll", "Scroll the page or an element."),
    ("scrollintoview", "Scroll an element into view."),
    ("drag", "Drag from source to target element."),
    ("upload", "Upload a file to a file input."),
    ("open", "Open a URL in a new tab."),
    ("goto", "Navigate to a URL."),
    ("close", "Close a browser tab."),
    ("tab", "Manage browser tabs."),
    ("window", "Manage browser windows."),
    ("frame", "Set frame target."),
    ("back", "Go back in history."),
    ("forward", "Go forward in history."),
    ("reload", "Reload the current page."),
    ("pushstate", "Push browser history state."),
    ("mouse", "Coordinate-based mouse operations."),
    ("dom", "DOM node interaction."),
    ("console", "Console log operations."),
    ("dialog", "Browser JavaScript dialog operations."),
    ("network", "Network request operations."),
    ("cdp", "Send raw CDP command."),
    ("verify", "Inspect human-verification (captcha) widgets."),
    ("clipboard", "Clipboard operations."),
    ("viewport", "Viewport operations."),
    ("assets", "Page resource operations."),
    ("browser", "Browser session operations."),
    ("session", "Session operations."),
    ("record", "Record operations."),
    ("replay", "Replay recorded flow."),
    ("trace", "Trace operations."),
    ("visibility", "Automation browser visibility mode."),
    ("batch", "Send multiple extension/CDP commands in one request."),
    ("wait", "Wait for time, selector, text, URL, load, or JS condition."),
    ("navigate", "Open a URL in a new tab, or reuse the active tab."),
    ("screenshot", "Capture a PNG screenshot from a browser tab."),
    ("skills", "Install packaged omnibot skills for agent clients."),
    ("doctor", "Check daemon and browser extension health."),
    ("version", "Print the omnibot CLI version."),
]
BROWSER_CHOICES = ["chrome", "edge", "brave", "arc"]
BROWSER_LABELS = {"chrome": "Chrome", "edge": "Edge", "brave": "Brave", "arc": "Arc"}


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR") is not None:
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _version() -> str:
    # Standalone builds carry an explicit VERSION file next to the binary.
    # Prefer it so stale editable-install metadata on build hosts cannot leak
    # an older version into the packaged CLI banner.
    try:
        version_file = Path(sys.argv[0]).resolve().parent / "VERSION"
        if version_file.is_file():
            value = version_file.read_text(encoding="utf-8").strip()
            if value:
                return value
    except Exception:
        pass
    try:
        return version("omnibot")
    except Exception:
        return "1.6.22"


def _colors() -> dict[str, str]:
    if not _supports_color():
        return {"CYAN": "", "WHITE": "", "GRAY": "", "BOLD": "", "RESET": ""}
    return {
        "CYAN": "\033[36m",
        "WHITE": "\033[97m",
        "GRAY": "\033[90m",
        "BOLD": "\033[1m",
        "RESET": "\033[0m",
    }


def _print_banner() -> None:
    colors = _colors()
    banner_lines = [
        " ▄▄▄▄▄▄▄   ▄▄     ▄▄  ▄▄   ▄▄  ▄▄▄▄▄▄",
        "██╔═══██╗  ███╗   ███╗ ██╗  ██║ ╚═██╔═╝",
        "██║   ██║  ████╗ ████║ ███╗ ██║   ██║",
        "██║   ██║  ██╔████╔██║ ████╗██║   ██║",
        "██║   ██║  ██║╚██╔╝██║ ██╔████║   ██║",
        "╚██████╔╝  ██║ ╚═╝ ██║ ██║ ╚██║ ▄▄██▄▄",
        " ╚═════╝   ╚═╝     ╚═╝ ╚═╝  ╚═╝ ╚════╝",
    ]
    title = f"omnibot CLI v{_version()}"
    subtitle = "Control your real browser through AI agents"
    info_col = 44

    for i, line in enumerate(banner_lines):
        padded = line.ljust(info_col)
        if i == 1:
            print(f"{colors['CYAN']}{colors['BOLD']}{padded}{colors['WHITE']}{colors['BOLD']}{title}{colors['RESET']}")
        else:
            print(f"{colors['CYAN']}{colors['BOLD']}{padded}{colors['RESET']}")
    print(f"{' ' * info_col}{colors['GRAY']}{subtitle}{colors['RESET']}")
    print()


def print_help() -> None:
    _print_banner()
    colors = _colors()
    heading = f"{colors['CYAN']}{colors['BOLD']}{{}}{colors['RESET']}"

    print(heading.format("Usage:"), "omnibot [global options] <command> [command options]")
    print()
    print(heading.format("Global Options:"))
    print(f"  {'-h, --help':<34} Show this help message.")
    print(f"  {'-V, --version':<34} Print the omnibot CLI version and exit.")
    print(f"  {'--api-port API_PORT':<34} Local daemon HTTP API port. Defaults to {DEFAULT_API_PORT}.")
    print(f"  {'--ws-port WS_PORT':<34} Browser extension WebSocket port. Defaults to {DEFAULT_WS_PORT}.")
    print(f"  {'--no-start':<34} Do not auto-start the local daemon.")
    print()
    print(heading.format("Commands:"))
    for command, description in COMMANDS:
        print(f"  {command:<34} {description}")
    print()


def _subparser_aliases() -> dict[str, dict[str, str]]:
    return {
        "skills": {
            "install": "Install omnibot skills for an agent",
            "path": "Show packaged skills path",
        },
        "daemon": {
            "run": "Run the daemon in the foreground",
            "start": "Start the daemon in the background",
            "stop": "Stop the running daemon",
            "status": "Show daemon status",
        },
        "tab": {
            "list": "List browser tabs",
            "new": "Open a new tab",
            "switch": "Switch to a tab",
            "close": "Close a tab",
        },
        "browser": {
            "list": "List connected browsers",
            "current": "Show current browser",
            "claim": "Claim a browser session",
            "release": "Release a browser session",
        },
        "session": {
            "name": "Set session name",
            "list": "List sessions",
        },
        "visibility": {
            "status": "Show visibility mode",
            "set": "Set visibility mode",
            "launch": "Launch a browser in a visibility mode",
        },
        "clipboard": {
            "read": "Read clipboard",
            "write": "Write to clipboard",
        },
        "assets": {
            "list": "List page assets",
            "export": "Export page assets",
        },
        "viewport": {
            "get": "Get viewport size",
            "set": "Set viewport size",
        },
        "console": {
            "logs": "Show console logs",
            "errors": "Show console errors",
            "clear": "Clear console",
        },
        "dialog": {
            "logs": "Show browser JavaScript dialogs",
            "clear": "Clear browser JavaScript dialog log buffer",
            "handle": "Accept or dismiss the current browser JavaScript dialog",
        },
        "network": {
            "logs": "Show network logs",
            "summary": "Show network summary",
            "start": "Start network capture",
            "stop": "Stop network capture",
            "clear": "Clear network capture buffer",
        },
        "keyboard": {
            "type": "Type text via keyboard",
            "inserttext": "Insert text via keyboard",
        },
        "window": {
            "new": "Open new window",
        },
        "record": {
            "start": "Start recording",
            "stop": "Stop recording",
        },
        "trace": {
            "start": "Start tracing",
            "stop": "Stop tracing",
        },
        "mouse": {
            "click": "Click at coordinates",
            "move": "Move to coordinates",
            "scroll": "Scroll at coordinates",
            "drag": "Drag between coordinates",
        },
        "dom": {
            "visible": "Check DOM visibility",
            "click": "Click DOM node",
            "dblclick": "Double-click DOM node",
            "scroll": "Scroll DOM node",
        },
    }


def _print_concise_help() -> None:
    colors = _colors()
    heading = f"{colors['CYAN']}{colors['BOLD']}{{}}{colors['RESET']}"
    gray = colors["GRAY"]
    reset = colors["RESET"]

    _print_banner()
    print(heading.format("Common commands:"))
    print(f"  {'doctor':<20} Check daemon and browser extension status")
    print(f"  {'status':<20} Show daemon status")
    print(f"  {'start':<20} Start the daemon")
    print(f"  {'stop':<20} Stop the daemon")
    print(f"  {'read':<20} Read a page as clean text")
    print(f"  {'tabs':<20} List connected browser tabs")
    print(f"  {'skills':<20} Install or locate agent skills")
    print()
    print(f"{gray}Run `omnibot -h` to show all commands.{reset}")
    print(f"{gray}Run `omnibot <command> -h` for command-specific help.{reset}")
    print()


def _print_group_help(command: str) -> None:
    aliases = _subparser_aliases().get(command, {})
    if aliases:
        print(f"Usage: omnibot {command} <command>")
        print()
        print("Commands:")
        for name, desc in aliases.items():
            print(f"  {name:<20} {desc}")
        print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="omnibot", description="Control a real browser through the omnibot local daemon.", add_help=False)
    parser.add_argument("-h", "--help", action="store_true", help="Show this help message.")
    parser.add_argument("-V", "--version", action="store_true", help="Print the omnibot CLI version and exit.")
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--ws-port", type=int, default=DEFAULT_WS_PORT)
    parser.add_argument("--no-start", action="store_true", help="Do not auto-start the local daemon.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_bridge = subparsers.add_parser("install-bridge", help=argparse.SUPPRESS)
    install_bridge.add_argument("--extension-id", help=argparse.SUPPRESS)
    install_bridge.add_argument("--browser", choices=BROWSER_CHOICES, help=argparse.SUPPRESS)
    install_bridge.add_argument("--timeout", type=float, default=60, help=argparse.SUPPRESS)
    install_bridge.set_defaults(json=True)

    uninstall_bridge = subparsers.add_parser("uninstall-bridge", help=argparse.SUPPRESS)
    uninstall_bridge.add_argument("--browser", choices=BROWSER_CHOICES, help=argparse.SUPPRESS)
    uninstall_bridge.set_defaults(json=True)

    daemon_parser = subparsers.add_parser("daemon", help="Manage the local omnibot daemon.")
    daemon_sub = daemon_parser.add_subparsers(dest="daemon_command", required=False)
    daemon_sub.add_parser("run", help="Run the daemon in the foreground.")
    daemon_sub.add_parser("start", help="Start the daemon in the background.")
    daemon_sub.add_parser("stop", help="Stop the running daemon.")
    daemon_sub.add_parser("status", help="Show daemon status.")

    for alias in ["start", "stop", "status", "run"]:
        p = subparsers.add_parser(alias, help=argparse.SUPPRESS)
        p.set_defaults(_daemon_alias=alias)

    tabs = subparsers.add_parser("tabs", help="List connected browser tabs.")
    tabs.add_argument("--json", action="store_true", default=True, help="Return structured JSON output.")
    tabs.set_defaults(json=True)

    read_parser = subparsers.add_parser("read", help="Read a page as clean text; opens URL in a temporary tab when provided.")
    read_parser.add_argument("url", nargs="?", default="", help="Optional URL to read in a temporary tab.")
    read_parser.add_argument("--screens", type=int, default=5, help="Number of viewport scrolls to trigger lazy loading.")
    read_parser.add_argument("--tab-id", default="", dest="switch_tab_id", help="Existing tab id to read when no URL is provided.")
    read_parser.add_argument("--json", action="store_true", default=False, help="Return structured JSON instead of clean text.")
    read_parser.add_argument("--timeout", type=float, default=None, dest="action_timeout", help="Daemon request timeout in seconds.")

    execute_js = subparsers.add_parser("execute-js", help="Run JavaScript or extension/CDP commands in a tab.")
    execute_js.add_argument("script", nargs="?", help="JavaScript code to execute.")
    execute_js.add_argument("--file", help="Read script from file.")
    execute_js.add_argument("--tab-id", default="", dest="switch_tab_id", help="Switch to tab before executing.")
    execute_js.add_argument("--no-monitor", action="store_true", help="Disable script monitoring.")

    snapshot = subparsers.add_parser("snapshot", help="Accessibility tree snapshot with @eN refs; text output by default.")
    snapshot.add_argument("-i", "--interactive", action="store_true", default=False)
    snapshot.add_argument("-c", "--compact", action="store_true", default=False)
    snapshot.add_argument("-d", "--depth", type=int, default=None, dest="max_depth")
    snapshot.add_argument("-s", "--selector", default="")
    snapshot.add_argument("-u", "--urls", action="store_true", default=False)
    snapshot.add_argument("--tab-id", default="", dest="switch_tab_id")
    snapshot.add_argument("--json", action="store_true", default=False)

    click_parser = subparsers.add_parser("click", help="Click an element by selector or @eN ref.")
    click_parser.add_argument("selector")
    click_parser.add_argument("--new-tab", action="store_true", default=False)
    click_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    click_parser.set_defaults(json=True)

    dblclick_parser = subparsers.add_parser("dblclick", help="Double-click an element by selector or @eN ref.")
    dblclick_parser.add_argument("selector")
    dblclick_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    dblclick_parser.set_defaults(json=True)

    fill_parser = subparsers.add_parser("fill", help="Replace an input value by selector or @eN ref.")
    fill_parser.add_argument("selector")
    fill_parser.add_argument("value")
    fill_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    fill_parser.set_defaults(json=True)

    type_parser = subparsers.add_parser("type", help="Type text into an element by selector or @eN ref.")
    type_parser.add_argument("selector")
    type_parser.add_argument("text")
    type_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    type_parser.set_defaults(json=True)

    press_parser = subparsers.add_parser("press", help="Press a key in the active tab.")
    press_parser.add_argument("key")
    press_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    press_parser.set_defaults(json=True)

    keyboard_parser = subparsers.add_parser("keyboard", help="Send keyboard text to the active focus.")
    keyboard_sub = keyboard_parser.add_subparsers(dest="keyboard_command", required=False)
    for name in ["type", "inserttext"]:
        sub = keyboard_sub.add_parser(name)
        sub.add_argument("value")
        sub.add_argument("--tab-id", default="", dest="switch_tab_id")
        sub.set_defaults(json=True)

    keydown_parser = subparsers.add_parser("keydown", help="Dispatch keyDown without keyUp.")
    keydown_parser.add_argument("key")
    keydown_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    keydown_parser.set_defaults(json=True)

    keyup_parser = subparsers.add_parser("keyup", help="Dispatch keyUp without keyDown.")
    keyup_parser.add_argument("key")
    keyup_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    keyup_parser.set_defaults(json=True)

    hover_parser = subparsers.add_parser("hover", help="Hover over an element by selector or @eN ref.")
    hover_parser.add_argument("selector")
    hover_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    hover_parser.set_defaults(json=True)

    focus_parser = subparsers.add_parser("focus", help="Focus an element by selector.")
    focus_parser.add_argument("selector")
    focus_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    focus_parser.set_defaults(json=True)

    select_parser = subparsers.add_parser("select", help="Select an option in a dropdown.")
    select_parser.add_argument("selector")
    select_parser.add_argument("value")
    select_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    select_parser.set_defaults(json=True)

    check_parser = subparsers.add_parser("check", help="Check a checkbox.")
    check_parser.add_argument("selector")
    check_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    check_parser.set_defaults(json=True)

    uncheck_parser = subparsers.add_parser("uncheck", help="Uncheck a checkbox.")
    uncheck_parser.add_argument("selector")
    uncheck_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    uncheck_parser.set_defaults(json=True)

    scroll_parser = subparsers.add_parser("scroll", help="Scroll the page or an element.")
    scroll_parser.add_argument("direction", choices=["up", "down", "left", "right"])
    scroll_parser.add_argument("pixels", type=int)
    scroll_parser.add_argument("--selector", default="")
    scroll_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    scroll_parser.set_defaults(json=True)

    scrollintoview_parser = subparsers.add_parser("scrollintoview", help="Scroll an element into view.")
    scrollintoview_parser.add_argument("selector")
    scrollintoview_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    scrollintoview_parser.set_defaults(json=True)

    drag_parser = subparsers.add_parser("drag", help="Drag from source to target element.")
    drag_parser.add_argument("source")
    drag_parser.add_argument("target")
    drag_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    drag_parser.set_defaults(json=True)

    upload_parser = subparsers.add_parser("upload", help="Upload a file to a file input.")
    upload_parser.add_argument("selector")
    upload_parser.add_argument("file")
    upload_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    upload_parser.set_defaults(json=True)

    execute_js.set_defaults(json=True)

    get_parser = subparsers.add_parser("get", help="Read page or element state.")
    get_sub = get_parser.add_subparsers(dest="get_command", required=False)
    for name in ["text", "html", "value", "count", "box", "styles"]:
        sub = get_sub.add_parser(name)
        sub.add_argument("selector")
        sub.add_argument("--tab-id", default="", dest="switch_tab_id")
        sub.set_defaults(json=True)
    attr_parser = get_sub.add_parser("attr")
    attr_parser.add_argument("selector")
    attr_parser.add_argument("attr")
    attr_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    attr_parser.set_defaults(json=True)
    for name in ["title", "url"]:
        sub = get_sub.add_parser(name)
        sub.add_argument("--tab-id", default="", dest="switch_tab_id")
        sub.set_defaults(json=True)

    is_parser = subparsers.add_parser("is", help="Check element state.")
    is_sub = is_parser.add_subparsers(dest="is_command", required=False)
    for name in ["visible", "hidden", "enabled", "checked"]:
        sub = is_sub.add_parser(name)
        sub.add_argument("selector")
        sub.add_argument("--tab-id", default="", dest="switch_tab_id")
        sub.set_defaults(json=True)

    find_parser = subparsers.add_parser("find", help="Find element by semantic locator.")
    find_sub = find_parser.add_subparsers(dest="find_command", required=False)
    role_parser = find_sub.add_parser("role")
    role_parser.add_argument("value")
    role_parser.add_argument("--name", default=None)
    role_parser.add_argument("--exact", action="store_true")
    role_parser.add_argument("--index", type=int, default=None)
    role_parser.add_argument("--action", default="text")
    role_parser.add_argument("--action-value", default=None)
    role_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    role_parser.set_defaults(json=True)
    text_parser = find_sub.add_parser("text")
    text_parser.add_argument("value")
    text_parser.add_argument("--exact", action="store_true")
    text_parser.add_argument("--index", type=int, default=None)
    text_parser.add_argument("--action", default="text")
    text_parser.add_argument("--action-value", default=None)
    text_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    text_parser.set_defaults(json=True)
    for strategy in ["label", "placeholder", "alt", "title", "testid"]:
        sub = find_sub.add_parser(strategy)
        sub.add_argument("value")
        sub.add_argument("--exact", action="store_true")
        sub.add_argument("--action", default="text")
        sub.add_argument("--action-value", default=None)
        sub.add_argument("--tab-id", default="", dest="switch_tab_id")
        sub.set_defaults(json=True)
    nth_parser = find_sub.add_parser("nth")
    nth_parser.add_argument("selector")
    nth_parser.add_argument("index", type=int)
    nth_parser.add_argument("--action", default="text")
    nth_parser.add_argument("--action-value", default=None)
    nth_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    nth_parser.set_defaults(json=True)

    open_parser = subparsers.add_parser("open", help="Open a URL in a new tab.")
    open_parser.add_argument("url")
    open_parser.set_defaults(json=True)

    goto_parser = subparsers.add_parser("goto", help="Navigate to a URL.")
    goto_parser.add_argument("url")
    goto_parser.add_argument("--tab-id", default="", dest="switch_tab_id", help="Target tab ID for same-tab navigation.")
    goto_parser.set_defaults(json=True)

    close_parser = subparsers.add_parser("close", help="Close a browser tab.")
    close_parser.add_argument("tab_id", nargs="?", default="")
    close_parser.set_defaults(json=True)

    tab_parser = subparsers.add_parser("tab", help="Manage browser tabs.")
    tab_sub = tab_parser.add_subparsers(dest="tab_command", required=False)
    tab_sub.add_parser("list").set_defaults(json=True)
    tab_new = tab_sub.add_parser("new")
    tab_new.add_argument("url", nargs="?", default=None)
    tab_new.add_argument("--label", default=None)
    tab_new.set_defaults(json=True)
    tab_close = tab_sub.add_parser("close")
    tab_close.add_argument("target")
    tab_close.set_defaults(json=True)
    tab_group = tab_sub.add_parser("group", help="Put a tab into a named tab group.")
    tab_group.add_argument("target")
    tab_group.add_argument("label", nargs="?", default="")
    tab_group.set_defaults(json=True)
    tab_ungroup = tab_sub.add_parser("ungroup", help="Remove a tab from its tab group.")
    tab_ungroup.add_argument("target")
    tab_ungroup.set_defaults(json=True)
    tab_group_info = tab_sub.add_parser("group-info", help="Read a tab's tab group state.")
    tab_group_info.add_argument("target")
    tab_group_info.set_defaults(json=True)

    window_parser = subparsers.add_parser("window", help="Manage browser windows.")
    window_sub = window_parser.add_subparsers(dest="window_command", required=False)
    window_new = window_sub.add_parser("new")
    window_new.add_argument("url", nargs="?", default="about:blank")
    window_new.set_defaults(json=True)

    frame_parser = subparsers.add_parser("frame", help="Set frame target.")
    frame_parser.add_argument("frame_target")
    frame_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    frame_parser.set_defaults(json=True)

    back_parser = subparsers.add_parser("back", help="Go back in history.")
    back_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    back_parser.set_defaults(json=True)
    forward_parser = subparsers.add_parser("forward", help="Go forward in history.")
    forward_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    forward_parser.set_defaults(json=True)
    reload_parser = subparsers.add_parser("reload", help="Reload the current page.")
    reload_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    reload_parser.set_defaults(json=True)

    pushstate_parser = subparsers.add_parser("pushstate", help="Push browser history state.")
    pushstate_parser.add_argument("url")
    pushstate_parser.add_argument("--tab-id", default="", dest="switch_tab_id")
    pushstate_parser.set_defaults(json=True)

    mouse_parser = subparsers.add_parser("mouse", help="Coordinate-based mouse operations.")
    mouse_sub = mouse_parser.add_subparsers(dest="mouse_command", required=False)
    mc = mouse_sub.add_parser("click")
    mc.add_argument("--x", type=float, required=True)
    mc.add_argument("--y", type=float, required=True)
    mc.add_argument("--button", default="left")
    mc.add_argument("--click-count", type=int, default=1)
    mc.add_argument("--tab-id", default="", dest="switch_tab_id")
    mc.set_defaults(json=True)
    mm = mouse_sub.add_parser("move")
    mm.add_argument("--x", type=float, required=True)
    mm.add_argument("--y", type=float, required=True)
    mm.add_argument("--tab-id", default="", dest="switch_tab_id")
    mm.set_defaults(json=True)
    ms = mouse_sub.add_parser("scroll")
    ms.add_argument("--x", type=float, required=True)
    ms.add_argument("--y", type=float, required=True)
    ms.add_argument("--dx", type=float, default=0)
    ms.add_argument("--dy", type=float, default=0)
    ms.add_argument("--tab-id", default="", dest="switch_tab_id")
    ms.set_defaults(json=True)
    md = mouse_sub.add_parser("drag")
    md.add_argument("--from-x", type=float, required=True)
    md.add_argument("--from-y", type=float, required=True)
    md.add_argument("--to-x", type=float, required=True)
    md.add_argument("--to-y", type=float, required=True)
    md.add_argument("--duration-ms", type=int, default=None, dest="duration_ms")
    md.add_argument("--steps", type=int, default=None)
    md.add_argument("--jitter", type=float, default=None)
    md.add_argument("--overshoot", type=float, default=None)
    md.add_argument("--fast", action="store_true", default=False)
    md.add_argument("--tab-id", default="", dest="switch_tab_id")
    md.add_argument("--action-timeout", type=float, default=None, help="Daemon request timeout in seconds.")
    md.set_defaults(json=True)

    dom_parser = subparsers.add_parser("dom", help="DOM node interaction.")
    dom_sub = dom_parser.add_subparsers(dest="dom_command", required=False)
    dv = dom_sub.add_parser("visible")
    dv.add_argument("--limit", type=int, default=200)
    dv.add_argument("--tab-id", default="", dest="switch_tab_id")
    dv.set_defaults(json=True)
    dc = dom_sub.add_parser("click")
    dc.add_argument("node_id")
    dc.add_argument("--tab-id", default="", dest="switch_tab_id")
    dc.set_defaults(json=True)
    ddc = dom_sub.add_parser("dblclick")
    ddc.add_argument("node_id")
    ddc.add_argument("--tab-id", default="", dest="switch_tab_id")
    ddc.set_defaults(json=True)
    ds = dom_sub.add_parser("scroll")
    ds.add_argument("node_id")
    ds.add_argument("--dy", type=int, default=800)
    ds.add_argument("--tab-id", default="", dest="switch_tab_id")
    ds.set_defaults(json=True)

    console_parser = subparsers.add_parser("console", help="Console log operations.")
    console_sub = console_parser.add_subparsers(dest="console_command", required=False)
    cl = console_sub.add_parser("logs")
    cl.add_argument("--tab-id", default="")
    cl.set_defaults(json=True)
    ce = console_sub.add_parser("errors")
    ce.add_argument("--tab-id", default="")
    ce.set_defaults(json=True)
    cc = console_sub.add_parser("clear")
    cc.add_argument("--tab-id", default="")
    cc.set_defaults(json=True)

    dialog_parser = subparsers.add_parser("dialog", help="Browser JavaScript dialog operations.")
    dialog_sub = dialog_parser.add_subparsers(dest="dialog_command", required=False)
    dl = dialog_sub.add_parser("logs")
    dl.add_argument("--tab-id", default="")
    dl.set_defaults(json=True)
    dc = dialog_sub.add_parser("clear")
    dc.add_argument("--tab-id", default="")
    dc.set_defaults(json=True)
    dh = dialog_sub.add_parser("handle")
    dh.add_argument("choice", choices=["accept", "dismiss"])
    dh.add_argument("--text", default=None, help="Prompt text to submit when accepting a JavaScript prompt dialog.")
    dh.add_argument("--tab-id", default="")
    dh.set_defaults(json=True)

    network_parser = subparsers.add_parser("network", help="Network request operations.")
    network_sub = network_parser.add_subparsers(dest="network_command", required=False)
    nl = network_sub.add_parser("logs")
    nl.add_argument("--tab-id", default="")
    nl.set_defaults(json=True)
    ns = network_sub.add_parser("summary")
    ns.add_argument("--tab-id", default="")
    ns.set_defaults(json=True)
    for _name in ["start", "stop", "clear"]:
        _np = network_sub.add_parser(_name)
        _np.add_argument("--tab-id", default="")
        _np.set_defaults(json=True)

    cdp_parser = subparsers.add_parser("cdp", help="Send raw CDP command.")
    cdp_parser.add_argument("method")
    cdp_parser.add_argument("params_json", nargs="?", default="{}")
    cdp_parser.add_argument("--tab-id", default="")
    cdp_parser.set_defaults(json=True)

    verify_parser = subparsers.add_parser("verify", help="Inspect human-verification (captcha) widgets on the page.")
    verify_sub = verify_parser.add_subparsers(dest="verify_command", required=False)
    vi = verify_sub.add_parser("inspect", help="Detect and extract captcha metadata for an agent to solve.")
    vi.add_argument("--tab-id", default="")
    vi.add_argument("--no-image", action="store_true", default=False, help="Skip capturing the panel screenshot (faster, metadata only).")
    vi.set_defaults(json=True)

    clipboard_parser = subparsers.add_parser("clipboard", help="Clipboard operations.")
    clipboard_sub = clipboard_parser.add_subparsers(dest="clipboard_command", required=False)
    cr = clipboard_sub.add_parser("read")
    cr.add_argument("--tab-id", default="", dest="switch_tab_id")
    cr.set_defaults(json=True)
    cw = clipboard_sub.add_parser("write")
    cw.add_argument("text")
    cw.add_argument("--tab-id", default="", dest="switch_tab_id")
    cw.set_defaults(json=True)

    viewport_parser = subparsers.add_parser("viewport", help="Viewport operations.")
    viewport_sub = viewport_parser.add_subparsers(dest="viewport_command", required=False)
    vg = viewport_sub.add_parser("get")
    vg.add_argument("--tab-id", default="", dest="switch_tab_id")
    vg.set_defaults(json=True)
    vs = viewport_sub.add_parser("set")
    vs.add_argument("width", type=int)
    vs.add_argument("height", type=int)
    vs.add_argument("--tab-id", default="", dest="switch_tab_id")
    vs.set_defaults(json=True)

    assets_parser = subparsers.add_parser("assets", help="Page resource operations.")
    assets_sub = assets_parser.add_subparsers(dest="assets_command", required=False)
    al = assets_sub.add_parser("list")
    al.add_argument("--tab-id", default="", dest="switch_tab_id")
    al.set_defaults(json=True)
    ae = assets_sub.add_parser("export")
    ae.add_argument("-o", "--output", default="")
    ae.add_argument("--tab-id", default="", dest="switch_tab_id")
    ae.set_defaults(json=True)

    browser_parser = subparsers.add_parser("browser", help="Browser session operations.")
    browser_sub = browser_parser.add_subparsers(dest="browser_command", required=False)
    browser_sub.add_parser("list").set_defaults(json=True)
    browser_sub.add_parser("current").set_defaults(json=True)
    bcl = browser_sub.add_parser("claim")
    bcl.add_argument("tab_id")
    bcl.set_defaults(json=True)
    brl = browser_sub.add_parser("release")
    brl.add_argument("tab_id")
    brl.set_defaults(json=True)
    brc = browser_sub.add_parser("recently-closed")
    brc.add_argument("--max-results", type=int, default=10)
    brc.add_argument("--tab-id", default="")
    brc.set_defaults(json=True)
    bts = browser_sub.add_parser("top-sites")
    bts.add_argument("--tab-id", default="")
    bts.set_defaults(json=True)
    bex = browser_sub.add_parser("extensions", help="List installed browser extensions.")
    bex.add_argument("--tab-id", default="")
    bex.set_defaults(json=True)
    bcs = browser_sub.add_parser("content-settings", help="Read a browser content setting (read-only).")
    bcs.add_argument("type", default="automaticDownloads", nargs="?")
    bcs.add_argument("url", default="https://example.com/", nargs="?")
    bcs.add_argument("--tab-id", default="")
    bcs.set_defaults(json=True)
    bmv = browser_sub.add_parser("mouse-visual-state", help="Inspect the visual mouse bridge state (read-only).")
    bmv.add_argument("--tab-id", default="")
    bmv.set_defaults(json=True)
    bbs = browser_sub.add_parser("bookmarks", help="Read the browser bookmark tree.")
    bbs.add_argument("--tab-id", default="")
    bbs.set_defaults(json=True)
    bds = browser_sub.add_parser("downloads", help="Inspect browser downloads.")
    bds.add_argument("query", nargs="*")
    bds.add_argument("--id", dest="download_id")
    bds.add_argument("--limit", type=int, default=20)
    bds.add_argument("--tab-id", default="")
    bds.set_defaults(json=True)
    bhs = browser_sub.add_parser("history", help="Search browser history.")
    bhs.add_argument("text", nargs="?", default="")
    bhs.add_argument("--max-results", type=int, default=20)
    bhs.add_argument("--start-time", type=float)
    bhs.add_argument("--end-time", type=float)
    bhs.add_argument("--tab-id", default="")
    bhs.set_defaults(json=True)
    bn = browser_sub.add_parser("notify")
    bn.add_argument("title")
    bn.add_argument("message", nargs="?", default="")
    bn.add_argument("--priority", type=int, default=0)
    bn.add_argument("--id", dest="notification_id", default="")
    bn.add_argument("--tab-id", default="")
    bn.set_defaults(json=True)

    history_parser = subparsers.add_parser("history", help="Search browser history.")
    history_sub = history_parser.add_subparsers(dest="history_command", required=False)
    hs = history_sub.add_parser("search")
    hs.add_argument("text", nargs="?", default="")
    hs.add_argument("--max-results", type=int, default=20)
    hs.add_argument("--start-time", type=float)
    hs.add_argument("--end-time", type=float)
    hs.add_argument("--tab-id", default="")
    hs.set_defaults(json=True)

    bookmarks_parser = subparsers.add_parser("bookmarks", help="Read browser bookmarks.")
    bookmarks_sub = bookmarks_parser.add_subparsers(dest="bookmarks_command", required=False)
    bt = bookmarks_sub.add_parser("tree")
    bt.add_argument("--tab-id", default="")
    bt.set_defaults(json=True)

    downloads_parser = subparsers.add_parser("downloads", help="Inspect browser downloads.")
    downloads_sub = downloads_parser.add_subparsers(dest="downloads_command", required=False)
    ds = downloads_sub.add_parser("search")
    ds.add_argument("query", nargs="*")
    ds.add_argument("--id", dest="download_id")
    ds.add_argument("--limit", type=int, default=20)
    ds.add_argument("--tab-id", default="")
    ds.set_defaults(json=True)
    do = downloads_sub.add_parser("open")
    do.add_argument("download_id")
    do.add_argument("--tab-id", default="")
    do.set_defaults(json=True)

    session_parser = subparsers.add_parser("session", help="Session operations.")
    session_sub = session_parser.add_subparsers(dest="session_command", required=False)
    sn = session_sub.add_parser("name")
    sn.add_argument("name")
    sn.set_defaults(json=True)
    session_sub.add_parser("list").set_defaults(json=True)

    record_parser = subparsers.add_parser("record", help="Record operations.")
    record_sub = record_parser.add_subparsers(dest="record_command", required=False)
    record_sub.add_parser("start").set_defaults(json=True)
    rs = record_sub.add_parser("stop")
    rs.add_argument("-o", "--output", default="")
    rs.set_defaults(json=True)

    replay_parser = subparsers.add_parser("replay", help="Replay recorded flow.")
    replay_parser.add_argument("flow_file")
    replay_parser.set_defaults(json=True)

    trace_parser = subparsers.add_parser("trace", help="Trace operations.")
    trace_sub = trace_parser.add_subparsers(dest="trace_command", required=False)
    trace_sub.add_parser("start").set_defaults(json=True)
    ts = trace_sub.add_parser("stop")
    ts.add_argument("-o", "--output", default="")
    ts.set_defaults(json=True)

    visibility_parser = subparsers.add_parser("visibility", help="Automation browser visibility mode.")
    visibility_sub = visibility_parser.add_subparsers(dest="visibility_command", required=False)
    visibility_sub.add_parser("status").set_defaults(json=True)
    sv = visibility_sub.add_parser("set")
    sv.add_argument("mode", choices=["visible", "background", "dedicated-profile", "headless"])
    sv.add_argument("--browser", choices=BROWSER_CHOICES)
    sv.add_argument("--user-data-dir")
    sv.add_argument("--remote-debugging-port", type=int, default=9222)
    sv.set_defaults(json=True)
    lv = visibility_sub.add_parser("launch")
    lv.add_argument("mode", choices=["dedicated-profile", "headless"])
    lv.add_argument("--browser", choices=BROWSER_CHOICES, default="chrome")
    lv.add_argument("--user-data-dir", required=True)
    lv.add_argument("--remote-debugging-port", type=int, default=9222)
    lv.set_defaults(json=True)

    execute_js.set_defaults(json=True)

    batch = subparsers.add_parser("batch", help="Send multiple extension/CDP commands in one request.")
    batch.add_argument("commands_json", nargs="?", help="JSON array of commands.")
    batch.add_argument("--file", help="Read commands from file.")
    batch.add_argument("--tab-id", default="", help="Target tab ID.")
    batch.add_argument("--timeout", type=float, default=30, help="Timeout in seconds.")
    batch.set_defaults(json=True)

    wait = subparsers.add_parser("wait", help="Wait for time, selector, text, URL, load, or JS condition.")
    wait.add_argument("wait_target", nargs="?")
    wait.add_argument("--text")
    wait.add_argument("--url")
    wait.add_argument(
        "--load",
        nargs="?",
        const="load",
        choices=["load", "domcontentloaded", "networkidle"],
        metavar="{load,domcontentloaded,networkidle}",
        help="Wait for a page lifecycle event; defaults to 'load' when no value is given.",
    )
    wait.add_argument("--fn")
    wait.add_argument("--state", choices=["visible", "hidden"], default="visible")
    wait.add_argument("--timeout", type=float, default=10)
    wait.add_argument("--interval", type=float, default=0.5)
    wait.add_argument("--tab-id", default="", dest="switch_tab_id")
    wait.set_defaults(json=True)

    navigate = subparsers.add_parser("navigate", help="Open a URL in a new tab, or reuse the active tab.")
    navigate.add_argument("url", help="URL to navigate to.")
    navigate.add_argument("--same-tab", action="store_true", help="Navigate in the current tab instead of opening a new one.")
    navigate.add_argument("--new-tab", action="store_true", help="Explicitly open a new tab (the default; provided for agent/CLI compatibility).")
    navigate.add_argument("--tab-id", default="", dest="switch_tab_id", help="Target tab ID when --same-tab is used.")
    navigate.add_argument("--json", action="store_true", default=True, help="Return structured JSON output.")
    navigate.set_defaults(json=True)

    screenshot = subparsers.add_parser("screenshot", help="Capture a PNG screenshot from a browser tab.")
    screenshot.add_argument("--tab-id", default="", help="Target tab ID.")
    screenshot.add_argument("--base64", action="store_true", help="Return base64 instead of file path.")
    screenshot.add_argument("-o", "--output", help="Output file path.")
    screenshot.add_argument("--full", action="store_true", help="Capture full page content when supported.")
    screenshot.add_argument("--ref", help="Capture a visual region ref from snapshot, such as @e146.")
    screenshot.add_argument("--annotate", action="store_true", help="Overlay @eN labels before capture.")
    screenshot.add_argument("--screenshot-dir", help="Directory for default screenshot output.")
    screenshot.add_argument("--screenshot-format", choices=["png", "jpeg"], default="png")
    screenshot.add_argument("--screenshot-quality", type=int)
    screenshot.set_defaults(json=True)

    skills = subparsers.add_parser("skills", help="Install packaged omnibot skills for agent clients.")
    skills_sub = skills.add_subparsers(dest="skills_command", required=False)
    install = skills_sub.add_parser("install", help="Install skills for a specific agent.")
    install.add_argument("--agent", choices=["hermes", "opencode", "claude", "codex", "openclaw", "workbuddy", "trae"], required=True, help="Target agent.")
    install.add_argument("--profile", help="Specific profile to install.")
    install.add_argument("--all-profiles", action="store_true", help="Install all profiles.")
    install.add_argument("--target-dir", help="Custom installation directory.")
    install.set_defaults(json=True)
    skills_sub.add_parser("path", help="Show packaged skills directory path.").set_defaults(json=True)

    doctor = subparsers.add_parser("doctor", help="Check daemon and browser extension health.")
    doctor.set_defaults(json=True)

    version_parser = subparsers.add_parser("version", help="Print the omnibot CLI version.")
    version_parser.set_defaults(json=False)

    bridge_host = subparsers.add_parser("bridge-host", help=argparse.SUPPRESS)
    bridge_host.set_defaults(json=False)

    return parser


def _base_url(args: argparse.Namespace) -> str:
    if args.no_start:
        return daemon_client.daemon_url(port=args.api_port)
    if os.environ.get("OMNIBOT_SESSION_TOKEN"):
        return daemon_client.ensure_daemon(api_port=args.api_port, ws_port=args.ws_port)
    return daemon_client.ensure_runtime(api_port=args.api_port, ws_port=args.ws_port)


def _print_result(result: dict[str, Any], as_json: bool = True) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, default=str))
    else:
        print(result)


def _normalize_action_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") not in {"error", "timeout"} or result.get("error_code"):
        return result
    normalized = dict(result)
    message = str(result.get("msg") or result.get("error") or "")
    lowered = message.lower()
    if result.get("status") == "timeout":
        code = "ACTION_TIMEOUT"
    elif "no browser tabs connected" in lowered:
        code = "NO_BROWSER_TABS"
    elif "not found or ambiguous" in lowered or "no tab with id" in lowered or "no tab with given id" in lowered:
        code = "TAB_NOT_FOUND"
    elif "extension" in lowered and ("not connected" in lowered or "disconnected" in lowered):
        code = "EXTENSION_DISCONNECTED"
    else:
        code = "ACTION_FAILED"
    normalized["error_code"] = code
    return normalized


def _action_exit_code(result: dict[str, Any]) -> int:
    return 1 if result.get("status") in {"error", "timeout"} else 0


def _select_browser(browser: str | None) -> str:
    if browser:
        return browser
    print("Select a browser to install bridge for:")
    for index, key in enumerate(BROWSER_CHOICES, start=1):
        print(f"  {index}. {BROWSER_LABELS[key]}")
    choice = input("Browser [1]: ").strip() or "1"
    try:
        return BROWSER_CHOICES[int(choice) - 1]
    except Exception:
        lowered = choice.lower()
        if lowered in BROWSER_CHOICES:
            return lowered
    raise ValueError(f"Unsupported browser selection: {choice}")


def _wait_for_extension_id(base_url: str, browser: str, timeout: float) -> str | None:
    from .bridge_installer import find_extension_id

    deadline = time.time() + timeout
    while time.time() < deadline:
        result = daemon_client.call_action("tabs", {}, base_url)
        extension_id = find_extension_id(result.get("tabs", []), browser)
        if extension_id:
            return extension_id
        time.sleep(1)
    return None


def _print_bridge_install_result(result: dict[str, Any], bridge: dict[str, Any] | None) -> None:
    browser = str(result.get("browser") or "")
    label = BROWSER_LABELS.get(browser, browser or "Unknown")
    print("✔ Bridge installed")
    print(f"  Browser: {label}")
    print(f"  Extension ID: {result.get('extension_id')}")
    print(f"  Launcher: {result.get('launcher')}")
    print(f"  Manifest: {result.get('manifest')}")
    print()
    if bridge:
        print(f"✔ Bridge connected ({bridge.get('device_id')})")
        print("🎉 omnibot is ready.")
    else:
        print("Bridge installed, but no bridge connection was detected yet.")
        print("Reload the omnibot extension or restart the selected browser, then run `omnibot doctor`.")


def action_request_from_args(args: argparse.Namespace) -> tuple[str, dict[str, Any], bool]:
    if args.command == "tabs":
        return "tabs", {}, True
    if args.command == "read":
        return "read", {"url": args.url, "screens": args.screens, "switch_tab_id": args.switch_tab_id}, args.json
    if args.command == "snapshot":
        return "snapshot", {"interactive": args.interactive, "compact": args.compact, "max_depth": args.max_depth, "selector": args.selector, "include_urls": args.urls, "switch_tab_id": args.switch_tab_id}, args.json
    if args.command == "click":
        return "click", {"selector": args.selector, "new_tab": args.new_tab, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "dblclick":
        return "dblclick", {"selector": args.selector, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "fill":
        return "fill", {"selector": args.selector, "value": args.value, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "type":
        return "type", {"selector": args.selector, "text": args.text, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "press":
        return "press", {"key": args.key, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "keyboard":
        return "keyboard", {"keyboard_command": args.keyboard_command, "value": args.value, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "keydown":
        return "keydown", {"key": args.key, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "keyup":
        return "keyup", {"key": args.key, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "hover":
        return "hover", {"selector": args.selector, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "focus":
        return "focus", {"selector": args.selector, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "select":
        return "select", {"selector": args.selector, "value": args.value, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "check":
        return "check", {"selector": args.selector, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "uncheck":
        return "uncheck", {"selector": args.selector, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "scroll":
        return "scroll", {"direction": args.direction, "pixels": args.pixels, "selector": args.selector or "", "switch_tab_id": args.switch_tab_id}, True
    if args.command == "scrollintoview":
        return "scrollintoview", {"selector": args.selector, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "drag":
        return "drag", {"source": args.source, "target": args.target, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "upload":
        return "upload", {"selector": args.selector, "file": args.file, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "execute-js":
        script = Path(args.file).read_text(encoding="utf-8") if args.file else (args.script or "")
        return "execute_js", {"script": script, "switch_tab_id": args.switch_tab_id, "no_monitor": args.no_monitor}, True
    if args.command == "batch":
        raw = Path(args.file).read_text(encoding="utf-8") if args.file else args.commands_json
        commands = json.loads(raw or "[]")
        return "batch", {"commands": commands, "tab_id": args.tab_id, "timeout": args.timeout}, True
    if args.command == "wait":
        return "wait", {"wait_target": args.wait_target, "text": args.text, "url": args.url, "load": args.load, "fn": args.fn, "state": args.state, "timeout": args.timeout, "interval": args.interval, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "navigate":
        return "navigate", {"url": args.url, "new_tab": not args.same_tab, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "screenshot":
        return "screenshot", {
            "tab_id": args.tab_id,
            "full": args.full,
            "ref": args.ref or "",
            "annotate": args.annotate,
            "screenshot_format": args.screenshot_format,
            "screenshot_quality": args.screenshot_quality,
        }, True
    if args.command == "get":
        return "get", {"kind": args.get_command, "selector": getattr(args, "selector", None), "attr": getattr(args, "attr", None), "switch_tab_id": args.switch_tab_id}, True
    if args.command == "is":
        return "is", {"kind": args.is_command, "selector": args.selector, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "find":
        return "find", {
            "strategy": args.find_command,
            "value": getattr(args, "value", ""),
            "action": args.action,
            "action_value": getattr(args, "action_value", None),
            "name": getattr(args, "name", None),
            "exact": getattr(args, "exact", False),
            "index": getattr(args, "index", None),
            "selector": getattr(args, "selector", None),
            "switch_tab_id": args.switch_tab_id,
        }, True
    if args.command == "open":
        return "navigate", {"url": args.url, "new_tab": True}, True
    if args.command == "goto":
        return "navigate", {"url": args.url, "new_tab": False, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "close":
        return "close", {"tab_id": args.tab_id}, True
    if args.command == "tab":
        return "tab", {"tab_command": args.tab_command, "url": getattr(args, "url", None), "label": getattr(args, "label", None), "target": getattr(args, "target", None)}, True
    if args.command == "window":
        return "window", {"window_command": args.window_command, "url": getattr(args, "url", "about:blank")}, True
    if args.command == "frame":
        params = {"frame_target": args.frame_target}
        if args.switch_tab_id:
            params["switch_tab_id"] = args.switch_tab_id
        return "frame", params, True
    if args.command == "back":
        return "back", {"switch_tab_id": args.switch_tab_id}, True
    if args.command == "forward":
        return "forward", {"switch_tab_id": args.switch_tab_id}, True
    if args.command == "reload":
        return "reload", {"switch_tab_id": args.switch_tab_id}, True
    if args.command == "pushstate":
        return "pushstate", {"url": args.url, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "mouse":
        if args.mouse_command == "click":
            return "mouse_click", {"x": args.x, "y": args.y, "button": args.button, "click_count": args.click_count, "switch_tab_id": args.switch_tab_id}, True
        if args.mouse_command == "move":
            return "mouse_move", {"x": args.x, "y": args.y, "switch_tab_id": args.switch_tab_id}, True
        if args.mouse_command == "scroll":
            return "mouse_scroll", {"x": args.x, "y": args.y, "dx": args.dx, "dy": args.dy, "switch_tab_id": args.switch_tab_id}, True
        if args.mouse_command == "drag":
            return "mouse_drag", {"from_x": args.from_x, "from_y": args.from_y, "to_x": args.to_x, "to_y": args.to_y, "duration_ms": args.duration_ms, "steps": args.steps, "jitter": args.jitter, "overshoot": args.overshoot, "fast": args.fast, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "dom":
        if args.dom_command == "visible":
            return "dom_visible", {"limit": args.limit, "switch_tab_id": args.switch_tab_id}, True
        if args.dom_command == "click":
            return "dom_click", {"node_id": args.node_id, "switch_tab_id": args.switch_tab_id}, True
        if args.dom_command == "dblclick":
            return "dom_dblclick", {"node_id": args.node_id, "switch_tab_id": args.switch_tab_id}, True
        if args.dom_command == "scroll":
            return "dom_scroll", {"node_id": args.node_id, "dy": args.dy, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "console":
        if args.console_command == "logs":
            return "console_logs", {"tab_id": args.tab_id}, True
        if args.console_command == "errors":
            return "console_errors", {"tab_id": args.tab_id}, True
        if args.console_command == "clear":
            return "console_clear", {"tab_id": args.tab_id}, True
    if args.command == "dialog":
        if args.dialog_command == "logs":
            return "dialog_logs", {"tab_id": args.tab_id}, True
        if args.dialog_command == "clear":
            return "dialog_clear", {"tab_id": args.tab_id}, True
        if args.dialog_command == "handle":
            params = {"tab_id": args.tab_id, "accept": args.choice == "accept"}
            if args.text is not None:
                params["prompt_text"] = args.text
            return "dialog_handle", params, True
    if args.command == "network":
        if args.network_command == "logs":
            return "network_logs", {"tab_id": args.tab_id}, True
        if args.network_command == "summary":
            return "network_summary", {"tab_id": args.tab_id}, True
        if args.network_command == "start":
            return "network_capture_start", {"tab_id": args.tab_id}, True
        if args.network_command == "stop":
            return "network_capture_stop", {"tab_id": args.tab_id}, True
        if args.network_command == "clear":
            return "network_capture_clear", {"tab_id": args.tab_id}, True
    if args.command == "cdp":
        params = json.loads(args.params_json or "{}")
        return "raw_cdp", {"method": args.method, "params": params, "tab_id": args.tab_id}, True
    if args.command == "verify":
        if args.verify_command == "inspect":
            return "verify_inspect", {"tab_id": args.tab_id, "no_image": args.no_image}, True
    if args.command == "clipboard":
        if args.clipboard_command == "read":
            return "clipboard_read", {"switch_tab_id": args.switch_tab_id}, True
        if args.clipboard_command == "write":
            return "clipboard_write", {"text": args.text, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "viewport":
        if args.viewport_command == "get":
            return "viewport_get", {"switch_tab_id": args.switch_tab_id}, True
        if args.viewport_command == "set":
            return "viewport_set", {"width": args.width, "height": args.height, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "assets":
        if args.assets_command == "list":
            return "assets_list", {"switch_tab_id": args.switch_tab_id}, True
        if args.assets_command == "export":
            return "assets_export", {"output": args.output, "switch_tab_id": args.switch_tab_id}, True
    if args.command == "browser":
        if args.browser_command == "list":
            return "browser_list", {}, True
        if args.browser_command == "current":
            return "browser_current", {}, True
        if args.browser_command == "claim":
            return "browser_claim", {"tab_id": args.tab_id}, True
        if args.browser_command == "release":
            return "browser_release", {"tab_id": args.tab_id}, True
        if args.browser_command == "recently-closed":
            return "sessions_recently_closed", {"max_results": args.max_results, "tab_id": args.tab_id}, True
        if args.browser_command == "top-sites":
            return "top_sites", {"tab_id": args.tab_id}, True
        if args.browser_command == "extensions":
            return "browser_extensions", {"tab_id": args.tab_id}, True
        if args.browser_command == "content-settings":
            return "browser_content_settings", {"setting_type": args.type, "url": args.url, "tab_id": args.tab_id}, True
        if args.browser_command == "mouse-visual-state":
            return "browser_mouse_visual_state", {"tab_id": args.tab_id}, True
        if args.browser_command == "bookmarks":
            return "bookmarks_tree", {"tab_id": args.tab_id}, True
        if args.browser_command == "downloads":
            return "downloads_search", {"query": args.query, "download_id": args.download_id, "limit": args.limit, "tab_id": args.tab_id}, True
        if args.browser_command == "history":
            return "history_search", {"text": args.text, "max_results": args.max_results, "start_time": args.start_time, "end_time": args.end_time, "tab_id": args.tab_id}, True
        if args.browser_command == "notify":
            return "browser_notify", {"title": args.title, "message": args.message, "priority": args.priority, "notification_id": args.notification_id, "tab_id": args.tab_id}, True
    if args.command == "history" and args.history_command == "search":
        return "history_search", {"text": args.text, "max_results": args.max_results, "start_time": args.start_time, "end_time": args.end_time, "tab_id": args.tab_id}, True
    if args.command == "bookmarks" and args.bookmarks_command == "tree":
        return "bookmarks_tree", {"tab_id": args.tab_id}, True
    if args.command == "downloads":
        if args.downloads_command == "search":
            return "downloads_search", {"query": args.query, "download_id": args.download_id, "limit": args.limit, "tab_id": args.tab_id}, True
        if args.downloads_command == "open":
            return "downloads_open", {"download_id": args.download_id, "tab_id": args.tab_id}, True
    if args.command == "session":
        if args.session_command == "name":
            return "session_name", {"name": args.name}, True
        if args.session_command == "list":
            return "session_list", {}, True
    if args.command == "record":
        if args.record_command == "start":
            return "record_start", {}, True
        if args.record_command == "stop":
            return "record_stop", {"output": args.output}, True
    if args.command == "replay":
        return "replay", {"_flow_file": args.flow_file}, True
    if args.command == "trace":
        if args.trace_command == "start":
            return "trace_start", {}, True
        if args.trace_command == "stop":
            return "trace_stop", {"output": args.output}, True
    if args.command == "visibility":
        if args.visibility_command == "status":
            return "visibility_status", {}, True
        if args.visibility_command == "set":
            return "visibility_set", {"mode": args.mode}, True
        if args.visibility_command == "launch":
            return "visibility_launch", {"mode": args.mode, "browser": args.browser, "user_data_dir": args.user_data_dir, "remote_debugging_port": args.remote_debugging_port}, True
    raise ValueError(f"Unsupported command: {args.command}")


def run_command(args: argparse.Namespace) -> int:
    if args.command == "bridge-host":
        from .bridge_host import run as bridge_host_run
        return bridge_host_run()

    if args.command == "install-bridge":
        from .bridge_installer import BROWSER_LABELS as INSTALLER_BROWSER_LABELS, install_bridge, wait_for_bridge

        browser = _select_browser(args.browser)
        label = INSTALLER_BROWSER_LABELS.get(browser, browser)
        print(f"✔ Select a browser to install bridge for: {label}")
        base_url = daemon_client.ensure_runtime(api_port=args.api_port, ws_port=args.ws_port)
        extension_id = args.extension_id
        if not extension_id:
            print("Waiting for omnibot extension to report its extension ID...")
            extension_id = _wait_for_extension_id(base_url, browser, timeout=args.timeout)
        if not extension_id:
            print("Could not detect the omnibot extension ID.", file=sys.stderr)
            print(f"Open {label}, load or reload the omnibot extension, keep the browser open, then rerun `omnibot install-bridge --browser {browser}`.", file=sys.stderr)
            return 1
        result = install_bridge(extension_id=extension_id, browser=browser)
        print(f"  Launcher: {result.get('launcher')}")
        print(f"  Manifest: {result.get('manifest')}")
        print()
        bridge = wait_for_bridge(timeout=args.timeout)
        _print_bridge_install_result(result, bridge)
        return 0
    if args.command == "uninstall-bridge":
        from .bridge_installer import uninstall_bridge
        _print_result(uninstall_bridge(browser=args.browser))
        return 0

    if args.command == "daemon":
        if args.daemon_command == "run":
            from . import daemon

            daemon.run_foreground(api_port=args.api_port, ws_port=args.ws_port)
            return 0
        if args.daemon_command == "start":
            base_url = daemon_client.ensure_daemon(api_port=args.api_port, ws_port=args.ws_port)
            _print_result({"status": "success", "url": base_url})
            return 0
        if args.daemon_command == "stop":
            _print_result(daemon_client.stop_daemon(daemon_client.daemon_url(port=args.api_port)))
            return 0
        if args.daemon_command == "status":
            _print_result(daemon_client.health(daemon_client.daemon_url(port=args.api_port)) or {"status": "stopped"})
            return 0
        _print_group_help("daemon")
        return 0

    if args.command == "skills":
        if args.skills_command == "install":
            from .skill_installer import install
            result = install(agent=args.agent, profile=args.profile, all_profiles=args.all_profiles, target_dir=args.target_dir)
            _print_result(result)
            return 0
        if args.skills_command == "path":
            from .skill_installer import packaged_skills_dir
            _print_result({"status": "success", "path": str(packaged_skills_dir())})
            return 0
        _print_group_help("skills")
        return 0

    if args.command == "doctor":
        base_url = _base_url(args)
        daemon_health = daemon_client.health(base_url)
        # A healthy extension can briefly disappear from daemon state while its
        # WebSocket reconnects. Retry the empty state so doctor does not turn a
        # sub-second transport flap into misleading installation guidance.
        for _ in range(2):
            if not daemon_health or daemon_health.get("tabs_count", 0) > 0 or daemon_health.get("extension_clients_count", 0) > 0:
                break
            time.sleep(0.2)
            refreshed_health = daemon_client.health(base_url)
            if refreshed_health:
                daemon_health = refreshed_health
        extension = {"status": "unknown", "message": "Daemon health unavailable."}
        if daemon_health and (daemon_health.get("tabs_count", 0) > 0 or daemon_health.get("extension_clients_count", 0) > 0):
            extension = {"status": "connected", "message": "Browser extension is connected."}
            if "" in (daemon_health.get("extension_versions") or []):
                extension["status"] = "stale"
                extension["message"] = "Browser extension is connected, but it does not report a version; reload the current omnibot extension build."
        elif daemon_health:
            extension = {
                "status": "not_connected",
                "message": "Load or reload the omnibot browser extension, then keep an HTTP/HTTPS tab open.",
            }
        _print_result({"status": "success", "daemon": daemon_health, "extension": extension})
        return 0

    if args.command == "version":
        print(f"omnibot {_version()}")
        return 0

    base_url = _base_url(args)
    action, params, as_json = action_request_from_args(args)
    session_token = os.environ.get("OMNIBOT_SESSION_TOKEN")
    if session_token:
        params["_token"] = session_token
    if action == "replay":
        from .trace import parse_replay_payload

        flow_file = params.pop("_flow_file")
        flow = parse_replay_payload(json.loads(Path(flow_file).read_text(encoding="utf-8")))
        params["flow"] = flow
    action_timeout = getattr(args, "action_timeout", None)
    if action_timeout is None:
        result = daemon_client.call_action(action, params, base_url)
    else:
        result = daemon_client.call_action(action, params, base_url, timeout=action_timeout)
    result = _normalize_action_result(result)
    exit_code = _action_exit_code(result)
    if args.command == "read" and not as_json:
        from .output import read_to_text
        print(read_to_text(result))
        return exit_code
    if args.command == "snapshot" and not as_json:
        if result.get("status") == "success":
            print(str(result.get("content") or ""))
        else:
            _print_result(result, as_json=True)
        return exit_code
    if args.command == "screenshot" and not args.base64:
        from .output import write_screenshot_file
        result = write_screenshot_file(result, args.output, screenshot_dir=args.screenshot_dir)
    _print_result(result, as_json=as_json)
    return exit_code


def main(argv: list[str] | None = None) -> int:
    raw_argv = sys.argv[1:] if argv is None else list(argv)
    if not raw_argv:
        _print_concise_help()
        return 0
    if raw_argv in (["-h"], ["--help"]):
        print_help()
        return 0
    if raw_argv and raw_argv[0] in ("-V", "--version"):
        print(f"omnibot {_version()}")
        return 0

    parser = build_parser()
    args = parser.parse_args(raw_argv)

    if hasattr(args, "_daemon_alias"):
        alias = args._daemon_alias
        if alias == "run":
            from . import daemon
            daemon.run_foreground(api_port=args.api_port, ws_port=args.ws_port)
            return 0
        if alias == "start":
            base_url = daemon_client.ensure_daemon(api_port=args.api_port, ws_port=args.ws_port)
            _print_result({"status": "success", "url": base_url})
            return 0
        if alias == "stop":
            _print_result(daemon_client.stop_daemon(daemon_client.daemon_url(port=args.api_port)))
            return 0
        if alias == "status":
            _print_result(daemon_client.health(daemon_client.daemon_url(port=args.api_port)) or {"status": "stopped"})
            return 0

    if args.command in _subparser_aliases():
        subgroup = f"{args.command}_command"
        if not getattr(args, subgroup, None):
            _print_group_help(args.command)
            return 0

    try:
        return run_command(args)
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if "connection" in lowered or "remote end closed" in lowered:
            code = "DAEMON_DISCONNECTED"
        elif "timed out" in lowered or "timeout" in lowered:
            code = "DAEMON_TIMEOUT"
        else:
            code = "CLI_ERROR"
        print(json.dumps({"status": "error", "error_code": code, "msg": message}, ensure_ascii=False), file=sys.stdout)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
