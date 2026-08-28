from omnibot import ipc_server


def test_make_endpoint_uses_unix_socket_on_posix(tmp_path, monkeypatch):
    monkeypatch.setattr(ipc_server.os, "name", "posix", raising=False)

    endpoint = ipc_server.make_endpoint("dev1", base_dir=tmp_path)

    assert endpoint.startswith("unix:")
    assert endpoint.endswith("dev1.sock")


def test_endpoint_to_url_maps_tcp_endpoint():
    assert ipc_server.endpoint_to_url("tcp:127.0.0.1:19000") == "http://127.0.0.1:19000"


def test_endpoint_to_url_rejects_unknown_scheme():
    try:
        ipc_server.endpoint_to_url("bad:value")
    except ValueError as exc:
        assert "Unsupported endpoint" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_make_app_exposes_health_and_action_dispatch():
    app = ipc_server.make_app(lambda action, params: {"status": "success", "action": action, "params": params})

    routes = {(route.method, route.rule) for route in app.routes}

    assert ("GET", "/api/health") in routes
    assert ("POST", "/api/actions/<action_name>") in routes
