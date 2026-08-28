from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urljoin

from . import cdp
from . import cua
from . import frame_context
from .refs import RefMap, parse_ref


class InteractionError(RuntimeError):
    pass


def box_model_center(model: dict[str, Any]) -> tuple[float, float]:
    quad = model.get("content") or model.get("border") or []
    if len(quad) < 8:
        raise InteractionError("Element box model has no usable content quad")
    xs = [float(quad[i]) for i in range(0, 8, 2)]
    ys = [float(quad[i]) for i in range(1, 8, 2)]
    return (sum(xs) / 4.0, sum(ys) / 4.0)


def box_from_model(model: dict[str, Any]) -> dict[str, float]:
    quad = model.get("content") or model.get("border") or []
    if len(quad) < 8:
        raise InteractionError("Element box model has no usable content quad")
    xs = [float(quad[i]) for i in range(0, 8, 2)]
    ys = [float(quad[i]) for i in range(1, 8, 2)]
    return {
        "x": min(xs),
        "y": min(ys),
        "width": max(xs) - min(xs),
        "height": max(ys) - min(ys),
    }


def _boxes_are_stable(first: dict[str, float], second: dict[str, float], *, tolerance: float = 0.5) -> bool:
    return all(abs(float(first[key]) - float(second[key])) <= tolerance for key in ("x", "y", "width", "height"))


def _backend_box(driver, tab_id: str | int, backend_node_id: int, *, token: str | None = None) -> dict[str, float]:
    result = cdp.send_cdp(
        driver,
        tab_id,
        "DOM.getBoxModel",
        {"backendNodeId": backend_node_id},
        token=token,
    )
    return box_from_model(result.get("model", {}))


def _viewport_metrics(driver, tab_id: str | int, *, token: str | None = None) -> dict[str, float]:
    metrics = cdp.send_cdp(driver, tab_id, "Page.getLayoutMetrics", {}, token=token)
    viewport = (
        metrics.get("cssVisualViewport")
        or metrics.get("visualViewport")
        or metrics.get("cssLayoutViewport")
        or metrics.get("layoutViewport")
        or {}
    )
    return {
        "page_x": float(viewport.get("pageX") or 0),
        "page_y": float(viewport.get("pageY") or 0),
        "width": float(viewport.get("clientWidth") or 0),
        "height": float(viewport.get("clientHeight") or 0),
    }


def _assert_backend_enabled(driver, tab_id: str | int, backend_node_id: int, *, token: str | None = None) -> None:
    node = cdp.send_cdp(
        driver,
        tab_id,
        "DOM.describeNode",
        {"backendNodeId": backend_node_id, "depth": 0},
        token=token,
    ).get("node", {})
    attributes = node.get("attributes") or []
    attrs = {str(attributes[index]).lower(): str(attributes[index + 1]).lower() for index in range(0, len(attributes) - 1, 2)}
    if "disabled" in attrs or attrs.get("aria-disabled") == "true":
        raise InteractionError("Element is disabled")


def _backend_hit_diagnostic(driver, tab_id: str | int, x: float, y: float, *, token: str | None = None) -> int | None:
    try:
        hit = cdp.send_cdp(
            driver,
            tab_id,
            "DOM.getNodeForLocation",
            {"x": round(x), "y": round(y), "includeUserAgentShadowDOM": True},
            token=token,
        )
    except Exception:
        # Older extension/debugger combinations may not implement this
        # diagnostic. Geometry and viewport checks still prevent stale or
        # off-screen coordinates from being dispatched.
        hit = {}
    backend_id = hit.get("backendNodeId")
    return int(backend_id) if backend_id is not None else None


def _backend_contains_node(
    driver,
    tab_id: str | int,
    backend_node_id: int,
    candidate_backend_node_id: int,
    *,
    token: str | None = None,
) -> bool:
    if backend_node_id == candidate_backend_node_id:
        return True
    described = cdp.send_cdp(
        driver,
        tab_id,
        "DOM.describeNode",
        {"backendNodeId": backend_node_id, "depth": -1, "pierce": True},
        token=token,
    ).get("node", {})
    pending = [described]
    while pending:
        node = pending.pop()
        if int(node.get("backendNodeId") or 0) == candidate_backend_node_id:
            return True
        pending.extend(node.get("children") or [])
        pending.extend(node.get("shadowRoots") or [])
        pending.extend(node.get("pseudoElements") or [])
        if node.get("contentDocument"):
            pending.append(node["contentDocument"])
    return False


def selector_center_script(selector: str) -> str:
    return f"""
(() => {{
  const selector = {json.dumps(selector)};
  let el = null;
  if (selector.startsWith('text=')) {{
    const needle = selector.slice(5);
    el = Array.from(document.querySelectorAll('a,button,input,textarea,select,[role],*')).find(node => (node.innerText || node.textContent || '').trim().includes(needle));
  }} else if (selector.startsWith('xpath=')) {{
    el = document.evaluate(selector.slice(6), document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  }} else {{
    el = document.querySelector(selector);
  }}
  if (!el) return null;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  const rect = el.getBoundingClientRect();
  return {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }};
}})()
"""


def resolve_center(
    driver,
    tab_id: str | int,
    selector_or_ref: str,
    ref_map: RefMap,
    *,
    token: str | None = None,
    frame_target: str = "",
) -> tuple[float, float]:
    entry = ref_map.get(tab_id, selector_or_ref)
    if entry and entry.backend_node_id is not None:
        try:
            result = cdp.send_cdp(
                driver,
                tab_id,
                "DOM.getBoxModel",
                {"backendNodeId": entry.backend_node_id},
                token=token,
            )
            return box_model_center(result.get("model", {}))
        except Exception:
            if entry.box:
                return (
                    float(entry.box["x"]) + float(entry.box["width"]) / 2.0,
                    float(entry.box["y"]) + float(entry.box["height"]) / 2.0,
                )
    if entry and entry.box:
        return (
            float(entry.box["x"]) + float(entry.box["width"]) / 2.0,
            float(entry.box["y"]) + float(entry.box["height"]) / 2.0,
        )
    result = cdp.send_cdp(
        driver,
        tab_id,
        "Runtime.evaluate",
        {
            "expression": frame_context.scoped_script(selector_center_script(selector_or_ref), frame_target),
            "awaitPromise": True,
            "returnByValue": True,
        },
        token=token,
    )
    value = result.get("result", {}).get("value")
    if not value:
        raise InteractionError(f"Element not found: {selector_or_ref}")
    width = float(value.get("width") or 0)
    height = float(value.get("height") or 0)
    if width <= 0 or height <= 0:
        raise InteractionError(f"Element is not visible: {selector_or_ref}")
    return (float(value["x"]) + width / 2.0, float(value["y"]) + height / 2.0)


def dispatch_click(driver, tab_id: str | int, x: float, y: float, *, button: str = "left", click_count: int = 1, token: str | None = None) -> None:
    cua.click(driver, tab_id, x, y, button=button, click_count=click_count, token=token)


def dispatch_verified_click(driver, tab_id: str | int, x: float, y: float, *, button: str = "left", click_count: int = 1, token: str | None = None) -> dict[str, Any]:
    """Dispatch pointer input after the caller has completed hit-testing.

    The extension transport may attach/detach the debugger around individual
    commands, so use the established CUA click synthesis and its checked DOM
    fallback instead of assuming a cross-session press/release made a click.
    """
    return cua.click(driver, str(tab_id), x, y, button=button, click_count=click_count, token=token)


