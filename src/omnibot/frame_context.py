from __future__ import annotations

import json
from typing import Any


def active_frame_target(ctx: Any) -> str:
    target = str(getattr(ctx, "frame_target", "") or "").strip()
    return "" if target.lower() in {"", "/", "main", "top", "default", "root"} else target


def frame_error_value(reason: str) -> str:
    messages = {
        "not_found": "Selected frame was not found in the current page.",
        "cross_origin_or_inaccessible": "Selected frame is cross-origin or inaccessible from this page context.",
    }
    return (
        "({"
        "__omnibotFrameError: true, "
        "target, "
        f"reason: {json.dumps(reason)}, "
        f"message: {json.dumps(messages.get(reason, 'Selected frame is not available.'))}"
        "})"
    )


def scoped_script(
    script: str,
    frame_target: str = "",
    missing_value: str = "null",
    inaccessible_value: str | None = None,
) -> str:
    target = str(frame_target or "").strip()
    if not target or target.lower() in {"main", "top", "default"}:
        return script
    inaccessible_value = inaccessible_value or missing_value
    return f"""
(() => {{
  const target = {json.dumps(target)};
  const frames = Array.from(globalThis.document.querySelectorAll('iframe,frame'));
  function matches(frame) {{
    if (!frame) return false;
    if (target.startsWith('#') || target.startsWith('.') || target.startsWith('[')) {{
      try {{ return frame.matches(target); }} catch (_) {{ return false; }}
    }}
    const attrs = [
      frame.id,
      frame.name,
      frame.title,
      frame.getAttribute('name'),
      frame.getAttribute('title'),
      frame.getAttribute('src'),
      frame.src
    ].filter(Boolean).map(String);
    return attrs.some((value) => value === target || value.includes(target));
  }}
  let directFrame = null;
  try {{ directFrame = globalThis.document.querySelector(target); }} catch (_) {{}}
  const frame = directFrame && frames.includes(directFrame) ? directFrame : frames.find(matches);
  if (!frame) return {missing_value};
  if (!frame.contentWindow || !frame.contentDocument) return {inaccessible_value};
  const window = frame.contentWindow;
  const document = frame.contentDocument;
  const NodeFilter = window.NodeFilter;
  const getComputedStyle = window.getComputedStyle.bind(window);
  return ({script});
}})()
"""


def select_frame_id(frame_tree: dict[str, Any], descriptor: dict[str, Any] | None) -> str | None:
    """Find the CDP frame id matching the selected iframe element."""
    if not isinstance(frame_tree, dict) or not isinstance(descriptor, dict):
        return None
    frame_tree = frame_tree.get("frameTree", frame_tree)
    if not isinstance(frame_tree, dict):
        return None
    wanted = {
        str(value)
        for key in ("id", "name", "title", "src", "url")
        if (value := descriptor.get(key))
    }
    if not wanted:
        return None

    def walk(node: dict[str, Any]) -> str | None:
        frame = node.get("frame")
        if isinstance(frame, dict):
            values = {str(frame.get(key)) for key in ("id", "name", "url") if frame.get(key)}
            if any(needle == value or needle in value for needle in wanted for value in values):
                return str(frame.get("id"))
        for child in node.get("childFrames") or []:
            if isinstance(child, dict):
                found = walk(child)
                if found:
                    return found
        return None

    return walk(frame_tree)
