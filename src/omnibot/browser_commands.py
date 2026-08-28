from __future__ import annotations

import json
from typing import Any


def element_expression(selector: str) -> str:
    return f"document.querySelector({json.dumps(selector)})"


def get_script(kind: str, selector: str | None = None, attr: str | None = None) -> str:
    if kind == "title":
        return "document.title"
    if kind == "url":
        return "location.href"
    if selector is None:
        raise ValueError(f"get {kind} requires a selector")
    el = element_expression(selector)
    missing = "({__omnibotElementError: true, reason: 'element_not_found'})"
    if kind == "text":
        return f"(() => {{ const el = {el}; return el ? el.textContent : {missing}; }})()"
    if kind == "html":
        return f"(() => {{ const el = {el}; return el ? el.innerHTML : {missing}; }})()"
    if kind == "value":
        return f"(() => {{ const el = {el}; return el ? el.value : {missing}; }})()"
    if kind == "attr":
        return f"(() => {{ const el = {el}; return el ? el.getAttribute({json.dumps(attr or '')}) : {missing}; }})()"
    if kind == "count":
        return f"document.querySelectorAll({json.dumps(selector)}).length"
    if kind == "box":
        return f"(() => {{ const el = {el}; if (!el) return {missing}; const r = el.getBoundingClientRect(); return {{x:r.left,y:r.top,width:r.width,height:r.height}}; }})()"
    if kind == "styles":
        return f"(() => {{ const el = {el}; if (!el) return {missing}; const s = getComputedStyle(el); return {{display:s.display,visibility:s.visibility,opacity:s.opacity,position:s.position,zIndex:s.zIndex}}; }})()"
    raise ValueError(f"Unsupported get kind: {kind}")


def is_script(kind: str, selector: str) -> str:
    el = element_expression(selector)
    if kind == "visible":
        return f"(() => {{ const el = {el}; if (!el) return false; const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && Number(s.opacity) !== 0; }})()"
    if kind == "hidden":
        return f"(() => {{ const el = {el}; if (!el) return false; const r = el.getBoundingClientRect(); const s = getComputedStyle(el); return r.width === 0 || r.height === 0 || s.visibility === 'hidden' || s.display === 'none' || Number(s.opacity) === 0; }})()"
    if kind == "enabled":
        return f"(() => {{ const el = {el}; return Boolean(el && !el.disabled && el.getAttribute('aria-disabled') !== 'true'); }})()"
    if kind == "checked":
        return f"(() => {{ const el = {el}; return Boolean(el && el.checked); }})()"
    raise ValueError(f"Unsupported is kind: {kind}")


def wait_condition_script(*, target: str | None, text: str | None, url: str | None, load: str | None, fn: str | None, state: str) -> str:
    if fn:
        return f"Boolean({fn})"
    if text:
        return f"document.body && document.body.innerText.includes({json.dumps(text)})"
    if url:
        pattern = url.replace("**", "")
        return f"location.href.includes({json.dumps(pattern)})"
    if load:
        if load == "domcontentloaded":
            return "document.readyState === 'interactive' || document.readyState === 'complete'"
        return "document.readyState === 'complete'"
    if target and target.isdigit():
        return "true"
    if target:
        visible = is_script("visible", target)
        if state == "hidden":
            return f"Boolean(document.querySelector({json.dumps(target)}) && !({visible}))"
        return visible
    return "true"


def looks_like_js_condition(value: str) -> bool:
    return any(marker in value for marker in ["window.", "document.", "=>", "return", "(", ";"])


def assign_tab_alias(ctx: Any, tab_id: str, label: str | None = None) -> str:
    if label:
        if label in ctx.tab_aliases and ctx.tab_aliases[label] != tab_id:
            raise ValueError(f"Tab label already exists: {label}")
        ctx.tab_aliases[label] = tab_id
        return label
    for existing, existing_tab_id in ctx.tab_aliases.items():
        if existing_tab_id == tab_id and existing.startswith("t"):
            return existing
    alias = f"t{ctx.next_tab_alias_number}"
    ctx.next_tab_alias_number += 1
    ctx.tab_aliases[alias] = tab_id
    return alias


def resolve_tab_alias(ctx: Any, value: str) -> str:
    return ctx.tab_aliases.get(value, value)


def viewport_get_script() -> str:
    return "({width: window.innerWidth, height: window.innerHeight, deviceScaleFactor: window.devicePixelRatio})"
