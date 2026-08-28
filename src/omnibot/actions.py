import importlib
import sys
import json
import base64
import mimetypes
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from . import simphtml
from .TMWebDriver import TMWebDriver


STATUS_MAP = {
    "read": {"in_progress": "读取中", "done": "已读取"},
    "navigate": {"in_progress": "导航中", "done": "已导航"},
    "wait": {"in_progress": "等待中", "done": "等待完成"},
    "screenshot": {"in_progress": "截图中", "done": "已截图"},
    "batch": {"in_progress": "批量操作中", "done": "已操作"},
    "scroll_down": {"in_progress": "下滑中", "done": "已下滑"},
    "scroll_up": {"in_progress": "上滑中", "done": "已上滑"},
    "click": {"in_progress": "点击中", "done": "已点击"},
    "mouse_move": {"in_progress": "移动中", "done": "已移动"},
    "mouse_drag": {"in_progress": "拖动中", "done": "已拖动"},
    "js_execute": {"in_progress": "执行中", "done": "已执行"},
    "new_tab": {"in_progress": "创建中", "done": "已创建"},
}

TOOL_CREATED_TAB_CLEANUP_TIMEOUT_SECONDS = 60
USER_TAB_UNGROUP_TIMEOUT_SECONDS = 8


def ensure_sessions(driver: TMWebDriver, token: str | None = None) -> list[dict[str, Any]]:
    sessions = driver.get_all_sessions(token=token)
    if len(sessions) == 0:
        raise RuntimeError("No browser tabs connected.")
    return sessions


def normalize_tab_id(tab_id: str | int | None) -> int | None:
    if tab_id is None or tab_id == "":
        return None
    return int(tab_id)


def mark_explicit_target(driver: TMWebDriver, tab_id: str, token: str | None = None) -> None:
    ctx = driver.get_context(token)
    if not hasattr(ctx, "explicit_target_tabs"):
        ctx.explicit_target_tabs = set()
    ctx.explicit_target_tabs.add(tab_id)


def resolve_session_id(driver: TMWebDriver, tab_id: str | int | None, token: str | None = None) -> str | None:
    if tab_id is None or tab_id == "":
        return None
    requested = str(tab_id)
    try:
        sessions = driver.get_all_sessions(token=token)
    except Exception:
        sessions = []
    for session in sessions:
        if str(session.get("id")) == requested:
            return str(session.get("id"))
    matches = [str(session.get("id")) for session in sessions if str(session.get("tab_id", "")) == requested]
    if len(matches) == 1:
        return matches[0]
    return None


def require_tab_id(driver: TMWebDriver, tab_id: str | int | None, token: str | None = None) -> tuple[str | None, dict[str, Any] | None]:
    if tab_id is None or str(tab_id).strip() == "":
        return None, {"status": "error", "msg": "tab_id is required. Pass --tab-id <TAB_ID>."}
    if len(driver.get_all_sessions(token=token)) == 0:
        return None, {"status": "error", "msg": "No browser tabs connected."}
    resolved = resolve_session_id(driver, tab_id, token=token)
    if not resolved:
        return None, {"status": "error", "msg": f"Tab {tab_id} not found or ambiguous."}
    return resolved, None


def update_group_status(driver: TMWebDriver, tab_id: str | None, status: str | None, phase: str, token: str | None = None) -> None:
    if tab_id is None or status is None:
        return
    name = STATUS_MAP.get(status, {}).get(phase)
    if name is None:
        return
    try:
        driver.update_tab_group(tab_id, name, token=token)
    except Exception:
        pass


def broadcast_group_status(driver: TMWebDriver, tab_id: str | None, status: str | None, phase: str, token: str | None = None) -> None:
    if tab_id is None or status is None:
        return
    name = STATUS_MAP.get(status, {}).get(phase)
    if name is None:
        return
    broadcaster = getattr(driver, "broadcast_extension_event", None)
    if not callable(broadcaster):
        update_group_status(driver, tab_id, status, phase, token=token)
        return
    try:
        raw_tab_id = driver._raw_tab_id(tab_id, token=token)
        broadcaster({"groupStatus": name, "tabId": int(raw_tab_id), "statusTabId": int(raw_tab_id)}, token=token)
    except Exception:
        update_group_status(driver, tab_id, status, phase, token=token)


def schedule_new_tabs_from_result(
    driver: TMWebDriver,
    ctx: Any,
    result: dict[str, Any],
    source_tab_id: str | None = None,
    token: str | None = None,
) -> None:
    new_tabs = result.get("newTabs", []) if isinstance(result, dict) else []
    if not new_tabs:
        return
    raw_source_tab_id = str(driver._raw_tab_id(source_tab_id, token=token)) if source_tab_id else ""
    for new_tab in new_tabs:
        raw_new_tab_id = str(new_tab.get("id", "")) if isinstance(new_tab, dict) else ""
        if not raw_new_tab_id:
            continue
        # A tab appearing during an operation is not proof that the operation
        # created it: the user may open an unrelated tab concurrently. Prefer
        # Chrome's openerTabId. For rel=noopener sites, a current extension can
        # instead certify that the tab inherited the source's operation-scoped
        # Omnibot status group.
        opener_tab_id = str(new_tab.get("openerTabId", "")) if isinstance(new_tab, dict) else ""
        ownership_reason = str(new_tab.get("ownershipReason", "")) if isinstance(new_tab, dict) else ""
        extension_confirmed = ownership_reason == "status-group"
        if not raw_source_tab_id or (opener_tab_id != raw_source_tab_id and not extension_confirmed):
            continue
        browser_client_id = new_tab.get("browserClientId") if isinstance(new_tab, dict) else None
        new_session_id = f"{browser_client_id}:{raw_new_tab_id}" if browser_client_id else raw_new_tab_id
        ctx.tool_created_tabs.add(new_session_id)
        session = ctx.sessions.get(new_session_id)
        if session:
            session.created_by_tool = True
        driver._schedule_tab_close(new_session_id, token=token)


def infer_or_default_js_status(script: str) -> str:
    return TMWebDriver._infer_js_action(script)


def get_tabs(driver: TMWebDriver, token: str | None = None) -> dict[str, Any]:
    sessions = driver.get_all_sessions(token=token)
    tabs = []
    for session in sessions:
        item = dict(session)
        item.pop("connected_at", None)
        item.pop("type", None)
        tabs.append(item)
    return {"tabs": tabs}


