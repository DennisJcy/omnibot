"""Human-verification (captcha) inspection module.

This module is the perception layer: it detects captcha widgets on the page,
extracts their geometry/images, and returns structured metadata so an external
LLM agent can decide how to solve it. It does NOT solve captchas itself.

Design principles:
- Detection is heuristic DOM probing (no ML).
- Coordinate mapping converts image-pixel coordinates (what the vision model
  sees) to browser CSS viewport coordinates (what Input.dispatchMouseEvent
  needs).
- State detection (success/error) is best-effort from DOM classes; the agent
  should always cross-check with a screenshot because visual state is the
  ground truth for behavioral captchas.
"""
from __future__ import annotations

import math
from typing import Any

from . import cdp
from .logger import log


# ---------------------------------------------------------------------------
# Page probing — runs a single JS expression to collect captcha DOM metadata
# ---------------------------------------------------------------------------

_PROBE_SCRIPT = r"""
(() => {
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return null;
    return { x: r.x, y: r.y, width: r.width, height: r.height,
             left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  };
  const imgInfo = (el) => {
    if (!el) return null;
    const box = rect(el);
    if (!box) return null;
    return { src: (el.src || '').slice(0, 200), box,
             natural_width: el.naturalWidth || null,
             natural_height: el.naturalHeight || null };
  };

  // --- NetEase Yidun detection ---
  // Find all yidun instances and prefer the one with a visible panel.
  const yidunRoots = Array.from(document.querySelectorAll('.yidun'));
  let best = null;
  let bestArea = 0;
  for (const root of yidunRoots) {
    const panelEl = root.querySelector('.yidun_panel, .yidun_bgimg');
    const panelBox = panelEl ? rect(panelEl) : null;
    const area = panelBox ? panelBox.width * panelBox.height : 0;
    if (area > bestArea) { bestArea = area; best = root; }
  }
  // Fallback: if no visible panel, use the first yidun root.
  const yidunRoot = best || yidunRoots[0] || null;
  if (yidunRoot) {
    const yidunClasses = yidunRoot.className || '';
    const bgImg = imgInfo(yidunRoot.querySelector('.yidun_bg-img'));
    const jigsawImg = imgInfo(yidunRoot.querySelector('.yidun_jigsaw'));
    const sliderEl = yidunRoot.querySelector('.yidun_slider') || yidunRoot.querySelector('.yidun_control [role=button]');
    const slider = sliderEl ? (() => { const b = rect(sliderEl); return b ? { box: b } : null; })() : null;
    const controlEl = yidunRoot.querySelector('.yidun_control');
    const control = controlEl ? rect(controlEl) : null;
    const tipsEl = yidunRoot.querySelector('.yidun_tips__text, .yidun_tips');
    const instruction = tipsEl ? (tipsEl.textContent || '').trim().slice(0, 300) : null;
    const state = yidunClasses.includes('yidun--success') ? 'success'
                : yidunClasses.includes('yidun--error') ? 'error'
                : yidunClasses.includes('yidun--loading') ? 'loading'
                : 'ready';
    const panelEl = yidunRoot.querySelector('.yidun_panel, .yidun_bgimg');
    const panel = panelEl ? rect(panelEl) : (bgImg ? bgImg.box : null);
    return JSON.stringify({
      yidun: true, url: location.href, yidun_classes: yidunClasses,
      has_bg_img: !!bgImg, has_jigsaw_img: !!jigsawImg, has_slider: !!slider,
      bg_img: bgImg, jigsaw_img: jigsawImg, slider: slider, control, panel,
      instruction, state, panel_visible: !!panel,
      scroll_x: window.scrollX || 0,
      scroll_y: window.scrollY || 0,
      device_pixel_ratio: window.devicePixelRatio || 1
    });
  }

  // --- Generic extension: add more providers here ---

  return JSON.stringify({ yidun: false });
})()
"""


def probe_page(driver, tab_id: str, token: str | None = None) -> dict[str, Any]:
    """Run the DOM probe script and return parsed captcha metadata."""
    import json

    try:
        raw = cdp.evaluate(driver, tab_id, _PROBE_SCRIPT, token=token, await_promise=False)
    except Exception as exc:
        log(f"[verify] probe failed: {exc}")
        return {"yidun": False, "error": str(exc)}
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return {"yidun": False}
    if isinstance(raw, dict):
        return raw
    return {"yidun": False}


