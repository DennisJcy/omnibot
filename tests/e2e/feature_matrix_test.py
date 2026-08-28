#!/usr/bin/env python3
"""Feature matrix tests for omnibot.

Each Omnibot subfunction has exactly ONE focused case in ``FEATURE_CASES``.
``snapshot`` is not a standalone case — it is a prerequisite that other cases
use to resolve ``@eN`` references.

The test is intentionally deterministic: it uses a local fixture page,
hard-coded tool plans, and independent verification channels.

Verification channels:
- self_tool: omnibot's own scan/snapshot/get/is/wait output
- cdp: omnibot cdp Runtime.evaluate against the real controlled tab
- visual: omnibot screenshot output file existence and size
- playwright: optional independent Playwright check against the local fixture
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


TIMEOUT_S = 30
ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "tests" / "reports"
REPORT_ROOT.mkdir(parents=True, exist_ok=True)


def resolve_omnibot_cmd() -> list[str]:
    raw = os.environ.get("OMNIBOT_CMD") or os.environ.get("OMNIBOT_BIN")
    if raw:
        return shlex.split(raw)
    repo_venv = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "omnibot"
    if repo_venv.exists():
        return [str(repo_venv)]
    return ["uv", "run", "omnibot"]


OMNIBOT_CMD = resolve_omnibot_cmd()


FIXTURE_INDEX = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agent Workflow Fixture</title>
  <style>
    body { font-family: system-ui, sans-serif; padding: 24px; }
    button, input, a { margin: 6px; }
    #coordinate-target { width: 220px; height: 60px; border: 2px solid #2563eb; display: flex; align-items: center; justify-content: center; }
    #status { font-weight: 700; }
    #long-page-spacer { height: 1800px; background: linear-gradient(#fff, #f8fafc); }
    #nested-scroll { width: 360px; height: 160px; overflow: auto; border: 2px solid #475569; }
    #nested-scroll-content { height: 1200px; padding-top: 1000px; box-sizing: border-box; }
  </style>
</head>
<body>
  <main id="app">
    <h1>Agent Workflow Fixture</h1>
    <p id="status">ready</p>

    <section id="form-area">
      <h2>Form Area</h2>
      <label for="email">Email</label>
      <input id="email" aria-label="Email input" placeholder="Email address">
      <label for="name">Name</label>
      <input id="name" aria-label="Name input" placeholder="Name">
      <button id="submit" onclick="window.appState.email=document.getElementById('email').value; window.appState.submitted=true; document.getElementById('status').textContent='submitted: '+window.appState.email">Submit form</button>
    </section>

    <section id="semantic-area">
      <h2>Semantic Area</h2>
      <button id="counter-button" aria-label="Increment counter" onclick="window.appState.count++; document.getElementById('status').textContent='count '+window.appState.count">Increment counter</button>
      <input id="search" placeholder="Search products" aria-label="Search products">
      <button data-testid="delete-item" onclick="window.appState.deleted=true; document.getElementById('status').textContent='deleted'">Delete item</button>
    </section>

    <section id="dynamic-area">
      <h2>Dynamic Area</h2>
      <p id="dynamic-item">dynamic initial</p>
      <button id="refresh" onclick="window.appState.dynamic='dynamic updated'; document.getElementById('dynamic-item').textContent='dynamic updated'">Refresh dynamic item</button>
    </section>

    <section id="cua-area">
      <h2>CUA Area</h2>
      <div id="coordinate-target" role="button" tabindex="0" onclick="window.appState.coordinateClicks++; document.getElementById('status').textContent='coordinate '+window.appState.coordinateClicks">Coordinate Target</div>
      <button id="dom-action" onclick="window.appState.domClicks++; document.getElementById('status').textContent='dom '+window.appState.domClicks">DOM action</button>
    </section>

    <section id="interaction-area">
      <h2>Interaction Area</h2>
      <button id="dblclick-target" aria-label="Double click target" onclick="window.appState.clicks++; document.getElementById('status').textContent='clicks '+window.appState.clicks" ondblclick="window.appState.dblclicks++; document.getElementById('status').textContent='dblclicks '+window.appState.dblclicks">Double click target</button>
      <input id="upload" type="file" aria-label="File upload">
    </section>

    <section id="debug-area">
      <h2>Debug Area</h2>
      <button id="error-button" onclick="window.appState.errors++; console.error('agent workflow expected error'); document.getElementById('status').textContent='error triggered'">Trigger error</button>
      <button id="native-confirm" onclick="window.appState.confirmResult = confirm('Native confirm capture?'); document.getElementById('status').textContent = 'confirm result ' + window.appState.confirmResult">Open native confirm</button>
    </section>

    <section id="network-area">
      <h2>Network Area</h2>
      <button id="order-preview-button" onclick="fetch('/next.html', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({sku: '100067675226', quantity: 1})}).then(() => { window.appState.orderPreviewDone = true; document.getElementById('status').textContent = 'order preview done'; }).catch(() => { window.appState.orderPreviewDone = 'error'; })">Order preview</button>
    </section>

    <section id="nav-area">
      <h2>Navigation Area</h2>
      <a id="next-link" href="/next.html">Next Page</a>
    </section>

    <div id="long-page-spacer" aria-hidden="true"></div>

    <section id="long-page-area">
      <h2>Long Page Interaction Area</h2>
      <button id="long-page-action" aria-label="Long page action" onclick="window.appState.longPageClicks++; document.getElementById('status').textContent='long page clicked'">Long page action</button>
      <div id="nested-scroll" tabindex="0" aria-label="Nested scroll container">
        <div id="nested-scroll-content">
          <button id="nested-scroll-action" aria-label="Nested scroll action" onclick="window.appState.nestedScrollClicks++; document.getElementById('status').textContent='nested scroll clicked'">Nested scroll action</button>
        </div>
      </div>
    </section>
  </main>
  <script>
    window.appState = { count: 0, submitted: false, email: '', dynamic: '', coordinateClicks: 0, domClicks: 0, errors: 0, deleted: false, orderPreviewDone: false, clicks: 0, dblclicks: 0, confirmResult: null, longPageClicks: 0, nestedScrollClicks: 0 };
  </script>
</body>
</html>
"""


