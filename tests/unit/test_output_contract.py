import base64
from pathlib import Path

from omnibot import output


def test_read_to_text_returns_clean_content():
    result = {
        "status": "success",
        "content": "# Title\n> https://example.com/\n\nBody\n",
    }

    text = output.read_to_text(result)

    assert text == "# Title\n> https://example.com/\n\nBody\n"


def test_read_to_text_appends_newline_if_missing():
    result = {
        "status": "success",
        "content": "# Title",
    }

    text = output.read_to_text(result)

    assert text == "# Title\n"


def test_write_screenshot_file_writes_png(tmp_path):
    png = base64.b64encode(b"png-bytes").decode()
    result = {
        "status": "success",
        "format": "png",
        "base64": png,
        "url": "https://example.com/login",
        "title": "Sign in",
        "viewport": {"width": 390, "height": 844, "deviceScaleFactor": 2},
    }

    written = output.write_screenshot_file(result, str(tmp_path / "shot.png"))

    assert written == {
        "status": "success",
        "format": "png",
        "path": str(tmp_path / "shot.png"),
        "bytes": 9,
        "url": "https://example.com/login",
        "title": "Sign in",
        "viewport": {"width": 390, "height": 844, "deviceScaleFactor": 2},
    }
    assert (tmp_path / "shot.png").read_bytes() == b"png-bytes"


def test_write_screenshot_file_fsyncs_before_atomic_replace(tmp_path, monkeypatch):
    png = base64.b64encode(b"durable-png").decode()
    target = tmp_path / "shot.png"
    fsynced = []
    replacements = []
    real_fsync = output.os.fsync
    real_replace = output.os.replace

    def tracked_fsync(fd):
        fsynced.append(fd)
        return real_fsync(fd)

    def tracked_replace(source, destination):
        replacements.append((Path(source), Path(destination), bool(fsynced)))
        return real_replace(source, destination)

    monkeypatch.setattr(output.os, "fsync", tracked_fsync)
    monkeypatch.setattr(output.os, "replace", tracked_replace)

    written = output.write_screenshot_file(
        {"status": "success", "format": "png", "base64": png},
        str(target),
    )

    assert written["bytes"] == len(b"durable-png")
    assert len(replacements) == 1
    temp_path, destination, was_fsynced = replacements[0]
    assert destination == target
    assert was_fsynced is True
    assert not temp_path.exists()
    assert target.read_bytes() == b"durable-png"


def test_default_screenshot_path_uses_omni_prefix(tmp_path, monkeypatch):
    monkeypatch.setattr(output, "default_storage_dir", lambda: tmp_path)
    path = output.default_screenshot_path()

    assert path.parent == tmp_path / "screenshots"
    assert path.name.startswith("omni-")
    assert path.suffix == ".png"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


def test_default_screenshot_path_accepts_format_and_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(output, "default_storage_dir", lambda: tmp_path)

    path = output.default_screenshot_path(screenshot_format="jpeg", screenshot_dir=str(tmp_path / "custom"))

    assert path.parent == tmp_path / "custom"
    assert path.suffix == ".jpg"