def activate_selector_script(selector: str, click_count: int) -> str:
    return f"""
(() => {{
  const selector = {json.dumps(selector)};
  const clickCount = {int(click_count)};
  function deferElementClick(el) {{
    el.click();
  }}
  let el = null;
  if (selector.startsWith('text=')) {{
    const needle = selector.slice(5);
    el = Array.from(document.querySelectorAll('a,button,input,textarea,select,[role],*')).find(node => (node.innerText || node.textContent || '').trim().includes(needle));
  }} else if (selector.startsWith('xpath=')) {{
    el = document.evaluate(selector.slice(6), document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
  }} else {{
    el = document.querySelector(selector);
  }}
  if (!el) return null;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  const rect = el.getBoundingClientRect();
  function textMatchRange(element) {{
    const rawOffset = element.getAttribute('data-omnibot-text-offset');
    const rawLength = element.getAttribute('data-omnibot-text-length');
    if (rawOffset === null || rawLength === null) return null;
    const offset = Number(rawOffset);
    const length = Number(rawLength);
    if (!Number.isFinite(offset) || !Number.isFinite(length) || length <= 0) return null;
    function boundary(targetOffset) {{
      let seen = 0;
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {{
        const textLength = (node.nodeValue || '').length;
        if (seen + textLength >= targetOffset) {{
          return {{ node, offset: Math.max(0, Math.min(textLength, targetOffset - seen)) }};
        }}
        seen += textLength;
        node = walker.nextNode();
      }}
      return null;
    }}
    const start = boundary(offset);
    const end = boundary(offset + length);
    if (!start || !end) return null;
    const range = document.createRange(); // Range used for text-node precision.
    range.setStart(start.node, start.offset);
    range.setEnd(end.node, end.offset);
    return {{ range, end }};
  }}
  const match = textMatchRange(el);
  let matchPoint = null;
  if (match) {{
    const rects = Array.from(match.range.getClientRects());
    const textRect = rects[rects.length - 1];
    if (textRect) matchPoint = {{ x: textRect.right, y: textRect.top, width: 1, height: textRect.height }};
    const editable = el.closest('[contenteditable="true"]');
    if (editable) {{
      const caret = document.createRange();
      caret.setStart(match.end.node, match.end.offset);
      caret.collapse(true);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(caret);
      editable.focus();
      if (matchPoint) return matchPoint;
    }}
  }}
  if (clickCount >= 2) {{
    el.dispatchEvent(new MouseEvent('dblclick', {{ bubbles: true, cancelable: true, view: window, detail: 2 }}));
  }} else {{
    deferElementClick(el);
    if (el.focus) el.focus();
  }}
  return matchPoint || {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }};
}})()
"""


def activate_transient_option_script(opener_selector: str, option_selector: str, option_name: str, click_count: int) -> str:
    return f"""
(() => new Promise((resolve) => {{
  const openerSelector = {json.dumps(opener_selector)};
  const optionSelector = {json.dumps(option_selector)};
  const optionName = {json.dumps(option_name)};
  const clickCount = {int(click_count)};
  function label(el) {{ return (el.getAttribute('aria-label') || el.innerText || el.textContent || el.value || '').trim(); }}
  function visible(el) {{
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
  }}
  function findOption() {{
    const byName = Array.from(document.querySelectorAll('[role="option"], [role="menuitem"]')).find((node) => visible(node) && label(node) === optionName);
    if (byName) return byName;
    let el = null;
    try {{ el = document.querySelector(optionSelector); }} catch (_) {{}}
    if (visible(el) && (!optionName || label(el) === optionName)) return el;
    return null;
  }}
  function rectOf(el) {{
    el.scrollIntoView({{ block: 'center', inline: 'center' }});
    const rect = el.getBoundingClientRect();
    return {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }};
  }}
  function openElement(el) {{
    el.scrollIntoView({{ block: 'center', inline: 'center' }});
    const rect = el.getBoundingClientRect();
    el.click();
    return {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }};
  }}
  let option = findOption();
  if (option) return resolve(rectOf(option));
  let opener = null;
  try {{ opener = document.querySelector(openerSelector); }} catch (_) {{}}
  if (!visible(opener)) return resolve(null);
  openElement(opener);
  requestAnimationFrame(() => requestAnimationFrame(() => {{
    option = findOption();
    resolve(option ? rectOf(option) : null);
  }}));
}}))
// activateTransientOption
"""


def open_transient_opener_script(opener_selector: str) -> str:
    return f"""
(() => {{
  const openerSelector = {json.dumps(opener_selector)};
  let opener = null;
  try {{ opener = document.querySelector(openerSelector); }} catch (_) {{}}
  if (!opener) return false;
  const style = getComputedStyle(opener);
  const rect = opener.getBoundingClientRect();
  if (style.display === 'none' || style.visibility === 'hidden' || rect.width <= 0 || rect.height <= 0) return false;
  opener.scrollIntoView({{ block: 'center', inline: 'center' }});
  opener.click();
  return true;
}})()
"""


def visible_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    width = float(value.get("width") or 0)
    height = float(value.get("height") or 0)
    return value if width > 0 and height > 0 else None


def backend_action_function() -> str:
    return """
function(clickCount) {
  const el = this;
  if (!el || !el.scrollIntoView || !el.getBoundingClientRect) return null;
  function deferElementClick(el) {
    el.click();
  }
  el.scrollIntoView({ block: 'center', inline: 'center' });
  const rect = el.getBoundingClientRect();
  if (clickCount >= 2) {
    el.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window, detail: 2 }));
  } else {
    deferElementClick(el);
  }
  return { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
}
"""


def named_element_script(role: str, name: str, nth: int | None, click_count: int) -> str:
    return f"""
(() => {{
  const role = {json.dumps(role)};
  const name = {json.dumps(name)};
  const nth = {int(nth or 0)};
  const clickCount = {int(click_count)};
  function deferElementClick(el) {{
    el.click();
  }}
  const roleSelectors = {{
    button: 'button,[role="button"]',
    link: 'a,[role="link"]',
    textbox: 'input,textarea,[role="textbox"]',
    richtext: '[contenteditable="true"],[role="textbox"][aria-multiline="true"]',
    searchbox: 'input[type="search"],[role="searchbox"]'
  }};
  const selector = roleSelectors[role] || 'a,button,input,textarea,select,[role],*';
  const label = (el) => (el.getAttribute('aria-label') || el.closest('label')?.innerText || el.innerText || el.textContent || el.placeholder || el.value || '').trim();
  const labelText = (el) => (el.closest('label') ? label(el.closest('label')) : '');
  const controls = Array.from(document.querySelectorAll('input[type="radio"],input[type="checkbox"]'));
  const control = ['checkbox', 'radio'].includes(role)
    ? controls.find(control => control.type === role && labelText(control) === name)
    : null;
  if (control) {{
    const target = control.closest('label') || control;
    target.scrollIntoView({{ block: 'center', inline: 'center' }});
    const rectSource = target.getBoundingClientRect().width > 0 && target.getBoundingClientRect().height > 0 ? target : control;
    const rect = rectSource.getBoundingClientRect();
    deferElementClick(control);
    if (control.focus) control.focus();
    return {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }};
  }}
  const matches = Array.from(document.querySelectorAll(selector)).filter(el => label(el) === name);
  const el = matches[nth] || matches[0];
  if (!el) return null;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  const rect = el.getBoundingClientRect();
  if (clickCount >= 2) {{
    el.dispatchEvent(new MouseEvent('dblclick', {{ bubbles: true, cancelable: true, view: window, detail: 2 }}));
  }} else {{
    deferElementClick(el);
    if (el.focus) el.focus();
  }}
  return {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }};
}})()
"""


