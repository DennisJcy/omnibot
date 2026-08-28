from __future__ import annotations

import json
from typing import Any


def _line_number(value: Any) -> int:
    try:
        return int(value) + 1 if value is not None else 0
    except (TypeError, ValueError):
        return 0


def console_arg_text(arg: dict[str, Any]) -> str:
    if "value" in arg:
        value = arg.get("value")
        if isinstance(value, str):
            return value
        if value is None:
            return "null"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        return str(value)
    description = arg.get("description")
    if description:
        return str(description)
    unserializable = arg.get("unserializableValue")
    if unserializable:
        return str(unserializable)
    return str(arg.get("type") or "")


def normalize_console_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "level": entry.get("level", "log"),
        "text": entry.get("text", ""),
        "url": entry.get("url", ""),
        "line": entry.get("lineNumber", entry.get("line", 0)),
    }


def normalize_cdp_console_event(event: dict[str, Any]) -> dict[str, Any]:
    method = str(event.get("method") or "")
    params = event.get("params") if isinstance(event.get("params"), dict) else {}

    if method == "Runtime.consoleAPICalled":
        frames = (params.get("stackTrace") or {}).get("callFrames") or []
        frame = frames[0] if frames else {}
        level = str(params.get("type") or "log")
        if level == "warning":
            level = "warn"
        return {
            "level": level,
            "text": " ".join(console_arg_text(arg) for arg in params.get("args", [])),
            "url": str(frame.get("url") or ""),
            "line": _line_number(frame.get("lineNumber")),
            "timestamp": params.get("timestamp"),
            "source": "cdp:Runtime.consoleAPICalled",
        }

    if method == "Runtime.exceptionThrown":
        details = params.get("exceptionDetails") if isinstance(params.get("exceptionDetails"), dict) else {}
        exception = details.get("exception") if isinstance(details.get("exception"), dict) else {}
        text = str(exception.get("description") or details.get("text") or "")
        return {
            "level": "error",
            "text": text,
            "url": str(details.get("url") or ""),
            "line": _line_number(details.get("lineNumber")),
            "timestamp": params.get("timestamp"),
            "source": "cdp:Runtime.exceptionThrown",
        }

    if method == "Log.entryAdded":
        entry = params.get("entry") if isinstance(params.get("entry"), dict) else {}
        return {
            "level": str(entry.get("level") or "log"),
            "text": str(entry.get("text") or ""),
            "url": str(entry.get("url") or ""),
            "line": _line_number(entry.get("lineNumber")),
            "timestamp": entry.get("timestamp"),
            "source": "cdp:Log.entryAdded",
        }

    return {"level": "log", "text": "", "url": "", "line": 0, "timestamp": None, "source": method}


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url or "").netloc
    except Exception:
        return ""


def normalize_network_event(entry: dict[str, Any]) -> dict[str, Any]:
    method = str(entry.get("method") or "")
    params = entry.get("params") if isinstance(entry.get("params"), dict) else {}
    out: dict[str, Any] = {
        "source": "cdp:" + method,
        "timestamp": entry.get("timestamp"),
        "request_id": params.get("requestId"),
        "resource_type": params.get("type"),
    }

    if method == "Network.requestWillBeSent":
        request = params.get("request") if isinstance(params.get("request"), dict) else {}
        url = str(request.get("url") or params.get("documentURL") or "")
        out.update({
            "event": "request",
            "url": url,
            "host": _host(url),
            "method": request.get("method"),
            "headers": request.get("headers") if isinstance(request.get("headers"), dict) else {},
        })
        if "postData" in request:
            out["post_data"] = request.get("postData")
        return out

    if method == "Network.responseReceived":
        response = params.get("response") if isinstance(params.get("response"), dict) else {}
        url = str(response.get("url") or "")
        out.update({
            "event": "response",
            "url": url,
            "host": _host(url),
            "status": response.get("status"),
            "mime_type": response.get("mimeType"),
        })
        return out

    if method == "Network.loadingFailed":
        out.update({
            "event": "loadingFailed",
            "url": params.get("url") or "",
            "host": _host(str(params.get("url") or "")),
            "error_text": params.get("errorText"),
            "blocked_reason": params.get("blockedReason"),
        })
        return out

    out["event"] = method.replace("Network.", "") or "unknown"
    return out


def network_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    hosts: dict[str, int] = {}
    methods: dict[str, int] = {}
    resource_types: dict[str, int] = {}
    api_candidates: list[str] = []
    failures = 0

    for item in entries:
        if not isinstance(item, dict):
            continue
        status = int(item.get("status") or 0)
        if status >= 200:
            status_counts[str(status)] = status_counts.get(str(status), 0) + 1
        host = item.get("host")
        if host:
            hosts[str(host)] = hosts.get(str(host), 0) + 1
        req_method = item.get("method")
        if req_method:
            methods[str(req_method)] = methods.get(str(req_method), 0) + 1
        resource_type = item.get("resource_type")
        if resource_type:
            resource_types[str(resource_type)] = resource_types.get(str(resource_type), 0) + 1
        if item.get("event") == "loadingFailed":
            failures += 1
        url = str(item.get("url") or "")
        if item.get("event") == "request" and (item.get("resource_type") in {"XHR", "Fetch"} or "/api/" in url or "api." in url):
            if url and url not in api_candidates:
                api_candidates.append(url)

    errors = [item for item in entries if isinstance(item, dict) and int(item.get("status") or 0) >= 400]
    return {
        "total": len(entries),
        "errors": len(errors),
        "status_counts": status_counts,
        "hosts": hosts,
        "methods": methods,
        "resource_types": resource_types,
        "failures": failures,
        "api_candidates": api_candidates[:50],
        "entries": entries[-100:],
    }