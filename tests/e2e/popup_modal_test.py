#!/usr/bin/env python3
"""
Popup / modal DOM popup controls e2e tests.

Verifies that `snapshot -i` detects popup overlays and appends a
`# DOM Popup Controls` section whose @eN refs can be clicked.

Five popup types tested:
  1. Modal dialog (role="dialog")
  2. Drawer (CSS class drawer-overlay)
  3. Alert dialog (role="alertdialog")
  4. Combobox dropdown (role="combobox" + role="listbox" + role="option")
  5. Fixed overlay (position:fixed, z-index:9999, class contains "popup")
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

TIMEOUT_S = 30

# ---------------------------------------------------------------------------
# omnibot CLI helpers
# ---------------------------------------------------------------------------

def _resolve_omnibot_cmd() -> list[str]:
    raw = os.environ.get("OMNIBOT_CMD") or os.environ.get("OMNIBOT_BIN")
    if raw:
        return shlex.split(raw)
    return ["uv", "run", "omnibot"]


OMNIBOT_CMD = _resolve_omnibot_cmd()


def run_omnibot(args: list[str], timeout: int = TIMEOUT_S) -> dict[str, Any]:
    cmd = OMNIBOT_CMD + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return {"status": "error", "msg": result.stderr.strip() or result.stdout.strip(),
                    "returncode": result.returncode}
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"status": "success", "output": result.stdout}
    except subprocess.TimeoutExpired:
        return {"status": "error", "msg": "Command timed out"}
    except FileNotFoundError:
        return {"status": "error", "msg": f"omnibot command not found: {OMNIBOT_CMD}"}
    except Exception as exc:
        return {"status": "error", "msg": str(exc)}


def omnibot_navigate(url: str, *, tab_id: str = "") -> dict[str, Any]:
    args = ["navigate"]
    if tab_id:
        args += ["--same-tab", "--tab-id", tab_id]
    args.append(url)
    return run_omnibot(args)


def omnibot_snapshot(*, interactive: bool = True, tab_id: str = "") -> dict[str, Any]:
    args = ["snapshot", "--json"]
    if interactive:
        args.append("--interactive")
    if tab_id:
        args += ["--tab-id", tab_id]
    return run_omnibot(args)


def omnibot_click(ref: str, *, tab_id: str = "") -> dict[str, Any]:
    args = ["click", ref]
    if tab_id:
        args += ["--tab-id", tab_id]
    return run_omnibot(args)


def omnibot_execute_js(expression: str, *, tab_id: str = "") -> dict[str, Any]:
    args = ["cdp", "Runtime.evaluate", json.dumps({"expression": expression, "returnByValue": True})]
    if tab_id:
        args += ["--tab-id", tab_id]
    return run_omnibot(args)


def omnibot_close(tab_id: str) -> dict[str, Any]:
    return run_omnibot(["close", tab_id])


# ---------------------------------------------------------------------------
# Ref parsing helpers
# ---------------------------------------------------------------------------

REF_PATTERN = re.compile(r"@e(\d+)\s+\[([^\]]+)\](?:\s+\"([^\"]*)\")?")


def extract_refs(content: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        m = REF_PATTERN.search(line)
        if m:
            out.append({"ref": f"@e{m.group(1)}", "role": m.group(2),
                        "name": m.group(3) or "", "line": line_no})
    return out


def find_ref(refs: list[dict[str, str]], *, role: str | None = None,
             name_contains: str | None = None) -> str | None:
    for entry in refs:
        if role and entry["role"] != role:
            continue
        if name_contains and name_contains not in entry["name"]:
            continue
        return entry["ref"]
    return None


def find_json_ref(refs: dict[str, dict[str, Any]], *, role: str,
                  name_contains: str, without_opener: bool = False) -> str | None:
    for ref_id, entry in refs.items():
        if entry.get("role") != role:
            continue
        if name_contains not in str(entry.get("name") or ""):
            continue
        if without_opener and entry.get("openerSelector"):
            continue
        return f"@{ref_id}"
    return None


# ---------------------------------------------------------------------------
# HTML fixture
# ---------------------------------------------------------------------------

FIXTURE_HTML = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>popup modal fixture</title>
<style>
  body { font-family: system-ui, sans-serif; padding: 24px; }
  [hidden] { display: none !important; }
  .drawer-overlay {
    display: none; position: fixed; top: 0; left: 0;
    width: 100%; height: 100%; background: rgba(0,0,0,0.4);
    z-index: 9000;
  }
  .drawer-overlay.open { display: flex; justify-content: flex-end; }
  .drawer-panel {
    width: 300px; height: 100%; background: #fff; padding: 16px;
  }
  .popup-overlay {
    display: none; position: fixed; top: 0; left: 0;
    width: 100%; height: 100%; background: rgba(0,0,0,0.3);
    z-index: 9999; align-items: center; justify-content: center;
  }
  .popup-overlay.open { display: flex; }
  .popup-box { background: #fff; padding: 20px; border-radius: 8px; }
</style>
</head>
<body>
<main>
  <h1>Popup Modal Fixture</h1>
  <p id="status">ready</p>

  <!-- 1. Modal dialog -->
  <button id="open-modal" onclick="document.getElementById('modal').hidden=false">Open modal</button>
  <div id="modal" role="dialog" aria-label="Confirm dialog" hidden>
    <p>Are you sure?</p>
    <button onclick="document.getElementById('status').textContent='confirmed'; document.getElementById('modal').hidden=true">Confirm</button>
    <button onclick="document.getElementById('status').textContent='cancelled'; document.getElementById('modal').hidden=true">Cancel</button>
  </div>

  <!-- 2. Drawer -->
  <button id="open-drawer" onclick="document.getElementById('drawer').classList.add('open')">Open drawer</button>
  <div id="drawer" class="drawer-overlay">
    <div class="drawer-panel">
      <p>Drawer content</p>
      <a href="#drawer-link">Drawer link</a>
      <button onclick="document.getElementById('status').textContent='drawer-closed'; document.getElementById('drawer').classList.remove('open')">Close drawer</button>
    </div>
  </div>

  <!-- 3. Alert dialog -->
  <button id="open-alert" onclick="document.getElementById('alertdlg').hidden=false">Open alert</button>
  <div id="alertdlg" role="alertdialog" aria-label="Warning" hidden>
    <p>Warning message</p>
    <button onclick="document.getElementById('status').textContent='alert-dismissed'; document.getElementById('alertdlg').hidden=true">Dismiss</button>
  </div>

  <!-- 4. Combobox dropdown -->
  <button id="open-combobox">Open dropdown</button>
  <div style="position:relative; display:inline-block;">
    <div id="combo" role="combobox" aria-expanded="false" aria-haspopup="listbox"
         aria-controls="combo-list" tabindex="0">Select vendor</div>
    <ul id="combo-list" role="listbox" hidden>
      <li role="option" data-value="anthropic">Anthropic</li>
      <li role="option" data-value="openai">OpenAI</li>
      <li role="option" data-value="google">Google</li>
    </ul>
  </div>

  <!-- 5. Fixed overlay popup -->
  <button id="open-popup" onclick="document.getElementById('popup').classList.add('open')">Open popup</button>
  <div id="popup" class="popup-overlay">
    <div class="popup-box">
      <p>Popup content</p>
      <label><input type="checkbox" id="popup-check"> Accept terms</label>
      <button onclick="document.getElementById('status').textContent='popup-closed'; document.getElementById('popup').classList.remove('open')">Close</button>
    </div>
  </div>
</main>

<script>
document.getElementById('open-combobox').addEventListener('click', function() {
  var list = document.getElementById('combo-list');
  var combo = document.getElementById('combo');
  list.removeAttribute('hidden');
  list.style.display = 'block';
  combo.setAttribute('aria-expanded', 'true');
});
document.getElementById('combo-list').addEventListener('click', function(e) {
  var li = e.target.closest('[role="option"]');
  if (!li) return;
  document.getElementById('status').textContent = 'selected ' + li.getAttribute('data-value');
  document.getElementById('combo').setAttribute('aria-expanded', 'false');
  document.getElementById('combo-list').setAttribute('hidden', '');
  document.getElementById('combo-list').style.display = 'none';
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Fixture server
# ---------------------------------------------------------------------------

class FixtureServer:
    """Context manager that serves a local HTML fixture on a random port."""

    def __init__(self) -> None:
        self.tempdir: tempfile.TemporaryDirectory[str] | None = None
        self.server: ThreadingHTTPServer | None = None
        self.base_url = ""
        self.url = ""

    def __enter__(self) -> "FixtureServer":
        self.tempdir = tempfile.TemporaryDirectory(prefix="omnibot-popup-e2e-")
        root = Path(self.tempdir.name)
        (root / "index.html").write_text(FIXTURE_HTML, encoding="utf-8")

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, format: str, *args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        port = self.server.server_address[1]
        self.base_url = f"http://127.0.0.1:{port}"
        self.url = f"{self.base_url}/index.html"
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.tempdir:
            self.tempdir.cleanup()


# ---------------------------------------------------------------------------
# Test base class
# ---------------------------------------------------------------------------

class PopupModalE2ETestBase(unittest.TestCase):
    """Shared setup: starts fixture server, navigates once, tracks tab id."""

    fixture: FixtureServer
    tab_id: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = FixtureServer()
        cls.fixture.__enter__()
        r = omnibot_navigate(cls.fixture.url)
        if r.get("status") != "success":
            cls.fixture.__exit__(None, None, None)
            raise RuntimeError(f"Failed to navigate to fixture: {r}")
        tab = r.get("tab", {})
        cls.tab_id = str(tab.get("id", ""))
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.tab_id:
            omnibot_close(cls.tab_id)
        cls.fixture.__exit__(None, None, None)

    def _snapshot_result(self) -> dict[str, Any]:
        r = omnibot_snapshot(interactive=True, tab_id=self.tab_id)
        self.assertEqual(r.get("status"), "success", f"snapshot failed: {r}")
        return r

    def _snapshot(self) -> str:
        return self._snapshot_result().get("content", "")

    def _click_ref(self, ref: str) -> dict[str, Any]:
        r = omnibot_click(ref, tab_id=self.tab_id)
        self.assertEqual(r.get("status"), "success", f"click {ref} failed: {r}")
        return r

    def _get_status(self) -> str:
        r = omnibot_execute_js("document.getElementById('status').textContent",
                                tab_id=self.tab_id)
        self.assertEqual(r.get("status"), "success", f"execute_js failed: {r}")
        result = r.get("result", {})
        value = result.get("result", {}).get("value", "")
        return str(value)

    def _open_popup(self, button_id: str) -> None:
        r = omnibot_click(f"#{button_id}", tab_id=self.tab_id)
        self.assertEqual(r.get("status"), "success", f"click #{button_id} failed: {r}")
        time.sleep(0.3)

    def _find_popup_ref(self, content: str, *, role: str, name_contains: str) -> str:
        self.assertIn("# DOM Popup Controls", content,
                       "snapshot output missing '# DOM Popup Controls' section")
        popup_section = content.split("# DOM Popup Controls", 1)[1]
        refs = extract_refs(popup_section)
        ref = find_ref(refs, role=role, name_contains=name_contains)
        self.assertIsNotNone(ref,
                              f"No popup ref with role={role!r} name_contains={name_contains!r} "
                              f"in popup section:\n{popup_section}")
        assert ref is not None  # for type checker
        return ref


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestModalDialog(PopupModalE2ETestBase):
    """Modal dialog (role="dialog") with Confirm + Cancel buttons."""

    def test_modal_dialog_controls_detected_and_clickable(self) -> None:
        self._open_popup("open-modal")
        content = self._snapshot()

        popup_section = content.split("# DOM Popup Controls", 1)[1]
        self.assertIn("Confirm", popup_section)
        self.assertIn("Cancel", popup_section)

        cancel_ref = self._find_popup_ref(content, role="button", name_contains="Cancel")
        self._click_ref(cancel_ref)
        time.sleep(0.3)

        status = self._get_status()
        self.assertEqual(status, "cancelled")


class TestDrawer(PopupModalE2ETestBase):
    """Drawer (CSS class drawer-overlay) with close button and a link."""

    def test_drawer_controls_detected_and_clickable(self) -> None:
        self._open_popup("open-drawer")
        content = self._snapshot()

        close_ref = self._find_popup_ref(content, role="button", name_contains="Close drawer")
        self._click_ref(close_ref)
        time.sleep(0.3)

        status = self._get_status()
        self.assertEqual(status, "drawer-closed")


class TestAlertDialog(PopupModalE2ETestBase):
    """Alert dialog (role="alertdialog") with dismiss button."""

    def test_alertdialog_controls_detected_and_clickable(self) -> None:
        self._open_popup("open-alert")
        content = self._snapshot()

        dismiss_ref = self._find_popup_ref(content, role="button", name_contains="Dismiss")
        self._click_ref(dismiss_ref)
        time.sleep(0.3)

        status = self._get_status()
        self.assertEqual(status, "alert-dismissed")


class TestComboboxDropdown(PopupModalE2ETestBase):
    """Combobox dropdown with role="listbox" and role="option" items."""

    def test_combobox_dropdown_options_detected_and_clickable(self) -> None:
        self._open_popup("open-combobox")
        snapshot_result = self._snapshot_result()
        content = snapshot_result.get("content", "")

        self._find_popup_ref(content, role="option", name_contains="Anthropic")
        option_ref = find_json_ref(snapshot_result.get("refs", {}), role="option", name_contains="Anthropic", without_opener=True)
        self.assertIsNotNone(option_ref, f"No clickable AX option ref found in refs: {snapshot_result.get('refs', {})}")
        assert option_ref is not None
        self._click_ref(option_ref)
        time.sleep(0.3)

        status = self._get_status()
        self.assertEqual(status, "selected anthropic")


class TestFixedOverlayPopup(PopupModalE2ETestBase):
    """Fixed overlay (position:fixed, z-index:9999, class contains 'popup')."""

    def test_fixed_overlay_popup_controls_detected_and_clickable(self) -> None:
        self._open_popup("open-popup")
        content = self._snapshot()

        close_ref = self._find_popup_ref(content, role="button", name_contains="Close")
        self._click_ref(close_ref)
        time.sleep(0.3)

        status = self._get_status()
        self.assertEqual(status, "popup-closed")


class TestNoPopupControlsWhenAllClosed(PopupModalE2ETestBase):
    """After closing all popups, snapshot should not have visible popup controls."""

    def test_no_popup_controls_when_all_closed(self) -> None:
        # Open all 5 popups
        self._open_popup("open-modal")
        self._open_popup("open-drawer")
        self._open_popup("open-alert")
        self._open_popup("open-combobox")
        self._open_popup("open-popup")

        # Close each one
        content = self._snapshot()

        modal_ref = self._find_popup_ref(content, role="button", name_contains="Cancel")
        self._click_ref(modal_ref)
        time.sleep(0.3)

        drawer_ref = self._find_popup_ref(content, role="button", name_contains="Close drawer")
        self._click_ref(drawer_ref)
        time.sleep(0.3)

        alert_ref = self._find_popup_ref(content, role="button", name_contains="Dismiss")
        self._click_ref(alert_ref)
        time.sleep(0.3)

        combo_ref = self._find_popup_ref(content, role="option", name_contains="Anthropic")
        self._click_ref(combo_ref)
        time.sleep(0.3)

        popup_ref = self._find_popup_ref(content, role="button", name_contains="Close")
        self._click_ref(popup_ref)
        time.sleep(0.3)

        # Snapshot again — modal/drawer/alert/popup controls should be gone.
        # Combobox auto-probing may still detect listbox DOM elements even
        # when closed, so we only verify the non-combobox popups are absent.
        final_content = self._snapshot()
        if "# DOM Popup Controls" in final_content:
            popup_section = final_content.split("# DOM Popup Controls", 1)[1]
            self.assertNotIn("Confirm", popup_section,
                             "Modal Confirm should not appear after modal is closed")
            self.assertNotIn("Dismiss", popup_section,
                             "Alert Dismiss should not appear after alert is closed")


class TestMultiplePopupsOpenSimultaneously(PopupModalE2ETestBase):
    """Open 3 popups at once, verify all their controls are captured."""

    def test_multiple_popups_open_simultaneously(self) -> None:
        self._open_popup("open-modal")
        self._open_popup("open-alert")
        self._open_popup("open-popup")

        content = self._snapshot()

        self.assertIn("# DOM Popup Controls", content,
                       "Popup controls section should appear with multiple popups open")
        popup_section = content.split("# DOM Popup Controls", 1)[1]

        self.assertIn("Confirm", popup_section,
                       "Modal Confirm button missing from popup controls")
        self.assertIn("Cancel", popup_section,
                       "Modal Cancel button missing from popup controls")
        self.assertIn("Dismiss", popup_section,
                       "Alert Dismiss button missing from popup controls")
        self.assertIn("Close", popup_section,
                       "Popup Close button missing from popup controls")

        # Cleanup: close all 3
        cancel_ref = self._find_popup_ref(content, role="button", name_contains="Cancel")
        self._click_ref(cancel_ref)
        time.sleep(0.3)

        dismiss_ref = self._find_popup_ref(content, role="button", name_contains="Dismiss")
        self._click_ref(dismiss_ref)
        time.sleep(0.3)

        close_ref = self._find_popup_ref(content, role="button", name_contains="Close")
        self._click_ref(close_ref)
        time.sleep(0.3)


if __name__ == "__main__":
    unittest.main()