def named_element_box_script(role: str, name: str, nth: int | None) -> str:
    return f"""
(() => {{
  const role = {json.dumps(role)};
  const name = {json.dumps(name)};
  const nth = {int(nth or 0)};
  const roleSelectors = {{
    button: 'button,[role="button"]',
    link: 'a,[role="link"]',
    textbox: 'input,textarea,[role="textbox"]',
    searchbox: 'input[type="search"],[role="searchbox"]'
  }};
  const selector = roleSelectors[role] || 'a,button,input,textarea,select,[role],*';
  const label = (el) => (el.getAttribute('aria-label') || el.closest('label')?.innerText || el.innerText || el.textContent || el.placeholder || el.value || '').trim();
  const matches = Array.from(document.querySelectorAll(selector)).filter(el => label(el) === name);
  const el = matches[nth] || matches[0];
  if (!el) return null;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  const rect = el.getBoundingClientRect();
  return {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }};
}})()
"""


def named_href_script(role: str, name: str, nth: int | None) -> str:
    return f"""
(() => {{
  const name = {json.dumps(name)};
  const nth = {int(nth or 0)};
  const label = (el) => (el.getAttribute('aria-label') || el.innerText || el.textContent || '').trim();
  const matches = Array.from(document.querySelectorAll('a,[role="link"]')).filter(el => label(el) === name);
  const el = matches[nth] || matches[0];
  if (!el) return null;
  const href = el.href || el.getAttribute('href');
  return href ? new URL(href, document.baseURI).toString() : null;
}})()
"""


def activate_backend_node(driver, tab_id: str | int, backend_node_id: int, click_count: int, *, token: str | None = None) -> dict[str, Any]:
    try:
        before_box = _backend_box(driver, tab_id, backend_node_id, token=token)
        cdp.send_cdp(
            driver,
            tab_id,
            "DOM.scrollIntoViewIfNeeded",
            {"backendNodeId": backend_node_id},
            token=token,
        )
        first_box = _backend_box(driver, tab_id, backend_node_id, token=token)
        clicked_viewport = _viewport_metrics(driver, tab_id, token=token)
        _assert_backend_enabled(driver, tab_id, backend_node_id, token=token)
        # The intervening CDP reads give layout a rendering opportunity even
        # when the tab is backgrounded and requestAnimationFrame is throttled.
        # DOM.getBoxModel is already in the visual-viewport coordinate space
        # consumed by Input.dispatchMouseEvent; Page.getLayoutMetrics supplies
        # viewport bounds but its page offset must not be subtracted again.
        clicked_box = _backend_box(driver, tab_id, backend_node_id, token=token)
        if not _boxes_are_stable(first_box, clicked_box):
            raise InteractionError("Element did not become stable before click")
        if clicked_box["width"] <= 0 or clicked_box["height"] <= 0:
            raise InteractionError("Element is not visible after scrolling")
        left = max(0.0, clicked_box["x"])
        top = max(0.0, clicked_box["y"])
        right = min(clicked_viewport["width"], clicked_box["x"] + clicked_box["width"])
        bottom = min(clicked_viewport["height"], clicked_box["y"] + clicked_box["height"])
        if right <= left or bottom <= top:
            raise InteractionError(
                f"Element is outside the browser viewport after scrolling "
                f"(box={clicked_box}, viewport={clicked_viewport})"
            )
        x = (left + right) / 2.0
        y = (top + bottom) / 2.0
        hit_backend_node_id = _backend_hit_diagnostic(driver, tab_id, x, y, token=token)
        if hit_backend_node_id is not None and not _backend_contains_node(
            driver,
            tab_id,
            backend_node_id,
            hit_backend_node_id,
            token=token,
        ):
            raise InteractionError("Element is covered by another element at the click point")
        pointer_result = dispatch_verified_click(driver, tab_id, x, y, token=token, click_count=click_count) or {}
        hit_test = hit_backend_node_id is not None or bool(pointer_result.get("target"))
        return {
            **clicked_box,
            "auto_scrolled": before_box is None or not _boxes_are_stable(before_box, clicked_box),
            "before_box": before_box,
            "clicked_box": clicked_box,
            "hit_test": hit_test,
            "hit_backend_node_id": hit_backend_node_id,
        }
    except (InteractionError, cdp.CdpError):
        raise
    except Exception as exc:
        raise InteractionError(f"Unable to activate backend node {backend_node_id}: {exc}") from exc


def activate_element(driver, tab_id: str | int, selector_or_ref: str, ref_map: RefMap, *, token: str | None = None, click_count: int = 1, frame_target: str = "") -> tuple[float, float, list[dict[str, Any]], dict[str, Any]]:
    entry = ref_map.get(tab_id, selector_or_ref)
    value = None
    new_tabs: list[dict[str, Any]] = []
    activation: dict[str, Any] = {}
    is_transient_option = bool(entry and entry.role in {"option", "menuitem"} and entry.opener_selector and entry.selector)
    # Ref boxes describe the snapshot moment and are never safe click
    # coordinates. Re-resolve the precise backend node, scroll it into view,
    # wait for stable live geometry, and hit-test before dispatching input.
    if entry and entry.backend_node_id is not None and not is_transient_option and not frame_target:
        value = activate_backend_node(driver, tab_id, entry.backend_node_id, click_count, token=token)
        activation = {
            key: value.get(key)
            for key in ("auto_scrolled", "before_box", "clicked_box", "hit_test", "hit_backend_node_id")
            if key in value
        }
    if frame_target:
        frame_script = (
            named_element_script(entry.role, entry.name, entry.nth, click_count)
            if entry and not entry.selector
            else activate_selector_script(entry.selector if entry and entry.selector else selector_or_ref, click_count)
        )
        try:
            value = visible_result(cdp.evaluate_in_frame(driver, tab_id, frame_target, frame_script, token=token))
        except Exception:
            value = None
    if not value and entry and frame_target and not entry.selector and not is_transient_option:
        result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.evaluate",
            {
                "expression": frame_context.scoped_script(named_element_script(entry.role, entry.name.strip(), entry.nth, click_count), frame_target),
                "awaitPromise": True,
                "returnByValue": True,
            },
            token=token,
            watch_new_tabs=True,
        )
        new_tabs.extend(result.get("_omnibot_newTabs", []) if isinstance(result, dict) else [])
        value = visible_result(result.get("result", {}).get("value"))
    if not value and entry and entry.role in {"button", "link", "textbox", "searchbox"} and not entry.selector and not is_transient_option:
        result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.evaluate",
            {
                "expression": frame_context.scoped_script(named_element_box_script(entry.role, entry.name, entry.nth), frame_target),
                "awaitPromise": True,
                "returnByValue": True,
            },
            token=token,
            watch_new_tabs=True,
        )
        new_tabs.extend(result.get("_omnibot_newTabs", []) if isinstance(result, dict) else [])
        value = visible_result(result.get("result", {}).get("value"))
        if value:
            dispatch_click(
                driver,
                tab_id,
                float(value["x"]) + float(value["width"]) / 2.0,
                float(value["y"]) + float(value["height"]) / 2.0,
                token=token,
                click_count=click_count,
            )
    if not value and entry and not is_transient_option and not (entry.role == "richtext" and entry.selector):
        result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.evaluate",
            {
                "expression": frame_context.scoped_script(named_element_script(entry.role, entry.name, entry.nth, click_count), frame_target),
                "awaitPromise": True,
                "returnByValue": True,
            },
            token=token,
            watch_new_tabs=True,
        )
        new_tabs.extend(result.get("_omnibot_newTabs", []) if isinstance(result, dict) else [])
        value = visible_result(result.get("result", {}).get("value"))
    fallback_selector = entry.selector if entry and entry.selector else selector_or_ref
    if not value and is_transient_option:
        result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.evaluate",
            {
                "expression": frame_context.scoped_script(activate_transient_option_script(entry.opener_selector, entry.selector, entry.name, click_count), frame_target),
                "awaitPromise": True,
                "returnByValue": True,
            },
            token=token,
            watch_new_tabs=True,
        )
        new_tabs.extend(result.get("_omnibot_newTabs", []) if isinstance(result, dict) else [])
        value = visible_result(result.get("result", {}).get("value"))
        if not value and entry and entry.box:
            opened = cdp.send_cdp(
                driver,
                tab_id,
                "Runtime.evaluate",
                {
                    "expression": frame_context.scoped_script(open_transient_opener_script(entry.opener_selector), frame_target),
                    "awaitPromise": True,
                    "returnByValue": True,
                },
                token=token,
            )
            if opened.get("result", {}).get("value") is True:
                value = entry.box
        if value:
            dispatch_click(
                driver,
                tab_id,
                float(value["x"]) + float(value["width"]) / 2.0,
                float(value["y"]) + float(value["height"]) / 2.0,
                token=token,
                click_count=click_count,
            )
    if not value:
        result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.evaluate",
            {
                "expression": frame_context.scoped_script(activate_selector_script(fallback_selector, click_count), frame_target),
                "awaitPromise": True,
                "returnByValue": True,
            },
            token=token,
            watch_new_tabs=True,
        )
        new_tabs.extend(result.get("_omnibot_newTabs", []) if isinstance(result, dict) else [])
        value = visible_result(result.get("result", {}).get("value"))
    if not value and entry and entry.box and entry.role == "richtext":
        x = float(entry.box["x"]) + float(entry.box["width"]) / 2.0
        y = float(entry.box["y"]) + float(entry.box["height"]) / 2.0
        dispatch_click(driver, tab_id, x, y, token=token, click_count=click_count)
        cdp.evaluate(driver, tab_id, focus_active_element_script(), token=token)
        value = entry.box
    if not value:
        raise InteractionError(f"Element not found: {selector_or_ref}")
    width = float(value.get("width") or 0)
    height = float(value.get("height") or 0)
    x = float(value["x"]) + width / 2.0
    y = float(value["y"]) + height / 2.0
    if frame_target:
        try:
            offset = cdp.evaluate(
                driver,
                tab_id,
                frame_context.scoped_script(
                    "(() => { const rect = frame.getBoundingClientRect(); return {x: rect.left, y: rect.top}; })()",
                    frame_target,
                ),
                token=token,
            )
            if isinstance(offset, dict):
                x += float(offset.get("x") or 0)
                y += float(offset.get("y") or 0)
            # Same-origin frame activation currently uses the frame document's
            # native DOM click. Mirror the final top-viewport point explicitly
            # so the visual cursor replaces any previous top-document click.
            cua.broadcast_mouse_visual(driver, str(tab_id), "release", x=x, y=y, token=token)
        except Exception:
            # Cursor visualization is best-effort and must never turn a
            # successful frame click into a reported interaction failure.
            pass
    return (x, y, new_tabs, activation)


