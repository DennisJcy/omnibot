from __future__ import annotations

import json
import math
import random
import time

from . import cdp


def broadcast_mouse_visual(driver, tab_id: str, event: str, *, x: float, y: float,
                           token: str | None = None, **extra) -> None:
    """Mirror CUA input to the extension's in-page mouse visualizer.

    CDP changes the page's input state but cannot move the browser-host cursor.
    The extension receives this best-effort side channel and paints the same
    point/phase in the visible tab.  Never let visualization break an action.
    """
    broadcaster = getattr(driver, "broadcast_extension_event", None)
    if not callable(broadcaster):
        return
    try:
        raw_tab_id = driver._raw_tab_id(tab_id, token=token)
        payload = {
            "type": "mouse_visual",
            "tabId": int(raw_tab_id),
            "event": {"type": event, "x": float(x), "y": float(y), **extra},
        }
        broadcaster(payload, token=token)
    except Exception:
        return


def click(driver, tab_id: str, x: float, y: float, *, button: str = "left", click_count: int = 1, token: str | None = None) -> dict:
    mask = 1 if button == "left" else 2
    new_tabs = []
    cdp.evaluate(driver, tab_id, _coordinate_click_probe_start_script(x, y), token=token)
    broadcast_mouse_visual(driver, tab_id, "move", x=x, y=y, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, token=token)
    presses = 2 if click_count >= 2 else 1
    for current_click in range(1, presses + 1):
        broadcast_mouse_visual(driver, tab_id, "press", x=x, y=y, button=button, clickCount=current_click, token=token)
        cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": button, "buttons": mask, "clickCount": current_click}, token=token)
        broadcast_mouse_visual(driver, tab_id, "release", x=x, y=y, button=button, clickCount=current_click, token=token)
        release_result = cdp.send_cdp(
            driver,
            tab_id,
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": button, "buttons": 0, "clickCount": current_click},
            token=token,
            watch_new_tabs=True,
        )
        new_tabs.extend(release_result.get("_omnibot_newTabs", []))
    probe = cdp.evaluate(driver, tab_id, _coordinate_click_probe_result_script(), token=token)
    target = probe.get("target") if isinstance(probe, dict) else None
    if not (isinstance(probe, dict) and probe.get("clicked")):
        fallback_result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.evaluate",
            {
                "expression": _coordinate_click_fallback_script(x, y, button, click_count),
                "awaitPromise": True,
                "returnByValue": True,
            },
            token=token,
            watch_new_tabs=True,
        )
        target = fallback_result.get("result", {}).get("value")
        new_tabs.extend(fallback_result.get("_omnibot_newTabs", []))
    result = {"x": x, "y": y, "button": button, "click_count": click_count}
    if isinstance(target, dict) and target:
        result["target"] = target
    if new_tabs:
        result["newTabs"] = list({
            (str(tab.get("browserClientId", "")), str(tab.get("id", ""))): tab
            for tab in new_tabs
            if isinstance(tab, dict) and tab.get("id") is not None
        }.values())
    return result


def _coordinate_click_probe_start_script(x: float, y: float) -> str:
    return f"""
(() => {{
  const x = {float(x)};
  const y = {float(y)};
  const el = document.elementFromPoint(x, y);
  const target = el ? {{ tag: el.tagName, id: el.id || '', text: (el.innerText || el.textContent || '').trim().slice(0, 80) }} : null;
  window.__omnibotCoordinateClickProbe = {{ clicked: false, target }};
  if (!el) return null;
  const handler = () => {{ window.__omnibotCoordinateClickProbe.clicked = true; }};
  el.addEventListener('click', handler, {{ capture: true, once: true }});
  return target;
}})()
"""


def _coordinate_click_probe_result_script() -> str:
    return """
(() => {
  const result = window.__omnibotCoordinateClickProbe || { clicked: false, target: null };
  delete window.__omnibotCoordinateClickProbe;
  return result;
})()
"""


