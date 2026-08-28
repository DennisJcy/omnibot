import json
import struct
from typing import Any, BinaryIO


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    raw_length = stream.read(4)
    if raw_length == b"":
        return None
    if len(raw_length) != 4:
        raise EOFError("Incomplete native messaging length header")
    message_length = struct.unpack("<I", raw_length)[0]
    payload = stream.read(message_length)
    if len(payload) != message_length:
        raise EOFError("Incomplete native messaging payload")
    decoded = json.loads(payload.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Native messaging payload must be a JSON object")
    return decoded


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    payload = json.dumps(message, ensure_ascii=False, default=str).encode("utf-8")
    stream.write(struct.pack("<I", len(payload)))
    stream.write(payload)
    stream.flush()
