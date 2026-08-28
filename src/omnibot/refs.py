from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RefEntry:
    ref_id: str
    role: str
    name: str
    backend_node_id: int | None = None
    selector: str | None = None
    frame_id: int | str | None = None
    nth: int | None = None
    box: dict[str, float] | None = None
    opener_selector: str | None = None
    kind: str | None = None
    contenteditable: bool | None = None
    input_type: str | None = None


def parse_ref(value: str) -> str | None:
    text = str(value).strip()
    if text.startswith("@"):
        text = text[1:]
    elif text.startswith("ref="):
        text = text[4:]
    if len(text) > 1 and text[0] == "e" and text[1:].isdigit():
        return text
    return None


class RefMap:
    def __init__(self) -> None:
        self._entries: dict[str, dict[str, RefEntry]] = {}
        self._next: dict[str, int] = {}

    def clear_tab(self, tab_id: str | int) -> None:
        key = str(tab_id)
        self._entries[key] = {}
        self._next[key] = 1

    def add(
        self,
        tab_id: str | int,
        *,
        role: str,
        name: str,
        backend_node_id: int | None = None,
        selector: str | None = None,
        frame_id: int | str | None = None,
        nth: int | None = None,
        box: dict[str, float] | None = None,
        opener_selector: str | None = None,
        kind: str | None = None,
        contenteditable: bool | None = None,
        input_type: str | None = None,
    ) -> str:
        key = str(tab_id)
        if key not in self._entries:
            self.clear_tab(key)
        number = self._next[key]
        self._next[key] = number + 1
        ref_id = f"e{number}"
        self._entries[key][ref_id] = RefEntry(
            ref_id=ref_id,
            role=role,
            name=name,
            backend_node_id=backend_node_id,
            selector=selector,
            frame_id=frame_id,
            nth=nth,
            box=box,
            opener_selector=opener_selector,
            kind=kind,
            contenteditable=contenteditable,
            input_type=input_type,
        )
        return ref_id

    def get(self, tab_id: str | int, selector_or_ref: str) -> RefEntry | None:
        ref_id = parse_ref(selector_or_ref)
        if ref_id is None:
            return None
        return self._entries.get(str(tab_id), {}).get(ref_id)

    def entries(self, tab_id: str | int) -> list[RefEntry]:
        entries = self._entries.get(str(tab_id), {})
        return [entries[key] for key in sorted(entries, key=lambda item: int(item[1:]))]

    def as_json(self, tab_id: str | int) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for entry in self.entries(tab_id):
            item: dict[str, Any] = {"role": entry.role, "name": entry.name}
            if entry.box is not None:
                item["box"] = entry.box
            if entry.frame_id is not None:
                item["frameId"] = entry.frame_id
            if entry.opener_selector is not None:
                item["openerSelector"] = entry.opener_selector
            if entry.kind is not None:
                item["kind"] = entry.kind
            if entry.contenteditable is not None:
                item["contenteditable"] = entry.contenteditable
            if entry.input_type is not None:
                item["type"] = entry.input_type
            result[entry.ref_id] = item
        return result
