from __future__ import annotations

from typing import Any

from .refs import RefMap


INTERACTIVE_ROLES = {
    "button", "link", "textbox", "checkbox", "radio", "combobox", "listbox",
    "menuitem", "menuitemcheckbox", "menuitemradio", "option", "searchbox",
    "slider", "spinbutton", "switch", "tab", "treeitem", "Iframe",
}

CONTENT_ROLES = {"heading", "cell", "gridcell", "columnheader", "rowheader", "listitem", "article", "region", "main", "navigation"}

# Visual containers are screenshot targets. Interactive controls remain
# interaction refs and are not classified as visual regions.
VISUAL_REGION_ROLES = {
    "article", "region", "dialog", "alertdialog", "listitem", "figure",
    "image", "img", "video", "Video", "canvas", "table",
}

STRUCTURAL_ROLES = {"generic", "group", "list", "table", "row", "rowgroup", "grid", "treegrid", "menu", "menubar", "toolbar", "tablist", "tree", "directory", "document", "application", "presentation", "none", "WebArea", "RootWebArea"}


def ax_value(value: dict[str, Any] | None) -> str:
    raw = (value or {}).get("value")
    if raw is None:
        return ""
    return str(raw)


def ax_bool(value: dict[str, Any] | None) -> bool | None:
    raw = (value or {}).get("value")
    return raw if isinstance(raw, bool) else None


def node_property(node: dict[str, Any], name: str) -> dict[str, Any] | None:
    for prop in node.get("properties", []) or []:
        if prop.get("name") == name:
            return prop.get("value")
    return None


def should_include(role: str, name: str, interactive: bool, compact: bool) -> bool:
    if interactive:
        return role in INTERACTIVE_ROLES or role in VISUAL_REGION_ROLES
    if role in INTERACTIVE_ROLES or role in CONTENT_ROLES:
        return True
    if compact and role in STRUCTURAL_ROLES and not name:
        return False
    return bool(name and role not in {"none", "presentation"})


def format_ax_snapshot(
    ax_tree: dict[str, Any],
    *,
    tab_id: str | int,
    ref_map: RefMap,
    interactive: bool,
    compact: bool,
    max_depth: int | None,
    include_urls: bool,
    input_types: dict[int, str] | None = None,
) -> tuple[str, dict[str, dict[str, Any]]]:
    ref_map.clear_tab(tab_id)
    nodes = ax_tree.get("nodes", []) or []
    by_id = {str(node.get("nodeId")): node for node in nodes}
    parent: dict[str, str] = {}
    for node in nodes:
        for child_id in node.get("childIds", []) or []:
            parent[str(child_id)] = str(node.get("nodeId"))
    roots = [node for node in nodes if str(node.get("nodeId")) not in parent]
    lines: list[str] = []
    duplicate_counts: dict[tuple[str, str], int] = {}

    def walk(node: dict[str, Any], depth: int) -> None:
        if max_depth is not None and depth > max_depth:
            return
        role = ax_value(node.get("role"))
        name = ax_value(node.get("name"))
        include = False if node.get("ignored") is True else should_include(role, name, interactive, compact)
        rendered_depth = depth
        if include:
            key = (role, name)
            nth = duplicate_counts.get(key, 0)
            duplicate_counts[key] = nth + 1
            backend_node_id = node.get("backendDOMNodeId")
            kind = "visual" if role in VISUAL_REGION_ROLES else None
            input_type = (input_types or {}).get(int(backend_node_id)) if backend_node_id is not None else None
            ref_id = ref_map.add(
                tab_id,
                role=role,
                name=name,
                backend_node_id=backend_node_id,
                nth=nth,
                kind=kind,
                input_type=input_type,
            )
            attrs = []
            if input_type:
                attrs.append(f"type={input_type}")
            level = ax_value(node_property(node, "level"))
            if level:
                attrs.append(f"level={level}")
            required = ax_bool(node_property(node, "required"))
            if required is True:
                attrs.append("required=true")
            disabled = ax_bool(node_property(node, "disabled"))
            if disabled is True:
                attrs.append("disabled=true")
            checked = ax_value(node_property(node, "checked"))
            if checked:
                attrs.append(f"checked={checked}")
            url = ax_value(node_property(node, "url"))
            if include_urls and url:
                attrs.append(f"url={url}")
            if kind == "visual":
                attrs.append("visual=true")
            suffix = " " + " ".join(f"[{attr}]" for attr in attrs) if attrs else ""
            quoted = f' "{name}"' if name else ""
            lines.append(f"{'  ' * rendered_depth}@{ref_id} [{role}]{quoted}{suffix}")
        for child_id in node.get("childIds", []) or []:
            child = by_id.get(str(child_id))
            if child:
                walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    return "\n".join(lines), ref_map.as_json(tab_id)