def _location_href(driver, tab_id: str | int, *, token: str | None = None, timeout: float = 15, fallback: str | None = None) -> str | None:
    try:
        href = cdp.evaluate(driver, tab_id, "location.href", token=token, timeout=timeout)
    except Exception:
        return fallback
    return href if isinstance(href, str) else fallback


def backend_link_info(driver, tab_id: str | int, backend_node_id: int, *, token: str | None = None) -> dict[str, str] | None:
    try:
        node = cdp.send_cdp(driver, tab_id, "DOM.describeNode", {"backendNodeId": backend_node_id, "depth": 0}, token=token).get("node", {})
        attrs = node.get("attributes", [])
        values = dict(zip(attrs[::2], attrs[1::2]))
        raw_href = values.get("href")
        if not raw_href:
            return None
        base_uri = cdp.evaluate(driver, tab_id, "document.baseURI", token=token)
        href = urljoin(base_uri, raw_href) if isinstance(base_uri, str) and base_uri else raw_href
        return {"href": href, "target": values.get("target", "")}
    except Exception:
        return None


def click(driver, tab_id: str | int, selector_or_ref: str, ref_map: RefMap, *, token: str | None = None, button: str = "left", click_count: int = 1, frame_target: str = "") -> dict[str, Any]:
    before = _location_href(driver, tab_id, token=token)
    try:
        x, y, new_tabs, activation = activate_element(driver, tab_id, selector_or_ref, ref_map, token=token, click_count=click_count, frame_target=frame_target)
    except (InteractionError, cdp.CdpError):
        after = _location_href(driver, tab_id, token=token, timeout=0.5, fallback=before)
        if before and after and after != before:
            return {"clicked": selector_or_ref, "navigation": True, "url": after}
        raise
    time.sleep(0.15)
    after = _location_href(driver, tab_id, token=token, timeout=0.5, fallback=before)
    entry = ref_map.get(tab_id, selector_or_ref)
    if before and after == before and entry and entry.role == "link" and entry.backend_node_id is not None and not entry.selector:
        link_info = backend_link_info(driver, tab_id, entry.backend_node_id, token=token)
        if link_info and link_info["target"] in {"", "_self"} and link_info["href"] != before:
            driver.jump(link_info["href"], timeout=10, token=token, session_id=tab_id)
            after = _location_href(driver, tab_id, token=token, timeout=0.5, fallback=link_info["href"])
    result = {"clicked": selector_or_ref, "x": x, "y": y, "navigation": before != after, "url": after}
    if new_tabs:
        result["newTabs"] = new_tabs
    result.update(activation)
    return result


def href_script(selector: str) -> str:
    return f"""
(() => {{
  const selector = {json.dumps(selector)};
  const el = selector.startsWith('@') ? null : document.querySelector(selector);
  if (!el) return null;
  const href = el.href || el.getAttribute('href');
  return href ? new URL(href, document.baseURI).toString() : null;
}})()
"""


def backend_href_function() -> str:
    return """
function() {
  const el = this;
  const link = el && (el.closest ? el.closest('a[href]') : null);
  if (!link) return null;
  const href = link.href || link.getAttribute('href');
  return href ? new URL(href, document.baseURI).toString() : null;
}
"""


def href_for_ref(driver, tab_id: str | int, selector_or_ref: str, ref_map: RefMap, *, token: str | None = None) -> str | None:
    entry = ref_map.get(tab_id, selector_or_ref)
    if not entry:
        return None
    result = cdp.send_cdp(
        driver,
        tab_id,
        "Runtime.evaluate",
        {"expression": named_href_script(entry.role, entry.name, entry.nth), "awaitPromise": True, "returnByValue": True},
        token=token,
    )
    value = result.get("result", {}).get("value")
    return str(value) if value else None


def click_new_tab(driver, tab_id: str | int, selector_or_ref: str, ref_map: RefMap, *, token: str | None = None) -> dict[str, Any]:
    href = None
    if parse_ref(selector_or_ref) is not None:
        href = href_for_ref(driver, tab_id, selector_or_ref, ref_map, token=token)
    else:
        href = cdp.evaluate(driver, tab_id, href_script(selector_or_ref), token=token)
    if not href:
        click_result = click(driver, tab_id, selector_or_ref, ref_map, token=token)
        return {"status": "success", **click_result, "new_tab": False, "warning": "Element did not expose href; performed normal click"}
    result = driver.execute_js({"cmd": "tabs", "method": "create", "url": href}, timeout=10, token=token, status_tab_id=int(driver._raw_tab_id(tab_id, token=token)))
    tab = result.get("data") or {}
    browser_client_id = result.get("browserClientId")
    raw_tab_id = str(tab.get("id", "")) if isinstance(tab, dict) else ""
    if isinstance(tab, dict) and raw_tab_id:
        session_id = f"{browser_client_id}:{raw_tab_id}" if browser_client_id else raw_tab_id
        tab = {**tab, "id": session_id, "tab_id": raw_tab_id}
        if browser_client_id:
            tab["browserClientId"] = browser_client_id
    return {"status": "success", "clicked": selector_or_ref, "new_tab": True, "url": href, "tab": tab}


