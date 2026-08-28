import os
from pathlib import Path

from omnibot import bridge_registry


def test_register_and_list_bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge_registry, "registry_dir", lambda: tmp_path)

    bridge_registry.register_bridge({"device_id": "dev1", "pid": os.getpid(), "endpoint": "unix:/tmp/omnibot.sock"})

    assert bridge_registry.list_bridges() == [{"device_id": "dev1", "pid": os.getpid(), "endpoint": "unix:/tmp/omnibot.sock"}]


def test_list_bridges_ignores_stale_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge_registry, "registry_dir", lambda: tmp_path)
    stale = tmp_path / "stale.json"
    stale.write_text('{"device_id":"stale","pid":99999999,"endpoint":"unix:/tmp/stale.sock"}', encoding="utf-8")

    assert bridge_registry.list_bridges() == []
    assert not stale.exists()


def test_unregister_bridge_removes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge_registry, "registry_dir", lambda: tmp_path)
    bridge_registry.register_bridge({"device_id": "dev1", "pid": os.getpid(), "endpoint": "tcp:127.0.0.1:19000"})

    bridge_registry.unregister_bridge("dev1")

    assert bridge_registry.list_bridges() == []
