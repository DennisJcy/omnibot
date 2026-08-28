from __future__ import annotations

import json

NODE_ATTR = "data-omnibot-node-id"


def node_selector(node_id: str) -> str:
    return f"[{NODE_ATTR}={json.dumps(node_id)}]".replace('"', "'")


def visible_dom_script(limit: int = 200) -> str:
    return f"""
(() => {{
  const selector = 'a,button,input,textarea,select,[role="button"],[role="link"],[onclick],[tabindex]';
  const nodes = [];
  let index = 1;
  for (const el of Array.from(document.querySelectorAll(selector)).slice(0, {int(limit)})) {{
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    if (rect.width <= 0 || rect.height <= 0 || style.visibility === 'hidden' || style.display === 'none') continue;
    const id = `n${{index++}}`;
    el.setAttribute('{NODE_ATTR}', id);
    nodes.push({{node_id:id, tag:el.tagName.toLowerCase(), role:el.getAttribute('role') || '', text:(el.innerText || el.value || el.placeholder || el.ariaLabel || '').trim().slice(0,120), box:{{x:rect.left,y:rect.top,width:rect.width,height:rect.height}}}});
  }}
  return nodes;
}})()
"""