def _is_macos() -> bool:
    import sys
    return sys.platform == "darwin"


KEY_INFO = {
    "Enter": ("Enter", "Enter", 13),
    "Tab": ("Tab", "Tab", 9),
    "Escape": ("Escape", "Escape", 27),
    "Backspace": ("Backspace", "Backspace", 8),
    "Delete": ("Delete", "Delete", 46),
    "ArrowUp": ("ArrowUp", "ArrowUp", 38),
    "ArrowDown": ("ArrowDown", "ArrowDown", 40),
    "ArrowLeft": ("ArrowLeft", "ArrowLeft", 37),
    "ArrowRight": ("ArrowRight", "ArrowRight", 39),
    "Shift": ("Shift", "ShiftLeft", 16),
    "Control": ("Control", "ControlLeft", 17),
    "Meta": ("Meta", "MetaLeft", 91),
}


def parse_key(key: str) -> tuple[str, str, int, int]:
    parts = key.split("+")
    modifiers = 0
    base = parts[-1]
    for part in parts[:-1]:
        lowered = part.lower()
        if lowered in {"control", "ctrl"}:
            modifiers |= 2
        elif lowered in {"meta", "cmd", "command"}:
            modifiers |= 4
        elif lowered == "alt":
            modifiers |= 1
        elif lowered == "shift":
            modifiers |= 8
    base_modifier = base.lower()
    if base_modifier == "shift":
        modifiers |= 8
    elif base_modifier in {"control", "ctrl"}:
        modifiers |= 2
    elif base_modifier in {"meta", "cmd", "command"}:
        modifiers |= 4
    elif base_modifier == "alt":
        modifiers |= 1
    if base in KEY_INFO:
        name, code, key_code = KEY_INFO[base]
        return name, code, key_code, modifiers
    if len(base) == 1 and base.isalpha():
        upper = base.upper()
        return base, f"Key{upper}", ord(upper), modifiers
    if len(base) == 1 and base.isdigit():
        return base, f"Digit{base}", ord(base), modifiers
    return base, base, 0, modifiers


def bring_to_front(driver, tab_id: str | int, *, token: str | None = None) -> None:
    cdp.send_cdp(driver, tab_id, "Page.bringToFront", {}, token=token)


