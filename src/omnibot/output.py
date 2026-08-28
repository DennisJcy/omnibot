import base64
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import default_storage_dir


def default_screenshot_path(screenshot_format: str = "png", screenshot_dir: str | None = None) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = ".jpg" if screenshot_format == "jpeg" else ".png"
    base = Path(screenshot_dir) if screenshot_dir else default_storage_dir() / "screenshots"
    path = base / f"omni-{stamp}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def read_to_text(result: dict[str, Any]) -> str:
    if result.get("status") == "error":
        return f"Error: {result.get('msg', '')}\n"
    content = str(result.get("content") or "")
    return content if content.endswith("\n") else content + "\n"


def write_screenshot_file(result: dict[str, Any], output_path: str | None = None, screenshot_dir: str | None = None) -> dict[str, Any]:
    if result.get("status") != "success" or not result.get("base64"):
        return result
    screenshot_format = str(result.get("format") or "png")
    path = Path(output_path) if output_path else default_screenshot_path(screenshot_format=screenshot_format, screenshot_dir=screenshot_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = base64.b64decode(result["base64"])
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("xb") as output:
            output.write(image_bytes)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
    written = {
        "status": "success",
        "format": screenshot_format,
        "path": str(path),
        "bytes": len(image_bytes),
    }
    for key in ("url", "title", "viewport", "ref", "mode"):
        if key in result:
            written[key] = result[key]
    return written