# ---------------------------------------------------------------------------
# Classification — pure function, easy to test
# ---------------------------------------------------------------------------

_YIDUN_TYPE_MAP = [
    ("jigsaw", "slider_jigsaw", "drag"),
    ("--click", "text_click", "click_sequence"),
    ("--word", "word_select", "click_sequence"),
    ("--icon", "icon_click", "click_sequence"),
    ("--order", "word_order", "click_sequence"),
    ("--inference", "inference", "click_sequence"),
    ("--space", "space_inference", "click_sequence"),
    ("--avoid", "avoid_obstacle", "drag"),
    ("--sms", "sms", "input"),
    ("--sense", "sense", "passive"),
    ("--slide", "slider_plain", "drag"),
]

_YIDUN_URL_TYPE_MAP = {
    "/trial/jigsaw": ("slider_jigsaw", "drag"),
    "/trial/picture-click": ("text_click", "click_sequence"),
    "/trial/word-group": ("word_select", "click_sequence"),
    "/trial/word-order": ("word_order", "click_sequence"),
    "/trial/icon-click": ("icon_click", "click_sequence"),
    "/trial/avoid": ("avoid_obstacle", "drag"),
    "/trial/inference": ("inference", "click_sequence"),
    "/trial/space-inference": ("space_inference", "click_sequence"),
    "/trial/sense": ("sense", "passive"),
    "/trial/sms": ("sms", "input"),
}


def classify(probe: dict[str, Any]) -> dict[str, Any] | None:
    """Classify the captcha type from a probe result. Returns None if no captcha."""
    if not probe or not probe.get("yidun"):
        return None

    classes = str(probe.get("yidun_classes", ""))
    url = str(probe.get("url", ""))
    has_jigsaw = probe.get("has_jigsaw_img")
    has_slider = probe.get("has_slider")
    instruction = probe.get("instruction")

    # Jigsaw slider is the most specific: requires both jigsaw image and slider.
    if has_jigsaw and has_slider:
        return {"provider": "netease_yidun", "type": "slider_jigsaw", "action_type": "drag", "instruction": instruction}

    for token, ctype, action in _YIDUN_TYPE_MAP:
        if token in classes:
            return {"provider": "netease_yidun", "type": ctype, "action_type": action, "instruction": instruction}

    for path, (ctype, action) in _YIDUN_URL_TYPE_MAP.items():
        if path in url:
            return {"provider": "netease_yidun", "type": ctype, "action_type": action, "instruction": instruction}

    # Fallback: if there's a slider but no jigsaw, it's likely a plain slider.
    if has_slider:
        return {"provider": "netease_yidun", "type": "slider_plain", "action_type": "drag", "instruction": instruction}

    return {"provider": "netease_yidun", "type": "unknown", "action_type": "unknown", "instruction": instruction}


# ---------------------------------------------------------------------------
# Coordinate mapping
# ---------------------------------------------------------------------------

def image_to_viewport(image_x: float, image_y: float, box: dict[str, float], image_width: int, image_height: int) -> tuple[float, float]:
    """Map a point from image-pixel coordinates to browser CSS viewport coordinates.

    box is the CSS bounding rect of the displayed image element.
    image_width/image_height are the natural (intrinsic) pixel dimensions.
    """
    if not image_width or not image_height:
        return box["x"] + image_x, box["y"] + image_y
    scale_x = box["width"] / image_width
    scale_y = box["height"] / image_height
    return box["x"] + image_x * scale_x, box["y"] + image_y * scale_y


def capture_clip_from_viewport_box(box: dict[str, float], scroll_x: float = 0, scroll_y: float = 0) -> dict[str, float]:
    """Convert a viewport bounding box to a Page.captureScreenshot clip.

    DOM getBoundingClientRect() returns viewport coordinates. In this extension/CDP
    path, Page.captureScreenshot clip expects document coordinates, so add the
    page scroll offsets for image capture only. Agent-facing element boxes remain
    viewport coordinates because Input.dispatchMouseEvent uses viewport CSS pixels.
    """
    return {
        "x": box["x"] + float(scroll_x or 0),
        "y": box["y"] + float(scroll_y or 0),
        "width": box["width"],
        "height": box["height"],
        "scale": 1,
    }


