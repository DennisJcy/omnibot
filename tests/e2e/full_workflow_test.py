#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness import assert_success, extract_tab_id, run_omnibot, start_fixture_server, timestamped_report_dir


FIXTURE_INDEX = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Full Workflow Fixture</title></head>
<body>
  <main>
    <h1>Full Workflow Fixture</h1>
    <p id="status">ready</p>
    <label for="email">Email</label>
    <input id="email" aria-label="Email input" placeholder="Email address">
    <button id="submit" onclick="window.appState.email=document.getElementById('email').value; document.getElementById('status').textContent='submitted '+window.appState.email">Submit</button>
    <button id="refresh" onclick="setTimeout(() => { document.getElementById('status').textContent='dynamic done'; window.appState.done=true; }, 100)">Refresh</button>
    <button id="console" onclick="console.error('full-workflow-error'); document.getElementById('status').textContent='console done'">Console</button>
    <button id="network" onclick="fetch('/api/full', {method:'POST', body:'ok'}).then(() => { document.getElementById('status').textContent='network done'; })">Network</button>
    <a id="next" href="/next.html">Next</a>
  </main>
  <script>window.appState = {email:'', done:false};</script>
</body>
</html>
"""

FIXTURE_NEXT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Full Workflow Next</title></head>
<body><main><h1>Full Workflow Next</h1><a href="/index.html">Back</a></main></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Omnibot full workflow E2E gate")
    parser.add_argument("--no-playwright", action="store_true", help="accepted for compatibility; this script does not use Playwright")
    args = parser.parse_args(argv)

    report_dir = timestamped_report_dir("full_workflow_report")
    token = f"full-workflow-{report_dir.name}"
    server = start_fixture_server({"index.html": FIXTURE_INDEX, "next.html": FIXTURE_NEXT})
    steps: list[dict[str, Any]] = []
    try:
        opened = run_omnibot(["open", f"{server.base_url}/index.html"], token=token)
        assert_success(opened, "open fixture")
        tab_id = extract_tab_id(opened)
        if not tab_id:
            raise AssertionError(f"open did not return a tab id: {opened}")
        steps.append({"open": opened})

        for command in [
            ["snapshot", "-i", "--json", "--tab-id", tab_id],
            ["fill", "#email", "agent@example.com", "--tab-id", tab_id],
            ["click", "#submit", "--tab-id", tab_id],
            ["click", "#refresh", "--tab-id", tab_id],
            ["wait", "--text", "dynamic done", "--tab-id", tab_id],
            ["console", "clear", "--tab-id", tab_id],
            ["click", "#console", "--tab-id", tab_id],
            ["console", "logs", "--tab-id", tab_id],
            ["network", "clear", "--tab-id", tab_id],
            ["network", "start", "--tab-id", tab_id],
            ["click", "#network", "--tab-id", tab_id],
            ["wait", "--text", "network done", "--tab-id", tab_id],
            ["network", "logs", "--tab-id", tab_id],
            ["screenshot", "--tab-id", tab_id, "-o", str(report_dir / "full_workflow.png")],
            ["goto", f"{server.base_url}/next.html", "--tab-id", tab_id],
            ["back", "--tab-id", tab_id],
        ]:
            result = run_omnibot(command, token=token)
            assert_success(result, " ".join(command))
            steps.append({"cmd": command, "result": result})

        report = {"status": "passed", "steps": steps}
        (report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Exception as exc:
        report = {"status": "failed", "error": str(exc), "steps": steps}
        (report_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        server.close()


if __name__ == "__main__":
    raise SystemExit(main())
