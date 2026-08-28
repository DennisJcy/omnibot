from __future__ import annotations

import json
from typing import Any

from .TMWebDriver import TMWebDriver


class CdpError(RuntimeError):
    pass


def normalize_tab_id(tab_id: str | int) -> int:
    raw = str(tab_id)
    if ":" in raw:
        raw = raw.rsplit(":", 1)[1]
    try:
        return int(raw)
    except ValueError as exc:
        raise CdpError(f"CDP requires a numeric Chrome tab id, got {tab_id!r}") from exc


def send_cdp(
    driver: TMWebDriver,
    tab_id: str | int,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    token: str | None = None,
    timeout: float = 15,
    group_status: str | None = None,
    watch_new_tabs: bool = False,
) -> dict[str, Any]:
    raw_tab_id = normalize_tab_id(driver._raw_tab_id(tab_id, token=token))
    payload: dict[str, Any] = {"cmd": "cdp", "tabId": raw_tab_id, "method": method, "params": params or {}}
    if watch_new_tabs:
        payload["watchNewTabs"] = True
    response = driver.execute_js(
        payload,
        timeout=timeout,
        token=token,
        group_status=group_status,
        status_tab_id=raw_tab_id,
    )
    data = response.get("data") if isinstance(response, dict) else response
    new_tabs = response.get("newTabs") if isinstance(response, dict) else None
    if isinstance(data, dict) and data.get("ok") is False:
        raise CdpError(str(data.get("error") or f"CDP command failed: {method}"))
    if isinstance(data, dict) and data.get("ok") is True:
        inner = data.get("data", {})
        result = dict(inner) if isinstance(inner, dict) else {"value": inner}
        if new_tabs:
            result["_omnibot_newTabs"] = new_tabs
        return result
    if isinstance(data, dict):
        result = dict(data)
        if new_tabs:
            result["_omnibot_newTabs"] = new_tabs
        return result
    result = {"value": data}
    if new_tabs:
        result["_omnibot_newTabs"] = new_tabs
    return result


def evaluate(
    driver: TMWebDriver,
    tab_id: str | int,
    expression: str,
    *,
    token: str | None = None,
    await_promise: bool = True,
    return_by_value: bool = True,
    timeout: float = 15,
) -> Any:
    result = send_cdp(
        driver,
        tab_id,
        "Runtime.evaluate",
        {
            "expression": expression,
            "awaitPromise": await_promise,
            "returnByValue": return_by_value,
        },
        token=token,
        timeout=timeout,
    )
    runtime_result = result.get("result", {})
    if "value" in runtime_result:
        return runtime_result["value"]
    if "description" in runtime_result:
        return runtime_result["description"]
    return runtime_result


def evaluate_in_frame(
    driver: TMWebDriver,
    tab_id: str | int,
    frame_target: str,
    expression: str,
    *,
    token: str | None = None,
    timeout: float = 15,
) -> Any:
    """Evaluate in the selected iframe execution context, including cross-origin frames."""
    from . import frame_context

    descriptor = evaluate(
        driver,
        tab_id,
        f"""(() => {{
          const target = {json.dumps(str(frame_target))};
          const frames = Array.from(document.querySelectorAll('iframe,frame'));
          let frame = null;
          try {{ frame = document.querySelector(target); }} catch (_) {{}}
          if (!frame || !frames.includes(frame)) frame = frames.find((item) =>
            [item.id, item.name, item.title, item.getAttribute('src'), item.src]
              .filter(Boolean).some((value) => String(value) === target || String(value).includes(target))
          );
          return frame ? {{id: frame.id, name: frame.name, title: frame.title, src: frame.getAttribute('src'), url: frame.src}} : null;
        }})()""",
        token=token,
        timeout=timeout,
    )
    if not isinstance(descriptor, dict):
        descriptor = {"url": str(frame_target), "name": str(frame_target), "id": str(frame_target)}
    frame_tree = send_cdp(driver, tab_id, "Page.getFrameTree", {}, token=token, timeout=timeout)
    frame_id = frame_context.select_frame_id(frame_tree, descriptor)
    if not frame_id:
        raise CdpError(f"Selected frame was not found: {frame_target}")
    world = send_cdp(
        driver,
        tab_id,
        "Page.createIsolatedWorld",
        {"frameId": frame_id, "worldName": "omnibot-frame"},
        token=token,
        timeout=timeout,
    )
    context_id = world.get("executionContextId")
    if context_id is None:
        raise CdpError(f"Unable to create execution context for frame: {frame_target}")
    result = send_cdp(
        driver,
        tab_id,
        "Runtime.evaluate",
        {"expression": expression, "contextId": context_id, "awaitPromise": True, "returnByValue": True},
        token=token,
        timeout=timeout,
    )
    runtime_result = result.get("result", {})
    if "value" in runtime_result:
        return runtime_result["value"]
    if "description" in runtime_result:
        return runtime_result["description"]
    return runtime_result