def _popup_bool(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def _popup_box(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        width = float(value.get("width") or 0)
        height = float(value.get("height") or 0)
        if width <= 0 or height <= 0:
            return None
        return {"x": float(value.get("x") or 0), "y": float(value.get("y") or 0), "width": width, "height": height}
    except (TypeError, ValueError):
        return None


def append_dom_popup_controls(
    text: str,
    refs_json: dict[str, dict[str, Any]],
    popup_controls: list[dict[str, Any]],
    *,
    tab_id: str | int,
    ref_map: RefMap,
) -> tuple[str, dict[str, dict[str, Any]]]:
    existing_backend_ids = {entry.backend_node_id for entry in ref_map.entries(tab_id) if entry.backend_node_id is not None}
    lines: list[str] = []
    for control in popup_controls:
        backend_node_id = control.get("backendNodeId")
        if backend_node_id in existing_backend_ids:
            continue
        role = str(control.get("role") or "generic")
        name = str(control.get("name") or "")
        selector = str(control.get("selector") or "") or None
        opener_selector = str(control.get("openerSelector") or "") or None
        box = _popup_box(control.get("box"))
        ref_id = ref_map.add(tab_id, role=role, name=name, backend_node_id=backend_node_id, selector=selector, box=box, opener_selector=opener_selector)
        item: dict[str, Any] = {"role": role, "name": name}
        if box is not None:
            item["box"] = box
        if opener_selector is not None:
            item["openerSelector"] = opener_selector
        refs_json[ref_id] = item
        suffix = " [disabled=true]" if _popup_bool(control.get("disabled")) else ""
        quoted = f' "{name}"' if name else ""
        lines.append(f"  @{ref_id} [{role}]{quoted}{suffix}")
    if not lines:
        return text, refs_json
    prefix = "\n" if text else ""
    return f"{text}{prefix}# DOM Popup Controls\n" + "\n".join(lines), refs_json


def append_dom_richtext_controls(
    text: str,
    refs_json: dict[str, dict[str, Any]],
    richtext_controls: list[dict[str, Any]],
    *,
    tab_id: str | int,
    ref_map: RefMap,
) -> tuple[str, dict[str, dict[str, Any]]]:
    existing_backend_ids = {entry.backend_node_id for entry in ref_map.entries(tab_id) if entry.backend_node_id is not None}
    lines: list[str] = []
    for control in richtext_controls:
        backend_node_id = control.get("backendNodeId")
        if backend_node_id in existing_backend_ids:
            continue
        role = "richtext"
        name = str(control.get("name") or "")
        selector = str(control.get("selector") or "") or None
        box = _popup_box(control.get("box"))
        contenteditable = _popup_bool(control.get("contenteditable"))
        ref_id = ref_map.add(
            tab_id,
            role=role,
            name=name,
            backend_node_id=backend_node_id,
            selector=selector,
            box=box,
            kind="richtext",
            contenteditable=contenteditable,
        )
        item: dict[str, Any] = {"role": role, "name": name, "kind": "richtext", "contenteditable": contenteditable}
        if box is not None:
            item["box"] = box
        refs_json[ref_id] = item
        attrs = []
        if contenteditable:
            attrs.append("contenteditable=true")
        suffix = " " + " ".join(f"[{attr}]" for attr in attrs) if attrs else ""
        quoted = f' "{name}"' if name else ""
        lines.append(f"  @{ref_id} [{role}]{quoted}{suffix}")
    if not lines:
        return text, refs_json
    prefix = "\n" if text else ""
    return f"{text}{prefix}# DOM Rich Text Editors\n" + "\n".join(lines), refs_json


def resolve_selector_backend_node(driver, tab_id: str | int, selector: str, *, token: str | None = None) -> int:
    from . import cdp

    expression = f"document.querySelector({selector!r})"
    result = cdp.send_cdp(driver, tab_id, "Runtime.evaluate", {"expression": expression, "returnByValue": False}, token=token)
    object_id = result.get("result", {}).get("objectId")
    if not object_id:
        raise RuntimeError(f"Selector {selector!r} did not match any element")
    described = cdp.send_cdp(driver, tab_id, "DOM.describeNode", {"objectId": object_id}, token=token)
    backend_node_id = described.get("node", {}).get("backendNodeId")
    if not backend_node_id:
        raise RuntimeError(f"Selector {selector!r} did not resolve to a backend node")
    return int(backend_node_id)


def collect_interaction_metadata(driver, tab_id: str | int, *, token: str | None = None, limit: int = 80) -> dict[str, Any]:
    from . import cdp

    expression = f"""
(() => {{
  const candidates = Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"],[role="link"],[onclick],[tabindex]')).slice(0, {int(limit)});
  return candidates.map((el, index) => {{
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const label = el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || el.title || '';
    return {{
      index,
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      type: el.getAttribute('type') || '',
      label: String(label).trim().slice(0, 120),
      visible: rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none',
      box: {{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }}
    }};
  }}).filter(item => item.visible);
}})()
"""
    try:
        data = cdp.evaluate(driver, tab_id, expression, token=token)
        return {"elements": data if isinstance(data, list) else []}
    except Exception as exc:
        return {"elements": [], "warning": str(exc)}


def annotation_overlay_script(refs: dict[str, dict[str, Any]]) -> str:
    import json as _json

    items = []
    for ref_id, item in refs.items():
        box = item.get("box")
        if not box:
            continue
        items.append({"number": int(ref_id[1:]), "ref": ref_id, "box": box})
    return f"""
(() => {{
  const old = document.getElementById('__omnibot_annotations__');
  if (old) old.remove();
  const host = document.createElement('div');
  host.id = '__omnibot_annotations__';
  host.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647;font-family:Arial,sans-serif';
  const items = {_json.dumps(items)};
  for (const item of items) {{
    const box = item.box;
    const label = document.createElement('div');
    label.textContent = String(item.number);
    label.style.cssText = `position:absolute;left:${{box.x}}px;top:${{box.y}}px;background:#f97316;color:white;border:2px solid white;border-radius:999px;padding:1px 6px;font-size:12px;font-weight:700;box-shadow:0 1px 4px rgba(0,0,0,.4)`;
    host.appendChild(label);
  }}
  document.documentElement.appendChild(host);
  return true;
}})()
"""


def remove_annotation_overlay_script() -> str:
    return "document.getElementById('__omnibot_annotations__')?.remove(); true"


def dom_richtext_controls_script(limit: int = 20) -> str:
    limit = max(1, min(int(limit), 50))
    return f"""
(() => {{
  const limit = {limit};
  const editorSelector = [
    '[contenteditable="true"]',
    '[role="textbox"][aria-multiline="true"]',
    '.ProseMirror',
    '.ql-editor',
    '.public-DraftEditor-content',
    '[data-slate-editor="true"]',
    '[class*="editor" i][contenteditable]',
    '[class*="rich" i][contenteditable]'
  ].join(',');
  const titleRe = /标题|title/i;
  const bodyPlaceholderRe = /请输入正文|正文|写正文|内容|article body|body/i;
  const isVisible = (el) => {{
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 &&
      rect.width > 0 && rect.height > 0 && rect.right >= 0 && rect.bottom >= 0 && rect.left <= innerWidth && rect.top <= innerHeight;
  }};
  const cssPath = (el) => {{
    if (el.id && !/^[:\\d]/.test(el.id)) return `#${{CSS.escape(el.id)}}`;
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && node !== document.documentElement; node = node.parentElement) {{
      const tag = node.tagName.toLowerCase();
      const siblings = Array.from(node.parentElement ? node.parentElement.children : []).filter((sibling) => sibling.tagName === node.tagName);
      const nth = siblings.length > 1 ? `:nth-of-type(${{siblings.indexOf(node) + 1}})` : '';
      parts.unshift(`${{tag}}${{nth}}`);
    }}
    return `html > ${{parts.join(' > ')}}`;
  }};
  const label = (el) => {{
    const aria = el.getAttribute('aria-label') || el.getAttribute('data-placeholder') || el.getAttribute('placeholder') || el.getAttribute('title') || '';
    const text = (el.innerText || el.textContent || '').trim();
    const before = getComputedStyle(el, '::before').content || '';
    const cleanedBefore = before.replace(/^['"]|['"]$/g, '');
    return String(aria || text || cleanedBefore || '富文本编辑器').trim().slice(0, 120);
  }};
  const controls = [];
  const seen = new Set();
  for (const el of Array.from(document.querySelectorAll(editorSelector))) {{
    if (controls.length >= limit) break;
    if (!isVisible(el)) continue;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') continue;
    const name = label(el);
    const contextText = `${{name}} ${{el.id || ''}} ${{el.className || ''}} ${{el.getAttribute('aria-label') || ''}}`;
    if (titleRe.test(contextText) && !bodyPlaceholderRe.test(contextText)) continue;
    const rect = el.getBoundingClientRect();
    if (rect.height < 40 && !bodyPlaceholderRe.test(contextText)) continue;
    const selector = cssPath(el);
    if (seen.has(selector)) continue;
    seen.add(selector);
    controls.push({{
      role: 'richtext',
      kind: 'richtext',
      name,
      selector,
      contenteditable: el.isContentEditable || el.getAttribute('contenteditable') === 'true',
      box: {{x: rect.left, y: rect.top, width: rect.width, height: rect.height}}
    }});
  }}
  return controls;
}})()
"""


def dom_popup_controls_script(limit: int = 50) -> str:
    limit = max(1, min(int(limit), 100))
    return f"""
(() => {{
  const limit = {limit};
  const keywordRe = /modal|dialog|popup|popover|drawer|overlay|mask|portal/i;
  const candidateSelectors = [
    '[role="dialog"]', '[role="alertdialog"]', 'dialog[open]', '[popover]',
    '[role="listbox"]', '[role="menu"]', '[role="tree"]', '[role="grid"]',
    '[aria-expanded="true"]',
    '[class*="modal" i]', '[class*="dialog" i]', '[class*="popup" i]', '[class*="popover" i]',
    '[class*="drawer" i]', '[class*="overlay" i]', '[class*="mask" i]', '[class*="portal" i]',
    '[id*="modal" i]', '[id*="dialog" i]', '[id*="popup" i]', '[id*="popover" i]',
    '[aria-modal="true"]'
  ];
  const controlSelector = 'button,a[href],input,textarea,select,[role],[contenteditable="true"],[tabindex]:not([tabindex="-1"])';
  const isVisible = (el) => {{
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style && style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 &&
      rect.width > 0 && rect.height > 0 && rect.right >= 0 && rect.bottom >= 0 && rect.left <= innerWidth && rect.top <= innerHeight;
  }};
  const cssPath = (el) => {{
    if (el.id && !/^[:\\d]/.test(el.id)) return `#${{CSS.escape(el.id)}}`;
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && node !== document.documentElement; node = node.parentElement) {{
      const tag = node.tagName.toLowerCase();
      const siblings = Array.from(node.parentElement ? node.parentElement.children : []).filter((sibling) => sibling.tagName === node.tagName);
      const nth = siblings.length > 1 ? `:nth-of-type(${{siblings.indexOf(node) + 1}})` : '';
      parts.unshift(`${{tag}}${{nth}}`);
    }}
    return `html > ${{parts.join(' > ')}}`;
  }};
  const visibleExpandedComboboxes = () => Array.from(document.querySelectorAll('[role="combobox"][aria-expanded="true"], [aria-haspopup][aria-expanded="true"]')).filter(isVisible);
  const findOpenerSelector = (el) => {{
    const popup = el.closest('[role="listbox"], [role="menu"], [role="tree"], [role="grid"]') || el;
    const popupId = popup.getAttribute('id') || '';
    if (popupId) {{
      const controlled = visibleExpandedComboboxes().find((combo) => (combo.getAttribute('aria-controls') || '') === popupId);
      if (controlled) return cssPath(controlled);
    }}
    const rect = popup.getBoundingClientRect();
    let best = null;
    let bestScore = Infinity;
    for (const combo of visibleExpandedComboboxes()) {{
      const comboRect = combo.getBoundingClientRect();
      const xOverlap = Math.max(0, Math.min(rect.right, comboRect.right) - Math.max(rect.left, comboRect.left));
      const yGap = Math.min(Math.abs(rect.top - comboRect.bottom), Math.abs(comboRect.top - rect.bottom));
      const score = yGap - xOverlap;
      if (score < bestScore) {{ best = combo; bestScore = score; }}
    }}
    return best ? cssPath(best) : '';
  }};
  const candidates = new Set();
  for (const selector of candidateSelectors) {{
    try {{ document.querySelectorAll(selector).forEach((el) => candidates.add(el)); }} catch (_) {{}}
  }}
  Array.from(document.body ? document.body.children : []).slice(-12).forEach((el) => {{
    const text = `${{el.className || ''}} ${{el.id || ''}} ${{el.getAttribute('aria-label') || ''}}`;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const position = style.position;
    const zIndex = parseInt(style.zIndex || '0', 10) || 0;
    const largeFixed = (position === 'fixed' || position === 'sticky') && (zIndex >= 10 || rect.width * rect.height > innerWidth * innerHeight * 0.08);
    if (keywordRe.test(text) || largeFixed) candidates.add(el);
  }});
  const controls = [];
  const seen = new Set();
  for (const candidate of candidates) {{
    if (!isVisible(candidate)) continue;
    const nodes = Array.from(candidate.matches(controlSelector) ? [candidate] : []).concat(Array.from(candidate.querySelectorAll(controlSelector)));
    if (!nodes.length && !(candidate.innerText || candidate.textContent || '').trim()) continue;
    for (const el of nodes) {{
      if (controls.length >= limit) break;
      if (!isVisible(el)) continue;
      const transientAncestor = el.closest('[role="listbox"], [role="menu"], [role="tree"], [role="grid"], [role="dialog"], [role="alertdialog"], dialog[open], [popover]');
      if ((el.getAttribute('role') === 'option' || el.getAttribute('role') === 'menuitem') && !transientAncestor) continue;
      const selector = cssPath(el);
      if (seen.has(selector)) continue;
      seen.add(selector);
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute('role') || (tag === 'a' ? 'link' : tag === 'input' || tag === 'textarea' ? 'textbox' : tag === 'button' ? 'button' : tag);
      const name = (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.innerText || el.textContent || el.value || '').trim().slice(0, 120);
      const rect = el.getBoundingClientRect();
      const openerSelector = ['option', 'menuitem', 'listbox', 'menu', 'treeitem'].includes(role) ? findOpenerSelector(el) : '';
      controls.push({{
        role, name, selector,
        openerSelector,
        disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
        checked: Boolean(el.checked || el.getAttribute('aria-checked') === 'true'),
        box: {{x: rect.left, y: rect.top, width: rect.width, height: rect.height}}
      }});
    }}
  }}
  return controls;
}})()
"""


def dom_combobox_options_script(limit: int = 8) -> str:
    limit = max(0, min(int(limit), 20))
    return f"""
// dom_combobox_options
(async () => {{
  const limit = {limit};
  const controlSelector = '[role="combobox"], select, [aria-haspopup][aria-expanded]';
  const optionSelector = '[role="option"], [role="menuitem"]';
  const isVisible = (el) => {{
    if (!el) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 &&
      rect.width > 0 && rect.height > 0 && rect.right >= 0 && rect.bottom >= 0 && rect.left <= innerWidth && rect.top <= innerHeight;
  }};
  const isProbeSafeOpener = (el) => {{
    const tag = el.tagName.toLowerCase();
    const role = (el.getAttribute('role') || '').toLowerCase();
    const hasPopup = (el.getAttribute('aria-haspopup') || '').toLowerCase();
    if (tag === 'select') return true;
    if (role === 'combobox') return true;
    if (['listbox', 'tree', 'grid'].includes(hasPopup)) return true;
    return false;
  }};
  const cssPath = (el) => {{
    if (el.id && !/^[:\\d]/.test(el.id)) return `#${{CSS.escape(el.id)}}`;
    const parts = [];
    for (let node = el; node && node.nodeType === 1 && node !== document.documentElement; node = node.parentElement) {{
      const tag = node.tagName.toLowerCase();
      const siblings = Array.from(node.parentElement ? node.parentElement.children : []).filter((sibling) => sibling.tagName === node.tagName);
      const nth = siblings.length > 1 ? `:nth-of-type(${{siblings.indexOf(node) + 1}})` : '';
      parts.unshift(`${{tag}}${{nth}}`);
    }}
    return `html > ${{parts.join(' > ')}}`;
  }};
  const label = (el) => (el.getAttribute('aria-label') || el.getAttribute('placeholder') || el.innerText || el.textContent || el.value || '').trim().slice(0, 120);
  const frame = () => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)));
  const activateOpener = (opener) => {{
    const rect = opener.getBoundingClientRect();
    const x = rect.left + rect.width / 2;
    const y = rect.top + rect.height / 2;
    const down = {{bubbles: true, cancelable: true, view: window, clientX: x, clientY: y, button: 0, buttons: 1}};
    const up = {{...down, buttons: 0}};
    opener.dispatchEvent(new MouseEvent('mousedown', down));
    opener.dispatchEvent(new MouseEvent('mouseup', up));
    opener.dispatchEvent(new MouseEvent('click', up));
  }};
  const closeCombobox = (opener) => {{
    if (opener.getAttribute('aria-expanded') === 'true') opener.click();
  }};
  const dismissComboboxWithinOwner = async (opener) => {{
    closeCombobox(opener);
    await frame();
    const owner = opener.closest('[role="dialog"], [role="alertdialog"], dialog[open]') || opener.parentElement;
    if (!owner) return;
    const previousTabindex = owner.getAttribute('tabindex');
    owner.setAttribute('tabindex', '-1');
    owner.focus({{preventScroll: true}});
    if (previousTabindex === null) owner.removeAttribute('tabindex');
    else owner.setAttribute('tabindex', previousTabindex);
    await frame();
  }};
  const openCombobox = async (opener) => {{
    activateOpener(opener);
    await frame();
  }};
  const optionIdentity = (el) => `${{cssPath(el)}}::${{label(el)}}`;
  const visibleOptionSet = () => new Set(Array.from(document.querySelectorAll(optionSelector)).filter(isVisible).map(optionIdentity));
  const candidates = Array.from(document.querySelectorAll(controlSelector)).filter(isVisible).filter(isProbeSafeOpener).slice(0, limit);
  const activeBefore = document.activeElement;
  const controls = [];
  const seen = new Set();
  for (const opener of candidates) {{
    const openerSelector = cssPath(opener);
    try {{
      const beforeOptions = visibleOptionSet();
      await openCombobox(opener);
      const afterOptions = Array.from(document.querySelectorAll(optionSelector)).filter(isVisible);
      const newOptions = afterOptions.filter((option) => !beforeOptions.has(optionIdentity(option)) || opener.getAttribute('aria-expanded') === 'true');
      for (const option of newOptions) {{
        const name = label(option);
        if (!name) continue;
        const selector = cssPath(option);
        const key = `${{openerSelector}}::${{name}}::${{selector}}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const role = option.getAttribute('role') || 'option';
        const rect = option.getBoundingClientRect();
        controls.push({{
          role, name, selector, openerSelector,
          disabled: option.getAttribute('aria-disabled') === 'true',
          checked: option.getAttribute('aria-selected') === 'true' || option.getAttribute('aria-checked') === 'true',
          box: {{x: rect.left, y: rect.top, width: rect.width, height: rect.height}}
        }});
      }}
    }} catch (_)
    {{}} finally {{
      try {{ await dismissComboboxWithinOwner(opener); }} catch (_)
      {{}}
    }}
  }}
  try {{
    if (activeBefore && activeBefore.isConnected && typeof activeBefore.focus === 'function') activeBefore.focus({{preventScroll: true}});
  }} catch (_) {{}}
  return controls;
}})()
"""
