from __future__ import annotations

import json

MARK = "data-omnibot-located"
TEXT_OFFSET = "data-omnibot-text-offset"
TEXT_LENGTH = "data-omnibot-text-length"


def text_match_expression(value: str, exact: bool) -> str:
    target = json.dumps(value)
    if exact:
        return f"(el.textContent || '').trim() === {target} || (el.getAttribute('aria-label') || '') === {target}"
    return f"(el.textContent || '').includes({target}) || (el.getAttribute('aria-label') || '').includes({target})"


def clear_marker_statement() -> str:
    return f"document.querySelectorAll('[{MARK}]').forEach(el => {{ el.removeAttribute('{MARK}'); el.removeAttribute('{TEXT_OFFSET}'); el.removeAttribute('{TEXT_LENGTH}'); }});"


def locator_script(strategy: str, value: str, *, name: str | None = None, exact: bool = False) -> str:
    encoded = json.dumps(value)
    clear = clear_marker_statement()
    if strategy == "role":
        role_selector = f"[role=\"{value}\"],{value}"
        match = "true" if name is None else text_match_expression(name, exact)
        return f"""
(() => {{
  {clear}
  for (const el of document.querySelectorAll({json.dumps(role_selector)})) {{
    if ({match}) {{ el.setAttribute('{MARK}', 'true'); return true; }}
  }}
  return false;
}})()
"""
    if strategy == "label":
        match = text_match_expression(value, exact)
        return f"""
(() => {{
  {clear}
  for (const el of document.querySelectorAll('label')) {{
    if ({match}) {{
      const forId = el.getAttribute('for');
      const target = forId ? document.getElementById(forId) : el.querySelector('input,textarea,select,button');
      if (target) {{ target.setAttribute('{MARK}', 'true'); return true; }}
    }}
  }}
  return false;
}})()
"""
    selector_by_strategy = {
        "placeholder": f"input[placeholder={encoded}],textarea[placeholder={encoded}]",
        "alt": f"[alt={encoded}]",
        "title": f"[title={encoded}]",
        "testid": f"[data-testid={encoded}]",
    }
    if strategy in selector_by_strategy:
        return f"""
(() => {{
  {clear}
  const el = document.querySelector({json.dumps(selector_by_strategy[strategy])});
  if (!el) return false;
  el.setAttribute('{MARK}', 'true');
  return true;
}})()
"""
    if strategy == "text":
        target = json.dumps(value)
        exact_js = "true" if exact else "false"
        return f"""
(() => {{
  {clear}
  const target = {target};
  const exact = {exact_js};
  const selector = 'a,button,input,textarea,select,[role],p,li,h1,h2,h3,h4,h5,h6,blockquote,pre,span,div,[contenteditable="true"]';
  function visible(el) {{
    if (!el || !el.getBoundingClientRect) return false;
    const style = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
  }}
  function matchesText(text) {{
    const value = (text || '');
    return exact ? value.trim() === target : value.includes(target);
  }}
  function closestMatchContainer(textNode) {{
    const direct = textNode.parentElement;
    if (!direct) return null;
    let candidate = direct.closest(selector) || direct;
    while (candidate && !visible(candidate)) candidate = candidate.parentElement;
    if (!candidate) return null;
    for (const other of Array.from(candidate.querySelectorAll(selector))) {{
      if (other !== candidate && other.contains(direct) && matchesText(other.textContent || '') && visible(other)) {{
        candidate = other;
      }}
    }}
    return candidate;
  }}
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT, {{
    acceptNode(node) {{
      if (!matchesText(node.nodeValue || '')) return NodeFilter.FILTER_REJECT;
      const parent = node.parentElement;
      if (!parent || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE'].includes(parent.tagName)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }}
  }});
  let textNode = walker.nextNode();
  while (textNode) {{
    const candidate = closestMatchContainer(textNode);
    if (candidate) {{
      const localOffset = Math.max(0, (textNode.nodeValue || '').indexOf(target));
      const before = document.createRange();
      before.setStart(candidate, 0);
      before.setEnd(textNode, localOffset);
      candidate.setAttribute('{MARK}', 'true');
      candidate.setAttribute('{TEXT_OFFSET}', String(before.toString().length));
      candidate.setAttribute('{TEXT_LENGTH}', String(target.length));
      return true;
    }}
    textNode = walker.nextNode();
  }}
  for (const el of document.querySelectorAll('a,button,input,textarea,select,[role]')) {{
    if (matchesText(el.getAttribute('aria-label') || '')) {{ el.setAttribute('{MARK}', 'true'); return true; }}
  }}
  return false;
}})()
"""
    match = text_match_expression(value, exact)
    return f"""
(() => {{
  {clear}
  for (const el of document.querySelectorAll('a,button,input,textarea,select,[role],span,div')) {{
    if ({match}) {{ el.setAttribute('{MARK}', 'true'); return true; }}
  }}
  return false;
}})()
"""


def nth_script(selector: str, index: int) -> str:
    return f"""
(() => {{
  {clear_marker_statement()}
  const els = document.querySelectorAll({json.dumps(selector)});
  const idx = {index};
  const actual = idx < 0 ? els.length + idx : idx;
  if (actual < 0 || actual >= els.length) return false;
  els[actual].setAttribute('{MARK}', 'true');
  return true;
}})()
"""


def located_selector() -> str:
    return f"[{MARK}='true']"