def panel_image_coordinate_map(panel: dict[str, float], device_pixel_ratio: float = 1) -> dict[str, Any]:
    """Return mapping metadata for the returned panel screenshot.

    Page.captureScreenshot returns device pixels. The element boxes returned to
    agents are CSS viewport pixels. If a vision model points at x/y in the panel
    screenshot, convert with:

      viewport_x = panel_box.x + panel_image_x * panel_image_to_viewport_scale_x
      viewport_y = panel_box.y + panel_image_y * panel_image_to_viewport_scale_y
    """
    dpr = float(device_pixel_ratio or 1)
    if dpr <= 0:
        dpr = 1
    return {
        "panel_box": panel,
        "panel_image_width": round(panel["width"] * dpr),
        "panel_image_height": round(panel["height"] * dpr),
        "panel_image_to_viewport_scale_x": panel["width"] / max(panel["width"] * dpr, 1),
        "panel_image_to_viewport_scale_y": panel["height"] / max(panel["height"] * dpr, 1),
        "device_pixel_ratio": dpr,
    }


# ---------------------------------------------------------------------------
# Panel screenshot — captures just the captcha region via CDP clip
# ---------------------------------------------------------------------------

def capture_panel_image(driver, tab_id: str, box: dict[str, float], token: str | None = None) -> str | None:
    """Capture a screenshot clipped to the captcha panel box. Returns base64 PNG or None."""
    if not box or box.get("width", 0) < 2 or box.get("height", 0) < 2:
        return None
    clip = {"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"], "scale": 1}
    try:
        result = cdp.send_cdp(
            driver, tab_id, "Page.captureScreenshot",
            {"format": "png", "clip": clip, "fromSurface": True},
            token=token,
        )
    except Exception as exc:
        log(f"[verify] panel screenshot failed: {exc}")
        return None
    data = result
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    if isinstance(data, str):
        return data
    return None


# ---------------------------------------------------------------------------
# Full inspection — assembles the final agent-facing payload
# ---------------------------------------------------------------------------

def inspect(driver, tab_id: str, *, include_image: bool = True, token: str | None = None) -> dict[str, Any]:
    """Inspect the page for a captcha widget and return structured metadata.

    Returns a dict with at least:
      - status: "success"
      - found: bool
    When found, also includes:
      - provider, type, action_type, instruction, state
      - elements: bounding boxes of key DOM nodes
      - images: panel_base64 (and/or bg_base64) — only when include_image=True
      - coordinate_map: scale factors for image-to-viewport conversion
    """
    probe = probe_page(driver, tab_id, token=token)
    info = classify(probe)
    if info is None:
        return {"status": "success", "found": False, "tab_id": tab_id}

    result: dict[str, Any] = {
        "status": "success",
        "found": True,
        "tab_id": tab_id,
        "provider": info["provider"],
        "type": info["type"],
        "action_type": info["action_type"],
        "instruction": info.get("instruction"),
        "state": probe.get("state", "ready"),
        "panel_visible": probe.get("panel_visible", False),
        "elements": {},
        "images": {},
        "coordinate_map": {},
    }

    bg = probe.get("bg_img") or {}
    bg_box = bg.get("box")
    panel = probe.get("panel") or bg_box
    result["elements"]["background"] = bg_box
    result["elements"]["panel"] = panel
    result["elements"]["jigsaw"] = (probe.get("jigsaw_img") or {}).get("box")
    result["elements"]["slider"] = (probe.get("slider") or {}).get("box")
    result["elements"]["control"] = probe.get("control")

    # Coordinate map: how to convert image-pixel coords → viewport coords.
    natural_w = bg.get("natural_width") or 0
    natural_h = bg.get("natural_height") or 0
    if bg_box and natural_w and natural_h:
        result["coordinate_map"]["image_to_viewport_scale_x"] = bg_box["width"] / natural_w
        result["coordinate_map"]["image_to_viewport_scale_y"] = bg_box["height"] / natural_h
        result["coordinate_map"]["image_natural_width"] = natural_w
        result["coordinate_map"]["image_natural_height"] = natural_h
        result["coordinate_map"]["background_box"] = bg_box

    if panel:
        result["coordinate_map"].update(panel_image_coordinate_map(panel, probe.get("device_pixel_ratio", 1)))

    if include_image and panel:
        capture_box = capture_clip_from_viewport_box(panel, probe.get("scroll_x", 0), probe.get("scroll_y", 0))
        panel_b64 = capture_panel_image(driver, tab_id, capture_box, token=token)
        if panel_b64:
            result["images"]["panel_base64"] = panel_b64

    return result
