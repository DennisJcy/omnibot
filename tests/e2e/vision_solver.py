#!/usr/bin/env python3
"""Vision-based captcha solver using mimo-v2.5.

Reads solver protocol JSON from stdin, sends the captcha screenshot to a
vision LLM, parses the response for coordinates, and prints solver protocol
JSON on stdout.

Solver protocol input:
  {
    "case": "jigsaw",
    "panel_image_path": "/tmp/.../panel.png",
    "inspect": { ... verify inspect output ... }
  }

Solver protocol output:
  {"actions": [
    {"type": "drag", "from_x": ..., "from_y": ..., "to_x": ..., "to_y": ...,
     "duration_ms": 800, "steps": 100}
  ]}
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

API_BASE = os.environ.get("VISION_API_BASE", "https://token-plan-cn.xiaomimimo.com/v1")
API_KEY = os.environ.get("VISION_API_KEY")
MODEL = os.environ.get("VISION_MODEL", "mimo-v2.5")


JIGSAW_PROMPT = """You are analyzing a slider jigsaw captcha screenshot. The image is {width}x{height} pixels.

Find the PUZZLE GAP — the shadowed cutout shape where the puzzle piece needs to go.

The puzzle piece (floating element) is currently near the LEFT side of the image. The gap is to its RIGHT, somewhere in the middle-to-right portion of the background image.

Look carefully at the image. The gap appears as a semi-transparent or darker puzzle-piece-shaped region on the background.

Return ONLY: {{"gap_x": <center_x_pixel_of_gap}}
- gap_x must be the CENTER X of the gap, in IMAGE PIXEL coordinates (0 = left edge of image)
- Be precise: look at the gap shape and find its horizontal center
- Do NOT return drag coordinates or actions — only the gap center X"""

CLICK_PROMPT_TEMPLATE = """Captcha type: {captcha_type}
Instruction: {instruction}
Image: {width}x{height}px

Click each target shown in the instruction, in order.