def dispatch_printable_key(driver, tab_id: str | int, char: str, *, modifiers: int = 0, emit_text: bool = True, token: str | None = None) -> None:
    key_name, code, key_code, char_modifiers = parse_key(char)
    modifiers |= char_modifiers
    generated_char = char.upper() if modifiers & 8 and char.isalpha() else char
    if char == " ":
        key_name, code, key_code = " ", "Space", 32
    elif key_code == 0 and len(char) == 1:
        key_code = ord(char.upper())
    down = {
        "type": "rawKeyDown",
        "key": key_name,
        "code": code,
        "windowsVirtualKeyCode": key_code,
        "nativeVirtualKeyCode": key_code,
        "modifiers": modifiers,
        "text": generated_char if emit_text else "",
        "unmodifiedText": char if emit_text else "",
    }
    up = {
        "type": "keyUp",
        "key": key_name,
        "code": code,
        "windowsVirtualKeyCode": key_code,
        "nativeVirtualKeyCode": key_code,
        "modifiers": modifiers,
    }
    cdp.send_cdp(driver, tab_id, "Input.dispatchKeyEvent", down, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchKeyEvent", up, token=token)


def dispatch_text_keys(driver, tab_id: str | int, text: str, *, modifiers: int = 0, emit_text: bool = True, token: str | None = None, ensure_front: bool = True) -> None:
    if ensure_front:
        bring_to_front(driver, tab_id, token=token)
    for char in text:
        if char == "\n":
            press_key(driver, tab_id, "Enter", token=token)
        else:
            dispatch_printable_key(driver, tab_id, char, modifiers=modifiers, emit_text=emit_text, token=token)


def press_key(driver, tab_id: str | int, key: str, *, token: str | None = None, event_type: str = "press") -> dict[str, Any]:
    key_name, code, key_code, modifiers = parse_key(key)
    # Modifier key state is preserved by CDP's rawKeyDown path; plain keyDown
    # reports the event but does not make Shift/Ctrl/Alt affect later keys.
    down_type = "rawKeyDown" if key_name in {"Shift", "Control", "Meta", "Alt"} else "keyDown"
    down = {"type": down_type, "key": key_name, "code": code, "windowsVirtualKeyCode": key_code, "nativeVirtualKeyCode": key_code, "modifiers": modifiers}
    up = {"type": "keyUp", "key": key_name, "code": code, "windowsVirtualKeyCode": key_code, "nativeVirtualKeyCode": key_code, "modifiers": modifiers}
    bring_to_front(driver, tab_id, token=token)
    if event_type in {"press", "down"}:
        cdp.send_cdp(driver, tab_id, "Input.dispatchKeyEvent", down, token=token)
    if event_type in {"press", "up"}:
        cdp.send_cdp(driver, tab_id, "Input.dispatchKeyEvent", up, token=token)
    return {"key": key, "event": event_type}


def save_active_element(driver, tab_id: str | int, *, token: str | None = None) -> bool:
    return bool(cdp.evaluate(driver, tab_id, """
(() => {
  const active = document.activeElement;
  if (active && active !== document.body && active !== document.documentElement) {
    window.__omnibotKeyboardFocus = active;
    return true;
  }
  return false;
})()
""", token=token))


def restore_saved_active_element(driver, tab_id: str | int, *, token: str | None = None) -> bool:
    return bool(cdp.evaluate(driver, tab_id, """
(() => {
  const active = window.__omnibotKeyboardFocus;
  try {
    if (active && active.focus) active.focus();
  } finally {
    try { delete window.__omnibotKeyboardFocus; } catch (_) {}
  }
  return Boolean(active && document.activeElement === active);
})()
""", token=token))


def fill(driver, tab_id: str | int, selector_or_ref: str, value: str, ref_map: RefMap, *, token: str | None = None, frame_target: str = "") -> dict[str, Any]:
    def eval_page(script: str, *, missing_value: str = "null") -> Any:
        if frame_target:
            return cdp.evaluate_in_frame(driver, tab_id, frame_target, script, token=token)
        return cdp.evaluate(driver, tab_id, frame_context.scoped_script(script, frame_target, missing_value=missing_value), token=token)

    entry = ref_map.get(tab_id, selector_or_ref)
    if entry and entry.role == "richtext" and entry.selector:
        ok = eval_page(fill_richtext_script(entry.selector, value))
        if ok is True:
            return {"filled": selector_or_ref, "value": value}
    if parse_ref(selector_or_ref) is None and _looks_like_richtext_selector(selector_or_ref):
        ok = eval_page(fill_richtext_script(selector_or_ref))
        if ok is True:
            return {"filled": selector_or_ref, "value": value}
    if entry and entry.backend_node_id is not None and not frame_target and entry.role in {"textbox", "searchbox"}:
        focused = call_backend_node(
            driver,
            tab_id,
            entry.backend_node_id,
            focus_backend_editable_function(),
            token=token,
        )
        if not isinstance(focused, dict) or focused.get("ok") is not True:
            raise InteractionError(f"Element could not be focused: {selector_or_ref}")
        cdp.send_cdp(driver, tab_id, "Input.insertText", {"text": value}, token=token)
        reconciled = call_backend_node(
            driver,
            tab_id,
            entry.backend_node_id,
            reconcile_backend_value_function(),
            arguments=[value],
            token=token,
        )
        if not isinstance(reconciled, dict) or reconciled.get("ok") is not True or reconciled.get("value") != value:
            raise InteractionError(f"Element value was not updated: {selector_or_ref}")
        return {"filled": selector_or_ref, "value": value}
    if entry and not entry.selector and entry.role in {"textbox", "searchbox", "richtext"}:
        focused = eval_page(named_element_script(entry.role, entry.name.strip(), entry.nth, 1), missing_value="null")
        if not focused:
            raise InteractionError(f"Element could not be focused: {selector_or_ref}")
    elif frame_target:
        target = entry.selector if entry and entry.selector else (selector_or_ref if parse_ref(selector_or_ref) is None else None)
        if target and not eval_page(focus_target_script(target), missing_value="false"):
            raise InteractionError(f"Element could not be focused: {selector_or_ref}")
    else:
        click(driver, tab_id, selector_or_ref, ref_map, token=token, frame_target=frame_target)
    entry = ref_map.get(tab_id, selector_or_ref)
    target_selector = entry.selector if entry and entry.selector else None
    editable = eval_page(editable_element_script(target_selector), missing_value="false")
    if editable is not True:
        raise InteractionError(f"Element is not editable: {selector_or_ref}")
    focused = eval_page(select_active_editable_script(target_selector), missing_value="false")
    if focused is not True:
        raise InteractionError(f"Element could not be focused: {selector_or_ref}")
    cdp.send_cdp(driver, tab_id, "Input.insertText", {"text": value}, token=token)
    reconciliation_selector = target_selector or selector_or_ref
    if target_selector or (parse_ref(selector_or_ref) is None and not selector_or_ref.startswith(("text=", "xpath="))):
        eval_page(form_value_reconciliation_script(reconciliation_selector, value))
    return {"filled": selector_or_ref, "value": value}


def call_backend_node(
    driver,
    tab_id: str | int,
    backend_node_id: int,
    function_declaration: str,
    *,
    arguments: list[Any] | None = None,
    token: str | None = None,
) -> Any:
    resolved = cdp.send_cdp(
        driver,
        tab_id,
        "DOM.resolveNode",
        {"backendNodeId": backend_node_id},
        token=token,
    )
    object_id = resolved.get("object", {}).get("objectId")
    if not object_id:
        raise InteractionError(f"Unable to resolve backend node {backend_node_id}")
    try:
        result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.callFunctionOn",
            {
                "objectId": object_id,
                "functionDeclaration": function_declaration,
                "arguments": [{"value": argument} for argument in (arguments or [])],
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
            token=token,
        )
        return result.get("result", {}).get("value")
    finally:
        try:
            cdp.send_cdp(driver, tab_id, "Runtime.releaseObject", {"objectId": object_id}, token=token)
        except Exception:
            pass


def focus_backend_editable_function() -> str:
    return """
function() {
  const el = this;
  const tag = (el.tagName || '').toLowerCase();
  const inputType = String(el.type || '').toLowerCase();
  const blockedInputTypes = new Set(['button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit']);
  const editable = tag === 'textarea' || el.isContentEditable === true || el.getAttribute('role') === 'textbox' ||
    (tag === 'input' && !blockedInputTypes.has(inputType));
  if (!editable || el.disabled || el.readOnly) return { ok: false };
  el.scrollIntoView({ block: 'center', inline: 'center' });
  el.focus();
  if (document.activeElement !== el) return { ok: false };
  if (typeof el.select === 'function') el.select();
  else if (typeof el.setSelectionRange === 'function') el.setSelectionRange(0, String(el.value || '').length);
  return { ok: true, value: 'value' in el ? String(el.value || '') : String(el.textContent || '') };
}
"""


def reconcile_backend_value_function() -> str:
    return """
function(value) {
  const el = this;
  if (!el || !('value' in el)) return { ok: false };
  const prototype = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  if (setter) setter.call(el, value);
  else el.value = value;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: el.value === value && document.activeElement === el, value: String(el.value || '') };
}
"""


def select_active_editable_script(selector: str | None = None) -> str:
    target = f"document.querySelector({json.dumps(selector)})" if selector else "document.activeElement"
    return f"""
(() => {{
  const el = {target};
  if (!el) return false;
  if (el.focus) el.focus();
  if (typeof el.select === 'function') el.select();
  else if (typeof el.setSelectionRange === 'function') el.setSelectionRange(0, String(el.value || '').length);
  return document.activeElement === el;
}})()
"""


def form_value_reconciliation_script(selector: str, value: str) -> str:
    """Ensure controlled inputs observe the same replacement value as the browser surface."""
    return f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el || !('value' in el)) return false;
  const prototype = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  if (setter) setter.call(el, {json.dumps(value)});
  else el.value = {json.dumps(value)};
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return el.value === {json.dumps(value)};
}})()
"""


def _looks_like_richtext_selector(selector: str) -> bool:
    needle = selector.lower()
    return any(token in needle for token in (
        "contenteditable",
        "prosemirror",
        "ql-editor",
        "drafteditor",
        "slate-editor",
        '[role="textbox"]',
        'role=textbox',
    ))


def type_text(driver, tab_id: str | int, selector_or_ref: str, text: str, ref_map: RefMap, *, token: str | None = None, frame_target: str = "") -> dict[str, Any]:
    click(driver, tab_id, selector_or_ref, ref_map, token=token, frame_target=frame_target)
    bring_to_front(driver, tab_id, token=token)
    entry = ref_map.get(tab_id, selector_or_ref)
    target_selector = entry.selector if entry and entry.selector else (
        selector_or_ref if not parse_ref(selector_or_ref) and not selector_or_ref.startswith(("text=", "xpath=")) else None
    )
    if target_selector:
        focused = cdp.evaluate(
            driver,
            tab_id,
            frame_context.scoped_script(focus_target_script(target_selector), frame_target),
            token=token,
        )
        if focused is not True:
            raise InteractionError(f"Element could not be focused: {selector_or_ref}")
    else:
        cdp.evaluate(
            driver,
            tab_id,
            frame_context.scoped_script(focus_active_element_script(), frame_target),
            token=token,
        )
    before_value = cdp.evaluate(
        driver,
        tab_id,
        frame_context.scoped_script(active_editable_value_script(), frame_target),
        token=token,
    )
    dispatch_text_keys(driver, tab_id, text, token=token, ensure_front=False)
    after_value = cdp.evaluate(
        driver,
        tab_id,
        frame_context.scoped_script(active_editable_value_script(), frame_target),
        token=token,
    )
    if isinstance(before_value, str) and isinstance(after_value, str) and not after_value.endswith(text):
        cdp.send_cdp(driver, tab_id, "Input.insertText", {"text": text}, token=token)
    return {"typed": selector_or_ref, "text": text}


def keyboard_insert_text(driver, tab_id: str | int, text: str, *, token: str | None = None) -> dict[str, Any]:
    # Preserve the focused editable while Page.bringToFront changes browser focus.
    cdp.evaluate(driver, tab_id, """
(() => {
  const active = document.activeElement;
  if (active && active !== document.body && active !== document.documentElement) {
    window.__omnibotKeyboardFocus = active;
    return true;
  }
  return false;
})()
""", token=token)
    bring_to_front(driver, tab_id, token=token)
    cdp.evaluate(driver, tab_id, """
(() => {
  const active = window.__omnibotKeyboardFocus;
  try {
    if (active && active.focus) active.focus();
  } finally {
    try { delete window.__omnibotKeyboardFocus; } catch (_) {}
  }
  return Boolean(active && document.activeElement === active);
})()
""", token=token)
    cdp.send_cdp(driver, tab_id, "Input.insertText", {"text": text}, token=token)
    return {"inserted": text}


def keyboard_type(driver, tab_id: str | int, text: str, *, modifiers: int = 0, token: str | None = None) -> dict[str, Any]:
    """Type text as keyboard events while preserving the active element."""
    cdp.evaluate(driver, tab_id, """
