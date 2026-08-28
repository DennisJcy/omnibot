#!/usr/bin/env python3
"""Batch scoring harness for human-verification (captcha) workflows.

This script is intentionally an agent-facing E2E harness, not a unit test. It
does not contain a captcha solver. Omnibot is responsible for observation and
execution; an external vision/LLM solver can be attached with --solver-command.

Default scope matches the NetEase Yidun trial pages used during development:
- jigsaw: 滑动拼图
- picture_click: 文字点选
- word_group: 语序选词
- avoid: 障碍躲避
- icon_click: 图标点选

Each case runs 50 iterations by default and writes JSON + TXT reports under
tests/verify_workflow_report_<timestamp>.*.

Solver protocol:
  The solver command receives a JSON payload on stdin and must print JSON on
  stdout. Minimal schema:

  Input:
    {
      "case": "jigsaw",
      "iteration": 1,
      "tab_id": "...",
      "url": "https://dun.163.com/trial/jigsaw",
      "inspect": { ... omnibot verify inspect output ... },
      "panel_image_path": "/tmp/.../panel.png"
    }

  Output:
    {"actions": [
      {"type": "drag", "from_x": 806.5, "from_y": 526, "to_x": 1000, "to_y": 526,
       "duration_ms": 700, "steps": 90, "jitter": 1, "overshoot": 2},
      {"type": "click", "x": 900, "y": 420}
    ]}

  Return {"status":"skip","reason":"..."} when no action should be attempted.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


TIMEOUT_S = 45
VISION_TIMEOUT_S = 90
MOUSE_ACTION_TIMEOUT_S = 120
MAX_VISION_DRAG_STEPS = 12
MAX_SOLVE_ATTEMPTS = 3
ROOT = Path(__file__).resolve().parents[2]
REPORT_ROOT = ROOT / "tests" / "reports"
REPORT_ROOT.mkdir(parents=True, exist_ok=True)
VISION_SOLVER_PATH = Path(__file__).resolve().parent / "vision_solver.py"


@dataclass(frozen=True)
class VerifyCase:
    name: str
    label: str
    url: str
    expected_type: str | None = None
    expected_action_type: str | None = None


CASES: dict[str, VerifyCase] = {
    "jigsaw": VerifyCase(
        name="jigsaw",
        label="滑动拼图",
        url="https://dun.163.com/trial/jigsaw",
        expected_type="slider_jigsaw",
        expected_action_type="drag",
    ),
    "picture_click": VerifyCase(
        name="picture_click",
        label="文字点选",
        url="https://dun.163.com/trial/picture-click",
        expected_action_type="click_sequence",
    ),
    "word_group": VerifyCase(
        name="word_group",
        label="语序选词",
        url="https://dun.163.com/trial/word-group",
        expected_action_type="click_sequence",
    ),
    "avoid": VerifyCase(
        name="avoid",
        label="障碍躲避",
        url="https://dun.163.com/trial/avoid",
        expected_action_type="drag",
    ),
    "icon_click": VerifyCase(
        name="icon_click",
        label="图标点选",
        url="https://dun.163.com/trial/icon-click",
        expected_action_type="click_sequence",
    ),
}


@dataclass
class IterationResult:
    case: str
    iteration: int
    status: str
    found: bool = False
    verify_type: str | None = None
    action_type: str | None = None
    panel_visible: bool = False
    solver_status: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    screenshot_path: str | None = None
    panel_image_path: str | None = None
    page_url: str | None = None
    visual_verification: dict[str, Any] | None = None
    attempt: int = 1
    inspect: dict[str, Any] | None = None
    post_inspect: dict[str, Any] | None = None


def resolve_omnibot_cmd() -> list[str]:
    raw = os.environ.get("OMNIBOT_CMD") or os.environ.get("OMNIBOT_BIN")
    if raw:
        return shlex.split(raw)
    repo_venv = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "omnibot"
    if repo_venv.exists():
        return [str(repo_venv)]
    return ["uv", "run", "omnibot"]


OMNIBOT_CMD = resolve_omnibot_cmd()


def run_omnibot(args: list[str], *, token: str, timeout: int = TIMEOUT_S) -> dict[str, Any]:
    env = os.environ.copy()
    if token:
        env["OMNIBOT_SESSION_TOKEN"] = token
    else:
        env.pop("OMNIBOT_SESSION_TOKEN", None)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    cmd = OMNIBOT_CMD + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"status": "error", "msg": "command timed out", "cmd": cmd}
    if proc.returncode != 0:
        return {"status": "error", "msg": proc.stderr.strip() or proc.stdout.strip(), "cmd": cmd, "returncode": proc.returncode}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "success", "output": proc.stdout}


def open_case_tab(case: VerifyCase, *, token: str) -> str:
    result = run_omnibot(["open", case.url], token=token, timeout=TIMEOUT_S)
    if result.get("status") != "success":
        raise RuntimeError(f"open failed for {case.name}: {result}")
    tab = result.get("tab") if isinstance(result.get("tab"), dict) else {}
    tab_id = str(result.get("tab_id") or result.get("id") or tab.get("id") or tab.get("tab_id") or "")
    registered_tab_id = wait_for_registered_tab(case.url, tab_id, token=token)
    tab_info = wait_for_expected_page(case, registered_tab_id, token=token)
    ok, error = validate_real_trial_page(case, tab_info)
    if not ok:
        raise RuntimeError(error)
    return registered_tab_id


def tab_matches_id(tab: dict[str, Any], tab_id: str) -> bool:
    raw_tab_id = tab_id.rsplit(":", 1)[-1] if tab_id else ""
    return str(tab.get("id") or "") == tab_id or str(tab.get("tab_id") or "") == raw_tab_id


def get_tab_info(tab_id: str, *, token: str) -> dict[str, Any] | None:
    tabs = run_omnibot(["tabs"], token=token, timeout=TIMEOUT_S).get("tabs", [])
    for tab in tabs:
        if tab_matches_id(tab, tab_id):
            return tab
    return None


def validate_real_trial_page(case: VerifyCase, tab_info: dict[str, Any] | None) -> tuple[bool, str | None]:
    if not tab_info:
        return False, f"could not validate real Yidun page for {case.name}: tab not found"
    current_url = str(tab_info.get("url") or "")
    parsed = urlparse(current_url)
    expected = urlparse(case.url)
    if parsed.hostname != "dun.163.com":
        return False, f"expected real dun.163.com page for {case.name}, got {current_url or '<empty>'}"
    if parsed.path != expected.path:
        return False, f"expected {expected.path} for {case.name}, got {parsed.path or '<empty>'} ({current_url})"
    return True, None


def wait_for_expected_page(case: VerifyCase, tab_id: str, *, token: str, timeout_s: float = 15) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] | None = None
    while time.time() < deadline:
        last = get_tab_info(tab_id, token=token)
        ok, _error = validate_real_trial_page(case, last)
        if ok:
            return last or {}
        time.sleep(0.5)
    ok, error = validate_real_trial_page(case, last)
    if not ok:
        raise RuntimeError(error)
    return last or {}


def reset_case_tab(case: VerifyCase, tab_id: str, *, token: str) -> dict[str, Any]:
    result = run_omnibot(["navigate", case.url, "--same-tab", "--tab-id", tab_id], token=token, timeout=TIMEOUT_S)
    if result.get("status") != "success":
        raise RuntimeError(f"navigate failed for {case.name}: {result}")
    return wait_for_expected_page(case, tab_id, token=token)


def wait_for_registered_tab(url: str, preferred_tab_id: str = "", *, token: str, timeout_s: float = 15) -> str:
    """Wait until a newly opened tab appears in daemon session state."""
    deadline = time.time() + timeout_s
    preferred_raw = preferred_tab_id.rsplit(":", 1)[-1] if preferred_tab_id else ""
    while time.time() < deadline:
        tabs = run_omnibot(["tabs"], token=token, timeout=TIMEOUT_S).get("tabs", [])
        for tab in tabs:
            tid = str(tab.get("id") or "")
            raw = str(tab.get("tab_id") or "")
            if preferred_tab_id and (tid == preferred_tab_id or raw == preferred_raw):
                return tid or raw
        matches = [str(t.get("id") or t.get("tab_id") or "") for t in tabs if str(t.get("url", "")).startswith(url)]
        matches = [m for m in matches if m]
        if matches:
            return matches[-1]
        time.sleep(0.5)
    raise RuntimeError(f"could not discover tab for {url}")


def save_panel_image(inspect: dict[str, Any], output_dir: Path, case_name: str, iteration: int) -> str | None:
    encoded = (inspect.get("images") or {}).get("panel_base64")
    if not encoded:
        return None
    path = output_dir / f"{case_name}-{iteration:03d}-panel.png"
    path.write_bytes(base64.b64decode(encoded))
    return str(path)


def file_is_nonempty(path: str | None) -> bool:
    if not path:
        return False
    p = Path(path)
    return p.exists() and p.is_file() and p.stat().st_size > 0


def validate_visual_artifacts(page_screenshot_path: str | None, panel_image_path: str | None) -> tuple[bool, str | None]:
    if not file_is_nonempty(page_screenshot_path):
        return False, f"missing or empty page screenshot: {page_screenshot_path or '<none>'}"
    if not file_is_nonempty(panel_image_path):
        return False, f"missing or empty panel image: {panel_image_path or '<none>'}"
    return True, None


def capture_page_screenshot(tab_id: str, output_dir: Path, case_name: str, iteration: int, *, token: str) -> str | None:
    path = output_dir / f"{case_name}-{iteration:03d}-page.png"
    result = run_omnibot(["screenshot", "--tab-id", tab_id, "-o", str(path)], token=token, timeout=TIMEOUT_S)
    if result.get("status") != "success":
        return None
    return str(path)


def call_solver(command: str, payload: dict[str, Any], *, timeout: int = TIMEOUT_S) -> dict[str, Any]:
    out = call_solver_raw(command, payload, timeout=timeout)
    if out.get("status") == "error":
        return out
    return normalize_solver_output(out)


def call_solver_raw(command: str, payload: dict[str, Any], *, timeout: int = TIMEOUT_S) -> dict[str, Any]:
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        return {"status": "error", "msg": proc.stderr.strip() or proc.stdout.strip(), "returncode": proc.returncode}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "msg": f"solver returned non-JSON: {proc.stdout[:300]}"}


def call_visual_verifier(after_image_path: str, *, before_image_path: str | None = None, timeout: int = VISION_TIMEOUT_S) -> dict[str, Any]:
    command = f"python3 {VISION_SOLVER_PATH}"
    payload = {"mode": "verify", "after_image_path": after_image_path}
    if before_image_path:
        payload["before_image_path"] = before_image_path
    return call_solver_raw(command, payload, timeout=timeout)


def score_visual_verification(result: dict[str, Any]) -> str:
    if result.get("status") != "success":
        return "error"
    label = result.get("result")
    if label == "success_green_arrow":
        return "passed"
    if label == "reset_new_image":
        return "failed"
    return "needs_visual_review"


def resolve_effective_solver(solver_command: str | None) -> tuple[str | None, str | None]:
    if solver_command:
        return solver_command, None
    if not os.environ.get("VISION_API_KEY"):
        return None, "VISION_API_KEY is required for the built-in vision solver"
    return f"python3 {VISION_SOLVER_PATH}", None


def normalize_solver_output(output: dict[str, Any]) -> dict[str, Any]:
    if output.get("status") == "skip":
        return {"status": "skip", "reason": output.get("reason", "solver skipped")}
    actions = output.get("actions")
    if actions is None and output.get("type"):
        actions = [output]
    if not isinstance(actions, list):
        return {"status": "error", "msg": "solver output must contain actions list"}
    cleaned: list[dict[str, Any]] = []
    for action in actions:
        if not isinstance(action, dict):
            return {"status": "error", "msg": "each solver action must be an object"}
        kind = action.get("type")
        if kind not in {"drag", "click", "wait"}:
            return {"status": "error", "msg": f"unsupported solver action type: {kind}"}
        cleaned.append(action)
    return {"status": "success", "actions": cleaned}


def _panel_point_to_viewport(x: float, y: float, inspect: dict[str, Any]) -> tuple[float, float]:
    coord_map = inspect.get("coordinate_map") or {}
    panel = coord_map.get("panel_box") or {}
    scale_x = float(coord_map.get("panel_image_to_viewport_scale_x") or 1)
    scale_y = float(coord_map.get("panel_image_to_viewport_scale_y") or 1)
    return float(panel.get("x") or 0) + float(x) * scale_x, float(panel.get("y") or 0) + float(y) * scale_y


def convert_solver_actions_to_viewport(actions: list[dict[str, Any]], inspect: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert vision-solver panel image pixel coordinates to viewport CSS coordinates."""
    converted: list[dict[str, Any]] = []
    for action in actions:
        item = dict(action)
        if item.get("type") == "click":
            item["x"], item["y"] = _panel_point_to_viewport(item["x"], item["y"], inspect)
        elif item.get("type") == "drag":
            item["from_x"], item["from_y"] = _panel_point_to_viewport(item["from_x"], item["from_y"], inspect)
            item["to_x"], item["to_y"] = _panel_point_to_viewport(item["to_x"], item["to_y"], inspect)
            item["steps"] = min(int(item.get("steps") or MAX_VISION_DRAG_STEPS), MAX_VISION_DRAG_STEPS)
            item.setdefault("duration_ms", 800)
        converted.append(item)
    return converted