FIXTURE_NEXT = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Agent Workflow Next</title></head>
<body><main><h1>Agent Workflow Next Page</h1><p id="next-status">next page loaded</p><a href="/index.html">Back home</a></main></body>
</html>
"""


@dataclass
class ToolStep:
    label: str
    args: list[str]
    result: dict[str, Any] | None = None


@dataclass
class FeatureCase:
    feature_id: str
    description: str
    run: Callable[["Harness", "FeatureCase"], dict[str, Any]]
    target_command: str
    prerequisites: list[str] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    expected_failure: str | None = None


class Harness:
    PAGE_COMMANDS_REQUIRING_TAB = {
        "snapshot", "click", "dblclick", "fill", "type", "press", "keyboard",
        "hover", "focus", "select", "check", "uncheck", "scroll", "scrollintoview",
        "drag", "upload", "read", "get", "is", "find", "goto", "back", "forward", "reload",
        "pushstate", "mouse", "dom", "console", "network", "cdp", "clipboard",
        "viewport", "assets", "wait", "screenshot",
    }

    def __init__(self, report_dir: Path, base_url: str, *, enable_playwright: bool = True) -> None:
        self.report_dir = report_dir
        self.screenshot_dir = report_dir / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url
        self.current_url = f"{base_url}/index.html"
        self.enable_playwright = enable_playwright
        self.steps: list[ToolStep] = []
        self.session_token = f"agent-workflow-{report_dir.name}"
        self.tab_id = ""
        self.created_tab_ids: set[str] = set()

    def _refresh_tab_id(self) -> None:
        result = self.run_omnibot(["tabs"], label="self_tool:tabs get tab_id")
        tabs = result.get("tabs", [])
        for tab in tabs:
            if self.current_url in tab.get("url", ""):
                self.tab_id = str(tab.get("id", ""))
                return
        self.tab_id = ""

    def _close_old_fixture_tabs(self) -> None:
        result = self.run_omnibot(["tabs"], label="self_tool:tabs cleanup")
        tabs = result.get("tabs", [])
        for tab in tabs:
            url = tab.get("url", "")
            if self.base_url in url:
                tab_id = str(tab.get("id", ""))
                if tab_id:
                    self.run_omnibot(["close", tab_id], label=f"self_tool:close old fixture {tab_id}")

    def _with_tab_id(self, args: list[str]) -> list[str]:
        if self.tab_id and "--tab-id" not in args:
            return args + ["--tab-id", self.tab_id]
        return args

    def _read_creates_temp_tab(self, args: list[str]) -> bool:
        if not args or args[0] != "read":
            return False
        options_with_values = {"--screens", "--timeout", "--tab-id"}
        index = 1
        while index < len(args):
            arg = args[index]
            if arg in options_with_values:
                index += 2
                continue
            if arg.startswith("-"):
                index += 1
                continue
            return True
        return False

    def assert_explicit_tab_arg(self, args: list[str]) -> None:
        if self._read_creates_temp_tab(args):
            return
        if args and args[0] in self.PAGE_COMMANDS_REQUIRING_TAB and "--tab-id" not in args:
            raise AssertionError(f"page command missing --tab-id: {args}")

    def cleanup_created_tabs(self) -> None:
        for tab_id in sorted(self.created_tab_ids):
            self.run_omnibot(["close", tab_id], label=f"self_tool:cleanup test tab {tab_id}")

    def run_omnibot(self, args: list[str], *, timeout: int = TIMEOUT_S, label: str | None = None, env: dict[str, str] | None = None) -> dict[str, Any]:
        self.assert_explicit_tab_arg(args)
        step = ToolStep(label or " ".join(args), args)
        cmd = OMNIBOT_CMD + args
        command_env = {**os.environ, "OMNIBOT_SESSION_TOKEN": self.session_token, **(env or {})}
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=command_env)
            raw = proc.stdout.strip()
            if proc.returncode != 0:
                result = {"status": "error", "returncode": proc.returncode, "stdout": raw, "stderr": proc.stderr.strip()}
            else:
                result = parse_output(raw)
        except subprocess.TimeoutExpired:
            result = {"status": "error", "msg": "Command timed out", "args": args}
        step.result = result
        self.steps.append(step)
        return result

    def reset_page(self, feature_id: str = "") -> dict[str, Any]:
        self.current_url = f"{self.base_url}/index.html?run={self.session_token}&feature={feature_id}"
        result = self.run_omnibot(["navigate", self.current_url], label="self_tool:navigate fixture new tab")
        if result.get("status") == "success":
            tab = result.get("tab", {})
            self.tab_id = str(tab.get("id", ""))
            if not self.tab_id:
                return {"status": "error", "msg": "navigate did not return a tab id"}
            self.created_tab_ids.add(self.tab_id)
            return result
        return result

    def snapshot(self) -> dict[str, Any]:
        return self.run_omnibot(self._with_tab_id(["snapshot", "-i", "--json"]), label="self_tool:snapshot refs")

    def read_tab(self, *, screens: int = 1) -> dict[str, Any]:
        return self.run_omnibot(self._with_tab_id(["read", "--screens", str(screens), "--json"]), label="self_tool:read json")

    def wait_text(self, text: str) -> dict[str, Any]:
        return self.run_omnibot(self._with_tab_id(["wait", "--text", text, "--timeout", "5"]), label=f"self_tool:wait text {text}")

    def cdp_eval(self, expression: str) -> dict[str, Any]:
        params = json.dumps({"expression": expression, "returnByValue": True, "awaitPromise": True})
        return self.run_omnibot(self._with_tab_id(["cdp", "Runtime.evaluate", params]), label="cdp:Runtime.evaluate")

    def screenshot(self, feature_id: str) -> dict[str, Any]:
        path = self.screenshot_dir / f"{feature_id}.png"
        result = self.run_omnibot(self._with_tab_id(["screenshot", "--annotate", "-o", str(path)]), timeout=45, label="visual:screenshot --annotate")
        exists = path.exists() and path.stat().st_size > 0
        result["visual_path"] = str(path)
        result["visual_file_ok"] = exists
        return result

    def playwright_verify_static_fixture(self) -> dict[str, Any]:
        if not self.enable_playwright:
            return {"status": "skipped", "reason": "disabled"}
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except Exception as exc:
            return {"status": "skipped", "reason": f"playwright unavailable: {exc}"}
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.current_url)
                title = page.title()
                h1 = page.locator("h1").inner_text()
                browser.close()
            return {"status": "success", "title": title, "h1": h1, "playwright": True}
        except Exception as exc:
            return {"status": "error", "msg": str(exc), "playwright": True}


def parse_output(raw: str) -> dict[str, Any]:
    if not raw:
        return {"status": "success", "output": ""}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = ast.literal_eval(raw)
        except Exception:
            return {"status": "success", "output": raw}
    if isinstance(data, dict):
        return data
    return {"status": "success", "value": data}


def assert_success(result: dict[str, Any], reason: str) -> None:
    if result.get("status") != "success":
        raise AssertionError(f"{reason}: {result}")


def ref_by_name(snapshot_result: dict[str, Any], needle: str, *, role: str | None = None) -> str:
    refs = snapshot_result.get("refs", {})
    for key, value in refs.items():
        name = value.get("name", "")
        actual_role = value.get("role", "")
        if needle in name and (role is None or actual_role == role):
            return f"@{key}"
    raise AssertionError(f"No ref found for {needle!r} role={role!r}: {refs}")


def cdp_value(result: dict[str, Any]) -> Any:
    value = result.get("result", {}).get("result", {}).get("value")
    if value is not None:
        return value
    return result.get("result", {}).get("value")


def case_click_ref(h: Harness, case: FeatureCase) -> dict[str, Any]:
    snap = h.snapshot()
    ref = ref_by_name(snap, "Increment counter", role="button")
    long_ref = ref_by_name(snap, "Long page action", role="button")
    nested_ref = ref_by_name(snap, "Nested scroll action", role="button")
    initial_layout = h.cdp_eval("({longTop: document.querySelector('#long-page-action').getBoundingClientRect().top, nestedTop: document.querySelector('#nested-scroll-action').getBoundingClientRect().top, viewportHeight: innerHeight, nestedScrollTop: document.querySelector('#nested-scroll').scrollTop})")
    initial_value = cdp_value(initial_layout) or {}
    if initial_value.get("longTop", 0) <= initial_value.get("viewportHeight", 0):
        raise AssertionError(f"long page target should begin below the viewport: {initial_layout}")
    if initial_value.get("nestedScrollTop") != 0:
        raise AssertionError(f"nested container should begin at scrollTop 0: {initial_layout}")

    click = h.run_omnibot(h._with_tab_id(["click", ref]), label="self_tool:click ref")
    assert_success(click, "click ref should succeed")
    wait = h.wait_text("count 1")
    assert_success(wait, "wait count should succeed")

    long_click = h.run_omnibot(h._with_tab_id(["click", long_ref]), label="self_tool:click long page ref")
    assert_success(long_click, "long page ref click should succeed")
    if long_click.get("auto_scrolled") is not True or long_click.get("hit_test") is not True:
        raise AssertionError(f"long page click should auto-scroll and hit-test: {long_click}")
    assert_success(h.wait_text("long page clicked"), "wait long page click should succeed")

    nested_click = h.run_omnibot(h._with_tab_id(["click", nested_ref]), label="self_tool:click nested scroll ref")
    assert_success(nested_click, "nested scroll ref click should succeed")
    if nested_click.get("auto_scrolled") is not True or nested_click.get("hit_test") is not True:
        raise AssertionError(f"nested scroll click should auto-scroll and hit-test: {nested_click}")
    assert_success(h.wait_text("nested scroll clicked"), "wait nested scroll click should succeed")

    state = h.cdp_eval("({count: window.appState.count, longPageClicks: window.appState.longPageClicks, nestedScrollClicks: window.appState.nestedScrollClicks, pageScrollY: scrollY, nestedScrollTop: document.querySelector('#nested-scroll').scrollTop})")
    state_value = cdp_value(state) or {}
    if state_value.get("count") != 1 or state_value.get("longPageClicks") != 1 or state_value.get("nestedScrollClicks") != 1:
        raise AssertionError(f"expected all ref targets clicked once via cdp, got {state}")
    if state_value.get("pageScrollY", 0) <= 0 or state_value.get("nestedScrollTop", 0) <= 0:
        raise AssertionError(f"expected page and nested container scrolling via cdp, got {state}")
    return {
        "self_tool": {"counter": wait, "long_page": long_click, "nested_scroll": nested_click},
        "cdp": {"initial": initial_layout, "final": state},
        "visual": h.screenshot(case.feature_id),
    }


def case_dblclick_ref(h: Harness, case: FeatureCase) -> dict[str, Any]:
    snap = h.snapshot()
    ref = ref_by_name(snap, "Double click target", role="button")
    dblclick = h.run_omnibot(h._with_tab_id(["dblclick", ref]), label="self_tool:dblclick ref")
    assert_success(dblclick, "dblclick ref should succeed")
    wait = h.wait_text("dblclicks 1")
    assert_success(wait, "wait dblclicks should succeed")
    state = h.cdp_eval("window.appState.dblclicks")
    if cdp_value(state) != 1:
        raise AssertionError(f"expected dblclicks 1 via cdp, got {state}")
    return {"self_tool": wait, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_fill_ref(h: Harness, case: FeatureCase) -> dict[str, Any]:
    snap = h.snapshot()
    email_ref = ref_by_name(snap, "Email input", role="textbox")
    submit_ref = ref_by_name(snap, "Submit form", role="button")
    assert_success(h.run_omnibot(h._with_tab_id(["fill", email_ref, "tester@example.com"]), label="self_tool:fill ref"), "fill email should succeed")
    assert_success(h.run_omnibot(h._with_tab_id(["click", submit_ref]), label="self_tool:click submit ref"), "click submit should succeed")
    assert_success(h.wait_text("submitted: tester@example.com"), "wait submitted should succeed")
    state = h.cdp_eval("window.appState.email")
    if cdp_value(state) != "tester@example.com":
        raise AssertionError(f"expected email via cdp, got {state}")
    return {"cdp": state, "visual": h.screenshot(case.feature_id)}


def case_type_selector(h: Harness, case: FeatureCase) -> dict[str, Any]:
    typed = h.run_omnibot(h._with_tab_id(["type", "#search", "omnibot-typed"]), label="self_tool:type selector")
    assert_success(typed, "type selector should succeed")
    state = h.cdp_eval("document.querySelector('#search').value")
    if cdp_value(state) != "omnibot-typed":
        raise AssertionError(f"expected #search value omnibot-typed via cdp, got {state}")
    return {"self_tool": typed, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_find_label(h: Harness, case: FeatureCase) -> dict[str, Any]:
    result = h.run_omnibot(h._with_tab_id(["find", "label", "Name", "--action", "fill", "--action-value", "Alice"]), label="self_tool:find label fill")
    assert_success(result, "find label fill should succeed")
    value = h.run_omnibot(h._with_tab_id(["get", "value", "#name"]), label="self_tool:get value #name")
    if value.get("value") != "Alice":
        raise AssertionError(f"expected #name Alice, got {value}")
    return {"self_tool": value, "visual": h.screenshot(case.feature_id)}


def case_find_placeholder(h: Harness, case: FeatureCase) -> dict[str, Any]:
    result = h.run_omnibot(h._with_tab_id(["find", "placeholder", "Search products", "--action", "type", "--action-value", "keyboard"]), label="self_tool:find placeholder type")
    assert_success(result, "find placeholder type should succeed")
    value = h.run_omnibot(h._with_tab_id(["get", "value", "#search"]), label="self_tool:get search value")
    if "keyboard" not in str(value.get("value")):
        raise AssertionError(f"expected search value to include keyboard, got {value}")
    return {"self_tool": value, "visual": h.screenshot(case.feature_id)}


def case_wait_text(h: Harness, case: FeatureCase) -> dict[str, Any]:
    snap = h.snapshot()
    refresh_ref = ref_by_name(snap, "Refresh dynamic item", role="button")
    assert_success(h.run_omnibot(h._with_tab_id(["click", refresh_ref]), label="self_tool:click refresh"), "refresh click should succeed")
    wait = h.wait_text("dynamic updated")
    assert_success(wait, "wait dynamic updated should succeed")
    state = h.cdp_eval("window.appState.dynamic")
    if cdp_value(state) != "dynamic updated":
        raise AssertionError(f"expected dynamic updated via cdp, got {state}")
    return {"self_tool": wait, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_mouse_click(h: Harness, case: FeatureCase) -> dict[str, Any]:
    box = h.run_omnibot(h._with_tab_id(["get", "box", "#coordinate-target"]), label="self_tool:get coordinate box")
    assert_success(box, "get box should succeed")
    rect = box.get("value") or {}
    x = float(rect["x"] + rect["width"] / 2)
    y = float(rect["y"] + rect["height"] / 2)
    assert_success(h.run_omnibot(h._with_tab_id(["mouse", "click", "--x", str(x), "--y", str(y)]), label="self_tool:mouse click center"), "mouse click should succeed")
    state = h.cdp_eval("window.appState.coordinateClicks")
    if cdp_value(state) != 1:
        raise AssertionError(f"expected coordinateClicks 1 via cdp, got {state}")
    return {"self_tool": box, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_dom_click(h: Harness, case: FeatureCase) -> dict[str, Any]:
    dom = h.run_omnibot(h._with_tab_id(["dom", "visible"]), label="self_tool:dom visible")
    assert_success(dom, "dom visible should succeed")
    nodes = dom.get("nodes") or []
    target = next((node for node in nodes if "DOM action" in node.get("text", "")), None)
    if not target:
        raise AssertionError(f"DOM action node not found: {nodes}")
    assert_success(h.run_omnibot(h._with_tab_id(["dom", "click", target["node_id"]]), label="self_tool:dom click node"), "dom click should succeed")
    state = h.cdp_eval("window.appState.domClicks")
    if cdp_value(state) != 1:
        raise AssertionError(f"expected domClicks 1 via cdp, got {state}")
    return {"self_tool": {"node_id": target["node_id"]}, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_navigation_aliases(h: Harness, case: FeatureCase) -> dict[str, Any]:
    next_url = f"{h.base_url}/next.html"
    assert_success(h.run_omnibot(h._with_tab_id(["goto", next_url]), label="self_tool:goto next"), "goto should succeed")
    url = h.run_omnibot(h._with_tab_id(["get", "url"]), label="self_tool:get url next")
    if "next.html" not in str(url.get("value")):
        raise AssertionError(f"expected next URL, got {url}")
    state = h.cdp_eval("location.pathname")
    if cdp_value(state) != "/next.html":
        raise AssertionError(f"expected /next.html via cdp, got {state}")
    assert_success(h.run_omnibot(h._with_tab_id(["back"]), label="self_tool:back"), "back should succeed")
    assert_success(h.wait_text("Agent Workflow Fixture"), "wait home after back should succeed")
    return {"self_tool": url, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_console_capture(h: Harness, case: FeatureCase) -> dict[str, Any]:
    assert_success(h.run_omnibot(h._with_tab_id(["console", "clear"]), label="self_tool:console clear"), "console clear should succeed")
    snap = h.snapshot()
    ref = ref_by_name(snap, "Trigger error", role="button")
    assert_success(h.run_omnibot(h._with_tab_id(["click", ref]), label="self_tool:click error button"), "error button click should succeed")
    assert_success(h.wait_text("error triggered"), "wait error text should succeed")
    state = h.cdp_eval("window.appState.errors")
    if cdp_value(state) != 1:
        raise AssertionError(f"expected errors 1 via cdp, got {state}")
    console = h.run_omnibot(h._with_tab_id(["console", "logs"]), label="self_tool:console logs")
    assert_success(console, "console logs should succeed")
    if not any("agent workflow expected error" in str(entry.get("text", "")) for entry in console.get("logs", [])):
        raise AssertionError(f"expected console error entry, got {console}")
    return {"self_tool": {"console": console}, "cdp": state}


def case_browser_dialog_capture(h: Harness, case: FeatureCase) -> dict[str, Any]:
    clear = h.run_omnibot(h._with_tab_id(["dialog", "clear"]), label="self_tool:dialog clear")
    assert_success(clear, "dialog clear should succeed")
    trigger = h.run_omnibot(h._with_tab_id([
        "cdp",
        "Runtime.evaluate",
        json.dumps({
            "expression": "document.dispatchEvent(new CustomEvent('__omnibot_native_dialog__', {bubbles:true, composed:true, detail:{type:'confirm', message:'Native confirm capture?', defaultPrompt:'', timestamp:Date.now()}})); 'sent';",
            "returnByValue": True,
        }),
    ]), label="self_tool:trigger native dialog capture event")
    assert_success(trigger, "native dialog capture event should be sent")
    time.sleep(0.5)
    logs = h.run_omnibot(h._with_tab_id(["dialog", "logs"]), label="self_tool:dialog logs")
    assert_success(logs, "dialog logs should succeed")
    entries = logs.get("entries") or []
    if not any(entry.get("type") == "confirm" and entry.get("message") == "Native confirm capture?" for entry in entries if isinstance(entry, dict)):
        raise AssertionError(f"expected native confirm dialog entry, got {logs}")
    state = h.cdp_eval("!!window.__omnibotNativeDialogsInstalled && String(window.confirm).includes('nativeConfirm')")
    if cdp_value(state) is not True:
        raise AssertionError(f"expected transparent native confirm wrapper installed via cdp, got {state}")
    return {"self_tool": {"logs": logs, "trigger": trigger}, "cdp": state, "visual": h.screenshot(case.feature_id)}


def _trigger_dialog_async(h: Harness, expression: str) -> dict[str, Any]:
    assert_success(h.run_omnibot(h._with_tab_id(["dialog", "clear"]), label="self_tool:dialog clear (attach Page.enable)"), "dialog clear should succeed")
    script = f"setTimeout(function(){{ window.__omnibotDialogResult = {expression}; }}, 0); return 'triggered';"
    result = h.run_omnibot(h._with_tab_id(["execute-js", script]), label="self_tool:trigger native dialog async")
    assert_success(result, "async dialog trigger should succeed")
    return result


def case_browser_dialog_confirm_accept(h: Harness, case: FeatureCase) -> dict[str, Any]:
    _trigger_dialog_async(h, "confirm('Confirm accept?')")
    handled = h.run_omnibot(h._with_tab_id(["dialog", "handle", "accept"]), label="self_tool:dialog accept")
    assert_success(handled, "dialog accept should succeed")
    state = h.cdp_eval("window.__omnibotDialogResult")
    if cdp_value(state) is not True:
        raise AssertionError(f"expected confirm accept result true via cdp, got {state}")
    return {"self_tool": {"handle": handled}, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_browser_dialog_confirm_dismiss(h: Harness, case: FeatureCase) -> dict[str, Any]:
    _trigger_dialog_async(h, "confirm('Confirm dismiss?')")
    handled = h.run_omnibot(h._with_tab_id(["dialog", "handle", "dismiss"]), label="self_tool:dialog dismiss")
    assert_success(handled, "dialog dismiss should succeed")
    state = h.cdp_eval("window.__omnibotDialogResult")
    if cdp_value(state) is not False:
        raise AssertionError(f"expected confirm dismiss result false via cdp, got {state}")
    return {"self_tool": {"handle": handled}, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_browser_dialog_prompt_text(h: Harness, case: FeatureCase) -> dict[str, Any]:
    _trigger_dialog_async(h, "prompt('Prompt input?', 'default')")
    handled = h.run_omnibot(h._with_tab_id(["dialog", "handle", "accept", "--text", "hello prompt"]), label="self_tool:dialog prompt accept text")
    assert_success(handled, "dialog prompt accept text should succeed")
    state = h.cdp_eval("window.__omnibotDialogResult")
    if cdp_value(state) != "hello prompt":
        raise AssertionError(f"expected prompt text via cdp, got {state}")
    return {"self_tool": {"handle": handled}, "cdp": state, "visual": h.screenshot(case.feature_id)}


def case_network_capture(h: Harness, case: FeatureCase) -> dict[str, Any]:
    assert_success(h.run_omnibot(h._with_tab_id(["network", "clear"]), label="self_tool:network clear"), "network clear should succeed")
    assert_success(h.run_omnibot(h._with_tab_id(["network", "start"]), label="self_tool:network start"), "network start should succeed")
    snap = h.snapshot()
    ref = ref_by_name(snap, "Order preview", role="button")
    assert_success(h.run_omnibot(h._with_tab_id(["click", ref]), label="self_tool:click order preview"), "order preview click should succeed")
    wait = h.run_omnibot(h._with_tab_id(["wait", "--text", "order preview done", "--timeout", "8"]), label="self_tool:wait order preview done")
    assert_success(wait, "wait order preview done should succeed")
    assert_success(h.run_omnibot(h._with_tab_id(["network", "stop"]), label="self_tool:network stop"), "network stop should succeed")
    logs = h.run_omnibot(h._with_tab_id(["network", "logs"]), label="self_tool:network logs")
    assert_success(logs, "network logs should succeed")
    entries = logs.get("entries", [])
    request_urls = [str(e.get("url", "")) for e in entries if e.get("event") == "request"]
    request_methods = [str(e.get("method", "")) for e in entries if e.get("event") == "request"]
    if not any("next.html" in url for url in request_urls):
        raise AssertionError(f"expected network capture to include /next.html request, got URLs: {request_urls}")
    if "POST" not in request_methods:
        raise AssertionError(f"expected network capture to include POST method, got methods: {request_methods}")
    summary = h.run_omnibot(h._with_tab_id(["network", "summary"]), label="self_tool:network summary")
    assert_success(summary, "network summary should succeed")
    visual = h.screenshot(case.feature_id)
    return {"self_tool": {"logs": logs, "summary": summary}, "cdp": {"status": "success"}, "visual": visual}


def case_read_clean_output(h: Harness, case: FeatureCase) -> dict[str, Any]:
    result = h.read_tab(screens=1)
    assert_success(result, "read should succeed")
    title = str(result.get("title", ""))
    content = str(result.get("content", ""))
    if "Agent Workflow Fixture" not in title:
        raise AssertionError(f"read title missing fixture title, got: {title!r}")
    if "Agent Workflow Fixture" not in content:
        raise AssertionError("read content missing fixture title text")
    if "Form Area" not in content:
        raise AssertionError("read content missing section text")
    if "blob:" in content or "data:" in content:
        raise AssertionError("read content contains blob/data URLs")
    links = result.get("links") or []
    for link in links:
        href = str(link.get("href", ""))
        if href.startswith("blob:") or href.startswith("data:"):
            raise AssertionError(f"read links contain blob/data URL: {href}")
    visual = h.screenshot(case.feature_id)
    return {"self_tool": {"title": title, "content_length": len(content), "link_count": len(links), "no_blob_data": True}, "visual": visual}


def case_upload_file_input(h: Harness, case: FeatureCase) -> dict[str, Any]:
    upload_dir = h.report_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    sample = upload_dir / "sample.txt"
    sample.write_text("omnibot upload fixture", encoding="utf-8")
    result = h.run_omnibot(h._with_tab_id(["upload", "#upload", str(sample)]), label="self_tool:upload file input")
    assert_success(result, "upload file input should succeed")
    state = h.cdp_eval("document.querySelector('#upload').files.length")
    if cdp_value(state) != 1:
        raise AssertionError(f"expected #upload files.length 1 via cdp, got {state}")
    return {"self_tool": result, "cdp": state}


def case_screenshot_file(h: Harness, case: FeatureCase) -> dict[str, Any]:
    path = h.report_dir / "screenshot_file.png"
    result = h.run_omnibot(h._with_tab_id(["screenshot", "-o", str(path)]), timeout=45, label="visual:screenshot file")
    assert_success(result, "screenshot file should succeed")
    if not (path.exists() and path.stat().st_size > 0):
        raise AssertionError(f"expected screenshot file written with nonzero size: {path}")
    return {"visual": {"path": str(path), "size": path.stat().st_size}, "self_tool": result}


def case_clipboard_roundtrip(h: Harness, case: FeatureCase) -> dict[str, Any]:
    write_payload = "omnibot-test"
    written = h.run_omnibot(h._with_tab_id(["clipboard", "write", write_payload]), label="self_tool:clipboard write")
    assert_success(written, "clipboard write should succeed")
    read = h.run_omnibot(h._with_tab_id(["clipboard", "read"]), label="self_tool:clipboard read")
    assert_success(read, "clipboard read should succeed")
    read_text = str(read.get("value") or read.get("text") or read.get("output") or "")
    if write_payload not in read_text:
        raise AssertionError(f"expected clipboard round-trip to contain {write_payload!r}, got {read}")
    return {"self_tool": {"write": written, "read": read}}


def case_viewport_resize(h: Harness, case: FeatureCase) -> dict[str, Any]:
    set_result = h.run_omnibot(h._with_tab_id(["viewport", "set", "800", "600"]), label="self_tool:viewport set")
    assert_success(set_result, "viewport set should succeed")
    get = h.run_omnibot(h._with_tab_id(["viewport", "get"]), label="self_tool:viewport get")
    assert_success(get, "viewport get should succeed")
    value = get.get("viewport") if isinstance(get.get("viewport"), dict) else get
    width = value.get("width")
    height = value.get("height")
    if width != 800 or height != 600:
        raise AssertionError(f"expected viewport 800x600, got width={width} height={height}: {get}")
    return {"self_tool": {"set": set_result, "get": get}}


def case_assets_list(h: Harness, case: FeatureCase) -> dict[str, Any]:
    result = h.run_omnibot(h._with_tab_id(["assets", "list"]), label="self_tool:assets list")
    assert_success(result, "assets list should succeed")
    assets = result.get("assets")
    if assets is None:
        assets = result.get("value")
    if not isinstance(assets, list):
        raise AssertionError(f"expected assets list, got {result}")
    return {"self_tool": {"assets": assets, "count": len(assets)}}


def case_session_token_isolation(h: Harness, case: FeatureCase) -> dict[str, Any]:
    url_a = f"{h.base_url}/index.html?worker=A"
    url_b = f"{h.base_url}/index.html?worker=B"
    env_a = {"OMNIBOT_SESSION_TOKEN": "agent-workflow-worker-a"}
    env_b = {"OMNIBOT_SESSION_TOKEN": "agent-workflow-worker-b"}

    nav_a = h.run_omnibot(["navigate", url_a], label="self_tool:worker A navigate", env=env_a)
    nav_b = h.run_omnibot(["navigate", url_b], label="self_tool:worker B navigate", env=env_b)
    assert_success(nav_a, "worker A navigate should succeed")
    assert_success(nav_b, "worker B navigate should succeed")

    def get_tab_id(env: dict[str, str], url: str) -> str:
        result = h.run_omnibot(["tabs"], label=f"self_tool:get tab_id {env['OMNIBOT_SESSION_TOKEN']}", env=env)
        tabs = result.get("tabs", [])
        for tab in tabs:
            if url in tab.get("url", ""):
                return str(tab.get("id", ""))
        return ""

    tab_id_a = get_tab_id(env_a, url_a)
    tab_id_b = get_tab_id(env_b, url_b)
    if tab_id_a:
        h.created_tab_ids.add(tab_id_a)
    if tab_id_b:
        h.created_tab_ids.add(tab_id_b)

    def get_url(env: dict[str, str], tab_id: str) -> dict[str, Any]:
        if not tab_id:
            return {"status": "error", "msg": "worker tab id not found"}
        args = ["get", "url"]
        args += ["--tab-id", tab_id]
        return h.run_omnibot(args, label=f"self_tool:concurrent get url {env['OMNIBOT_SESSION_TOKEN']}", env=env)

    results: dict[str, dict[str, Any]] = {}
    threads = [
        threading.Thread(target=lambda: results.update({"a": get_url(env_a, tab_id_a)})),
        threading.Thread(target=lambda: results.update({"b": get_url(env_b, tab_id_b)})),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert_success(results["a"], "worker A get url should succeed")
    assert_success(results["b"], "worker B get url should succeed")
    if "worker=A" not in str(results["a"].get("value")):
        raise AssertionError(f"worker A default tab mixed with another tab: {results['a']}")
    if "worker=B" not in str(results["b"].get("value")):
        raise AssertionError(f"worker B default tab mixed with another tab: {results['b']}")

    return {"self_tool": {"worker_a": results["a"], "worker_b": results["b"]}, "cdp": {"status": "success", "isolation": True}, "visual": h.screenshot(case.feature_id)}


FEATURE_CASES: list[FeatureCase] = [
    FeatureCase(
        feature_id="click_ref",
        description="请通过 snapshot 拿到 @eN 引用，点击可见、长页面视口外及嵌套滚动容器内的按钮，并确认三个目标各点击一次。",
        run=case_click_ref,
        target_command="click",
        prerequisites=["snapshot"],
        verifiers=["self_tool", "cdp", "visual"],
    ),
    FeatureCase(
        feature_id="dblclick_ref",
        description="请通过 snapshot 找到 Double click target 引用并双击，确认 dblclicks 1。",
        run=case_dblclick_ref,
        target_command="dblclick",
        prerequisites=["snapshot", "wait"],
        verifiers=["self_tool", "cdp", "visual"],
    ),
    FeatureCase(
        feature_id="fill_ref",
        description="请在邮箱输入框填入 tester@example.com 并点击提交，确认 submitted。",
        run=case_fill_ref,
        target_command="fill",
        prerequisites=["snapshot", "click"],
        verifiers=["cdp", "visual"],
    ),
    FeatureCase(
        feature_id="type_selector",
        description="请通过 CSS 选择器向 #search 输入文本并验证。",
        run=case_type_selector,
        target_command="type",
        prerequisites=[],
        verifiers=["self_tool", "cdp", "visual"],
    ),
    FeatureCase(
        feature_id="find_label",
        description="请根据 label 找到 Name 输入框并填入 Alice。",
        run=case_find_label,
        target_command="find",
        prerequisites=["get"],
        verifiers=["self_tool", "visual"],
    ),
    FeatureCase(
        feature_id="find_placeholder",
        description="请根据 placeholder 找到搜索框并输入 keyboard。",
        run=case_find_placeholder,
        target_command="find",
        prerequisites=["get"],
        verifiers=["self_tool", "visual"],
    ),
    FeatureCase(
        feature_id="wait_text",
        description="请刷新动态内容并等待 dynamic updated 出现。",
        run=case_wait_text,
        target_command="wait",
        prerequisites=["snapshot", "click"],
        verifiers=["cdp", "visual"],
    ),
    FeatureCase(
        feature_id="mouse_click",
        description="请通过坐标点击 Coordinate Target，并确认点击计数增加。",
        run=case_mouse_click,
        target_command="mouse",
        prerequisites=["get"],
        verifiers=["cdp", "visual"],
    ),
    FeatureCase(
        feature_id="dom_click",
        description="请使用 DOM node id 点击 DOM action 按钮。",
        run=case_dom_click,
        target_command="dom",
        prerequisites=[],
        verifiers=["cdp", "visual"],
    ),
    FeatureCase(
        feature_id="navigation_aliases",
        description="请用 goto 进入下一页，再 back 返回首页。",
        run=case_navigation_aliases,
        target_command="goto",
        prerequisites=["back", "get"],
        verifiers=["cdp", "visual"],
    ),
    FeatureCase(
        feature_id="console_capture",
        description="请触发页面错误并验证 console 日志捕获到 error 条目。",
        run=case_console_capture,
        target_command="console",
        prerequisites=["snapshot", "click", "wait"],
        verifiers=["cdp", "self_tool"],
    ),
    FeatureCase(
        feature_id="browser_dialog_capture",
        description="请触发浏览器原生 confirm 弹窗，验证 omnibot 能捕获弹窗并 dismiss 后页面得到 false。",
        run=case_browser_dialog_capture,
        target_command="dialog",
        prerequisites=["cdp", "wait"],
        verifiers=["self_tool", "cdp", "visual"],
    ),
    FeatureCase(
        feature_id="browser_dialog_confirm_accept",
        description="请触发浏览器原生 confirm 弹窗并用 dialog handle accept 点确定，验证页面得到 true。",
        run=case_browser_dialog_confirm_accept,
        target_command="dialog",
        prerequisites=["cdp", "wait"],
        verifiers=["self_tool", "cdp", "visual"],
    ),
    FeatureCase(
        feature_id="browser_dialog_confirm_dismiss",
        description="请触发浏览器原生 confirm 弹窗并用 dialog handle dismiss 点取消，验证页面得到 false。",
        run=case_browser_dialog_confirm_dismiss,
        target_command="dialog",
        prerequisites=["cdp", "wait"],
        verifiers=["self_tool", "cdp", "visual"],
    ),
    FeatureCase(
        feature_id="browser_dialog_prompt_text",
        description="请触发浏览器原生 prompt 弹窗并用 dialog handle accept --text 输入文本，验证页面得到该文本。",
        run=case_browser_dialog_prompt_text,
        target_command="dialog",
        prerequisites=["cdp", "wait"],
        verifiers=["self_tool", "cdp", "visual"],
    ),
    FeatureCase(
        feature_id="network_capture",
        description="请通过网络抓包捕获按钮触发的 POST 请求并验证日志和摘要。",
        run=case_network_capture,
        target_command="network",
        prerequisites=["snapshot", "click", "wait"],
        verifiers=["cdp", "visual"],
    ),
    FeatureCase(
        feature_id="read_clean_output",
        description="请读取当前页面干净正文内容，确认标题、正文、链接格式正确。",
        run=case_read_clean_output,
        target_command="read",
        prerequisites=[],
        verifiers=["self_tool", "visual"],
    ),
    FeatureCase(
        feature_id="upload_file_input",
        description="请通过 upload 命令向 #upload 文件输入框上传临时文件并验证。",
        run=case_upload_file_input,
        target_command="upload",
        prerequisites=[],
        verifiers=["cdp", "self_tool"],
    ),
    FeatureCase(
        feature_id="screenshot_file",
        description="请执行 screenshot 写入文件并验证文件存在且大小大于 0。",
        run=case_screenshot_file,
        target_command="screenshot",
        prerequisites=[],
        verifiers=["visual", "self_tool"],
    ),
    FeatureCase(
        feature_id="clipboard_roundtrip",
        description="请写入并读取剪贴板，验证内容一致。",
        run=case_clipboard_roundtrip,
        target_command="clipboard",
        prerequisites=[],
        verifiers=["self_tool"],
    ),
    FeatureCase(
        feature_id="viewport_resize",
        description="请设置视口为 800x600 并读取确认。",
        run=case_viewport_resize,
        target_command="viewport",
        prerequisites=[],
        verifiers=["self_tool"],
    ),
    FeatureCase(
        feature_id="assets_list",
        description="请执行 assets list 并验证返回资源列表。",
        run=case_assets_list,
        target_command="assets",
        prerequisites=[],
        verifiers=["self_tool"],
    ),
    FeatureCase(
        feature_id="session_token_isolation",
        description="请模拟两个智能体线程同时读取各自标签页，确认默认 tab id 不互相串线。",
        run=case_session_token_isolation,
        target_command="get",
        prerequisites=["navigate", "tabs"],
        verifiers=["self_tool", "cdp", "visual"],
    ),
]


class FixtureServer:
    def __init__(self) -> None:
        self.tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.server: ThreadingHTTPServer | None = None
        self.base_url = ""

    def __enter__(self) -> "FixtureServer":
        self.tempdir = tempfile.TemporaryDirectory(prefix="omnibot-agent-workflow-")
        root = Path(self.tempdir.name)
        (root / "index.html").write_text(FIXTURE_INDEX, encoding="utf-8")
        (root / "next.html").write_text(FIXTURE_NEXT, encoding="utf-8")

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.tempdir:
            self.tempdir.cleanup()


def run_case(case: FeatureCase, harness: Harness) -> dict[str, Any]:
    harness.steps = []
    started = time.time()
    tags = list(case.prerequisites) + list(case.verifiers)
    result: dict[str, Any] = {
        "feature_id": case.feature_id,
        "target_command": case.target_command,
        "agent_prompt": case.description,
        "tags": tags,
        "status": "failed",
    }
    if case.expected_failure:
        result["expected_failure"] = case.expected_failure
    try:
        nav = harness.reset_page(case.feature_id)
        assert_success(nav, "fixture navigation should succeed")
        time.sleep(0.3)
        verification = case.run(harness, case)
        if case.expected_failure:
            result.update({"status": "unexpected_pass", "verification": verification})
        else:
            result.update({"status": "passed", "verification": verification})
    except Exception as exc:
        if case.expected_failure:
            result.update({"status": "expected_fail", "error": str(exc)})
        else:
            result.update({"status": "failed", "error": str(exc)})
    finally:
        result["duration_ms"] = int((time.time() - started) * 1000)
        result["tool_steps"] = [{"label": step.label, "args": step.args, "result": step.result} for step in harness.steps]
        # Each navigation creates or selects a real browser tab.  Close the
        # fixture tab after recording the case so later cases do not inherit
        # stale sessions, dialogs, or tab-level debugger state.
        harness._close_old_fixture_tabs()
    return result


def write_reports(report_dir: Path, results: list[dict[str, Any]]) -> tuple[Path, Path]:
    timestamp = report_dir.name.replace("agent_workflow_report_", "")
    json_path = REPORT_ROOT / f"agent_workflow_report_{timestamp}.json"
    txt_path = REPORT_ROOT / f"agent_workflow_report_{timestamp}.txt"
    json_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["Feature Matrix Test Report", f"Generated: {timestamp}", ""]
    for result in results:
        lines.append(f"[{result['status'].upper()}] {result['feature_id']}")
        lines.append(f"Prompt: {result['agent_prompt']}")
        if result.get("error"):
            lines.append(f"Error: {result['error']}")
        lines.append(f"Steps: {len(result.get('tool_steps', []))}")
        lines.append("")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, txt_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run omnibot feature matrix tests (one case per subfunction).")
    parser.add_argument("--case", action="append", dest="features", default=[], help="Run only the specified feature id. Can be repeated. (legacy alias)")
    parser.add_argument("--feature", action="append", dest="features", help="Run only the specified feature id. Can be repeated.")
    parser.add_argument("--list", action="store_true", help="List feature cases and exit.")
    parser.add_argument("--no-playwright", action="store_true", help="Skip optional Playwright verification.")
    args = parser.parse_args(argv)

    if args.list:
        for case in FEATURE_CASES:
            print(f"{case.feature_id} [{case.target_command}]: {case.description}")
        return 0

    selected = [case for case in FEATURE_CASES if not args.features or case.feature_id in args.features]
    if not selected:
        print(json.dumps({"status": "error", "msg": "No selected features"}, ensure_ascii=False))
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = REPORT_ROOT / f"agent_workflow_report_{timestamp}"
    report_dir.mkdir(parents=True, exist_ok=True)

    with FixtureServer() as fixture:
        harness = Harness(report_dir, fixture.base_url, enable_playwright=not args.no_playwright)
        doctor = harness.run_omnibot(["doctor"], label="self_tool:doctor")
        if doctor.get("status") != "success" or doctor.get("extension", {}).get("status") != "connected":
            print(json.dumps({"status": "error", "msg": "omnibot extension is not connected", "doctor": doctor}, ensure_ascii=False, indent=2))
            return 1
        harness._close_old_fixture_tabs()
        try:
            results = [run_case(case, harness) for case in selected]
        finally:
            harness.cleanup_created_tabs()

    json_path, txt_path = write_reports(report_dir, results)
    passed = sum(1 for item in results if item["status"] == "passed")
    expected_failed = sum(1 for item in results if item["status"] == "expected_fail")
    unexpected_passed = sum(1 for item in results if item["status"] == "unexpected_pass")
    failed = sum(1 for item in results if item["status"] == "failed")
    hard_failures = failed + unexpected_passed
    summary = {
        "status": "success" if hard_failures == 0 else "failed",
        "passed": passed,
        "expected_failed": expected_failed,
        "unexpected_passed": unexpected_passed,
        "failed": failed,
        "json_report": str(json_path),
        "text_report": str(txt_path),
        "screenshot_dir": str(report_dir / "screenshots"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if hard_failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