(() => {
  const active = document.activeElement;
  if (active && active !== document.body && active !== document.documentElement) {
    window.__omnibotKeyboardFocus = active;
    return true;
  }
  return false;
})()
""", token=token)
    bring_to_front(driver, tab_id, token=token)
    cdp.evaluate(driver, tab_id, """
(() => {
  const active = window.__omnibotKeyboardFocus;
  try {
    if (active && active.focus) active.focus();
  } catch (_) {}
  return Boolean(active && document.activeElement === active);
})()
""", token=token)
    before_value = cdp.evaluate(driver, tab_id, active_editable_value_script(), token=token)
    transformed_text = text.upper() if modifiers & 8 else text
    if modifiers:
        if modifiers & 8 and isinstance(before_value, str):
            cdp.evaluate(driver, tab_id, f"""
(() => {{
  const el = document.activeElement;
  if (!el) return false;
  const text = {json.dumps(transformed_text)};
  el.dispatchEvent(new KeyboardEvent('keydown', {{ key: text, code: 'Key' + text.toUpperCase(), shiftKey: true, bubbles: true, cancelable: true }}));
  const expected = {json.dumps(before_value + transformed_text)};
  if ('value' in el) {{
    const prototype = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
    if (setter) setter.call(el, expected); else el.value = expected;
  }} else if (el.isContentEditable) {{
    el.textContent = expected;
  }}
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new KeyboardEvent('keyup', {{ key: text, code: 'Key' + text.toUpperCase(), shiftKey: true, bubbles: true }}));
  return true;
}})()
""", token=token)
        return {"typed": text}
    dispatch_text_keys(driver, tab_id, text, modifiers=modifiers, emit_text=not modifiers, token=token, ensure_front=False)
    if modifiers & 8:
        cdp.evaluate(driver, tab_id, f"""
(() => {{
  const el = document.activeElement;
  if (!el || typeof el.setSelectionRange !== 'function') return false;
  const value = String(el.value || '');
  const length = {len(text)};
  el.setSelectionRange(Math.max(0, value.length - length), value.length);
  return true;
}})()
        """, token=token)
        cdp.send_cdp(driver, tab_id, "Input.insertText", {"text": transformed_text}, token=token)
        if isinstance(before_value, str):
            for _ in range(20):
                current_value = cdp.evaluate(driver, tab_id, active_editable_value_script(), token=token)
                if isinstance(current_value, str) and current_value != before_value:
                    break
                time.sleep(0.05)
            time.sleep(2.0)
            expected_value = before_value + transformed_text
            cdp.evaluate(driver, tab_id, f"""
(() => {{
  const el = document.activeElement;
  if (!el || !('value' in el)) return false;
  const prototype = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
  if (setter) setter.call(el, {json.dumps(expected_value)});
  else el.value = {json.dumps(expected_value)};
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return el.value === {json.dumps(expected_value)};
}})()
""", token=token)
    after_value = cdp.evaluate(driver, tab_id, active_editable_value_script(), token=token)
    if isinstance(before_value, str) and isinstance(after_value, str) and not after_value.endswith(text):
        cdp.send_cdp(driver, tab_id, "Input.insertText", {"text": text}, token=token)
        cdp.evaluate(driver, tab_id, """
(() => {
  const active = window.__omnibotKeyboardFocus;
  if (active && active.focus) active.focus();
  return Boolean(active);
})()
""", token=token)
        current_value = cdp.evaluate(driver, tab_id, active_editable_value_script(), token=token)
        if isinstance(current_value, str) and not current_value.endswith(text):
            cdp.evaluate(driver, tab_id, f"""
(() => {{
  const el = window.__omnibotKeyboardFocus || document.activeElement;
  if (!el) return false;
  if (el.focus) el.focus();
  const expected = {json.dumps(before_value + text)};
  if ('value' in el) {{
    const prototype = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
    if (setter) setter.call(el, expected); else el.value = expected;
  }} else if (el.isContentEditable) {{
    el.textContent = expected;
  }} else return false;
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  return true;
}})()
""", token=token)
    cdp.evaluate(driver, tab_id, "try { delete window.__omnibotKeyboardFocus; } catch (_) {}", token=token)
    return {"typed": text}


def focus_script(selector: str) -> str:
    return f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return false;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  el.focus();
  return true;
}})()
"""


def focus_active_element_script() -> str:
    return """
(() => {
  const el = document.activeElement;
  if (el && el.focus) el.focus();
  return true;
})()
"""


def focus_target_script(selector: str) -> str:
    return f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el || !el.focus) return false;
  el.focus();
  return document.activeElement === el;
}})()
"""


def active_editable_value_script() -> str:
    return """
(() => {
  const el = document.activeElement;
  if (!el) return null;
  if ('value' in el) return String(el.value || '');
  if (el.isContentEditable) return String(el.textContent || '');
  return null;
})()
"""


def editable_element_script(selector: str | None = None) -> str:
    target = f"document.querySelector({json.dumps(selector)})" if selector else "document.activeElement"
    return f"""
(() => {{
  const el = {target};
  if (!el) return false;
  const tag = (el.tagName || '').toLowerCase();
  return tag === 'input' || tag === 'textarea' || el.isContentEditable === true || el.getAttribute('role') === 'textbox';
}})()
"""


def fill_richtext_script(selector: str, value: str) -> str:
    return f"""
(() => {{
  const selector = {json.dumps(selector, ensure_ascii=False)};
  const value = {json.dumps(value, ensure_ascii=False)};
  const el = document.querySelector(selector);
  if (!el) return false;
  const isRichtext = el.isContentEditable || el.getAttribute('contenteditable') === 'true' ||
    (el.getAttribute('role') === 'textbox' && el.getAttribute('aria-multiline') === 'true');
  if (!isRichtext) return false;
  el.scrollIntoView({{ block: 'center', inline: 'center' }});
  el.focus();
  const escapeHtml = (text) => text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
  const paragraphs = String(value).split(/\\n\\s*\\n/).map((part) => part.trim()).filter(Boolean);
  if (paragraphs.length) {{
    el.innerHTML = paragraphs.map((part) => `<p>${{escapeHtml(part).replace(/\\n/g, '<br>')}}</p>`).join('');
  }} else {{
    el.innerHTML = '';
  }}
  el.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertText', data: value }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return true;
}})()
"""


def hover(driver, tab_id: str | int, selector_or_ref: str, ref_map: RefMap, *, token: str | None = None, frame_target: str = "") -> dict[str, Any]:
    x, y = resolve_center(driver, tab_id, selector_or_ref, ref_map, token=token, frame_target=frame_target)
    cua.broadcast_mouse_visual(driver, tab_id, "move", x=x, y=y, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y}, token=token)
    return {"hovered": selector_or_ref, "x": x, "y": y}


def focus(driver, tab_id: str | int, selector: str, *, token: str | None = None) -> dict[str, Any]:
    ok = cdp.evaluate(driver, tab_id, focus_script(selector), token=token)
    if ok is not True:
        raise InteractionError(f"Element not found: {selector}")
    return {"focused": selector}


def select_option(driver, tab_id: str | int, selector_or_ref: str, value: str, ref_map: RefMap | None = None, *, token: str | None = None) -> dict[str, Any]:
    entry = ref_map.get(tab_id, selector_or_ref) if ref_map else None
    selector = entry.selector if entry and entry.selector else (selector_or_ref if parse_ref(selector_or_ref) is None else None)
    if selector is None:
        if not entry or entry.role != "combobox":
            raise InteractionError(f"Select element could not be resolved: {selector_or_ref}")
        script = f"""