def execute_solver_actions(actions: list[dict[str, Any]], tab_id: str, *, token: str) -> tuple[bool, str | None]:
    for action in actions:
        kind = action["type"]
        if kind == "wait":
            time.sleep(float(action.get("seconds", 1)))
            continue
        if kind == "click":
            result = run_omnibot([
                "mouse", "click",
                "--x", str(action["x"]),
                "--y", str(action["y"]),
                "--tab-id", tab_id,
            ], token=token, timeout=MOUSE_ACTION_TIMEOUT_S)
        elif kind == "drag":
            args = [
                "mouse", "drag",
                "--from-x", str(action["from_x"]),
                "--from-y", str(action["from_y"]),
                "--to-x", str(action["to_x"]),
                "--to-y", str(action["to_y"]),
                "--tab-id", tab_id,
                "--action-timeout", "120",
            ]
            for flag in ("duration_ms", "steps", "jitter", "overshoot"):
                if flag in action and action[flag] is not None:
                    args += ["--" + flag.replace("_", "-"), str(action[flag])]
            if action.get("fast"):
                args.append("--fast")
            result = run_omnibot(args, token=token, timeout=MOUSE_ACTION_TIMEOUT_S)
        else:  # pragma: no cover - normalize_solver_output blocks this
            result = {"status": "error", "msg": f"unsupported action: {kind}"}
        if result.get("status") != "success":
            return False, str(result)
    return True, None


