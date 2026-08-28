#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "tests"


@dataclass(frozen=True)
class ReadCase:
    case_id: str
    url: str
    required_all: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    forbidden: tuple[str, ...] = ()
    min_content_length: int = 300
    min_links: int = 0
    require_image_link: bool = False
    screens: int = 2


CASES: dict[str, ReadCase] = {
    "xhs_note_overlay": ReadCase(
        case_id="xhs_note_overlay",
        url="http://xhslink.com/o/H0HwmxcnHH",
        required_all=("Vibe Coding", "真正的麻烦"),
        required_any=("第一批 Vibe Coding 创业的受害者", "过去半年，我看到不少创业者用 AI 写代码"),
        forbidden=("营业执照", "沪ICP备13030189号", "医疗器械网络交易服务第三方平台备案"),
        min_content_length=800,
        screens=2,
    ),
    "x_home_timeline": ReadCase(
        case_id="x_home_timeline",
        url="https://x.com/home",
        required_any=("Home", "For you", "Following", "Likes", "views"),
        forbidden=("blob:", "data:image"),
        min_content_length=300,
        screens=2,
    ),
    "github_readme": ReadCase(
        case_id="github_readme",
        url="https://github.com/DennisJcy/omnibot",
        required_all=("omnibot",),
        required_any=("README", "Browser", "CLI", "AI"),
        forbidden=("blob:", "data:image"),
        min_content_length=500,
        min_links=3,
        screens=2,
    ),
    "hacker_news_frontpage": ReadCase(
        case_id="hacker_news_frontpage",
        url="https://news.ycombinator.com/",
        required_all=("Hacker News",),
        required_any=("new", "past", "comments", "points"),
        forbidden=("blob:", "data:image"),
        min_content_length=500,
        min_links=10,
        screens=1,
    ),
    "wikipedia_article": ReadCase(
        case_id="wikipedia_article",
        url="https://en.wikipedia.org/wiki/Web_browser",
        required_all=("Web browser", "World Wide Web"),
        required_any=("browser", "website", "Internet"),
        forbidden=("blob:", "data:image"),
        min_content_length=1200,
        min_links=10,
        screens=2,
    ),
}


def omnibot_command(value: str | None) -> list[str]:
    raw = value or os.environ.get("OMNIBOT_CMD") or "uv run omnibot"
    return shlex.split(raw)


def run_read(case: ReadCase, command: list[str], timeout: int) -> dict[str, Any]:
    env = os.environ.copy()
    env["OMNIBOT_SESSION_TOKEN"] = env.get("OMNIBOT_SESSION_TOKEN") or f"read-real-sites-{case.case_id}"
    proc = subprocess.run(
        [*command, "read", "--json", "--screens", str(case.screens), case.url],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        return {
            "status": "error",
            "case_id": case.case_id,
            "url": case.url,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "case_id": case.case_id,
            "url": case.url,
            "msg": f"stdout is not JSON: {exc}",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
    result["case_id"] = case.case_id
    result["stderr"] = proc.stderr
    cleanup = close_created_tab(result, command, env, timeout)
    if cleanup:
        result["cleanup"] = cleanup
    return result


def close_created_tab(result: dict[str, Any], command: list[str], env: dict[str, str], timeout: int) -> dict[str, Any] | None:
    metadata = result.get("metadata") or {}
    if not metadata.get("created_tab"):
        return None
    tab_id = str(metadata.get("tab_id") or "")
    if not tab_id:
        return {"status": "error", "msg": "created read tab did not include metadata.tab_id"}
    proc = subprocess.run(
        [*command, "close", tab_id],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        return {"status": "error", "returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "success", "stdout": proc.stdout, "stderr": proc.stderr}


def validate(case: ReadCase, result: dict[str, Any]) -> dict[str, Any]:
    content = str(result.get("content") or "")
    title = str(result.get("title") or "")
    links = result.get("links") or []
    haystack = f"{title}\n{content}"
    missing_all = [needle for needle in case.required_all if needle not in haystack]
    matched_any = [needle for needle in case.required_any if needle in haystack]
    forbidden_found = [needle for needle in case.forbidden if needle in content]
    image_links = [
        link for link in links
        if any(token in str(link.get("href") or "") for token in ("pbs.twimg.com", "xhscdn.com", ".jpg", ".png", ".webp"))
    ]
    failures: list[str] = []
    if str(result.get("status")) != "success":
        failures.append(f"read status is {result.get('status')!r}")
    if len(content) < case.min_content_length:
        failures.append(f"content length {len(content)} < {case.min_content_length}")
    if missing_all:
        failures.append(f"missing required text: {missing_all}")
    if case.required_any and not matched_any:
        failures.append(f"none of required_any matched: {list(case.required_any)}")
    if forbidden_found:
        failures.append(f"forbidden text found: {forbidden_found}")
    if len(links) < case.min_links:
        failures.append(f"link count {len(links)} < {case.min_links}")
    if case.require_image_link and not image_links:
        failures.append("no image links found")
    return {
        "case_id": case.case_id,
        "url": case.url,
        "ok": not failures,
        "failures": failures,
        "title": title,
        "content_length": len(content),
        "link_count": len(links),
        "matched_any": matched_any,
        "image_link_count": len(image_links),
        "debug": (result.get("metadata") or {}).get("debug", {}),
    }


def write_reports(results: list[dict[str, Any]]) -> tuple[Path, Path]:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = REPORT_DIR / f"read_real_sites_report_{timestamp}.json"
    txt_path = REPORT_DIR / f"read_real_sites_report_{timestamp}.txt"
    payload = {"generated_at": timestamp, "results": results}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines: list[str] = []
    for item in results:
        prefix = "PASS" if item.get("ok") else "FAIL"
        lines.append(f"{prefix} {item.get('case_id')} length={item.get('content_length')} links={item.get('link_count')}")
        for failure in item.get("failures") or []:
            lines.append(f"  - {failure}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live omnibot read quality checks against real websites.")
    parser.add_argument("--case", choices=sorted(CASES), action="append", help="Case id to run. May be passed multiple times.")
    parser.add_argument("--omnibot-cmd", default=None, help="Command prefix, e.g. 'uv run omnibot' or a packaged binary path.")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    selected = args.case or list(CASES)
    command = omnibot_command(args.omnibot_cmd)
    results: list[dict[str, Any]] = []
    for case_id in selected:
        case = CASES[case_id]
        raw = run_read(case, command, timeout=args.timeout)
        results.append(validate(case, raw))
    json_path, txt_path = write_reports(results)
    for item in results:
        prefix = "PASS" if item["ok"] else "FAIL"
        print(f"{prefix} {item['case_id']} length={item['content_length']} links={item['link_count']}")
        for failure in item["failures"]:
            print(f"  - {failure}")
    print(f"JSON report: {json_path}")
    print(f"Text report: {txt_path}")
    return 0 if all(item["ok"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