(() => {{
  const name = {json.dumps(entry.name.strip())};
  const nth = {int(entry.nth or 0)};
  const label = (el) => (el.getAttribute('aria-label') || el.closest('label')?.innerText || el.innerText || el.textContent || '').trim();
  const matches = Array.from(document.querySelectorAll('select,[role="combobox"]')).filter((el) => label(el) === name);
  const el = matches[nth] || matches[0];
  if (!el || !el.options) return {{ok: false, reason: 'element_not_found'}};
  if (!Array.from(el.options).some((option) => option.value === {json.dumps(value)})) return {{ok: false, reason: 'option_not_found'}};
  el.value = {json.dumps(value)};
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ok: el.value === {json.dumps(value)}}};
}})()
"""
        result = cdp.evaluate(driver, tab_id, script, token=token)
        if isinstance(result, dict) and result.get("ok") is True:
            return {"selected": selector_or_ref, "value": value}
        raise InteractionError(f"Select element not found: {selector_or_ref}")
    script = f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ok: false, reason: 'element_not_found'}};
  if (!el.options) return {{ok: false, reason: 'not_select'}};
  if (!Array.from(el.options).some((option) => option.value === {json.dumps(value)})) return {{ok: false, reason: 'option_not_found'}};
  el.value = {json.dumps(value)};
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ok: el.value === {json.dumps(value)}, value: el.value}};
}})()
"""
    result = cdp.evaluate(driver, tab_id, script, token=token)
    if not isinstance(result, dict) or result.get("ok") is not True:
        reason = result.get("reason") if isinstance(result, dict) else "element_not_found"
        if reason == "option_not_found":
            raise InteractionError(f"Select option not found: {value}")
        if reason == "not_select":
            raise InteractionError(f"Element is not a select: {selector_or_ref}")
        raise InteractionError(f"Select element not found: {selector_or_ref}")
    return {"selected": selector_or_ref, "value": value}


def set_checked(driver, tab_id: str | int, selector_or_ref: str, ref_map: RefMap, checked: bool, *, token: str | None = None) -> dict[str, Any]:
    entry = ref_map.get(tab_id, selector_or_ref)
    selector = entry.selector if entry and entry.selector else (selector_or_ref if parse_ref(selector_or_ref) is None else None)
    if selector is None:
        if not entry or entry.role != "checkbox":
            raise InteractionError(f"Checkbox target could not be resolved: {selector_or_ref}")
        script = f"""
(() => {{
  const name = {json.dumps(entry.name.strip())};
  const nth = {int(entry.nth or 0)};
  const label = (el) => (el.closest('label')?.innerText || el.getAttribute('aria-label') || '').trim();
  const matches = Array.from(document.querySelectorAll('input[type="checkbox"],input[type="radio"],[role="checkbox"],[role="switch"],[role="radio"]')).filter((el) => label(el) === name);
  const el = matches[nth] || matches[0];
  if (!el) return {{ok: false}};
  if (Boolean(el.checked) !== {str(checked).lower()}) el.click();
  return {{ok: Boolean(el.checked) === {str(checked).lower()}}};
}})()
"""
        result = cdp.evaluate(driver, tab_id, script, token=token)
        if isinstance(result, dict) and result.get("ok") is True:
            return {"checked": checked, "selector": selector_or_ref}
        raise InteractionError(f"Checkbox element not found: {selector_or_ref}")
    state = cdp.evaluate(driver, tab_id, f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ok: false, reason: 'element_not_found'}};
  const type = (el.getAttribute('type') || '').toLowerCase();
  const role = (el.getAttribute('role') || '').toLowerCase();
  if (!((el.tagName || '').toLowerCase() === 'input' && (type === 'checkbox' || type === 'radio')) && !(['checkbox', 'switch', 'radio'].includes(role))) return {{ok: false, reason: 'not_checkable'}};
  return {{ok: true, checked: Boolean(el.checked)}};
}})()
""", token=token)
    if not isinstance(state, dict) or state.get("ok") is not True:
        reason = state.get("reason") if isinstance(state, dict) else "element_not_found"
        if reason == "not_checkable":
            raise InteractionError(f"Element is not checkable: {selector_or_ref}")
        raise InteractionError(f"Checkbox element not found: {selector_or_ref}")
    if bool(state.get("checked")) != checked:
        click(driver, tab_id, selector_or_ref, ref_map, token=token)
    return {"checked": checked, "selector": selector_or_ref}


def scroll(driver, tab_id: str | int, direction: str, pixels: int, selector: str | None = None, *, token: str | None = None) -> dict[str, Any]:
    dx = pixels if direction == "right" else -pixels if direction == "left" else 0
    dy = pixels if direction == "down" else -pixels if direction == "up" else 0
    target = "window" if not selector else f"document.querySelector({json.dumps(selector)})"
    script = f"""
(() => {{
  const target = {target};
  if (!target) return false;
  target.scrollBy({{ left: {dx}, top: {dy}, behavior: 'instant' }});
  return true;
}})()
"""
    ok = cdp.evaluate(driver, tab_id, script, token=token)
    if ok is not True:
        raise InteractionError("Scroll target not found")
    return {"direction": direction, "pixels": pixels, "selector": selector}


def scroll_into_view(driver, tab_id: str | int, selector: str, *, token: str | None = None) -> dict[str, Any]:
    ok = cdp.evaluate(driver, tab_id, f"(() => {{ const el = document.querySelector({json.dumps(selector)}); if (!el) return false; el.scrollIntoView({{block:'center', inline:'center'}}); return true; }})()", token=token)
    if ok is not True:
        raise InteractionError(f"Element not found: {selector}")
    return {"scrolledIntoView": selector}


def html5_drag_script(source: str, target: str) -> str:
    return f"""
(() => {{
  const source = document.querySelector({json.dumps(source)});
  const target = document.querySelector({json.dumps(target)});
  if (!source || !target || typeof DataTransfer === 'undefined' || typeof DragEvent === 'undefined') return false;
  const transfer = new DataTransfer();
  const options = {{ bubbles: true, cancelable: true, dataTransfer: transfer }};
  source.dispatchEvent(new DragEvent('dragstart', options));
  target.dispatchEvent(new DragEvent('dragenter', options));
  target.dispatchEvent(new DragEvent('dragover', options));
  target.dispatchEvent(new DragEvent('drop', options));
  source.dispatchEvent(new DragEvent('dragend', options));
  return true;
}})()
"""


def html5_drag_at_points_script(from_x: float, from_y: float, to_x: float, to_y: float) -> str:
    """Dispatch an HTML5 drag sequence using coordinates resolved from selectors or refs."""
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


def drag(driver, tab_id: str | int, source: str, target: str, ref_map: RefMap, *, token: str | None = None) -> dict[str, Any]:
    sx, sy = resolve_center(driver, tab_id, source, ref_map, token=token)
    tx, ty = resolve_center(driver, tab_id, target, ref_map, token=token)
    cua.broadcast_mouse_visual(driver, tab_id, "move", x=sx, y=sy, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": sx, "y": sy}, token=token)
    cua.broadcast_mouse_visual(driver, tab_id, "press", x=sx, y=sy, button="left", clickCount=1, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": sx, "y": sy, "button": "left", "buttons": 1, "clickCount": 1}, token=token)
    cua.broadcast_mouse_visual(driver, tab_id, "drag", x=tx, y=ty, buttons=1, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": tx, "y": ty, "buttons": 1}, token=token)
    cua.broadcast_mouse_visual(driver, tab_id, "release", x=tx, y=ty, button="left", clickCount=1, token=token)
    cdp.send_cdp(driver, tab_id, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": tx, "y": ty, "button": "left", "buttons": 0, "clickCount": 1}, token=token)
    cdp.send_cdp(
        driver,
        tab_id,
        "Runtime.evaluate",
        {"expression": html5_drag_at_points_script(sx, sy, tx, ty), "awaitPromise": True, "returnByValue": True},
        token=token,
    )
    return {"dragged": source, "target": target, "from": {"x": sx, "y": sy}, "to": {"x": tx, "y": ty}}
