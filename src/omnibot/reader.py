from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse


def _clean_text(value: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", value or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _normalize_href(href: str, base_url: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith(("javascript:", "mailto:", "tel:", "blob:", "data:")):
        return ""
    if "abs.twimg.com/emoji" in href:
        return ""
    raw_parsed = urlparse(href)
    if raw_parsed.scheme in {"http", "https"} and not raw_parsed.netloc:
        return ""
    normalized = urljoin(base_url, href)
    parsed = urlparse(normalized)
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        return ""
    if parsed.netloc.lower() == "news.ycombinator.com" and parsed.path in {"/vote", "/hide"}:
        return ""
    return normalized


def _title_or_fallback(title: str, url: str) -> str:
    cleaned = _clean_text(title)
    if cleaned and cleaned.lower() != "untitled":
        return cleaned
    if re.match(r"https?://(www\.)?(x|twitter)\.com/(home)?$", url.rstrip("/")):
        return "X"
    return cleaned or "Untitled"


def _parts_to_text(parts: list[dict[str, Any]], base_url: str, link_state: dict[str, Any]) -> str:
    output: list[str] = []
    for part in parts:
        text = _clean_text(str(part.get("text") or ""))
        browser_href = str(part.get("href") or "")
        raw_href = str(part.get("rawHref") or browser_href)
        raw_normalized = _normalize_href(raw_href, base_url)
        # Reject malformed raw attributes even when Chromium supplied a
        # browser-resolved fallback, but preserve the browser's resolution for
        # valid relative links and document <base> elements.
        href = raw_normalized if raw_href and not browser_href else _normalize_href(browser_href or raw_href, base_url)
        if raw_href and not raw_normalized and browser_href and urlparse(raw_href).scheme in {"http", "https"}:
            href = ""
        if raw_href and not href and text == _clean_text(raw_href):
            continue
        if not text and not href:
            continue
        if href:
            if "/analytics" in href:
                count_tokens: list[str] = []
                while output and re.fullmatch(r"\d+(?:\.\d+)?[KMB]?", output[-1], flags=re.IGNORECASE):
                    count_tokens.insert(0, output.pop())
                labels = ["Replies", "reposts", "Likes"] if len(count_tokens) >= 3 else (["Replies", "Likes"] if len(count_tokens) == 2 else ["Likes"])
                if count_tokens:
                    text = " ".join([f"{value} {label}" for value, label in zip(count_tokens[-len(labels):], labels)] + ([text] if text else []))
            key = (text or href, href)
            if key not in link_state["by_key"]:
                index = len(link_state["links"]) + 1
                link_state["by_key"][key] = index
                link_state["links"].append({"index": index, "text": text or href, "href": href})
            output.append(f"{text or href} [{link_state['by_key'][key]}]")
        elif text:
            output.append(text)
    return _clean_text(" ".join(output))


def _append_unique_line(lines: list[str], line: str, seen: set[str]) -> None:
    cleaned = _clean_text(line)
    if not cleaned:
        return
    key = cleaned.lower()
    if key in seen:
        return
    seen.add(key)
    lines.append(cleaned)


def read_extraction_script(screens: int = 5) -> str:
    safe_screens = max(int(screens or 0), 0)
    return f"""
const screens = {safe_screens};
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const priorityContentSelector = '#noteContainer,.note-container,.note-content,.note-scroller,#detail-desc,.comments-container,article.markdown-body,.markdown-body,.entry-content,[class*="markdown-body"]';
const pathParts = location.pathname.split('/').filter(Boolean);
const isXhsPage = /(^|\\.)xiaohongshu\\.com$/i.test(location.hostname);
const preferPriorityContent = isXhsPage || (/github\\.com$/i.test(location.hostname) && pathParts.length <= 2);
for (let i = 0; i < screens; i++) {{
  window.scrollBy(0, Math.max(window.innerHeight * 0.9, 600));
  await sleep(650);
  const nearBottom = window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 8;
  if (nearBottom) break;
}}

const articleWaitStart = Date.now();
const priorityWaitMs = preferPriorityContent ? 20000 : 8000;
const articleWaitDeadline = articleWaitStart + priorityWaitMs;
while (Date.now() < articleWaitDeadline) {{
  if (document.querySelector(priorityContentSelector)) break;
  if (document.querySelectorAll('article').length >= 2) break;
  if (!preferPriorityContent && document.readyState === 'complete' && Date.now() - articleWaitStart > 1600 && document.body && document.body.innerText && document.body.innerText.length > 200) break;
  await sleep(300);
}}

function cleanText(value) {{
  return String(value || '').replace(/\\u00a0/g, ' ').replace(/[ \\t\\r\\f\\v]+/g, ' ').replace(/\\n{{3,}}/g, '\\n\\n').trim();
}}

function meaningfulTitle() {{
  const title = cleanText(document.title || '');
  if (title && title !== 'Untitled') return title;
  if (/^(x|twitter)\\.com$/i.test(location.hostname) && location.pathname === '/home') return 'X';
  return title;
}}

function isVisible(el) {{
  if (!el || el.nodeType !== 1) return false;
  const style = getComputedStyle(el);
  const rect = el.getBoundingClientRect();
  return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0 && rect.width > 1 && rect.height > 1;
}}

function shouldSkip(el, inArticle=false) {{
  if (!el || el.nodeType !== 1) return true;
  const tag = el.tagName;
  if (['SCRIPT','STYLE','NOSCRIPT','TEMPLATE','META','LINK'].includes(tag)) return true;
  if (!inArticle && ['NAV','HEADER','FOOTER','FORM','ASIDE'].includes(tag)) return true;
  if (!inArticle && ['INPUT','TEXTAREA','SELECT','BUTTON'].includes(tag)) return true;
  if (el.getAttribute('aria-hidden') === 'true') return true;
  return !isVisible(el);
}}

function bestSrc(el) {{
  if (el.currentSrc) return el.currentSrc;
  const srcset = el.getAttribute('srcset');
  if (srcset) {{
    const candidates = srcset.split(',').map(s => {{
      const parts = s.trim().split(/\\s+/);
      const w = parseInt(parts[1]) || 0;
      return {{url: parts[0], w}};
    }}).filter(c => c.url && !c.url.startsWith('blob:'));
    if (candidates.length) {{
      candidates.sort((a, b) => b.w - a.w);
      return candidates[0].url;
    }}
  }}
  return el.src || '';
}}

function isRealCdn(url) {{
  if (!url) return false;
  if (url.startsWith('blob:')) return false;
  if (url.startsWith('data:')) return false;
  if (url.includes('abs.twimg.com/emoji')) return false;
  return true;
}}

function isTwitterCdn(url) {{
  return String(url || '').includes('pbs.twimg.com/');
}}

function xPhotoHref(url) {{
  try {{
    const parsed = new URL(String(url || ''));
    const parts = parsed.pathname.split('/').filter(Boolean);
    const isDigits = value => String(value || '').split('').every(ch => ch >= '0' && ch <= '9');
    return ['x.com', 'twitter.com'].includes(parsed.hostname.toLowerCase()) && parts.length === 5 && parts[1] === 'status' && isDigits(parts[2]) && parts[3] === 'photo' && isDigits(parts[4]);
  }} catch {{
    return false;
  }}
}}

function cssBackgroundUrl(el) {{
  const value = getComputedStyle(el).backgroundImage || '';
  const match = value.match(new RegExp('url\\(["\\']?([^"\\')]+)["\\']?\\)'));
  return match ? match[1] : '';
}}

function mediaUrlFromElement(el) {{
  if (!el || el.nodeType !== 1) return '';
  if (el.tagName === 'IMG') return bestSrc(el);
  if (el.tagName === 'VIDEO') return el.poster || bestSrc(el);
  return cssBackgroundUrl(el);
}}

function findCdnMediaNear(anchor) {{
  const scopes = [anchor, anchor.closest('article'), anchor.closest('[role="article"]')].filter(Boolean);
  for (const scope of scopes) {{
    const direct = mediaUrlFromElement(scope);
    if (isTwitterCdn(direct)) return direct;
    const media = scope.querySelectorAll('img,video,[style*="background-image"]');
    for (const item of media) {{
      const url = mediaUrlFromElement(item);
      if (isTwitterCdn(url)) return url;
    }}
  }}
  return '';
}}

function findPageCdnMedia() {{
  const media = document.querySelectorAll('img,video,[style*="background-image"]');
  for (const item of media) {{
    const url = mediaUrlFromElement(item);
    if (isTwitterCdn(url)) return url;
  }}
  return '';
}}

const photoMediaWaitDeadline = Date.now() + 4000;
while (xPhotoHref(location.href) && Date.now() < photoMediaWaitDeadline && !findPageCdnMedia()) {{
  await sleep(250);
}}

function extractDuration(el) {{
  if (el.duration && isFinite(el.duration) && el.duration > 0) {{
    const m = Math.floor(el.duration / 60);
    const s = Math.floor(el.duration % 60);
    return m + ':' + String(s).padStart(2, '0');
  }}
  return '';
}}

function extractEngagement(root) {{
  const labels = [];
  const nodes = root.querySelectorAll('[aria-label]');
  for (const node of nodes) {{
    const normalized = normalizeEngagementLabel(node.getAttribute('aria-label') || '');
    if (normalized) labels.push(normalized);
  }}
  return [...new Set(labels)].join(' ').trim();
}}

function normalizeEngagementLabel(label) {{
  const text = cleanText(label).replace(/,/g, '');
  const pairs = [];
  const patterns = [
    [/([0-9]+(?:\\.[0-9]+)?[KMB]?)\\s+(?:Replies|Reply)/i, 'Replies'],
    [/([0-9]+(?:\\.[0-9]+)?[KMB]?)\\s+(?:reposts|repost)/i, 'reposts'],
    [/([0-9]+(?:\\.[0-9]+)?[KMB]?)\\s+(?:Likes|Like)/i, 'Likes'],
    [/([0-9]+(?:\\.[0-9]+)?[KMB]?)\\s+(?:views|view)/i, 'views'],
  ];
  for (const [pattern, name] of patterns) {{
    const match = text.match(pattern);
    if (match) pairs.push(match[1] + ' ' + name);
  }}
  return pairs.join(' ');
}}

function partsFromNode(node) {{
  const parts = [];
  function walk(current) {{
    if (!current) return;
    if (current.nodeType === Node.TEXT_NODE) {{
      const text = cleanText(current.textContent);
      if (text) parts.push({{text}});
      return;
    }}
    if (current.nodeType !== Node.ELEMENT_NODE) return;
    const el = current;
    if (shouldSkip(el, !!el.closest('article'))) return;
    if (el.tagName === 'A') {{
      const rawHref = el.getAttribute('href') || '';
      const href = el.href || rawHref;
      if (href.startsWith('blob:') || href.includes('abs.twimg.com/emoji')) {{
        for (const child of el.childNodes) walk(child);
        return;
      }}
      let text = cleanText(el.innerText || el.getAttribute('aria-label') || href);
      if (href.includes('/analytics')) {{
        text = normalizeEngagementLabel(el.getAttribute('aria-label') || '') || text;
      }}
      if (xPhotoHref(href)) {{
        const cdn = findCdnMediaNear(el) || (xPhotoHref(location.href) && href === location.href ? findPageCdnMedia() : '');
        if (cdn) {{
          parts.push({{text: text || 'Image', href: cdn, media: 'img'}});
          return;
        }}
      }}
      if (text || href) parts.push({{text, href, rawHref}});
      return;
    }}
    if (el.tagName === 'IMG') {{
      const src = bestSrc(el);
      const label = cleanText(el.getAttribute('alt') || el.getAttribute('aria-label') || '');
      if (isRealCdn(src)) {{
        parts.push({{text: label || 'image', href: src, media: 'img'}});
      }} else if (label) {{
        parts.push({{text: label}});
      }}
      return;
    }}
    if (el.tagName === 'VIDEO') {{
      const poster = el.poster || '';
      const src = bestSrc(el);
      const duration = extractDuration(el);
      const cdn = isRealCdn(poster) ? poster : (isRealCdn(src) ? src : '');
      const label = duration || cleanText(el.getAttribute('aria-label') || 'video');
      if (cdn) {{
        parts.push({{text: label, href: cdn, media: 'video'}});
      }} else if (label) {{
        parts.push({{text: label}});
      }}
      return;
    }}
    if (el.tagName === 'AUDIO') {{
      const src = bestSrc(el);
      const label = cleanText(el.getAttribute('aria-label') || 'audio');
      if (isRealCdn(src)) {{
        parts.push({{text: label, href: src, media: 'audio'}});
      }} else if (label) {{
        parts.push({{text: label}});
      }}
      return;
    }}
    for (const child of el.childNodes) walk(child);
    const shadowRoot = el.shadowRoot || el.__omnibotClosedShadowRoot;
    if (shadowRoot) {{
      for (const child of shadowRoot.childNodes) walk(child);
    }}
  }}
  walk(node);
  return parts;
}}

function isTopLevelArticle(el) {{
  let parent = el.parentElement;
  while (parent) {{
    if (parent.tagName === 'ARTICLE') return false;
    parent = parent.parentElement;
  }}
  return true;
}}

function extractBlocks(root) {{
  const blocks = [];
  for (const child of root.children) {{
    if (child.nodeType !== 1) continue;
    if (child.tagName === 'ARTICLE') {{
      const inner = partsFromNode(child);
      if (inner.length) blocks.push({{type: 'quote', parts: inner}});
      continue;
    }}
    const parts = partsFromNode(child);
    if (parts.length) blocks.push({{type: 'paragraph', parts}});
  }}
  return blocks;
}}

function articleBlocks() {{
  const articles = Array.from(document.querySelectorAll('article')).filter(a => isVisible(a) && isTopLevelArticle(a));
  if (articles.length < 2) return [];
  const result = [];
  for (const article of articles) {{
    const mainParts = [];
    const quoteBlocks = [];
    for (const child of article.children) {{
      if (child.nodeType !== 1) continue;
      if (child.tagName === 'ARTICLE') {{
        const inner = partsFromNode(child);
        if (inner.length) quoteBlocks.push({{type: 'quote', parts: inner}});
        continue;
      }}
      const parts = partsFromNode(child);
      if (parts.length) mainParts.push(...parts);
    }}
    const allParts = [...mainParts, ...quoteBlocks.flatMap(q => q.parts)];
    if (allParts.length) {{
      const block = {{type: 'article', parts: mainParts}};
      if (quoteBlocks.length) block.quotes = quoteBlocks;
      result.push(block);
    }}
  }}
  return result;
}}

function scoreContainer(el) {{
  const text = cleanText(el.innerText || '');
  const links = el.querySelectorAll('a').length;
  const controls = el.querySelectorAll('input,textarea,select,button').length;
  const paragraphs = el.querySelectorAll('p,li,tr,article,blockquote,h1,h2,h3').length;
  return text.length + paragraphs * 80 - links * 8 - controls * 120;
}}

function overlayPriorityContainer() {{
  if (!isXhsPage) return null;
  const selectors = [
    '#noteContainer',
    '.note-container',
    '.note-content',
    '.note-scroller',
    '#detail-desc',
    '.comments-container',
    '[class*="note-content"]',
    '[class*="note-container"]',
    '[class*="detail"]'
  ];
  const candidates = selectors.flatMap(selector => Array.from(document.querySelectorAll(selector))).filter(isVisible);
  return candidates.sort((a, b) => scoreContainer(b) - scoreContainer(a))[0] || null;
}}

function hasReadableText(el) {{
  return cleanText(el && (el.innerText || el.textContent) || '').length > 20;
}}

function contentPriorityContainer() {{
  const selectors = [
    'article.markdown-body',
    '.markdown-body',
    '.entry-content',
    '[class*="markdown-body"]'
  ];
  const candidates = selectors.flatMap(selector => Array.from(document.querySelectorAll(selector))).filter(hasReadableText);
  return candidates.sort((a, b) => scoreContainer(b) - scoreContainer(a))[0] || null;
}}

function bestContainer() {{
  const overlay = overlayPriorityContainer();
  if (overlay) return overlay;
  const content = contentPriorityContainer();
  if (content) return content;
  const direct = document.querySelector('main, article, [role=main]');
  if (direct && isVisible(direct)) return direct;
  const candidates = Array.from(document.querySelectorAll('article, main, section, div, table, tbody')).filter(isVisible);
  return candidates.sort((a, b) => scoreContainer(b) - scoreContainer(a))[0] || document.body;
}}

function genericBlocks(root) {{
  const selector = 'h1,h2,h3,p,li,blockquote,pre,figure,article,section,tr,a[href],[id="detail-desc"],[class*="note-content"],[class*="desc"]';
  const elements = Array.from(root.querySelectorAll(selector)).filter(el => !shouldSkip(el, !!el.closest('article')));
  const blocks = [];
  for (const el of elements) {{
    const text = cleanText(el.innerText || el.textContent || '');
    if (!text && !el.querySelector('img,video,audio,a[href]')) continue;
    if (text.length < 2 && !el.querySelector('img,video,audio')) continue;
    const tag = el.tagName;
    const type = tag === 'BLOCKQUOTE' ? 'quote' : (tag.match(/^H[1-6]$/) ? 'heading' : (tag === 'FIGURE' ? 'media' : 'paragraph'));
    blocks.push({{type, parts: partsFromNode(el)}});
  }}
  const shadowHosts = Array.from(root.querySelectorAll('*')).filter(el => el.shadowRoot || el.__omnibotClosedShadowRoot);
  for (const host of shadowHosts) {{
    const parts = partsFromNode(host);
    if (parts.length) blocks.push({{type: 'paragraph', parts}});
  }}
  return blocks;
}}

function appendPagePhotoMediaFallback(blocks) {{
  if (!xPhotoHref(location.href)) return blocks;
  const cdn = findPageCdnMedia();
  if (!cdn) return blocks;
  const hasCdn = blocks.some(block => (block.parts || []).some(part => part && part.href === cdn));
  if (hasCdn) return blocks;
  const mediaPart = {{text: 'Image', href: cdn, media: 'img'}};
  const target = blocks.find(block => Array.isArray(block.parts) && block.parts.length) || null;
  if (target) {{
    target.parts.push(mediaPart);
    return blocks;
  }}
  blocks.push({{type: 'media', parts: [mediaPart]}});
  return blocks;
}}

function blockTextLength(blocks) {{
  return blocks.reduce((total, block) => {{
    const partsText = (block.parts || []).map(part => part.text || '').join(' ');
    return total + cleanText(block.text || partsText).length;
  }}, 0);
}}

function appendBodyTextFallback(blocks) {{
  const bodyText = cleanText(document.body && document.body.innerText || '');
  if (bodyText.length < 500) return blocks;
  if (blockTextLength(blocks) >= bodyText.length * 0.55) return blocks;
  return [...blocks, {{type: 'paragraph', text: bodyText}}];
}}

const blocks = articleBlocks();
const root = bestContainer();
const debugContentPriority = contentPriorityContainer();
const finalBlocks = appendBodyTextFallback(appendPagePhotoMediaFallback(blocks.length ? blocks : genericBlocks(root)));
return {{
  title: meaningfulTitle(),
  url: location.href,
  blocks: finalBlocks,
  debug: {{articleCount: document.querySelectorAll('article').length, rootTag: root ? root.tagName : 'BODY', screens, preferPriorityContent, priorityContentCount: document.querySelectorAll(priorityContentSelector).length, contentPriorityTag: debugContentPriority ? debugContentPriority.tagName : ''}}
}};
"""


def frame_read_extraction_script() -> str:
    """Read a same-origin frame without the top-level reader's async scrolling loop."""
    return """
(() => {
  const bodies = Array.from(document.querySelectorAll('body'));
  const bodyScore = (body) => {
    if (!body) return -1;
    const textLength = String(body.innerText || '').trim().length;
    const interactiveCount = body.querySelectorAll('a,button,input,textarea,select,[role]').length;
    return textLength * 10 + interactiveCount;
  };
  const body = bodies.reduce((best, candidate) => bodyScore(candidate) > bodyScore(best) ? candidate : best, document.body || null);
  const parts = [];
  if (body) {
    const readableBody = body.cloneNode(true);
    readableBody.querySelectorAll('script,style,noscript,template').forEach((node) => node.remove());
    const text = String(readableBody.textContent || '').trim();
    if (text) parts.push({text});
    for (const anchor of Array.from(document.querySelectorAll('a[href]'))) {
      const text = String(anchor.innerText || anchor.textContent || '').trim();
      const rawHref = anchor.getAttribute('href') || '';
      if (text || rawHref) parts.push({text, href: anchor.href || rawHref, rawHref});
    }
  }
  return {
    title: document.title || 'Untitled',
    url: location.href,
    blocks: parts.length ? [{type: 'paragraph', parts}] : [],
    debug: {
      frame: true,
      bodyCount: bodies.length,
      selectedBodyIndex: bodies.indexOf(body),
      selectedBodyTextLength: body ? String(body.innerText || '').trim().length : 0
    }
  };
})()
"""


def format_read_document(extracted: dict[str, Any]) -> dict[str, Any]:
    url = _clean_text(str(extracted.get("url") or ""))
    title = _title_or_fallback(str(extracted.get("title") or "Untitled"), url)
    link_state: dict[str, Any] = {"by_key": {}, "links": []}
    body_lines: list[str] = []
    seen_lines: set[str] = set()
    previous_type = ""

    for block in extracted.get("blocks") or []:
        block_type = str(block.get("type") or "paragraph")
        text = _parts_to_text(list(block.get("parts") or []), url, link_state)
        if not text:
            text = _clean_text(str(block.get("text") or ""))
        if not text:
            continue

        if body_lines and block_type in {"article", "separator"} and previous_type not in {"article", "separator"}:
            body_lines.append("---")
        elif body_lines and previous_type == "heading":
            body_lines.append("---")
        elif body_lines and block_type == "article" and previous_type == "article":
            body_lines.append("---")

        if block_type == "heading":
            _append_unique_line(body_lines, f"**{text}**", seen_lines)
        elif block_type == "quote":
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped:
                    _append_unique_line(body_lines, f"> {stripped}", seen_lines)
        elif block_type == "media":
            _append_unique_line(body_lines, text, seen_lines)
        else:
            _append_unique_line(body_lines, text, seen_lines)
        previous_type = block_type

    lines = [f"# {title}", f"> {url}", ""]
    lines.extend(body_lines)
    if link_state["links"]:
        lines.append("")
        for link in link_state["links"]:
            lines.append(f"[{link['index']}] {link['href']}")
    return {"content": "\n".join(lines).rstrip() + "\n", "links": link_state["links"]}
