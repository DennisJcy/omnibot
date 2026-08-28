from __future__ import annotations


def name_session(ctx, name: str) -> dict:
    ctx.session_name = name
    return {"name": name}


def claim_tab(ctx, tab_id: str) -> dict:
    ctx.claimed_tabs.add(tab_id)
    return {"tab_id": tab_id, "claimed": True}


def release_tab(ctx, tab_id: str) -> dict:
    ctx.claimed_tabs.discard(tab_id)
    return {"tab_id": tab_id, "claimed": False}
