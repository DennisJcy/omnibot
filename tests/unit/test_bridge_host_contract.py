from omnibot import bridge_host


def test_device_id_from_hello_prefers_message_device_id():
    assert bridge_host.device_id_from_hello({"deviceId": "abc"}) == "abc"


def test_device_id_from_hello_has_stable_fallback(monkeypatch):
    monkeypatch.setattr(bridge_host, "persistent_device_id", lambda: "stored-uuid-1")

    assert bridge_host.device_id_from_hello({}) == "stored-uuid-1"


def test_persistent_device_id_is_stable(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge_host.paths, "default_storage_dir", lambda: tmp_path)

    first = bridge_host.persistent_device_id()
    second = bridge_host.persistent_device_id()

    assert first == second
    assert first
    assert (tmp_path / "device_id").read_text(encoding="utf-8") == first


def test_dispatch_calls_daemon_action_registry():
    class Driver:
        pass

    result = bridge_host.dispatch_action("x", {"a": 1}, Driver(), registry={"x": lambda driver, a: {"a": a}})

    assert result == {"a": 1}