def _coordinate_click_fallback_script(x: float, y: float, button: str, click_count: int) -> str:
    return f"""
(() => {{
  const x = {float(x)};
  const y = {float(y)};
  const button = {json.dumps(button)};
  const detail = {int(click_count)};
  const el = document.elementFromPoint(x, y);
  if (!el) return null;
  const buttonValue = button === 'right' ? 2 : button === 'middle' ? 1 : 0;
  const opts = {{ bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: buttonValue, detail }};
  if (el.focus) el.focus();
  el.dispatchEvent(new MouseEvent('click', opts));
  if (detail >= 2) el.dispatchEvent(new MouseEvent('dblclick', opts));
  return {{ tag: el.tagName, id: el.id || '', text: (el.innerText || el.textContent || '').trim().slice(0, 80) }};
}})()
"""


def move(driver, tab_id: str, x: float, y: float, *, token: str | None = None) -> dict:
    broadcast_mouse_visual(driver, tab_id, "move", x=x, y=y, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, token=token)
    return {"x": x, "y": y}


def scroll(driver, tab_id: str, x: float, y: float, scroll_x: float, scroll_y: float, *, token: str | None = None) -> dict:
    broadcast_mouse_visual(driver, tab_id, "move", x=x, y=y, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseWheel", "x": x, "y": y, "deltaX": scroll_x, "deltaY": scroll_y}, token=token)
    return {"x": x, "y": y, "scrollX": scroll_x, "scrollY": scroll_y}


def _generate_trajectory(
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    *,
    steps: int,
    jitter: float,
    overshoot: float,
    rng: random.Random,
) -> list[tuple[float, float]]:
    """Pure trajectory generator (no side effects).

    Returns a list of (x, y) points from just after the origin to the target,
    including an overshoot-and-settle tail so the movement mimics a human hand.
    """
    dx = to_x - from_x
    dy = to_y - from_y
    direction = 1 if dx >= 0 else -1
    points: list[tuple[float, float]] = []
    for i in range(1, steps + 1):
        t = i / steps
        # smootherstep: 6t^5 - 15t^4 + 10t^3
        e = t * t * t * (t * (t * 6 - 15) + 10)
        x = from_x + dx * e
        y = from_y + dy * e
        arc = math.sin(t * math.pi) * jitter * rng.uniform(-1.0, 1.0)
        y += arc + rng.uniform(-jitter * 0.3, jitter * 0.3)
        x += rng.uniform(-jitter * 0.1, jitter * 0.1)
        points.append((x, y))
    if overshoot and overshoot > 0:
        points.append((to_x + direction * overshoot, to_y + rng.uniform(-jitter * 0.3, jitter * 0.3)))
        points.append((to_x + direction * overshoot * 0.4, to_y + rng.uniform(-jitter * 0.2, jitter * 0.2)))
    points.append((to_x, to_y))
    return points


def _realistic_drag(
    driver,
    tab_id: str,
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    *,
    duration_ms: float | None = None,
    steps: int | None = None,
    jitter: float | None = None,
    overshoot: float | None = None,
    token: str | None = None,
) -> None:
    rng = random.Random()
    if steps is None or steps < 8:
        steps = rng.randint(70, 110)
    if jitter is None:
        jitter = rng.uniform(1.0, 2.0)
    if overshoot is None:
        overshoot = rng.uniform(2.0, 6.0)
    if duration_ms is None:
        duration_ms = rng.randint(550, 900)

    points = _generate_trajectory(
        from_x, from_y, to_x, to_y,
        steps=steps, jitter=jitter, overshoot=overshoot, rng=rng,
    )

    broadcast_mouse_visual(driver, tab_id, "move", x=from_x, y=from_y, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": from_x, "y": from_y}, token=token)
    time.sleep(rng.uniform(0.03, 0.07))
    broadcast_mouse_visual(driver, tab_id, "press", x=from_x, y=from_y, button="left", clickCount=1, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": from_x, "y": from_y, "button": "left", "buttons": 1, "clickCount": 1}, token=token)

    per_step = max(0.004, duration_ms / 1000.0 / max(len(points), 1))
    pause_indices = {rng.randint(2, max(3, len(points) // 4)), rng.randint(len(points) // 2, len(points) * 3 // 4)}
    for idx, (x, y) in enumerate(points):
        broadcast_mouse_visual(driver, tab_id, "drag", x=x, y=y, buttons=1, token=token)
        cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": round(x, 2), "y": round(y, 2), "buttons": 1}, token=token)
        if idx in pause_indices:
            time.sleep(rng.uniform(0.02, 0.06))
        else:
            time.sleep(rng.uniform(per_step * 0.5, per_step * 1.4))

    time.sleep(rng.uniform(0.03, 0.08))
    broadcast_mouse_visual(driver, tab_id, "release", x=to_x, y=to_y, button="left", clickCount=1, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": to_x, "y": to_y, "button": "left", "buttons": 0, "clickCount": 1}, token=token)


def _coordinate_drag_probe_start_script(to_x: float, to_y: float) -> str:
    return f"""
(() => {{
  const target = document.elementFromPoint({float(to_x)}, {float(to_y)});
  window.__omnibotCoordinateDragProbe = {{ dropped: false }};
  if (target) target.addEventListener('drop', () => {{
    window.__omnibotCoordinateDragProbe.dropped = true;
  }}, {{ capture: true, once: true }});
  return !!target;
}})()
"""


def _coordinate_drag_probe_result_script() -> str:
    return """
(() => {
  const result = window.__omnibotCoordinateDragProbe || { dropped: false };
  delete window.__omnibotCoordinateDragProbe;
  return result;
})()
"""


def _coordinate_html5_drag_fallback_script(from_x: float, from_y: float, to_x: float, to_y: float) -> str:
    return f"""
(() => {{
  const source = document.elementFromPoint({float(from_x)}, {float(from_y)});
  const target = document.elementFromPoint({float(to_x)}, {float(to_y)});
  if (!source || !target || typeof DataTransfer === 'undefined' || typeof DragEvent === 'undefined') return false;
  const transfer = new DataTransfer();
  const options = (x, y) => ({{ bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, dataTransfer: transfer }});
  source.dispatchEvent(new DragEvent('dragstart', options({float(from_x)}, {float(from_y)})));
  target.dispatchEvent(new DragEvent('dragenter', options({float(to_x)}, {float(to_y)})));
  target.dispatchEvent(new DragEvent('dragover', options({float(to_x)}, {float(to_y)})));
  target.dispatchEvent(new DragEvent('drop', options({float(to_x)}, {float(to_y)})));
  source.dispatchEvent(new DragEvent('dragend', options({float(to_x)}, {float(to_y)})));
  return true;
}})()
"""


def drag(
    driver,
    tab_id: str,
    from_x: float,
    from_y: float,
    to_x: float,
    to_y: float,
    *,
    duration_ms: float | None = None,
    steps: int | None = None,
    jitter: float | None = None,
    overshoot: float | None = None,
    fast: bool = False,
    token: str | None = None,
) -> dict:
    cdp.evaluate(driver, tab_id, _coordinate_drag_probe_start_script(to_x, to_y), token=token)
    if fast:
        broadcast_mouse_visual(driver, tab_id, "move", x=from_x, y=from_y, token=token)
        cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": from_x, "y": from_y}, token=token)
        broadcast_mouse_visual(driver, tab_id, "press", x=from_x, y=from_y, button="left", clickCount=1, token=token)
        cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": from_x, "y": from_y, "button": "left", "buttons": 1, "clickCount": 1}, token=token)
        broadcast_mouse_visual(driver, tab_id, "drag", x=to_x, y=to_y, buttons=1, token=token)
        cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": to_x, "y": to_y, "buttons": 1}, token=token)
        broadcast_mouse_visual(driver, tab_id, "release", x=to_x, y=to_y, button="left", clickCount=1, token=token)
        cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": to_x, "y": to_y, "button": "left", "buttons": 0, "clickCount": 1}, token=token)
    else:
        _realistic_drag(
            driver, tab_id, from_x, from_y, to_x, to_y,
            duration_ms=duration_ms, steps=steps, jitter=jitter, overshoot=overshoot, token=token,
        )
    probe = cdp.evaluate(driver, tab_id, _coordinate_drag_probe_result_script(), token=token)
    if not (isinstance(probe, dict) and probe.get("dropped")):
        cdp.evaluate(driver, tab_id, _coordinate_html5_drag_fallback_script(from_x, from_y, to_x, to_y), token=token)
    return {"from": {"x": from_x, "y": from_y}, "to": {"x": to_x, "y": to_y}}
