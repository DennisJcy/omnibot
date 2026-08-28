from __future__ import annotations

from typing import Any


def collect_assets_script() -> str:
    return """
(() => {
  const resources = performance.getEntriesByType('resource').map(r => ({type:r.initiatorType || 'resource', url:r.name, transferSize:r.transferSize || 0}));
  const images = Array.from(document.images).map(img => ({type:'image', url:img.currentSrc || img.src, transferSize:0}));
  const stylesheets = Array.from(document.styleSheets).map(s => ({type:'stylesheet', url:s.href || location.href, transferSize:0}));
  return [...resources, ...images, ...stylesheets].filter(item => item.url);
})()
"""


def normalize_asset(asset: dict[str, Any]) -> dict[str, Any]:
    return {"type": str(asset.get("type") or "resource"), "url": str(asset.get("url") or ""), "size": int(asset.get("transferSize") or asset.get("size") or 0)}


def normalize_assets(raw_assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in raw_assets:
        asset = normalize_asset(raw)
        url = asset["url"]
        if not url:
            continue
        existing = by_url.get(url)
        if existing is None:
            by_url[url] = asset
            order.append(url)
            continue
        if asset["size"] > existing["size"]:
            by_url[url] = asset
    return [by_url[url] for url in order]
