from __future__ import annotations

import time
from typing import Any


def trace_event(action: str, params: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    return {"timestamp": time.time(), "action": action, "params": params, "result": result}


def parse_replay_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    actions = payload.get("actions")
    if not isinstance(actions, list):
        raise ValueError("replay payload requires an actions list")
    return actions