Return ONLY: {{"actions": [{{\"type\": \"click\", \"x\": N, \"y\": N}}, ...]}}
Coordinates are in IMAGE PIXEL space."""

VERIFY_PROMPT = """Look at this after-action captcha screenshot. If a before image is provided, compare it with the after image.

Classify the result:
- success_green_arrow: the captcha shows a green arrow or green success state.
- reset_new_image: the captcha has reset to a new puzzle/image after a failed drag, or the after image shows an untouched puzzle that differs from the before image.
- unclear: neither success nor reset can be confidently determined.

Return ONLY: {"result": "success_green_arrow|reset_new_image|unclear", "reason": "short reason"}"""

VERIFICATION_RESULTS = {"success_green_arrow", "reset_new_image", "unclear"}


def _call_api_core(b64_image: str, user_prompt: str) -> dict[str, Any]:
    """Core API call with retry. Returns parsed JSON from LLM response."""
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You MUST respond with ONLY a valid JSON object. No markdown, no explanation."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}},
                ],
            },
        ],
        "max_tokens": 4096,
        "temperature": 0.1,
    }

    url = f"{API_BASE}/chat/completions"
    data = json.dumps(payload).encode()
    last_error = ""

    for attempt in range(3):
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode() if exc.fp else ""
            last_error = f"API HTTP {exc.code}: {error_body[:500]}"
            time.sleep(2)
            continue
        except Exception as exc:
            last_error = f"API call failed: {exc}"
            time.sleep(2)
            continue

        message = body["choices"][0]["message"]
        content = (message.get("content") or "").strip()
        reasoning = (message.get("reasoning_content") or "").strip()

        candidates = [c for c in [content, reasoning, content + "\n" + reasoning if content and reasoning else ""] if c]
        if not candidates:
            last_error = f"empty content on attempt {attempt + 1}"
            time.sleep(2)
            continue

        for candidate in candidates:
            result = parse_llm_response(candidate)
            if result.get("status") == "success":
                return result

        last_error = f"unparseable on attempt {attempt + 1}"

    return {"status": "error", "msg": f"Vision API failed after 3 attempts: {last_error}"}


def _call_verify_api(b64_image: str, before_b64_image: str | None = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "text", "text": VERIFY_PROMPT}]
    if before_b64_image:
        content.append({"type": "text", "text": "Before image:"})
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{before_b64_image}"}})
    content.append({"type": "text", "text": "After image:"})
    content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_image}"}})

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You MUST respond with ONLY a valid JSON object. No markdown, no explanation."},
            {"role": "user", "content": content},
        ],
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    url = f"{API_BASE}/chat/completions"
    data = json.dumps(payload).encode()
    last_error = ""
    for attempt in range(3):
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode())
        except Exception as exc:
            last_error = str(exc)
            time.sleep(2)
            continue
        message = body["choices"][0]["message"]
        candidates = [c for c in [(message.get("content") or "").strip(), (message.get("reasoning_content") or "").strip()] if c]
        for candidate in candidates:
            parsed = parse_verification_response(candidate)
            if parsed.get("status") == "success":
                return parsed
        last_error = f"unparseable verification response on attempt {attempt + 1}"
    return {"status": "error", "msg": f"Vision verification failed after 3 attempts: {last_error}"}


def verify_captcha_result(after_image_path: str, before_path: str | None = None) -> dict[str, Any]:
    if not API_KEY:
        return {"status": "error", "msg": "VISION_API_KEY is required"}
    if not after_image_path or not Path(after_image_path).exists():
        return {"status": "error", "msg": f"after image not found: {after_image_path}"}
    b64_image = base64.b64encode(Path(after_image_path).read_bytes()).decode()
    before_b64 = None
    if before_path and Path(before_path).exists():
        before_b64 = base64.b64encode(Path(before_path).read_bytes()).decode()
    return _call_verify_api(b64_image, before_b64)


def _build_jigsaw_action_from_gap(api_result: dict[str, Any], elements: dict[str, Any], coord_map: dict[str, Any]) -> dict[str, Any]:
    """Construct a drag action from vision-identified gap_x + DOM-exact slider position."""
    data = api_result.get("data") or api_result
    gap_x_raw = data.get("gap_x")
    if gap_x_raw is None:
        return {"status": "error", "msg": f"vision response missing gap_x: {data}"}

    gap_x_img = float(gap_x_raw)

    slider = elements.get("slider") or {}
    if not slider:
        return {"status": "error", "msg": "DOM slider element missing"}

    panel = coord_map.get("panel_box") or {}
    scale_x = float(coord_map.get("panel_image_to_viewport_scale_x") or 1)

    # Slider handle center in viewport CSS coordinates (from DOM — exact)
    from_x = slider["x"] + slider["width"] / 2
    from_y = slider["y"] + slider["height"] / 2

    # Gap center in viewport CSS coordinates (from vision image pixel)
    gap_viewport_x = float(panel.get("x") or 0) + gap_x_img * scale_x
    gap_viewport_y = from_y  # slider stays on same horizontal line

    return {
        "status": "success",
        "actions": [{
            "type": "drag",
            "from_x": round(from_x, 1),
            "from_y": round(from_y, 1),
            "to_x": round(gap_viewport_x, 1),
            "to_y": round(gap_viewport_y, 1),
            "duration_ms": 800,
            "steps": 12,
        }],
    }


def call_vision_api(image_path: str, case_type: str, action_type: str, instruction: str | None, width: int, height: int, elements: dict[str, Any] | None = None, coord_map: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call the vision API with the captcha image. Retries up to 3 times."""
    if not API_KEY:
        return {"status": "error", "msg": "VISION_API_KEY is required"}

    image_bytes = Path(image_path).read_bytes()
    b64_image = base64.b64encode(image_bytes).decode()

    # For jigsaw: ask only for gap_x, then construct drag from DOM coordinates
    if case_type == "slider_jigsaw" and elements:
        prompt = JIGSAW_PROMPT.format(width=width, height=height)
        result = _call_api_core(b64_image, prompt)
        if result.get("status") != "success":
            return result
        return _build_jigsaw_action_from_gap(result, elements, coord_map or {})

    # For click-type: ask for click coordinates
    prompt = CLICK_PROMPT_TEMPLATE.format(
        captcha_type=case_type, instruction=instruction or "N/A", width=width, height=height
    )
    return _call_api_core(b64_image, prompt)


def parse_llm_response(content: str) -> dict[str, Any]:
    """Parse LLM response to extract action JSON or gap_x."""
    text = content.strip()

    # Strip markdown code fences if present
    if "```" in text:
        match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?\s*```", text)
        if match:
            text = match.group(1).strip()

    data = extract_actions_json(text)
    if data is not None:
        actions = data.get("actions")
        if isinstance(actions, list):
            cleaned = []
            for action in actions:
                if not isinstance(action, dict):
                    return {"status": "error", "msg": "each action must be an object"}
                kind = action.get("type")
                if kind not in {"drag", "click", "wait"}:
                    return {"status": "error", "msg": f"unsupported action type: {kind}"}
                cleaned.append(action)
            return {"status": "success", "actions": cleaned}

    # Try gap_x format (jigsaw)
    data = extract_first_json(text)
    if data is not None and "gap_x" in data:
        return {"status": "success", "data": {"gap_x": float(data["gap_x"])}}

    return {"status": "error", "msg": f"Could not parse JSON from LLM: {text[:500]}"}


def parse_verification_response(content: str) -> dict[str, Any]:
    data = extract_first_json(content.strip())
    if data is None:
        return {"status": "error", "msg": f"Could not parse verification JSON: {content[:500]}"}
    result = data.get("result")
    if result not in VERIFICATION_RESULTS:
        return {"status": "error", "msg": f"unsupported verification result: {result}"}
    return {"status": "success", "result": result, "reason": str(data.get("reason") or "")}


def extract_first_json(text: str) -> dict[str, Any] | None:
    """Extract the first valid JSON object from text."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def extract_actions_json(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            candidate, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict) and isinstance(candidate.get("actions"), list):
            return candidate
    return None


def solve(payload: dict[str, Any]) -> dict[str, Any]:
    """Main solver entry point."""
    if payload.get("mode") == "verify":
        return verify_captcha_result(str(payload.get("after_image_path") or ""), before_path=payload.get("before_image_path"))

    inspect = payload.get("inspect", {})
    case_type = inspect.get("type", "unknown")
    action_type = inspect.get("action_type", "unknown")
    instruction = inspect.get("instruction")

    panel_path = payload.get("panel_image_path")
    if not panel_path or not Path(panel_path).exists():
        return {"status": "error", "msg": f"panel image not found: {panel_path}"}

    coord_map = inspect.get("coordinate_map", {})
    width = coord_map.get("panel_image_width", 640)
    height = coord_map.get("panel_image_height", 350)
    elements = inspect.get("elements") or {}

    return call_vision_api(panel_path, case_type, action_type, instruction, width, height, elements=elements, coord_map=coord_map)


def main() -> int:
    payload = json.loads(sys.stdin.read())
    result = solve(payload)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
