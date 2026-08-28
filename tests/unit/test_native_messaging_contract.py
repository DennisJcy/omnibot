import io
import json
import struct

from omnibot import native_messaging


def test_write_message_uses_native_messaging_frame():
    output = io.BytesIO()

    native_messaging.write_message(output, {"type": "hello", "deviceId": "abc"})

    size = struct.unpack("<I", output.getvalue()[:4])[0]
    payload = output.getvalue()[4:]
    assert size == len(payload)
    assert json.loads(payload.decode("utf-8")) == {"type": "hello", "deviceId": "abc"}


def test_read_message_returns_none_on_eof():
    assert native_messaging.read_message(io.BytesIO()) is None


def test_read_message_decodes_native_messaging_frame():
    payload = json.dumps({"type": "result", "ok": True}).encode("utf-8")
    stream = io.BytesIO(struct.pack("<I", len(payload)) + payload)

    assert native_messaging.read_message(stream) == {"type": "result", "ok": True}