def read(driver: TMWebDriver, url: str = "", screens: int = 5, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import frame_context, reader

    ctx = driver.get_context(token)
    if len(driver.get_all_sessions(token=token)) == 0:
        return {"status": "error", "msg": "No browser tabs connected."}

    created_tab = False
    if switch_tab_id:
        tab_id, error = require_tab_id(driver, switch_tab_id, token=token)
        if error:
            return error
        driver._cancel_tab_close(tab_id, token=token)
    elif url:
        created = driver.new_tab(url, timeout=15, token=token)
        if not created or not created.get("id"):
            return {"status": "error", "msg": f"Failed to create tab for {url}"}
        tab_id = str(created.get("id"))
        created_tab = True
        driver._cancel_tab_close(tab_id, token=token)
    else:
        tab_id, error = require_tab_id(driver, switch_tab_id, token=token)
        if error:
            return error

    target_status_tab_id = driver._raw_tab_id(tab_id, token=token)
    try:
        update_group_status(driver, tab_id, "read", "in_progress", token=token)
        active_frame = _active_frame_target(ctx, tab_id)
        script = (
            frame_context.scoped_script(
                reader.frame_read_extraction_script(),
                active_frame,
                missing_value=frame_context.frame_error_value("not_found"),
                inaccessible_value=frame_context.frame_error_value("cross_origin_or_inaccessible"),
            )
            if active_frame
            else reader.read_extraction_script(screens=screens)
        )
        raw = driver.execute_js(script, timeout=max(30, 15 + max(int(screens or 0), 0) * 2), token=token, group_status=None, session_id=tab_id, status_tab_id=target_status_tab_id)
        extracted = raw.get("data", raw) if isinstance(raw, dict) else {}
        frame_error = _selected_frame_error(extracted)
        if frame_error is not None:
            return frame_error
        if not isinstance(extracted, dict):
            extracted = {"title": "Untitled", "url": url, "blocks": [{"type": "paragraph", "text": str(extracted)}]}
        formatted = reader.format_read_document(extracted)
        return {
            "status": "success",
            "title": extracted.get("title") or "Untitled",
            "url": extracted.get("url") or url,
            "content": formatted["content"],
            "links": formatted["links"],
            "metadata": {"tab_id": tab_id, "screens": max(int(screens or 0), 0), "created_tab": created_tab, "debug": extracted.get("debug", {})},
        }
    finally:
        update_group_status(driver, tab_id, "read", "done", token=token)
        _schedule_tab_cleanup_after_operation(driver, ctx, tab_id, token=token)


def execute_js(driver: TMWebDriver, script: str, switch_tab_id: str = "", no_monitor: bool = False, token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    if len(driver.get_all_sessions(token=token)) == 0:
        return {"status": "error", "msg": "No browser tabs connected."}
    tab_id, error = require_tab_id(driver, switch_tab_id, token=token)
    if error:
        return error
    status = infer_or_default_js_status(script)
    driver._cancel_tab_close(tab_id, token=token)
    target_status_tab_id = driver._raw_tab_id(tab_id, token=token)

    try:
        result = simphtml.execute_js_rich(
            script,
            driver,
            no_monitor=no_monitor,
            token=token,
            group_status=STATUS_MAP[status]["in_progress"],
            session_id=tab_id,
            status_tab_id=target_status_tab_id,
        )
        schedule_new_tabs_from_result(driver, ctx, result, source_tab_id=tab_id, token=token)
    finally:
        update_group_status(driver, tab_id, status, "done", token=token)
        _schedule_tab_cleanup_after_operation(driver, ctx, tab_id, token=token)
    return result


def extension_command(driver: TMWebDriver, cmd: dict[str, Any], tab_id: str | int | None = None, timeout: float = 15, token: str | None = None, group_status: str | None = None) -> Any:
    resolved_session_id = resolve_session_id(driver, tab_id, token=token)
    raw_tab_id: str | None = None
    target_session = None
    target_info: dict[str, Any] | None = None
    if resolved_session_id is not None:
        ctx = driver.get_context(token)
        target_session = ctx.sessions.get(resolved_session_id)
        if not target_session:
            for session in driver.get_all_sessions(token=token):
                if str(session.get("id")) == resolved_session_id:
                    target_info = session
                    break
        raw_tab_id = target_session.tab_id if target_session else None
        if raw_tab_id is None and target_info:
            raw_tab_id = str(target_info.get("tab_id", "")) or None
    elif tab_id is not None and tab_id != "":
        raw_tab_id = str(normalize_tab_id(tab_id))

    if raw_tab_id is not None and "tabId" not in cmd:
        cmd["tabId"] = int(raw_tab_id)

    transport_session_id: str | None = None
    status_tab_id: str | None = raw_tab_id
    if resolved_session_id is not None:
        target_client_id = getattr(target_session, "client_id", None) if target_session else (target_info or {}).get("client_id")
        target_is_active_ext_ws = (
            target_session.is_active() and target_session.type == "ext_ws"
            if target_session
            else bool(target_info) and target_info.get("type") == "ext_ws"
        )
        if not target_is_active_ext_ws:
            transport_session_id = driver.get_ext_ws_transport_session_id(token=token, client_id=target_client_id)
        else:
            transport_session_id = resolved_session_id
    elif raw_tab_id is not None:
        normalized_tab_id = normalize_tab_id(tab_id)
        if normalized_tab_id is not None:
            ctx = driver.get_context(token)
            target_session = ctx.sessions.get(str(normalized_tab_id))
            target_client_id = getattr(target_session, "client_id", None) if target_session else None
            if not target_session or not target_session.is_active() or target_session.type != "ext_ws":
                transport_session_id = driver.get_ext_ws_transport_session_id(token=token, client_id=target_client_id)
            else:
                transport_session_id = str(normalized_tab_id)

    result = driver.execute_js(
        json.dumps(cmd, ensure_ascii=False),
        timeout=timeout,
        token=token,
        group_status=group_status,
        session_id=transport_session_id,
        status_tab_id=status_tab_id,
    )
    return result.get("data", result)


def batch(driver: TMWebDriver, commands: list[dict[str, Any]], tab_id: str = "", timeout: float = 20, token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    ensure_sessions(driver, token=token)

    actual_tab_id, error = require_tab_id(driver, tab_id, token=token)
    if error:
        return error
    driver._cancel_tab_close(actual_tab_id, token=token)

    try:
        result = extension_command(driver, {"cmd": "batch", "commands": commands}, tab_id=tab_id, timeout=timeout, token=token, group_status=STATUS_MAP["batch"]["in_progress"])
    finally:
        update_group_status(driver, actual_tab_id, "batch", "done", token=token)
        _schedule_tab_cleanup_after_operation(driver, ctx, actual_tab_id, token=token)
    transport_error = result.get("error") if isinstance(result, dict) and result.get("ok") is False else None
    batch_results = result.get("results", []) if isinstance(result, dict) and "results" in result else result
    failures = [
        {"index": index, "result": item}
        for index, item in enumerate(batch_results if isinstance(batch_results, list) else [])
        if isinstance(item, dict) and item.get("ok") is False
    ]
    if transport_error or failures:
        return {
            "status": "error",
            "msg": transport_error or "Batch contained failed commands.",
            "results": batch_results,
            "failures": failures,
        }
    return {"status": "success", "results": batch_results}


def wait(driver: TMWebDriver, condition_js: str | None = None, wait_target: str | None = None, text: str | None = None, url: str | None = None, load: str | None = None, fn: str | None = None, state: str = "visible", timeout: float = 10, interval: float = 0.5, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import browser_commands, cdp
    ctx = driver.get_context(token)
    ensure_sessions(driver, token=token)

    tab_id, error = require_tab_id(driver, switch_tab_id, token=token)
    if error:
        return error
    driver._cancel_tab_close(tab_id, token=token)

    try:
        target = wait_target if wait_target is not None else condition_js
        # Accept the documented CLI shorthand `wait text=...` (and
        # `wait url=...`) as a semantic condition, rather than treating the
        # whole token as a CSS selector.
        if isinstance(target, str) and target.startswith("text=") and text is None:
            text = target[len("text="):]
            target = None
        elif isinstance(target, str) and target.startswith("url=") and url is None:
            url = target[len("url="):]
            target = None
        if target and target.isdigit():
            time.sleep(int(target) / 1000.0)
            return {"status": "success", "value": True, "attempts": 1, "tab_id": tab_id}
        effective_fn = fn
        if effective_fn:
            effective_fn = effective_fn.strip()
            if effective_fn.startswith("return "):
                effective_fn = effective_fn[len("return "):].strip()
        if condition_js and browser_commands.looks_like_js_condition(condition_js):
            effective_fn = condition_js.replace("return ", "", 1)
            target = None
        condition = browser_commands.wait_condition_script(target=target, text=text, url=url, load=load, fn=effective_fn, state=state)

        deadline = time.time() + max(timeout, 0)
        last_value = None
        last_error = None
        attempts = 0
        first = True
        while True:
            attempts += 1
            try:
                gs = STATUS_MAP["wait"]["in_progress"] if first else None
                first = False
                last_value = cdp.evaluate(driver, tab_id, condition, token=token)
                last_error = None
                if last_value is True:
                    return {
                        "status": "success",
                        "value": last_value,
                        "attempts": attempts,
                        "tab_id": tab_id,
                    }
            except Exception as exc:
                last_error = str(exc)
            if time.time() >= deadline:
                return {
                    "status": "timeout",
                    "value": last_value,
                    "error": last_error,
                    "attempts": attempts,
                    "tab_id": tab_id,
                }
            time.sleep(max(interval, 0.1))
    finally:
        update_group_status(driver, tab_id, "wait", "done", token=token)
        _schedule_tab_cleanup_after_operation(driver, ctx, tab_id, token=token)


def navigate_new_tab(driver: TMWebDriver, url: str, token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    try:
        result = driver.new_tab(url, timeout=15, token=token)
    except Exception as exc:
        return {"status": "error", "msg": str(exc)}
    if result is None:
        return {"status": "error", "msg": f"Failed to create tab for {url}"}
    tab_id = str(result.get("id", ""))
    if tab_id:
        driver._cancel_tab_close(tab_id, token=token)
        update_group_status(driver, tab_id, "new_tab", "done", token=token)
        driver._schedule_tab_close(tab_id, token=token)
    return {"status": "success", "tab": result}


def navigate(driver: TMWebDriver, url: str, new_tab: bool = True, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    if new_tab:
        return navigate_new_tab(driver, url, token=token)

    if len(driver.get_all_sessions(token=token)) == 0:
        return {"status": "error", "msg": "No browser tabs connected."}

    tab_id, error = require_tab_id(driver, switch_tab_id, token=token)
    if error:
        return error
    driver._cancel_tab_close(tab_id, token=token)

    try:
        driver.jump(url, timeout=10, token=token, group_status=STATUS_MAP["navigate"]["in_progress"], session_id=tab_id)
    finally:
        update_group_status(driver, tab_id, "navigate", "done", token=token)
        _schedule_tab_cleanup_after_operation(driver, ctx, tab_id, token=token)
    return {"status": "success", "msg": f"Navigating to {url}"}


def _visual_ref_clip(driver: TMWebDriver, tab_id: str, ref: str, token: str | None = None) -> dict[str, float]:
    """Resolve a visual snapshot ref, restore it into view, and return its clip."""
    from . import cdp

    ctx = driver.get_context(token)
    entry = ctx.refs.get(tab_id, ref)
    if entry is None:
        raise RuntimeError(f"Visual ref {ref!r} was not found. Run snapshot -i again.")
    if entry.kind != "visual":
        raise RuntimeError(f"Ref {ref!r} is [{entry.role}], not a visual region. Choose an article, region, dialog, media, or listitem ref.")

    if entry.backend_node_id is None:
        raise RuntimeError(f"Visual ref {ref!r} has no live DOM target. Run snapshot -i again.")
    try:
        value = get_ref_value(driver, tab_id, entry, "box", token=token)
        if not isinstance(value, dict) or value.get("__omnibotElementError"):
            value = get_backend_ref_value(driver, tab_id, entry.backend_node_id, "box", token=token)
    except Exception as exc:
        raise RuntimeError(f"Visual ref {ref!r} is stale. Run snapshot -i again.") from exc
    if not isinstance(value, dict) or value.get("__omnibotElementError"):
        raise RuntimeError(f"Visual ref {ref!r} is not visible or has no area. Run snapshot -i again.")
    box = {key: float(value.get(key) or 0) for key in ("x", "y", "width", "height")}
    if box["width"] <= 0 or box["height"] <= 0:
        raise RuntimeError(f"Visual ref {ref!r} is not visible or has no area. Run snapshot -i again.")
    return box


def _wait_for_screenshot_paint(driver: TMWebDriver, tab_id: str, token: str | None = None) -> dict[str, Any]:
    """Give fonts and the compositor a bounded chance to reach a painted frame."""
    from . import cdp

    try:
        value = cdp.evaluate(
            driver,
            tab_id,
            """(async () => {
              const bounded = (promise, timeout) => Promise.race([
                promise,
                new Promise((resolve) => setTimeout(resolve, timeout)),
              ]);
              if (document.fonts && document.fonts.ready) {
                await bounded(document.fonts.ready, 750);
              }
              await bounded(
                new Promise((resolve) =>
                  requestAnimationFrame(() => requestAnimationFrame(resolve))
                ),
                250
              );
              return {
                url: location.href,
                title: document.title,
                viewport: {
                  width: window.innerWidth,
                  height: window.innerHeight,
                  deviceScaleFactor: window.devicePixelRatio || 1,
                },
              };
            })()""",
            token=token,
            timeout=2,
        )
        return value if isinstance(value, dict) else {}
    except Exception:
        # Paint stabilization and page identity enrich screenshot evidence, but
        # a restricted document must not block the actual CDP capture.
        return {}


def screenshot(driver: TMWebDriver, tab_id: str = "", full: bool = False, annotate: bool = False, screenshot_format: str = "png", screenshot_quality: int | None = None, ref: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp, snapshot as snapshot_mod

    ctx = driver.get_context(token)
    if len(driver.get_all_sessions(token=token)) == 0:
        return {"status": "error", "msg": "No browser tabs connected."}

    actual_tab_id, error = require_tab_id(driver, tab_id, token=token)
    if error:
        return error
    driver._cancel_tab_close(actual_tab_id, token=token)

    if ref and full:
        return {"status": "error", "msg": "--ref and --full cannot be used together."}

    overlay_added = False
    try:
        params: dict[str, Any] = {"format": screenshot_format or "png", "fromSurface": True}
        if screenshot_format == "jpeg" and screenshot_quality is not None:
            params["quality"] = screenshot_quality
        if full:
            metrics = cdp.send_cdp(driver, actual_tab_id, "Page.getLayoutMetrics", token=token)
            size = metrics.get("contentSize") or metrics.get("cssContentSize") or {}
            params["captureBeyondViewport"] = True
            params["clip"] = {"x": 0, "y": 0, "width": size.get("width", 1280), "height": size.get("height", 720), "scale": 1}
        if ref:
            box = _visual_ref_clip(driver, actual_tab_id, ref, token=token)
            params["clip"] = {**box, "scale": 1}
        if annotate:
            snap = snapshot(driver, interactive=True, compact=True, switch_tab_id=str(actual_tab_id or ""), token=token)
            refs = snap.get("refs") if isinstance(snap, dict) else {}
            cdp.evaluate(driver, actual_tab_id, snapshot_mod.annotation_overlay_script(refs or {}), token=token)
            overlay_added = True
        page_meta = _wait_for_screenshot_paint(driver, actual_tab_id, token=token)
        result = extension_command(driver, {"cmd": "cdp", "method": "Page.captureScreenshot", "params": params}, tab_id=actual_tab_id, timeout=15, token=token, group_status=STATUS_MAP["screenshot"]["in_progress"])
    finally:
        if overlay_added and actual_tab_id:
            try:
                cdp.evaluate(driver, actual_tab_id, snapshot_mod.remove_annotation_overlay_script(), token=token)
            except Exception:
                pass
        update_group_status(driver, actual_tab_id, "screenshot", "done", token=token)
        _schedule_tab_cleanup_after_operation(driver, ctx, actual_tab_id, token=token)

    data = result.get("data", {})
    region_meta = {"ref": ref, "mode": "visual-region"} if ref else {}
    if isinstance(data, dict) and "data" in data:
        return {"status": "success", "format": screenshot_format or "png", "base64": data["data"], **page_meta, **region_meta}
    if isinstance(data, str):
        return {"status": "success", "format": screenshot_format or "png", "base64": data, **page_meta, **region_meta}
    return {"status": "success", "format": screenshot_format or "png", "data": data, **page_meta, **region_meta}


def click(driver: TMWebDriver, selector: str, switch_tab_id: str = "", new_tab: bool = False, token: str | None = None) -> dict[str, Any]:
    from . import interactions

    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        update_group_status(driver, tab_id, "click", "in_progress", token=token)
        if new_tab:
            result = interactions.click_new_tab(driver, tab_id, selector, ctx.refs, token=token)
            created_tab_id = str((result.get("tab") or {}).get("id") or "") if isinstance(result, dict) else ""
            if created_tab_id:
                ctx.tool_created_tabs.add(created_tab_id)
                session = ctx.sessions.get(created_tab_id)
                if session:
                    session.created_by_tool = True
                driver._schedule_tab_close(created_tab_id, token=token)
            return result
        data = interactions.click(driver, tab_id, selector, ctx.refs, token=token, frame_target=_active_frame_target(ctx, tab_id))
        schedule_new_tabs_from_result(driver, ctx, data, source_tab_id=tab_id, token=token)
        return {"status": "success", **data}
    finally:
        update_group_status(driver, tab_id, "click", "done", token=token)
        _schedule_tab_cleanup_after_operation(driver, ctx, tab_id, token=token)


def hover(driver: TMWebDriver, selector: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.hover(driver, tab_id, selector, ctx.refs, token=token, frame_target=_active_frame_target(ctx, tab_id))}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def focus(driver: TMWebDriver, selector: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.focus(driver, tab_id, selector, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def select(driver: TMWebDriver, selector: str, value: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.select_option(driver, tab_id, selector, value, ctx.refs, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def check(driver: TMWebDriver, selector: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.set_checked(driver, tab_id, selector, ctx.refs, True, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def uncheck(driver: TMWebDriver, selector: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.set_checked(driver, tab_id, selector, ctx.refs, False, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def scroll(driver: TMWebDriver, direction: str, pixels: int, selector: str = "", switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.scroll(driver, tab_id, direction, int(pixels), selector or None, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def scrollintoview(driver: TMWebDriver, selector: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.scroll_into_view(driver, tab_id, selector, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def drag(driver: TMWebDriver, source: str, target: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.drag(driver, tab_id, source, target, ctx.refs, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def upload(driver: TMWebDriver, selector: str, file: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from pathlib import Path
    from . import cdp

    upload_path = Path(file).expanduser().resolve()
    if not upload_path.exists() or not upload_path.is_file():
        return {"status": "error", "msg": f"Upload file not found: {upload_path}", "selector": selector, "file": str(upload_path)}
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        entry = getattr(ctx, "refs", None)
        entry = entry.get(tab_id, selector) if entry is not None else None
        if entry and entry.backend_node_id is not None and not entry.selector:
            try:
                resolved = cdp.send_cdp(driver, tab_id, "DOM.resolveNode", {"backendNodeId": entry.backend_node_id}, token=token)
                object_id = resolved.get("object", {}).get("objectId")
                if object_id:
                    cdp.send_cdp(driver, tab_id, "DOM.setFileInputFiles", {"files": [str(upload_path)], "objectId": object_id}, token=token, timeout=30)
                    return {"status": "success", "uploaded": 1, "selector": selector, "file": str(upload_path), "transport": "cdp-ref-object"}
            except Exception:
                pass
        try:
            resolved = cdp.send_cdp(
                driver,
                tab_id,
                "Runtime.evaluate",
                {"expression": f"document.querySelector({selector!r})", "returnByValue": False},
                token=token,
            )
            object_id = resolved.get("result", {}).get("objectId")
            if object_id:
                cdp.send_cdp(
                    driver,
                    tab_id,
                    "DOM.setFileInputFiles",
                    {"files": [str(upload_path)], "objectId": object_id},
                    token=token,
                    timeout=30,
                )
                return {"status": "success", "uploaded": 1, "selector": selector, "file": str(upload_path)}
        except Exception:
            pass

        try:
            document = cdp.send_cdp(driver, tab_id, "DOM.getDocument", {"depth": 0, "pierce": True}, token=token)
            root_node_id = document.get("root", {}).get("nodeId")
            if root_node_id:
                queried = cdp.send_cdp(driver, tab_id, "DOM.querySelector", {"nodeId": root_node_id, "selector": selector}, token=token)
                node_id = queried.get("nodeId")
                if node_id:
                    cdp.send_cdp(
                        driver,
                        tab_id,
                        "DOM.setFileInputFiles",
                        {"files": [str(upload_path)], "nodeId": node_id},
                        token=token,
                        timeout=30,
                    )
                    return {"status": "success", "uploaded": 1, "selector": selector, "file": str(upload_path), "transport": "cdp-node-id"}
        except Exception:
            pass

        file_bytes = upload_path.read_bytes()
        encoded = base64.b64encode(file_bytes).decode("ascii")
        mime_type = mimetypes.guess_type(str(upload_path))[0] or "application/octet-stream"
        expression = f"""
        (() => {{
          const inputs = Array.from(document.querySelectorAll({json.dumps(selector)})).filter((input) =>
            input.tagName && input.tagName.toLowerCase() === 'input' && (input.getAttribute('type') || '').toLowerCase() === 'file'
          );
          if (!inputs.length) return {{ok: false, error: 'selector-not-file-input'}};
          const binary = atob({json.dumps(encoded)});
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          const file = new File([bytes], {json.dumps(upload_path.name)}, {{type: {json.dumps(mime_type)}}});
          for (const input of inputs) {{
            const transfer = new DataTransfer();
            transfer.items.add(file);
            input.files = transfer.files;
            input.dispatchEvent(new Event('input', {{bubbles: true}}));
            input.dispatchEvent(new Event('change', {{bubbles: true}}));
          }}
          return {{ok: true, inputs: inputs.length, files: inputs[inputs.length - 1].files.length, name: inputs[inputs.length - 1].files[0] && inputs[inputs.length - 1].files[0].name}};
        }})()
        """
        result = cdp.send_cdp(
            driver,
            tab_id,
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
            token=token,
            timeout=30,
        )
        value = result.get("result", {}).get("value")
        if isinstance(value, dict) and value.get("ok"):
            return {"status": "success", "uploaded": int(value.get("files") or 1), "inputs": int(value.get("inputs") or 1), "selector": selector, "file": str(upload_path), "transport": "js-file-assignment"}
        return {"status": "error", "msg": str(value or "upload fallback failed"), "selector": selector, "file": str(upload_path)}
    except Exception as exc:
        return {"status": "error", "msg": str(exc), "selector": selector, "file": str(upload_path)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def _target_tab_for_interaction(
    driver: TMWebDriver,
    tab_id: str = "",
    token: str | None = None,
    *,
    clear_previous_status: bool = True,
) -> tuple[Any, str | None, dict[str, Any] | None]:
    ctx = driver.get_context(token)
    resolved_tab_id, error = require_tab_id(driver, tab_id, token=token)
    if error:
        return ctx, None, error
    # Coordinate mouse actions immediately replace the status with their own
    # broadcast.  Clearing it first synchronously waits up to five seconds
    # for a tabStatus cleanup ACK, which makes pointer input visibly lag.
    if clear_previous_status:
        driver._cancel_tab_close(resolved_tab_id, token=token)
    return ctx, resolved_tab_id, None


def _active_frame_target(ctx: Any, tab_id: str = "") -> str:
    from . import frame_context

    if tab_id and getattr(ctx, "frame_targets", None) is not None:
        requested = str(tab_id)
        raw_tab_id = requested.rsplit(":", 1)[-1]
        frame_targets = ctx.frame_targets
        if requested in frame_targets or raw_tab_id in frame_targets:
            target = frame_targets.get(requested, frame_targets.get(raw_tab_id, ""))
            return frame_context.active_frame_target(type("FrameState", (), {"frame_target": target})())

    bound_tab = getattr(ctx, "frame_target_tab_id", None)
    if bound_tab and tab_id:
        requested = str(tab_id)
        if requested != str(bound_tab) and requested.rsplit(":", 1)[-1] != str(bound_tab).rsplit(":", 1)[-1]:
            return ""
        return frame_context.active_frame_target(ctx)
    return frame_context.active_frame_target(ctx)


def _scope_script_to_active_frame(ctx: Any, script: str, missing_value: str = "null", tab_id: str = "") -> str:
    from . import frame_context

    return frame_context.scoped_script(script, _active_frame_target(ctx, tab_id), missing_value=missing_value)


def _keyboard_modifiers_for_tab(ctx: Any, tab_id: str) -> int:
    by_tab = getattr(ctx, "keyboard_modifiers_by_tab", None)
    if by_tab is not None:
        return int(by_tab.get(str(tab_id), 0))
    return int(getattr(ctx, "keyboard_modifiers", 0))


def _selected_frame_error(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("__omnibotFrameError") is not True:
        return None
    reason = str(value.get("reason") or "frame_unavailable")
    target = str(value.get("target") or "")
    message = str(value.get("message") or "Selected frame is not available.")
    return {"status": "error", "msg": message, "reason": reason, "frame": target}


def _schedule_tab_cleanup_after_operation(driver: TMWebDriver, ctx: Any, tab_id: str | None, token: str | None = None) -> None:
    if not tab_id:
        return
    session = ctx.sessions.get(tab_id)
    is_tool_tab = tab_id in ctx.tool_created_tabs or (session and session.created_by_tool)
    timeout = TOOL_CREATED_TAB_CLEANUP_TIMEOUT_SECONDS if is_tool_tab else USER_TAB_UNGROUP_TIMEOUT_SECONDS
    driver._schedule_tab_close(tab_id, timeout=timeout, token=token, close=bool(is_tool_tab))


def _schedule_tool_tab_close_if_needed(driver: TMWebDriver, ctx: Any, tab_id: str | None, token: str | None = None) -> None:
    _schedule_tab_cleanup_after_operation(driver, ctx, tab_id, token=token)


def ref_get_script(role: str, name: str, nth: int | None, kind: str, attr: str | None = None, scroll_into_view: bool = False, scroll_only: bool = False) -> str:
    attr_json = json.dumps(attr or "")
    return f"""
(() => {{
  const role = {json.dumps(role)};
  // AX names can contain presentation whitespace (for example a checkbox
  // label starting with a space). Ref actions normalize names before lookup.
  const name = {json.dumps(name.strip())};
  const nth = {int(nth or 0)};
  const kind = {json.dumps(kind)};
  const roleSelectors = {{
    button: 'button,[role="button"]',
    link: 'a,[role="link"]',
    textbox: 'input,textarea,[role="textbox"]',
    richtext: '[contenteditable="true"],[role="textbox"][aria-multiline="true"]',
    searchbox: 'input[type="search"],[role="searchbox"]'
  }};
  const selector = roleSelectors[role] || 'a,button,input,textarea,select,[role],*';
  const label = (el) => (el.getAttribute('aria-label') || el.innerText || el.textContent || el.value || el.placeholder || '').trim();
  const labelText = (el) => (el.closest('label') ? label(el.closest('label')) : '');
  const controls = Array.from(document.querySelectorAll('input[type="radio"],input[type="checkbox"]'));
  const control = controls.find(control => labelText(control) === name);
  const matches = control ? [control] : Array.from(document.querySelectorAll(selector)).filter(el => label(el) === name);
  const el = matches[nth] || matches[0];
  if (!el) return {{__omnibotElementError: true, reason: "element_not_found"}};
  if (kind === "text") return el.textContent;
  if (kind === "html") return el.innerHTML;
  if (kind === "value") return el.value;
  if (kind === "attr") {{
    const name = {attr_json};
    if ((name === "href" || name === "src" || name === "action") && el[name]) return el[name];
    return el.getAttribute(name);
  }}
  if (kind === "box") {{
    if ({str(bool(scroll_only)).lower()}) {{
      el.scrollIntoView({{block: 'center', inline: 'center'}});
      return true;
    }}
    if ({str(bool(scroll_into_view)).lower()}) {{
      el.scrollIntoView({{block: 'center', inline: 'center'}});
      return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => {{
        const r = el.getBoundingClientRect();
        resolve({{x: r.left, y: r.top, width: r.width, height: r.height}});
      }})));
    }}
    const r = el.getBoundingClientRect();
    return {{x: r.left, y: r.top, width: r.width, height: r.height}};
  }}
  if (kind === "styles") {{
    const s = getComputedStyle(el);
    return {{display: s.display, visibility: s.visibility, opacity: s.opacity, position: s.position, zIndex: s.zIndex}};
  }}
  if (kind === "visible") {{
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) !== 0;
  }}
  if (kind === "hidden") {{
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width === 0 || r.height === 0 || s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) === 0;
  }}
  if (kind === "enabled") return !el.disabled && el.getAttribute('aria-disabled') !== 'true';
  if (kind === "checked") return Boolean(el.checked);
  return null;
}})()
"""


class _RefTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "template"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "template"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)


def _inner_html_from_outer_html(outer_html: str) -> str:
    """Strip the serialized element wrapper while preserving its child markup."""
    quote: str | None = None
    opening_end = None
    for index, char in enumerate(outer_html):
        if char in {'"', "'"}:
            quote = None if quote == char else char if quote is None else quote
        elif char == ">" and quote is None:
            opening_end = index
            break
    if opening_end is None:
        return outer_html
    opening = outer_html[: opening_end + 1]
    if opening.rstrip().endswith("/>"):
        return ""
    closing_start = outer_html.rfind("</")
    if closing_start <= opening_end:
        return outer_html[opening_end + 1 :]
    return outer_html[opening_end + 1 : closing_start]


def get_backend_ref_value(driver: TMWebDriver, tab_id: str, backend_node_id: int, kind: str, attr: str | None = None, token: str | None = None) -> Any:
    from . import cdp

    if kind == "box":
        try:
            model = cdp.send_cdp(driver, tab_id, "DOM.getBoxModel", {"backendNodeId": backend_node_id}, token=token).get("model", {})
        except Exception:
            return None
        quad = model.get("border") or model.get("content") or []
        if len(quad) < 8:
            return None
        xs = [float(quad[index]) for index in range(0, 8, 2)]
        ys = [float(quad[index]) for index in range(1, 8, 2)]
        return {"x": min(xs), "y": min(ys), "width": max(xs) - min(xs), "height": max(ys) - min(ys)}
    if kind in {"attr", "enabled", "checked"}:
        node = cdp.send_cdp(driver, tab_id, "DOM.describeNode", {"backendNodeId": backend_node_id, "depth": 0}, token=token).get("node", {})
        attrs = node.get("attributes", [])
        values = dict(zip(attrs[::2], attrs[1::2]))
        if kind == "attr":
            value = values.get(attr or "")
            if value and attr in {"href", "src", "action"}:
                base_uri = cdp.evaluate(driver, tab_id, "document.baseURI", token=token)
                if isinstance(base_uri, str) and base_uri:
                    return urljoin(base_uri, value)
            return value
        if kind == "enabled":
            return "disabled" not in values and values.get("aria-disabled") != "true"
        return "checked" in values or values.get("aria-checked") == "true"
    if kind == "visible":
        box = get_backend_ref_value(driver, tab_id, backend_node_id, "box", token=token)
        return bool(box and box.get("width", 0) > 0 and box.get("height", 0) > 0)
    if kind == "hidden":
        box = get_backend_ref_value(driver, tab_id, backend_node_id, "box", token=token)
        return not bool(box and box.get("width", 0) > 0 and box.get("height", 0) > 0)
    outer_html = cdp.send_cdp(driver, tab_id, "DOM.getOuterHTML", {"backendNodeId": backend_node_id}, token=token).get("outerHTML")
    if not isinstance(outer_html, str):
        return None
    if kind == "html":
        return _inner_html_from_outer_html(outer_html)
    if kind == "text":
        parser = _RefTextParser()
        parser.feed(outer_html)
        return " ".join(" ".join(parser.parts).split())
    return None


def get_ref_value(driver: TMWebDriver, tab_id: str, entry: Any, kind: str, attr: str | None = None, token: str | None = None) -> Any:
    from . import browser_commands, cdp

    if kind == "count":
        return 1
    if entry.role and entry.name:
        value = cdp.evaluate(driver, tab_id, ref_get_script(entry.role, entry.name, entry.nth, kind, attr), token=token)
        if not (isinstance(value, dict) and value.get("__omnibotElementError")):
            return value
    if entry.backend_node_id is not None:
        backend_value = get_backend_ref_value(driver, tab_id, entry.backend_node_id, kind, attr, token=token)
        if backend_value is not None:
            return backend_value
    if entry.selector:
        return cdp.evaluate(driver, tab_id, browser_commands.get_script(kind, entry.selector, attr), token=token)
    return None


def _element_not_found_error(value: Any, selector: str | None, kind: str) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value.get("__omnibotElementError"):
        return None
    return {
        "status": "error",
        "msg": f"Element not found for {kind}: {selector}",
        "reason": "element_not_found",
        "selector": selector,
    }


def fill(driver: TMWebDriver, selector: str, value: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.fill(driver, tab_id, selector, value, ctx.refs, token=token, frame_target=_active_frame_target(ctx, tab_id))}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def type_text(driver: TMWebDriver, selector: str, text: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        return {"status": "success", **interactions.type_text(driver, tab_id, selector, text, ctx.refs, token=token, frame_target=_active_frame_target(ctx, tab_id))}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def press(driver: TMWebDriver, key: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp, interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        normalized_key = key.replace(" ", "").lower()
        paste_shortcut = normalized_key in {"control+v", "ctrl+v", "meta+v", "cmd+v", "command+v"}
        if paste_shortcut:
            interactions.save_active_element(driver, tab_id, token=token)
        result = interactions.press_key(driver, tab_id, key, token=token)
        if paste_shortcut and interactions.restore_saved_active_element(driver, tab_id, token=token):
            clipboard = extension_command(driver, {"cmd": "clipboard", "method": "readText"}, tab_id=tab_id, timeout=10, token=token)
            pasted_text = ""
            if isinstance(clipboard, dict):
                pasted_text = str(clipboard.get("text") or clipboard.get("data") or "")
            elif isinstance(clipboard, str):
                pasted_text = clipboard
            if pasted_text:
                cdp.send_cdp(driver, tab_id, "Input.insertText", {"text": pasted_text}, token=token)
            result["pasted"] = pasted_text
        return {"status": "success", **result}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def keyboard(driver: TMWebDriver, keyboard_command: str, value: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        if keyboard_command == "type":
            return {"status": "success", **interactions.keyboard_type(driver, tab_id, value, modifiers=_keyboard_modifiers_for_tab(ctx, tab_id), token=token)}
        if keyboard_command == "inserttext":
            return {"status": "success", **interactions.keyboard_insert_text(driver, tab_id, value, token=token)}
        return {"status": "error", "msg": f"Unsupported keyboard command: {keyboard_command}"}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def keydown(driver: TMWebDriver, key: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        result = interactions.press_key(driver, tab_id, key, token=token, event_type="down")
        _name, _code, _key_code, modifiers = interactions.parse_key(key)
        if modifiers:
            if hasattr(ctx, "keyboard_modifiers_by_tab"):
                ctx.keyboard_modifiers_by_tab[str(tab_id)] = _keyboard_modifiers_for_tab(ctx, tab_id) | modifiers
            else:
                ctx.keyboard_modifiers = getattr(ctx, "keyboard_modifiers", 0) | modifiers
        return {"status": "success", **result}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def keyup(driver: TMWebDriver, key: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        result = interactions.press_key(driver, tab_id, key, token=token, event_type="up")
        _name, _code, _key_code, modifiers = interactions.parse_key(key)
        if modifiers:
            if hasattr(ctx, "keyboard_modifiers_by_tab"):
                ctx.keyboard_modifiers_by_tab[str(tab_id)] = _keyboard_modifiers_for_tab(ctx, tab_id) & ~modifiers
            else:
                ctx.keyboard_modifiers = getattr(ctx, "keyboard_modifiers", 0) & ~modifiers
        return {"status": "success", **result}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def dblclick(driver: TMWebDriver, selector: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import interactions

    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    data = interactions.click(driver, tab_id, selector, ctx.refs, token=token, click_count=2)
    return {"status": "success", **data}


def snapshot(driver: TMWebDriver, interactive: bool = False, compact: bool = False, max_depth: int | None = None, selector: str = "", include_urls: bool = False, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp, frame_context, snapshot as snapshot_mod

    ctx = driver.get_context(token)
    if len(driver.get_all_sessions(token=token)) == 0:
        return {"status": "error", "msg": "No browser tabs connected. Ensure Chrome extension is running."}

    tab_id, error = require_tab_id(driver, switch_tab_id, token=token)
    if error:
        return error
    driver._cancel_tab_close(tab_id, token=token)
    if tab_id:
        driver._cancel_tab_close(tab_id, token=token)

    try:
        richtext_controls = cdp.evaluate(driver, tab_id, snapshot_mod.dom_richtext_controls_script(), token=token)
        if not isinstance(richtext_controls, list):
            richtext_controls = []
        popup_controls = cdp.evaluate(driver, tab_id, snapshot_mod.dom_popup_controls_script(), token=token)
        if not isinstance(popup_controls, list):
            popup_controls = []
        combobox_controls = cdp.evaluate(driver, tab_id, snapshot_mod.dom_combobox_options_script(), token=token)
        if not isinstance(combobox_controls, list):
            combobox_controls = []
        popup_controls = popup_controls + combobox_controls

        cdp.send_cdp(driver, tab_id, "DOM.enable", {}, token=token)
        cdp.send_cdp(driver, tab_id, "Accessibility.enable", {}, token=token)

        backend_node_id = None
        if selector:
            backend_node_id = snapshot_mod.resolve_selector_backend_node(driver, tab_id, selector, token=token)

        params: dict[str, Any] = {}
        if backend_node_id is not None:
            params["backendNodeId"] = backend_node_id

        active_frame = _active_frame_target(ctx, tab_id)
        if active_frame:
            descriptor = cdp.evaluate(
                driver,
                tab_id,
                f"""(() => {{
                  const target = {json.dumps(active_frame)};
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
            )
            if not isinstance(descriptor, dict):
                descriptor = {"url": active_frame, "name": active_frame, "id": active_frame}
            frame_tree = cdp.send_cdp(driver, tab_id, "Page.getFrameTree", {}, token=token)
            frame_id = frame_context.select_frame_id(frame_tree, descriptor)
            if not frame_id:
                return {
                    "status": "error",
                    "msg": "Selected frame was not found in the current page.",
                    "reason": "not_found",
                    "frame": active_frame,
                }
            params["frameId"] = frame_id

        ax_tree = cdp.send_cdp(driver, tab_id, "Accessibility.getFullAXTree", params, token=token)

        input_types: dict[int, str] = {}
        for node in ax_tree.get("nodes", []) or []:
            role = str((node.get("role") or {}).get("value") or "")
            backend_id = node.get("backendDOMNodeId")
            if role not in {"textbox", "searchbox"} or backend_id is None:
                continue
            try:
                described = cdp.send_cdp(
                    driver,
                    tab_id,
                    "DOM.describeNode",
                    {"backendNodeId": backend_id, "depth": 0},
                    token=token,
                ).get("node", {})
                attributes = described.get("attributes") or []
                attrs = dict(zip(attributes[::2], attributes[1::2]))
                if str(described.get("nodeName") or "").lower() == "input":
                    input_types[int(backend_id)] = str(attrs.get("type") or "text").lower()
            except Exception:
                continue

        text, refs_json = snapshot_mod.format_ax_snapshot(
            ax_tree,
            tab_id=tab_id,
            ref_map=ctx.refs,
            interactive=interactive,
            compact=compact,
            max_depth=max_depth,
            include_urls=include_urls,
            input_types=input_types,
        )

        text, refs_json = snapshot_mod.append_dom_richtext_controls(
            text,
            refs_json,
            richtext_controls,
            tab_id=tab_id,
            ref_map=ctx.refs,
        )

        text, refs_json = snapshot_mod.append_dom_popup_controls(
            text,
            refs_json,
            popup_controls,
            tab_id=tab_id,
            ref_map=ctx.refs,
        )

        return {"status": "success", "content": text, "refs": refs_json, "metadata": {"tab_id": tab_id}}
    finally:
        _schedule_tab_cleanup_after_operation(driver, ctx, tab_id, token=token)


def get(driver: TMWebDriver, kind: str, selector: str | None = None, attr: str | None = None, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import browser_commands, cdp, frame_context
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        entry = ctx.refs.get(tab_id, selector) if selector else None
        active_frame = _active_frame_target(ctx, tab_id)
        if active_frame and hasattr(driver, "_raw_tab_id"):
            if entry is not None and entry.backend_node_id is not None and not entry.selector:
                value = get_backend_ref_value(driver, tab_id, entry.backend_node_id, kind, attr, token=token)
            elif entry is not None and not entry.selector:
                script = ref_get_script(entry.role, entry.name, entry.nth, kind, attr)
                try:
                    value = cdp.evaluate_in_frame(driver, tab_id, active_frame, script, token=token)
                except cdp.CdpError as exc:
                    return {
                        "status": "error",
                        "msg": str(exc),
                        "reason": "cross_origin_or_inaccessible",
                        "frame": active_frame,
                    }
            else:
                target_selector = entry.selector if entry is not None and entry.selector else selector
                script = browser_commands.get_script(kind, target_selector, attr)
                try:
                    value = cdp.evaluate_in_frame(driver, tab_id, active_frame, script, token=token)
                except cdp.CdpError as exc:
                    return {
                        "status": "error",
                        "msg": str(exc),
                        "reason": "cross_origin_or_inaccessible",
                        "frame": active_frame,
                    }
        elif entry is not None:
            value = get_ref_value(driver, tab_id, entry, kind, attr, token=token)
        else:
            script = frame_context.scoped_script(
                browser_commands.get_script(kind, selector, attr),
                _active_frame_target(ctx, tab_id),
                missing_value=frame_context.frame_error_value("not_found"),
                inaccessible_value=frame_context.frame_error_value("cross_origin_or_inaccessible"),
            )
            value = cdp.evaluate(driver, tab_id, script, token=token)
        frame_error = _selected_frame_error(value)
        if frame_error is not None:
            return frame_error
        element_error = _element_not_found_error(value, selector, kind)
        if element_error is not None:
            return element_error
        return {"status": "success", "kind": kind, "selector": selector, "value": value}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def is_state(driver: TMWebDriver, kind: str, selector: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import browser_commands, cdp
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        entry = ctx.refs.get(tab_id, selector)
        active_frame = _active_frame_target(ctx, tab_id)
        if active_frame and hasattr(driver, "_raw_tab_id"):
            if entry is not None and not entry.selector:
                script = ref_get_script(entry.role, entry.name, entry.nth, kind)
            else:
                target_selector = entry.selector if entry is not None and entry.selector else selector
                script = browser_commands.is_script(kind, target_selector)
            try:
                value = cdp.evaluate_in_frame(driver, tab_id, active_frame, script, token=token)
            except cdp.CdpError as exc:
                return {
                    "status": "error",
                    "msg": str(exc),
                    "reason": "cross_origin_or_inaccessible",
                    "frame": active_frame,
                }
        elif entry is not None:
            raw_value = get_ref_value(driver, tab_id, entry, kind, token=token)
            value = raw_value if isinstance(raw_value, bool) else False
        else:
            value = bool(cdp.evaluate(driver, tab_id, _scope_script_to_active_frame(ctx, browser_commands.is_script(kind, selector), missing_value="false", tab_id=tab_id), token=token))
        return {"status": "success", "kind": kind, "selector": selector, "value": value}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def _run_find_subaction(driver: TMWebDriver, action: str, selector: str, value: str | None, tab_id: str, token: str | None) -> dict[str, Any]:
    if action == "click":
        return click(driver, selector, switch_tab_id=tab_id, token=token)
    if action == "fill":
        return fill(driver, selector, value or "", switch_tab_id=tab_id, token=token)
    if action == "type":
        return type_text(driver, selector, value or "", switch_tab_id=tab_id, token=token)
    if action == "hover":
        return hover(driver, selector, switch_tab_id=tab_id, token=token)
    if action == "focus":
        return focus(driver, selector, switch_tab_id=tab_id, token=token)
    if action == "check":
        return check(driver, selector, switch_tab_id=tab_id, token=token)
    if action == "uncheck":
        return uncheck(driver, selector, switch_tab_id=tab_id, token=token)
    if action == "text":
        return get(driver, "text", selector=selector, switch_tab_id=tab_id, token=token)
    return {"status": "error", "msg": f"Unsupported find action: {action}"}


def find(driver: TMWebDriver, strategy: str, value: str, action: str = "text", action_value: str | None = None, name: str | None = None, exact: bool = False, index: int | None = None, selector: str | None = None, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp, frame_context, locators
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    script = locators.nth_script(selector or value, index or 0) if strategy == "nth" else locators.locator_script(strategy, value, name=name, exact=exact)
    ok = cdp.evaluate(
        driver,
        tab_id,
        frame_context.scoped_script(
            script,
            _active_frame_target(ctx, tab_id),
            missing_value=frame_context.frame_error_value("not_found"),
            inaccessible_value=frame_context.frame_error_value("cross_origin_or_inaccessible"),
        ),
        token=token,
    )
    frame_error = _selected_frame_error(ok)
    if frame_error is not None:
        return frame_error
    if ok is not True:
        return {"status": "error", "msg": f"No element found for {strategy}: {value}"}
    return _run_find_subaction(driver, action, locators.located_selector(), action_value, tab_id, token)


def close(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    target, error = require_tab_id(driver, tab_id, token=token)
    if error:
        return error
    result = extension_command(driver, {"cmd": "tabs", "method": "close"}, tab_id=target, timeout=10, token=token)
    return {"status": "success", "closed": target, "extension_response": result}


def tab(driver: TMWebDriver, tab_command: str = "list", url: str | None = None, label: str | None = None, target: str | None = None, token: str | None = None) -> dict[str, Any]:
    from . import browser_commands
    ctx = driver.get_context(token)
    if tab_command == "list":
        result = get_tabs(driver, token=token)
        active_ids = {
            str(value)
            for session in driver.get_all_sessions(token=token)
            for value in (session.get("id"), session.get("tab_id"))
            if value not in (None, "")
        }
        ctx.tab_aliases = {
            alias: tab_id
            for alias, tab_id in getattr(ctx, "tab_aliases", {}).items()
            if str(tab_id) in active_ids
        }
        result["aliases"] = dict(getattr(ctx, "tab_aliases", {}))
        return result
    if tab_command == "new":
        created = navigate_new_tab(driver, url or "about:blank", token=token)
        if created.get("status") != "success":
            return created
        tab_id_str = str((created.get("tab") or {}).get("id") or "")
        alias = browser_commands.assign_tab_alias(ctx, tab_id_str, label=label) if tab_id_str else None
        return {"status": "success", "tab": created.get("tab"), "alias": alias}
    if tab_command == "close":
        return close(driver, browser_commands.resolve_tab_alias(ctx, target or ""), token=token)
    if tab_command in {"group", "ungroup", "group-info"}:
        resolved = browser_commands.resolve_tab_alias(ctx, target or "")
        tab_id, error = require_tab_id(driver, resolved, token=token)
        if error:
            return error
        method = {"group": "group", "ungroup": "ungroup", "group-info": "get"}[tab_command]
        payload: dict[str, Any] = {"cmd": "tabGroups", "method": method, "tabId": int(driver._raw_tab_id(tab_id, token=token))}
        if method == "group":
            payload["title"] = label or ""
        result = extension_command(driver, payload, tab_id=tab_id, timeout=15, token=token)
        ok, data, error = _normalize_browser_api_result(result, "Tab group operation failed")
        # Older workers return the tab-group object directly (without the
        # `{ok: true, data: ...}` envelope).
        if not ok and isinstance(result, dict) and "groupId" in result and "error" not in result:
            ok, data, error = True, result, ""
        if not ok:
            return {"status": "error", "msg": error, "extension_response": result}
        return {"status": "success", "tab_id": tab_id, **(data if isinstance(data, dict) else {})}
    return {"status": "error", "msg": f"Unsupported tab command: {tab_command}"}


def window(driver: TMWebDriver, window_command: str, url: str = "about:blank", token: str | None = None) -> dict[str, Any]:
    if window_command != "new":
        return {"status": "error", "msg": f"Unsupported window command: {window_command}"}
    ctx = driver.get_context(token)
    try:
        result = driver.new_window(url or "about:blank", timeout=15, token=token)
    except Exception as exc:
        return {"status": "error", "msg": str(exc)}
    if not isinstance(result, dict):
        return {"status": "error", "msg": "Failed to create browser window"}
    tab = result.get("tab") or {}
    tab_id = str(tab.get("id") or "")
    requested_url = str(url or "")
    if tab_id and requested_url not in {"", "about:blank"}:
        raw_tab_id = str(tab.get("tab_id") or tab_id.rsplit(":", 1)[-1])
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            sessions = driver.get_all_sessions(token=token)
            session = next((item for item in sessions if str(item.get("tab_id", "")) == raw_tab_id), None)
            if session and (session.get("url") or session.get("title")):
                tab.update({key: session.get(key, tab.get(key, "")) for key in ("url", "title")})
                break
            time.sleep(0.1)
    if tab_id:
        driver._cancel_tab_close(tab_id, token=token)
        update_group_status(driver, tab_id, "new_tab", "done", token=token)
        driver._schedule_tab_close(tab_id, token=token)
    return {"status": "success", "window_id": result.get("windowId"), "tab": tab}


def frame(driver: TMWebDriver, frame_target: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    if switch_tab_id:
        tab_id, error = require_tab_id(driver, switch_tab_id, token=token)
        if error:
            return error
        driver._cancel_tab_close(tab_id, token=token)
        ctx.frame_targets[str(tab_id)] = frame_target
        ctx.frame_targets[str(driver._raw_tab_id(tab_id, token=token))] = frame_target
        ctx.frame_target = frame_target
        ctx.frame_target_tab_id = str(tab_id)
    else:
        ctx.frame_target = frame_target
        ctx.frame_target_tab_id = None
    result = {"status": "success", "frame": frame_target}
    if switch_tab_id:
        result["metadata"] = {"tab_id": switch_tab_id}
    return result


def back(driver: TMWebDriver, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        cdp.evaluate(driver, tab_id, "history.back(); true", token=token)
        return {"status": "success", "action": "back"}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def forward(driver: TMWebDriver, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        cdp.evaluate(driver, tab_id, "history.forward(); true", token=token)
        return {"status": "success", "action": "forward"}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def reload_page(driver: TMWebDriver, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        cdp.send_cdp(driver, tab_id, "Page.reload", {}, token=token)
        return {"status": "success", "action": "reload"}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def pushstate(driver: TMWebDriver, url: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        script = f"history.pushState({{}}, '', {json.dumps(url)}); dispatchEvent(new PopStateEvent('popstate')); true"
        cdp.evaluate(driver, tab_id, script, token=token)
        return {"status": "success", "url": url}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def mouse_click(driver: TMWebDriver, x: float, y: float, button: str = "left", click_count: int = 1, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cua
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token, clear_previous_status=False)
    if error:
        return error
    try:
        broadcast_group_status(driver, tab_id, "click", "in_progress", token=token)
        data = cua.click(driver, tab_id, x, y, button=button, click_count=click_count, token=token)
        schedule_new_tabs_from_result(driver, ctx, data, source_tab_id=tab_id, token=token)
        return {"status": "success", **data}
    finally:
        broadcast_group_status(driver, tab_id, "click", "done", token=token)
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def mouse_move(driver: TMWebDriver, x: float, y: float, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cua
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token, clear_previous_status=False)
    if error:
        return error
    try:
        broadcast_group_status(driver, tab_id, "mouse_move", "in_progress", token=token)
        return {"status": "success", **cua.move(driver, tab_id, x, y, token=token)}
    finally:
        broadcast_group_status(driver, tab_id, "mouse_move", "done", token=token)
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def mouse_scroll(driver: TMWebDriver, x: float, y: float, dx: float = 0, dy: float = 0, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cua
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token, clear_previous_status=False)
    if error:
        return error
    status = "scroll_down" if dy >= 0 else "scroll_up"
    try:
        broadcast_group_status(driver, tab_id, status, "in_progress", token=token)
        return {"status": "success", **cua.scroll(driver, tab_id, x, y, dx, dy, token=token)}
    finally:
        broadcast_group_status(driver, tab_id, status, "done", token=token)
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def mouse_drag(driver: TMWebDriver, from_x: float, from_y: float, to_x: float, to_y: float, duration_ms: float | None = None, steps: int | None = None, jitter: float | None = None, overshoot: float | None = None, fast: bool = False, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cua
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token, clear_previous_status=False)
    if error:
        return error
    try:
        broadcast_group_status(driver, tab_id, "mouse_drag", "in_progress", token=token)
        return {"status": "success", **cua.drag(driver, tab_id, from_x, from_y, to_x, to_y, duration_ms=duration_ms, steps=steps, jitter=jitter, overshoot=overshoot, fast=fast, token=token)}
    finally:
        broadcast_group_status(driver, tab_id, "mouse_drag", "done", token=token)
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def verify_inspect(driver: TMWebDriver, tab_id: str = "", no_image: bool = False, token: str | None = None) -> dict[str, Any]:
    from . import verify as verify_mod

    if len(driver.get_all_sessions(token=token)) == 0:
        return {"status": "error", "msg": "No browser tabs connected."}
    actual_tab_id, error = require_tab_id(driver, tab_id, token=token)
    if error:
        return error
    driver._cancel_tab_close(actual_tab_id, token=token)
    ctx = driver.get_context(token)
    try:
        result = verify_mod.inspect(driver, actual_tab_id, include_image=not no_image, token=token)
    finally:
        _schedule_tab_cleanup_after_operation(driver, ctx, actual_tab_id, token=token)
    return result


def dom_visible(driver: TMWebDriver, limit: int = 200, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp, dom_cua
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        nodes = cdp.evaluate(driver, tab_id, dom_cua.visible_dom_script(limit), token=token)
        return {"status": "success", "nodes": nodes, "count": len(nodes) if isinstance(nodes, list) else 0}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def dom_click(driver: TMWebDriver, node_id: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import dom_cua, interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        selector = dom_cua.node_selector(node_id)
        data = interactions.click(driver, tab_id, selector, ctx.refs, token=token)
        return {"status": "success", **data}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def dom_dblclick(driver: TMWebDriver, node_id: str, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import dom_cua, interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        selector = dom_cua.node_selector(node_id)
        data = interactions.click(driver, tab_id, selector, ctx.refs, token=token, click_count=2)
        return {"status": "success", **data}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def dom_scroll(driver: TMWebDriver, node_id: str, dy: int = 800, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import dom_cua, interactions
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        selector = dom_cua.node_selector(node_id)
        return {"status": "success", **interactions.scroll(driver, tab_id, "down", abs(dy), selector, token=token)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def _console_hook_script(*, clear: bool = False) -> str:
    clear_expr = "window.__omnibotConsoleEntries.length = 0; console.clear();" if clear else ""
    return f"""
(() => {{
  if (!Array.isArray(window.__omnibotConsoleEntries)) window.__omnibotConsoleEntries = [];
  {clear_expr}
  if (!window.__omnibotConsoleOriginals) window.__omnibotConsoleOriginals = {{}};

  const serialize = (arg) => {{
    try {{
      if (typeof arg === 'string') return arg;
      if (arg instanceof Error) return arg.stack || (arg.name + ': ' + arg.message);
      if (arg && typeof arg === 'object') {{
        const json = JSON.stringify(arg);
        if (json && json !== '{{}}') return json;
        return String(arg);
      }}
      return String(arg);
    }} catch (_) {{
      try {{ return String(arg); }} catch (_) {{ return '[unserializable]'; }}
    }}
  }};

  const push = (entry) => {{
    window.__omnibotConsoleEntries.push({{ timestamp: Date.now(), ...entry }});
    if (window.__omnibotConsoleEntries.length > 200) {{
      window.__omnibotConsoleEntries.splice(0, window.__omnibotConsoleEntries.length - 200);
    }}
  }};

  if (!window.__omnibotConsoleHooked) {{
    for (const level of ['log', 'info', 'warn', 'error']) {{
      const original = console[level] ? console[level].bind(console) : console.log.bind(console);
      window.__omnibotConsoleOriginals[level] = original;
      console[level] = (...args) => {{
        push({{ level, text: args.map(serialize).join(' '), source: 'page:console' }});
        return original(...args);
      }};
    }}

    window.addEventListener('error', (event) => {{
      const err = event.error;
      push({{
        level: 'error',
        text: err ? serialize(err) : String(event.message || 'Uncaught error'),
        url: event.filename || '',
        line: event.lineno || 0,
        source: 'page:onerror'
      }});
    }});

    window.addEventListener('unhandledrejection', (event) => {{
      push({{
        level: 'error',
        text: serialize(event.reason || 'Unhandled promise rejection'),
        source: 'page:unhandledrejection'
      }});
    }});

    window.__omnibotConsoleHooked = true;
  }}

  return window.__omnibotConsoleEntries.slice(-200);
}})()
"""


def console_logs(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, target_tab_id, error = _target_tab_for_interaction(driver, tab_id, token=token)
    if error:
        return error
    script = _console_hook_script(clear=False)
    try:
        logs = cdp.evaluate(driver, target_tab_id, script, token=token)
        page_logs = logs if isinstance(logs, list) else []
        devtools_logs: list[dict[str, Any]] = []
        try:
            from . import devtools
            ext_result = extension_command(
                driver,
                {"cmd": "consoleCapture", "op": "logs"},
                tab_id=target_tab_id,
                timeout=10,
                token=token,
            )
            raw_entries = ext_result.get("entries") if isinstance(ext_result, dict) else []
            if isinstance(raw_entries, list):
                devtools_logs = [devtools.normalize_cdp_console_event(entry) for entry in raw_entries if isinstance(entry, dict)]
        except Exception:
            devtools_logs = []
        merged = page_logs + devtools_logs
        return {"status": "success", "logs": merged[-500:]}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, target_tab_id, token=token)


def console_errors(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    result = console_logs(driver, tab_id=tab_id, token=token)
    if result.get("status") != "success":
        return result
    logs = result.get("logs") if isinstance(result.get("logs"), list) else []
    return {"status": "success", "logs": [entry for entry in logs if isinstance(entry, dict) and entry.get("level") == "error"]}


def console_clear(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, target_tab_id, error = _target_tab_for_interaction(driver, tab_id, token=token)
    if error:
        return error
    script = _console_hook_script(clear=True)
    try:
        cdp.evaluate(driver, target_tab_id, script, token=token)
        try:
            extension_command(
                driver,
                {"cmd": "consoleCapture", "op": "clear"},
                tab_id=target_tab_id,
                timeout=10,
                token=token,
            )
        except Exception:
            pass
        return {"status": "success", "cleared": True}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, target_tab_id, token=token)


def network_logs(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    raw = _network_capture_command(driver, "logs", tab_id=tab_id, token=token)
    from . import devtools
    raw["entries"] = [devtools.normalize_network_event(entry) for entry in raw.get("entries", []) if isinstance(entry, dict)]
    return raw


def network_summary_action(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    result = network_logs(driver, tab_id=tab_id, token=token)
    from . import devtools
    return {"status": "success", **devtools.network_summary(result.get("entries", []))}


def _network_capture_command(driver: TMWebDriver, op: str, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "networkCapture", "op": op}, tab_id=tab_id or None, timeout=10, token=token)
    if isinstance(result, dict) and result.get("ok") is False:
        error = str(result.get("error") or result.get("msg") or "network capture failed")
        if "Unknown cmd" in error:
            return {"status": "error", "msg": f"Network capture requires a newer Omnibot browser extension. Reload or update the Omnibot browser extension. Original error: {error}", "entries": []}
        return {"status": "error", "msg": error, "entries": []}
    entries = result.get("entries", result.get("data", [])) if isinstance(result, dict) else []
    return {"status": "success", "entries": entries if isinstance(entries, list) else []}


def dialog_entry_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (str(entry.get("type") or ""), str(entry.get("message") or ""), str(entry.get("defaultPrompt") or ""))


def normalize_dialog_entries(entries: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw in entries:
        if not isinstance(raw, dict):
            continue
        entry = dict(raw)
        previous = normalized[-1] if normalized else None
        if previous and dialog_entry_key(previous) == dialog_entry_key(entry):
            previous_ts = previous.get("timestamp")
            entry_ts = entry.get("timestamp")
            try:
                close_in_time = abs(float(entry_ts) - float(previous_ts)) < 1000
            except (TypeError, ValueError):
                close_in_time = entry_ts == previous_ts
            delayed_wrapper_duplicate = bool(previous.get("hasBrowserHandler")) and not bool(entry.get("hasBrowserHandler"))
            if close_in_time or (delayed_wrapper_duplicate and _dialog_timestamp_delta_ms(previous_ts, entry_ts) < 30000):
                previous["hasBrowserHandler"] = bool(previous.get("hasBrowserHandler")) or bool(entry.get("hasBrowserHandler"))
                if entry_ts is not None:
                    previous["timestamp"] = entry_ts
                continue
        normalized.append(entry)
    return normalized


def _dialog_timestamp_delta_ms(previous_ts: Any, entry_ts: Any) -> float:
    try:
        return abs(float(entry_ts) - float(previous_ts))
    except (TypeError, ValueError):
        return float("inf")


def _dialog_capture_command(driver: TMWebDriver, op: str, tab_id: str = "", *, accept: bool | None = None, prompt_text: str | None = None, token: str | None = None) -> dict[str, Any]:
    cmd: dict[str, Any] = {"cmd": "dialogCapture", "op": op}
    if accept is not None:
        cmd["accept"] = accept
    if prompt_text is not None:
        cmd["promptText"] = prompt_text
    result = extension_command(driver, cmd, tab_id=tab_id or None, timeout=10, token=token)
    if isinstance(result, dict) and result.get("ok") is False:
        error = str(result.get("error") or result.get("msg") or "dialog capture failed")
        if "Unknown cmd" in error:
            return {"status": "error", "msg": f"Dialog capture requires a newer Omnibot browser extension. Reload or update the Omnibot browser extension. Original error: {error}", "entries": []}
        return {"status": "error", "msg": error, "entries": []}
    entries = result.get("entries", result.get("data", [])) if isinstance(result, dict) else []
    entries = normalize_dialog_entries(entries if isinstance(entries, list) else [])
    out: dict[str, Any] = {"status": "success"}
    if op != "handle" or (isinstance(result, dict) and "entries" in result):
        out["entries"] = entries
    if isinstance(result, dict) and "handled" in result:
        out["handled"] = bool(result.get("handled"))
    return out


def dialog_logs(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    return _dialog_capture_command(driver, "logs", tab_id=tab_id, token=token)


def dialog_clear(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    return _dialog_capture_command(driver, "clear", tab_id=tab_id, token=token)


def dialog_handle(driver: TMWebDriver, tab_id: str = "", accept: bool = True, prompt_text: str | None = None, token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, target_tab_id, error = _target_tab_for_interaction(driver, tab_id, token=token)
    if error:
        return error
    try:
        params: dict[str, Any] = {"accept": accept}
        if prompt_text is not None:
            params["promptText"] = prompt_text
        result = None
        last_error: Exception | None = None
        for attempt in range(81):
            try:
                result = cdp.send_cdp(driver, target_tab_id, "Page.handleJavaScriptDialog", params, token=token)
                last_error = None
                break
            except cdp.CdpError as exc:
                last_error = exc
                if "No dialog is showing" not in str(exc) or attempt >= 80:
                    raise
                time.sleep(0.1)
        if last_error is not None:
            raise last_error
        return {"status": "success", "handled": True, "result": result}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, target_tab_id, token=token)


def network_capture_start(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    return _network_capture_command(driver, "start", tab_id=tab_id, token=token)


def network_capture_stop(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    return _network_capture_command(driver, "stop", tab_id=tab_id, token=token)


def network_capture_clear(driver: TMWebDriver, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    return _network_capture_command(driver, "clear", tab_id=tab_id, token=token)


def raw_cdp(driver: TMWebDriver, method: str, params: dict | None = None, tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp
    ctx, actual_tab_id, error = _target_tab_for_interaction(driver, tab_id, token=token)
    if error:
        return error
    try:
        result = cdp.send_cdp(driver, actual_tab_id, method, params or {}, token=token)
        return {"status": "success", "method": method, "result": result}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, actual_tab_id, token=token)


def clipboard_read(driver: TMWebDriver, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        result = extension_command(driver, {"cmd": "clipboard", "method": "readText"}, tab_id=tab_id, timeout=10, token=token)
        text = ""
        if isinstance(result, dict):
            text = str(result.get("text") or result.get("data") or "")
        elif isinstance(result, str):
            text = result
        return {"status": "success", "text": text}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def clipboard_write(driver: TMWebDriver, text: str = "", switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        extension_command(driver, {"cmd": "clipboard", "method": "writeText", "text": text}, tab_id=tab_id, timeout=10, token=token)
        return {"status": "success", "text": text}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def viewport_get(driver: TMWebDriver, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import browser_commands, cdp
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        result = cdp.evaluate(driver, tab_id, browser_commands.viewport_get_script(), token=token)
        return {"status": "success", "viewport": result}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def viewport_set(driver: TMWebDriver, width: int = 1280, height: int = 720, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import browser_commands, cdp
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        params = {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False}
        cdp.send_cdp(driver, tab_id, "Emulation.setDeviceMetricsOverride", params, token=token)

        def read_css_viewport() -> tuple[int, int]:
            current = cdp.evaluate(driver, tab_id, browser_commands.viewport_get_script(), token=token)
            if not isinstance(current, dict):
                return 0, 0
            return int(round(float(current.get("width", 0)))), int(round(float(current.get("height", 0))))

        actual_width, actual_height = read_css_viewport()
        if actual_width != width or actual_height != height:
            scale = (width / actual_width) if actual_width > 0 else ((height / actual_height) if actual_height > 0 else 1)
            calibrated = {
                **params,
                "width": max(width, int(round(width * scale))),
                "height": max(height, int(round(height * scale))),
            }
            if calibrated["width"] != width or calibrated["height"] != height:
                cdp.send_cdp(driver, tab_id, "Emulation.setDeviceMetricsOverride", calibrated, token=token)
                actual_width, actual_height = read_css_viewport()
        # Chrome can round a CSS viewport dimension by one pixel after device
        # metrics override; do not turn that successful resize into a false error.
        if abs(actual_width - width) <= 1 and abs(actual_height - height) <= 1:
            if actual_width != width or actual_height != height:
                return {
                    "status": "success",
                    "width": width,
                    "height": height,
                    "actual": {"width": actual_width, "height": actual_height},
                }
            return {"status": "success", "width": width, "height": height}
        if actual_width != width or actual_height != height:
            return {
                "status": "error",
                "msg": f"Viewport override was not applied: requested {width}x{height}, got {actual_width}x{actual_height} CSS pixels.",
                "reason": "viewport_not_applied",
                "requested": {"width": width, "height": height},
                "actual": {"width": actual_width, "height": actual_height},
            }
        return {"status": "success", "width": width, "height": height}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def assets_list(driver: TMWebDriver, switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp, page_assets
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        raw = cdp.evaluate(driver, tab_id, page_assets.collect_assets_script(), token=token)
        assets = page_assets.normalize_assets(raw if isinstance(raw, list) else [])
        return {"status": "success", "assets": assets, "count": len(assets)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def assets_export(driver: TMWebDriver, output: str = "", switch_tab_id: str = "", token: str | None = None) -> dict[str, Any]:
    from . import cdp, page_assets
    ctx, tab_id, error = _target_tab_for_interaction(driver, switch_tab_id, token=token)
    if error:
        return error
    try:
        raw = cdp.evaluate(driver, tab_id, page_assets.collect_assets_script(), token=token)
        assets = page_assets.normalize_assets(raw if isinstance(raw, list) else [])
        if not output:
            return {"status": "success", "assets": assets, "count": len(assets)}
        try:
            import zipfile
            from pathlib import Path
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("assets.json", json.dumps(assets, ensure_ascii=False, indent=2))
            return {"status": "success", "output": str(output_path), "count": len(assets)}
        except Exception as exc:
            return {"status": "error", "msg": str(exc)}
    finally:
        _schedule_tool_tab_close_if_needed(driver, ctx, tab_id, token=token)


def browser_list(driver: TMWebDriver, token: str | None = None) -> dict[str, Any]:
    return get_tabs(driver, token=token)


def browser_current(driver: TMWebDriver, token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    latest_tab_id = ctx.latest_session_id or ""
    session = ctx.sessions.get(latest_tab_id) if latest_tab_id else None
    current_tab = None
    if session and session.is_active():
        current_tab = {
            "tab_id": session.tab_id,
            "url": session.url,
            "title": session.info.get("title", ""),
            "id": session.id,
        }
    return {
        "status": "success",
        "session_name": ctx.session_name,
        "visibility": ctx.visibility_mode,
        "claimed_tabs": sorted(ctx.claimed_tabs),
        "latest_tab_id": latest_tab_id,
        "current_tab": current_tab,
    }


def browser_claim(driver: TMWebDriver, tab_id: str, token: str | None = None) -> dict[str, Any]:
    from . import session_commands
    ctx = driver.get_context(token)
    if tab_id == "current":
        session = ctx.sessions.get(ctx.latest_session_id or "")
        if not session or not session.is_active():
            return {"status": "error", "error": "No current browser tab. Make sure the extension is connected and an HTTP/HTTPS tab is open."}
        tab_id = ctx.latest_session_id
    resolved_tab_id, error = require_tab_id(driver, tab_id, token=token)
    if error:
        return {"status": "error", "error": error.get("msg", "Tab not found or ambiguous.")}
    return {"status": "success", **session_commands.claim_tab(ctx, resolved_tab_id)}


def browser_release(driver: TMWebDriver, tab_id: str, token: str | None = None) -> dict[str, Any]:
    from . import session_commands
    ctx = driver.get_context(token)
    if tab_id == "current":
        tab_id = ctx.latest_session_id or ""
    resolved_tab_id, error = require_tab_id(driver, tab_id, token=token)
    if error:
        return {"status": "error", "error": error.get("msg", "Tab not found or ambiguous.")}
    return {"status": "success", **session_commands.release_tab(ctx, resolved_tab_id)}


def history_search(driver: TMWebDriver, text: str = "", max_results: int = 20, start_time: float | None = None, end_time: float | None = None, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {
        "cmd": "history",
        "method": "search",
        "text": text,
        "maxResults": max_results,
        "startTime": start_time,
        "endTime": end_time,
    }, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "History search failed")
    if not ok:
        return {"status": "error", "msg": error}
    return {"status": "success", "items": data or []}


def _normalize_browser_api_result(result: Any, fallback: str) -> tuple[bool, Any, str]:
    """Accept both current envelopes and legacy extension bare-data responses."""
    if isinstance(result, dict) and result.get("ok") is True:
        return True, result.get("data"), ""
    if not isinstance(result, dict):
        return True, result, ""
    return False, None, result.get("error", fallback)


def bookmarks_tree(driver: TMWebDriver, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "bookmarks", "method": "getTree"}, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "Bookmarks tree failed")
    return {"status": "success", "tree": data or []} if ok else {"status": "error", "msg": error}


def downloads_search(driver: TMWebDriver, query: list[str] | None = None, download_id: str | None = None, limit: int = 20, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "downloads", "method": "search", "query": query or [], "id": download_id, "limit": limit}, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "Downloads search failed")
    return {"status": "success", "items": data or []} if ok else {"status": "error", "msg": error}


def downloads_open(driver: TMWebDriver, download_id: str, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "downloads", "method": "open", "id": download_id}, tab_id=tab_id, timeout=15, token=token)
    if not isinstance(result, dict) or result.get("ok") is not True:
        return {"status": "error", "msg": (result or {}).get("error", "Downloads open failed") if isinstance(result, dict) else "Downloads open failed"}
    return {"status": "success"}


def sessions_recently_closed(driver: TMWebDriver, max_results: int = 10, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "sessions", "method": "recentlyClosed", "maxResults": max_results}, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "Recently closed query failed")
    return {"status": "success", "items": data or []} if ok else {"status": "error", "msg": error}


def top_sites(driver: TMWebDriver, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "topSites", "method": "get"}, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "Top sites query failed")
    return {"status": "success", "items": data or []} if ok else {"status": "error", "msg": error}


def browser_extensions(driver: TMWebDriver, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    """List installed browser extensions without allowing state changes."""
    result = extension_command(driver, {"cmd": "management", "method": "list"}, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "Browser extension list failed")
    return {"status": "success", "items": data or []} if ok else {"status": "error", "msg": error}


def browser_content_settings(driver: TMWebDriver, setting_type: str = "automaticDownloads", url: str = "https://example.com/", tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "contentSettings", "method": "get", "type": setting_type, "url": url}, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "Browser content setting query failed")
    if not ok and isinstance(result, dict) and ("setting" in result or "incognitoSpecific" in result) and "error" not in result:
        ok, data, error = True, result, ""
    return {"status": "success", "type": setting_type, "url": url, "setting": data or {}} if ok else {"status": "error", "msg": error}


def browser_mouse_visual_state(driver: TMWebDriver, tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "mouseVisualState", "tabId": int(driver._raw_tab_id(tab_id, token=token)) if tab_id else None}, tab_id=tab_id, timeout=15, token=token)
    ok, data, error = _normalize_browser_api_result(result, "Mouse visual state query failed")
    if not ok and isinstance(result, dict) and "host" in result and "error" not in result:
        ok, data, error = True, result, ""
    return {"status": "success", "state": data or {}} if ok else {"status": "error", "msg": error, "extension_response": result}


def browser_notify(driver: TMWebDriver, title: str = "Omnibot", message: str = "", priority: int = 0, notification_id: str = "", tab_id: str | None = None, token: str | None = None) -> dict[str, Any]:
    result = extension_command(driver, {"cmd": "notifications", "method": "create", "id": notification_id, "title": title, "message": message, "priority": priority}, tab_id=tab_id, timeout=15, token=token)
    # Legacy workers return the notification object directly instead of the
    # `{ok: true, data: ...}` envelope used by current workers.
    if isinstance(result, dict) and result.get("ok") is not True and "id" in result and "error" not in result:
        return {"status": "success", "id": result.get("id", "")}
    ok, data, error = _normalize_browser_api_result(result, "Notification failed")
    if not ok:
        return {"status": "error", "msg": error}
    if isinstance(data, dict):
        data = data.get("id", "")
    return {"status": "success", "id": data or ""}


def session_name(driver: TMWebDriver, name: str, token: str | None = None) -> dict[str, Any]:
    from . import session_commands
    ctx = driver.get_context(token)
    return {"status": "success", **session_commands.name_session(ctx, name)}


def session_list(driver: TMWebDriver, token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    return {"status": "success", "session_name": ctx.session_name, "visibility": ctx.visibility_mode, "claimed_tabs": sorted(ctx.claimed_tabs), "trace_enabled": ctx.trace_enabled, "recording": ctx.recording}


def record_start(driver: TMWebDriver, token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    ctx.recording = True
    ctx.recorded_actions = []
    return {"status": "success", "recording": True}


def record_stop(driver: TMWebDriver, output: str = "", token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    ctx.recording = False
    actions_list = list(ctx.recorded_actions)
    if output:
        try:
            from pathlib import Path
            Path(output).write_text(json.dumps({"actions": actions_list}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            return {"status": "error", "msg": str(exc)}
    return {"status": "success", "recording": False, "actions": actions_list, "output": output}


def replay(driver: TMWebDriver, flow: list[dict] | None = None, token: str | None = None) -> dict[str, Any]:
    if not flow:
        return {"status": "error", "msg": "replay requires actions list"}

    # Recorded page actions contain the tab id from the original run. Map those
    # ids to tabs created during this replay so a flow is portable across runs.
    recorded_tab_ids: list[str] = []
    for item in flow:
        params = item.get("params", {}) if isinstance(item, dict) else {}
        for key in ("switch_tab_id", "tab_id"):
            value = params.get(key) if isinstance(params, dict) else None
            if value and str(value) not in recorded_tab_ids:
                recorded_tab_ids.append(str(value))
    tab_map: dict[str, str] = {}

    def rewrite(value: Any) -> Any:
        if isinstance(value, str):
            return tab_map.get(value, value)
        if isinstance(value, list):
            return [rewrite(item) for item in value]
        if isinstance(value, dict):
            return {key: rewrite(item) for key, item in value.items()}
        return value

    results = []
    for item in flow:
        action_name = item.get("action")
        params = rewrite(dict(item.get("params", {})))
        if token is not None:
            params["token"] = token
        func = {
            "snapshot": snapshot, "click": click, "dblclick": dblclick, "fill": fill,
            "type": type_text, "hover": hover, "navigate": navigate, "wait": wait,
            "get": get, "is": is_state, "find": find,
        }.get(action_name)
        if func:
            try:
                result = func(driver, **params)
            except Exception as exc:
                result = {"status": "error", "msg": str(exc)}
        else:
            result = {"status": "error", "msg": f"Unsupported replay action: {action_name}"}
        if action_name == "navigate" and params.get("new_tab", True) and isinstance(result, dict):
            created_tab = result.get("tab")
            new_tab_id = created_tab.get("id") if isinstance(created_tab, dict) else None
            if new_tab_id:
                for recorded_id in recorded_tab_ids:
                    if recorded_id not in tab_map:
                        tab_map[recorded_id] = str(new_tab_id)
                        break
        results.append({"action": action_name, "result": result})
    return {"status": "success", "results": results}


def trace_start(driver: TMWebDriver, token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    ctx.trace_enabled = True
    ctx.trace_events = []
    return {"status": "success", "trace_enabled": True}


def trace_stop(driver: TMWebDriver, output: str = "", token: str | None = None) -> dict[str, Any]:
    ctx = driver.get_context(token)
    ctx.trace_enabled = False
    events = list(ctx.trace_events)
    if output:
        try:
            from pathlib import Path
            import zipfile
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.suffix == ".zip":
                with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("trace.json", json.dumps({"events": events}, ensure_ascii=False, indent=2))
            else:
                output_path.write_text(json.dumps({"events": events}, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            return {"status": "error", "msg": str(exc)}
    return {"status": "success", "trace_enabled": False, "events": events, "output": output}


def visibility_status(driver: TMWebDriver, token: str | None = None) -> dict[str, Any]:
    from . import visibility as vis_mod
    ctx = driver.get_context(token)
    return {"status": "success", "visibility": vis_mod.mode_capabilities(ctx.visibility_mode)}


def visibility_set(driver: TMWebDriver, mode: str, token: str | None = None) -> dict[str, Any]:
    from . import visibility as vis_mod
    ctx = driver.get_context(token)
    normalized = vis_mod.normalize_mode(mode)
    ctx.visibility_mode = normalized
    return {"status": "success", "visibility": vis_mod.mode_capabilities(normalized)}


def visibility_launch(driver: TMWebDriver, mode: str, browser: str = "chrome", user_data_dir: str = "", remote_debugging_port: int = 9222, token: str | None = None) -> dict[str, Any]:
    from . import visibility as vis_mod
    normalized = vis_mod.normalize_mode(mode)
    if normalized not in {"dedicated-profile", "headless"}:
        return {"status": "error", "msg": "visibility launch only supports dedicated-profile or headless"}
    if not user_data_dir:
        return {"status": "error", "msg": "visibility launch requires --user-data-dir"}
    return {"status": "planned", "visibility": vis_mod.mode_capabilities(normalized), "browser": browser, "user_data_dir": user_data_dir, "remote_debugging_port": remote_debugging_port}