def score_post_state(post_inspect: dict[str, Any]) -> str:
    """Best-effort score from structured state.

    Yidun can show success/failure visually without stable text. This harness
    records screenshots for final review; structured scoring is conservative.
    """
    if post_inspect.get("status") != "success":
        return "error"
    if not post_inspect.get("found"):
        return "passed"
    if post_inspect.get("state") == "success":
        return "passed"
    if post_inspect.get("state") == "error":
        return "failed"
    return "needs_visual_review"


def wait_for_post_action_stability(tab_id: str, *, token: str, timeout_s: float = 8.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = run_omnibot(["verify", "inspect", "--tab-id", tab_id, "--no-image"], token=token, timeout=TIMEOUT_S)
        if last.get("status") == "success" and last.get("state") in {"ready", "success"}:
            return last
        time.sleep(0.8)
    return last


def run_iteration(case: VerifyCase, iteration: int, tab_id: str, *, solver_command: str | None, output_dir: Path, token: str, tab_info: dict[str, Any] | None = None) -> IterationResult:
    last_result: IterationResult | None = None
    for attempt in range(1, MAX_SOLVE_ATTEMPTS + 1):
        result = run_solve_attempt(case, iteration, attempt, tab_id, solver_command=solver_command, output_dir=output_dir, token=token, tab_info=tab_info)
        last_result = result
        if result.status == "failed" and attempt < MAX_SOLVE_ATTEMPTS:
            time.sleep(1.2)
            continue
        return result
    assert last_result is not None
    return last_result


def run_solve_attempt(case: VerifyCase, iteration: int, attempt: int, tab_id: str, *, solver_command: str | None, output_dir: Path, token: str, tab_info: dict[str, Any] | None = None) -> IterationResult:
    if tab_info is None:
        tab_info = get_tab_info(tab_id, token=token)
    ok, error = validate_real_trial_page(case, tab_info)
    if not ok:
        return IterationResult(case.name, iteration, "error", error=error, page_url=str((tab_info or {}).get("url") or ""), attempt=attempt)

    inspect = prepare_and_inspect(case, tab_id, token=token)
    if inspect.get("status") != "success":
        return IterationResult(case.name, iteration, "error", error=str(inspect), inspect=inspect, page_url=str(tab_info.get("url") or ""), attempt=attempt)

    panel_path = save_panel_image(inspect, output_dir, case.name, iteration)
    screenshot_path = capture_page_screenshot(tab_id, output_dir, case.name, iteration, token=token)
    artifacts_ok, artifacts_error = validate_visual_artifacts(screenshot_path, panel_path)
    if not artifacts_ok:
        return IterationResult(
            case.name,
            iteration,
            "error",
            found=bool(inspect.get("found")),
            verify_type=inspect.get("type"),
            action_type=inspect.get("action_type"),
            panel_visible=bool(inspect.get("panel_visible")),
            error=artifacts_error,
            screenshot_path=screenshot_path,
            panel_image_path=panel_path,
            page_url=str(tab_info.get("url") or ""),
            attempt=attempt,
            inspect=inspect,
        )
    base = IterationResult(
        case=case.name,
        iteration=iteration,
        status="inspect_only",
        found=bool(inspect.get("found")),
        verify_type=inspect.get("type"),
        action_type=inspect.get("action_type"),
        panel_visible=bool(inspect.get("panel_visible")),
        screenshot_path=screenshot_path,
        panel_image_path=panel_path,
        page_url=str(tab_info.get("url") or ""),
        attempt=attempt,
        inspect=inspect,
    )
    effective_solver, solver_error = resolve_effective_solver(solver_command)
    if solver_error:
        base.status = "error"
        base.error = solver_error
        return base
    solver_payload = {
        "case": case.name,
        "label": case.label,
        "iteration": iteration,
        "tab_id": tab_id,
        "url": case.url,
        "inspect": inspect,
        "panel_image_path": panel_path,
    }
    solver = call_solver(effective_solver or "", solver_payload, timeout=VISION_TIMEOUT_S)
    base.solver_status = solver.get("status")
    if solver.get("status") == "skip":
        base.status = "skipped"
        base.error = solver.get("reason")
        return base
    if solver.get("status") != "success":
        base.status = "error"
        base.error = str(solver)
        return base

    actions = solver.get("actions", [])
    # Jigsaw solver returns viewport coords directly; click-type needs conversion
    if inspect.get("type") != "slider_jigsaw":
        actions = convert_solver_actions_to_viewport(actions, inspect)
    else:
        clamped: list[dict[str, Any]] = []
        for a in actions:
            item = dict(a)
            if item.get("type") == "drag":
                item["steps"] = min(int(item.get("steps") or MAX_VISION_DRAG_STEPS), MAX_VISION_DRAG_STEPS)
                item.setdefault("duration_ms", 800)
            clamped.append(item)
        actions = clamped
    base.actions = actions
    ok, err = execute_solver_actions(actions, tab_id, token=token)
    if not ok:
        base.status = "error"
        base.error = err
        return base
    post = wait_for_post_action_stability(tab_id, token=token)
    after_path = output_dir / f"{case.name}-{iteration:03d}-attempt-{attempt}-after.png"
    screenshot = run_omnibot(["screenshot", "--tab-id", tab_id, "-o", str(after_path)], token=token, timeout=TIMEOUT_S)
    if screenshot.get("status") == "success":
        base.screenshot_path = str(after_path)
    base.post_inspect = post
    if base.screenshot_path:
        visual = call_visual_verifier(base.screenshot_path, before_image_path=panel_path)
        base.visual_verification = visual
        base.status = score_visual_verification(visual)
    else:
        base.status = "error"
        base.error = str(screenshot)
    return base


def prepare_and_inspect(case: VerifyCase, tab_id: str, *, token: str, attempts: int = 8) -> dict[str, Any]:
    """Wait for the widget and try to reveal collapsed captcha panels."""
    last: dict[str, Any] = {}
    for _ in range(attempts):
        last = run_omnibot(["verify", "inspect", "--tab-id", tab_id], token=token, timeout=TIMEOUT_S)
        if last.get("status") != "success":
            time.sleep(1.0)
            continue
        if last.get("found") and last.get("panel_visible"):
            return last
        elements = last.get("elements") or {}
        control = elements.get("control") or elements.get("slider")
        if control:
            run_omnibot(["scrollintoview", ".yidun", "--tab-id", tab_id], token=token, timeout=10)
            time.sleep(0.5)
            refreshed = run_omnibot(["verify", "inspect", "--tab-id", tab_id], token=token, timeout=TIMEOUT_S)
            if refreshed.get("status") == "success":
                last = refreshed
                if last.get("found") and last.get("panel_visible"):
                    return last
                elements = last.get("elements") or {}
                control = elements.get("control") or elements.get("slider") or control
            cx = control["x"] + control["width"] / 2
            cy = control["y"] + control["height"] / 2
            run_omnibot(["mouse", "move", "--x", str(cx), "--y", str(cy), "--tab-id", tab_id], token=token, timeout=10)
            run_omnibot(["mouse", "click", "--x", str(cx), "--y", str(cy), "--tab-id", tab_id], token=token, timeout=10)
        time.sleep(1.0)
    return last


def summarize(results: list[IterationResult]) -> dict[str, Any]:
    out: dict[str, Any] = {"total": len(results), "cases": {}}
    for result in results:
        case = out["cases"].setdefault(result.case, {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0, "inspect_only": 0, "needs_visual_review": 0})
        case["total"] += 1
        case[result.status] = case.get(result.status, 0) + 1
    for case in out["cases"].values():
        attempted = case["total"] - case.get("inspect_only", 0) - case.get("skipped", 0)
        case["attempted"] = attempted
        case["score"] = (case.get("passed", 0) / attempted) if attempted else None
    return out


def write_reports(results: list[IterationResult], summary: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = REPORT_ROOT / f"verify_workflow_report_{stamp}.json"
    txt_path = REPORT_ROOT / f"verify_workflow_report_{stamp}.txt"
    payload = {
        "generated_at": stamp,
        "output_dir": str(output_dir),
        "omnibot_cmd": OMNIBOT_CMD,
        "summary": summary,
        "results": [r.__dict__ for r in results],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["Verify Workflow Matrix Report", f"generated_at: {stamp}", f"output_dir: {output_dir}", ""]
    for name, data in summary["cases"].items():
        lines.append(f"{name}: total={data['total']} attempted={data['attempted']} passed={data['passed']} failed={data['failed']} error={data['error']} skipped={data['skipped']} inspect_only={data['inspect_only']} visual_review={data['needs_visual_review']} score={data['score']}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch score omnibot verify workflows against NetEase Yidun trial pages.")
    parser.add_argument("--case", choices=["all", *CASES.keys()], default="all")
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--solver-command", help="External solver command. Receives JSON on stdin, returns JSON actions on stdout.")
    parser.add_argument("--output-dir", default="", help="Directory for panel/after screenshots. Defaults to a temp directory.")
    parser.add_argument("--keep-tabs", action="store_true", help="Do not close tabs opened by the harness.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    selected = list(CASES.values()) if args.case == "all" else [CASES[args.case]]
    output_dir = Path(args.output_dir) if args.output_dir else Path(tempfile.mkdtemp(prefix="omnibot-verify-matrix-"))
    output_dir.mkdir(parents=True, exist_ok=True)
    token = ""

    results: list[IterationResult] = []
    opened_tabs: list[str] = []
    try:
        for case in selected:
            print(f"[verify-matrix] case={case.name} url={case.url}", flush=True)
            tab_id = open_case_tab(case, token=token)
            opened_tabs.append(tab_id)
            time.sleep(2)
            for iteration in range(1, args.iterations + 1):
                print(f"[verify-matrix] {case.name} iteration {iteration}/{args.iterations}", flush=True)
                tab_info = reset_case_tab(case, tab_id, token=token)
                time.sleep(1.5)
                results.append(run_iteration(case, iteration, tab_id, solver_command=args.solver_command, output_dir=output_dir, token=token, tab_info=tab_info))
    finally:
        if not args.keep_tabs:
            for tab_id in opened_tabs:
                run_omnibot(["close", tab_id], token=token, timeout=10)

    summary = summarize(results)
    json_path, txt_path = write_reports(results, summary, output_dir)
    print(json.dumps({"status": "success", "summary": summary, "json_report": str(json_path), "text_report": str(txt_path), "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
