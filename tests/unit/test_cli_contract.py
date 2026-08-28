import json
from types import SimpleNamespace

import pytest

from omnibot import actions, cli


def test_parser_has_browser_action_commands():
    parser = cli.build_parser()
    command_action = next(action for action in parser._actions if getattr(action, "dest", None) == "command")
    commands = set(command_action.choices.keys())

    assert {"daemon", "tabs", "read", "execute-js", "batch", "wait", "navigate", "screenshot", "skills", "doctor"}.issubset(commands)
    assert "scan" not in commands
    assert "full-scan" not in commands
    assert "explore" not in commands


def test_read_parser_defaults_to_text_output_with_five_screens():
    parser = cli.build_parser()
    args = parser.parse_args(["read"])

    assert args.command == "read"
    assert args.url == ""
    assert args.screens == 5
    assert args.switch_tab_id == ""
    assert args.json is False


def test_read_parser_accepts_url_screens_tab_id_and_json():
    parser = cli.build_parser()
    args = parser.parse_args(["read", "https://x.com/home", "--screens", "7", "--tab-id", "123", "--json"])

    assert args.command == "read"
    assert args.url == "https://x.com/home"
    assert args.screens == 7
    assert args.switch_tab_id == "123"
    assert args.json is True


def test_tabs_parser_accepts_explicit_json_flag_for_agent_consistency():
    parser = cli.build_parser()
    args = parser.parse_args(["tabs", "--json"])

    assert args.command == "tabs"
    assert args.json is True


def test_read_parser_accepts_action_timeout():
    parser = cli.build_parser()
    args = parser.parse_args(["read", "https://example.com", "--timeout", "120"])

    assert args.command == "read"
    assert args.action_timeout == 120


def test_read_action_request_maps_to_read_action():
    parser = cli.build_parser()
    args = parser.parse_args(["read", "https://example.com", "--screens", "2"])

    action, params, as_json = cli.action_request_from_args(args)

    assert action == "read"
    assert params == {"url": "https://example.com", "screens": 2, "switch_tab_id": ""}
    assert as_json is False


def test_upload_action_request_maps_to_upload_action():
    parser = cli.build_parser()
    args = parser.parse_args(["upload", "input[type=file]", "/tmp/image.png", "--tab-id", "123"])

    action, params, as_json = cli.action_request_from_args(args)

    assert action == "upload"
    assert params == {"selector": "input[type=file]", "file": "/tmp/image.png", "switch_tab_id": "123"}
    assert as_json is True


def test_frame_parser_accepts_explicit_tab_id():
    parser = cli.build_parser()
    args = parser.parse_args(["frame", "#payment-frame", "--tab-id", "123"])

    action, params, as_json = cli.action_request_from_args(args)

    assert action == "frame"
    assert params == {"frame_target": "#payment-frame", "switch_tab_id": "123"}
    assert as_json is True


def test_upload_action_sets_file_input_files_with_cdp(tmp_path, monkeypatch):
    from omnibot import cdp

    upload_file = tmp_path / "image.png"
    upload_file.write_bytes(b"png")
    sent = []

    class Driver:
        def get_context(self, token=None):
            return SimpleNamespace(
                sessions={"tab-1": SimpleNamespace(created_by_tool=False)},
                tool_created_tabs=set(),
            )

        def get_all_sessions(self, token=None):
            return [{"id": "tab-1"}]

        def _cancel_tab_close(self, tab_id, token=None):
            pass

        def _schedule_tab_close(self, tab_id, timeout=0, token=None, close=False):
            pass

    def fake_send_cdp(driver, tab_id, method, params=None, **kwargs):
        sent.append((tab_id, method, params))
        if method == "Runtime.evaluate":
            return {"result": {"objectId": "object-1"}}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.upload(Driver(), "input[type=file]", str(upload_file), switch_tab_id="tab-1")

    assert result == {
        "status": "success",
        "uploaded": 1,
        "selector": "input[type=file]",
        "file": str(upload_file.resolve()),
    }
    assert sent == [
        ("tab-1", "Runtime.evaluate", {"expression": "document.querySelector('input[type=file]')", "returnByValue": False}),
        ("tab-1", "DOM.setFileInputFiles", {"files": [str(upload_file.resolve())], "objectId": "object-1"}),
    ]


def test_upload_action_falls_back_to_js_file_assignment(tmp_path, monkeypatch):
    from omnibot import cdp

    upload_file = tmp_path / "image.png"
    upload_file.write_bytes(b"\x89PNG\r\n\x1a\n")
    methods = []

    class Driver:
        def get_context(self, token=None):
            return SimpleNamespace(
                sessions={"tab-1": SimpleNamespace(created_by_tool=False)},
                tool_created_tabs=set(),
            )

        def get_all_sessions(self, token=None):
            return [{"id": "tab-1"}]

        def _cancel_tab_close(self, tab_id, token=None):
            pass

        def _schedule_tab_close(self, tab_id, timeout=0, token=None, close=False):
            pass

    def fake_send_cdp(driver, tab_id, method, params=None, **kwargs):
        methods.append(method)
        if method == "Runtime.evaluate" and len(methods) == 1:
            return {"result": {"objectId": "object-1"}}
        if method == "DOM.setFileInputFiles":
            raise cdp.CdpError("Could not find object with given id")
        if method == "Runtime.evaluate":
            assert "DataTransfer" in params["expression"]
            assert "querySelectorAll" in params["expression"]
            assert "image.png" in params["expression"]
            return {"result": {"value": {"ok": True, "files": 1, "inputs": 2, "name": "image.png"}}}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.upload(Driver(), "input[type=file]", str(upload_file), switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert result["uploaded"] == 1
    assert result["inputs"] == 2
    assert result["transport"] == "js-file-assignment"
    assert methods == ["Runtime.evaluate", "DOM.setFileInputFiles", "DOM.getDocument", "Runtime.evaluate"]


def test_upload_action_falls_back_to_dom_node_id(tmp_path, monkeypatch):
    from omnibot import cdp

    upload_file = tmp_path / "image.png"
    upload_file.write_bytes(b"png")
    calls = []

    class Driver:
        def get_context(self, token=None):
            return SimpleNamespace(
                sessions={"tab-1": SimpleNamespace(created_by_tool=False)},
                tool_created_tabs=set(),
            )

        def get_all_sessions(self, token=None):
            return [{"id": "tab-1"}]

        def _cancel_tab_close(self, tab_id, token=None):
            pass

        def _schedule_tab_close(self, tab_id, timeout=0, token=None, close=False):
            pass

    def fake_send_cdp(driver, tab_id, method, params=None, **kwargs):
        calls.append((method, params))
        if method == "Runtime.evaluate":
            return {"result": {"objectId": "object-1"}}
        if method == "DOM.setFileInputFiles" and "objectId" in params:
            raise cdp.CdpError("Could not find object with given id")
        if method == "DOM.getDocument":
            return {"root": {"nodeId": 11}}
        if method == "DOM.querySelector":
            return {"nodeId": 22}
        return {}

    monkeypatch.setattr(cdp, "send_cdp", fake_send_cdp)

    result = actions.upload(Driver(), "input[type=file]", str(upload_file), switch_tab_id="tab-1")

    assert result["status"] == "success"
    assert result["transport"] == "cdp-node-id"
    assert ("DOM.setFileInputFiles", {"files": [str(upload_file.resolve())], "nodeId": 22}) in calls


def test_scan_command_is_removed():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["scan"])


def test_operational_command_defaults_to_json():
    parser = cli.build_parser()
    args = parser.parse_args(["navigate", "https://example.com"])

    assert args.command == "navigate"
    assert args.json is True


def test_navigate_accepts_explicit_json_flag_for_agent_consistency():
    parser = cli.build_parser()
    args = parser.parse_args(["navigate", "https://example.com", "--json"])

    assert args.command == "navigate"
    assert args.json is True


def test_navigate_accepts_explicit_new_tab_alias():
    parser = cli.build_parser()
    args = parser.parse_args(["navigate", "https://example.com", "--new-tab"])

    assert args.command == "navigate"
    assert args.new_tab is True
    assert args.same_tab is False


def test_tab_group_commands_parse_for_agent_use():
    parser = cli.build_parser()
    group = parser.parse_args(["tab", "group", "123", "Nuwa Test"])
    info = parser.parse_args(["tab", "group-info", "123"])
    ungroup = parser.parse_args(["tab", "ungroup", "123"])

    assert (group.tab_command, group.target, group.label) == ("group", "123", "Nuwa Test")
    assert (info.tab_command, info.target) == ("group-info", "123")
    assert (ungroup.tab_command, ungroup.target) == ("ungroup", "123")


def test_browser_extensions_command_parses_as_read_only_query():
    parser = cli.build_parser()
    args = parser.parse_args(["browser", "extensions"])

    assert args.browser_command == "extensions"
    assert args.tab_id == ""


def test_browser_content_settings_command_parses_read_only_query():
    parser = cli.build_parser()
    args = parser.parse_args(["browser", "content-settings", "automaticDownloads", "https://example.com/"])

    assert args.browser_command == "content-settings"
    assert args.type == "automaticDownloads"
    assert args.url == "https://example.com/"


def test_browser_mouse_visual_state_command_parses_read_only_query():
    parser = cli.build_parser()
    args = parser.parse_args(["browser", "mouse-visual-state", "--tab-id", "123"])

    assert args.browser_command == "mouse-visual-state"
    assert args.tab_id == "123"


def test_no_args_prints_banner_help_without_starting_daemon(monkeypatch, capsys):
    def fail_start(*args, **kwargs):
        raise AssertionError("daemon should not start for top-level help")

    monkeypatch.setattr(cli.daemon_client, "ensure_daemon", fail_start)

    exit_code = cli.main([])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "▄▄▄▄▄▄▄" in captured.out
    assert "omnibot CLI v" in captured.out
    assert "Common commands:" in captured.out
    assert "doctor" in captured.out
    assert "status" in captured.out
    assert "skills" in captured.out
    assert "Run `omnibot -h` to show all commands." in captured.out
    assert captured.err == ""


def test_help_prints_banner_help_without_starting_daemon(monkeypatch, capsys):
    def fail_start(*args, **kwargs):
        raise AssertionError("daemon should not start for --help")

    monkeypatch.setattr(cli.daemon_client, "ensure_daemon", fail_start)

    exit_code = cli.main(["--help"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "omnibot CLI v" in captured.out
    assert "Global Options:" in captured.out
    assert "--api-port" in captured.out
    assert "--no-start" in captured.out
    assert captured.err == ""


def test_top_level_help_lists_read_command(capsys):
    exit_code = cli.main(["--help"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "  read" in captured.out
    assert "Read a page as clean text" in captured.out


def test_skills_no_subcommand_shows_friendly_help(capsys):
    exit_code = cli.main(["skills"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Usage: omnibot skills <command>" in captured.out
    assert "install" in captured.out
    assert "path" in captured.out
    assert "error" not in captured.out.lower()


def test_daemon_no_subcommand_shows_friendly_help(capsys):
    exit_code = cli.main(["daemon"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Usage: omnibot daemon <command>" in captured.out
    assert "run" in captured.out
    assert "start" in captured.out
    assert "stop" in captured.out
    assert "status" in captured.out
    assert "error" not in captured.out.lower()


def test_status_alias_works(capsys):
    exit_code = cli.main(["status"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "status" in captured.out.lower() or "stopped" in captured.out.lower()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


def test_parser_has_bridge_install_commands():
    parser = cli.build_parser()
    command_action = next(action for action in parser._actions if getattr(action, "dest", None) == "command")
    commands = set(command_action.choices.keys())

    assert "install-bridge" in commands
    assert "uninstall-bridge" in commands


def test_install_bridge_auto_detects_extension_id(monkeypatch, capsys):
    calls = {}

    def fail_input(*args, **kwargs):
        raise AssertionError("install-bridge should not prompt for extension ID")

    def fake_ensure_runtime(api_port, ws_port):
        return "http://127.0.0.1:18764"

    def fake_call_action(action, params, base_url):
        assert action == "tabs"
        assert params == {}
        assert base_url == "http://127.0.0.1:18764"
        return {"tabs": [{"browser": "edge", "extension_id": "edge-extension"}]}

    def fake_install_bridge(extension_id, browser=None):
        calls["extension_id"] = extension_id
        calls["browser"] = browser
        return {"status": "success", "launcher": "launcher", "manifest": "manifest", "browser": browser, "extension_id": extension_id}

    def fake_wait_for_bridge(timeout=60.0, interval=1.0):
        return {"device_id": "edge-device"}

    monkeypatch.setattr("builtins.input", fail_input)
    monkeypatch.setattr(cli.daemon_client, "ensure_runtime", fake_ensure_runtime)
    monkeypatch.setattr(cli.daemon_client, "call_action", fake_call_action)
    monkeypatch.setattr("omnibot.bridge_installer.install_bridge", fake_install_bridge)
    monkeypatch.setattr("omnibot.bridge_installer.wait_for_bridge", fake_wait_for_bridge)

    exit_code = cli.main(["install-bridge", "--browser", "edge"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == {"extension_id": "edge-extension", "browser": "edge"}
    assert "Bridge installed" in captured.out
    assert "Bridge connected" in captured.out


def test_install_bridge_help_hides_extension_id(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["install-bridge", "--help"])

    captured = capsys.readouterr()
    assert exc.value.code == 0
    assert "--extension-id" not in captured.out
    assert "--browser" not in captured.out


def test_parser_has_hidden_bridge_host_command():
    parser = cli.build_parser()
    args = parser.parse_args(["bridge-host"])

    assert args.command == "bridge-host"


def test_bridge_host_delegates_to_bridge_host_run(monkeypatch):
    called = {}

    def fake_run():
        called["run"] = True
        return 0

    monkeypatch.setattr("omnibot.bridge_host.run", fake_run)
    exit_code = cli.main(["bridge-host"])

    assert exit_code == 0
    assert called.get("run") is True


def test_top_level_help_does_not_show_native_bridge_commands(capsys):
    exit_code = cli.main(["--help"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "install-bridge" not in captured.out
    assert "uninstall-bridge" not in captured.out
    assert "daemon" in captured.out
    assert "snapshot" in captured.out


def test_doctor_reports_extension_guidance_when_no_tabs(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")
    monkeypatch.setattr(cli.daemon_client, "health", lambda base_url: {"status": "ok", "pid": 123, "tabs_count": 0, "ws_port": 18765})
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    exit_code = cli.main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "success"
    assert payload["daemon"]["status"] == "ok"
    assert payload["extension"]["status"] == "not_connected"
    assert "Load or reload the omnibot browser extension" in payload["extension"]["message"]


def test_doctor_retries_transient_empty_extension_state(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")
    health_results = iter([
        {"status": "ok", "pid": 123, "tabs_count": 0, "extension_clients_count": 0, "ws_port": 18765},
        {"status": "ok", "pid": 123, "tabs_count": 40, "extension_clients_count": 1, "ws_port": 18765},
    ])
    monkeypatch.setattr(cli.daemon_client, "health", lambda base_url: next(health_results))
    sleeps = []
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: sleeps.append(seconds))

    exit_code = cli.main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["extension"]["status"] == "connected"
    assert payload["daemon"]["tabs_count"] == 40
    assert sleeps == [0.2]


def test_doctor_reports_connected_when_extension_client_without_tabs(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")
    monkeypatch.setattr(cli.daemon_client, "health", lambda base_url: {"status": "ok", "pid": 123, "tabs_count": 0, "extension_clients_count": 1, "ws_port": 18765})

    exit_code = cli.main(["doctor"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "success"
    assert payload["daemon"]["status"] == "ok"
    assert payload["extension"]["status"] == "connected"
    assert payload["extension"]["message"] == "Browser extension is connected."


def test_cli_forwards_session_token_to_daemon(monkeypatch, capsys):
    calls = {}

    monkeypatch.setenv("OMNIBOT_SESSION_TOKEN", "worker-a")
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")

    def fake_call_action(action, params, base_url):
        calls["action"] = action
        calls["params"] = params
        calls["base_url"] = base_url
        return {"status": "success", "kind": "title", "value": "fixture"}

    monkeypatch.setattr(cli.daemon_client, "call_action", fake_call_action)

    exit_code = cli.main(["get", "title"])

    assert exit_code == 0
    assert calls == {
        "action": "get",
        "params": {"kind": "title", "selector": None, "attr": None, "switch_tab_id": "", "_token": "worker-a"},
        "base_url": "http://127.0.0.1:18764",
    }


def test_session_token_uses_local_daemon_not_bridge_runtime(monkeypatch):
    args = cli.build_parser().parse_args(["get", "title"])
    calls = []

    monkeypatch.setenv("OMNIBOT_SESSION_TOKEN", "worker-a")
    monkeypatch.setattr(cli.daemon_client, "ensure_daemon", lambda api_port, ws_port: calls.append("daemon") or "http://daemon")
    monkeypatch.setattr(cli.daemon_client, "ensure_runtime", lambda api_port, ws_port: calls.append("runtime") or "http://runtime")

    assert cli._base_url(args) == "http://daemon"
    assert calls == ["daemon"]


def test_parser_has_snapshot_command():
    import omnibot.cli as cli

    parser = cli.build_parser()
    args = parser.parse_args(["snapshot", "--interactive", "--compact", "--depth", "3", "--selector", "#main", "--urls", "--json"])

    assert args.command == "snapshot"
    assert args.interactive is True
    assert args.compact is True
    assert args.max_depth == 3
    assert args.selector == "#main"
    assert args.urls is True
    assert args.json is True


def test_screenshot_parser_supports_p0_options():
    args = cli.build_parser().parse_args(["screenshot", "--full", "--annotate", "--ref", "@e7", "--screenshot-format", "jpeg", "--screenshot-quality", "80", "--screenshot-dir", "shots"])

    assert args.command == "screenshot"
    assert args.full is True
    assert args.annotate is True
    assert args.screenshot_format == "jpeg"
    assert args.screenshot_quality == 80
    assert args.screenshot_dir == "shots"
    assert args.ref == "@e7"


def test_parser_has_text_input_commands():
    parser = cli.build_parser()

    assert parser.parse_args(["fill", "#email", "a@b.com"]).command == "fill"
    assert parser.parse_args(["type", "#email", "abc"]).command == "type"
    assert parser.parse_args(["press", "Enter"]).command == "press"
    assert parser.parse_args(["keyboard", "type", "hello"]).keyboard_command == "type"
    assert parser.parse_args(["keyboard", "inserttext", "hello"]).keyboard_command == "inserttext"
    assert parser.parse_args(["keydown", "Shift"]).command == "keydown"
    assert parser.parse_args(["keyup", "Shift"]).command == "keyup"


def test_top_level_command_list_includes_public_interactions():
    command_names = {name for name, _description in cli.COMMANDS}

    for name in ["focus", "keyboard", "keydown", "keyup"]:
        assert name in command_names


def test_parser_has_remaining_p1_core_interactions():
    parser = cli.build_parser()
    for argv in [
        ["hover", "#menu"],
        ["focus", "#email"],
        ["select", "#country", "US"],
        ["check", "#terms"],
        ["uncheck", "#terms"],
        ["scroll", "down", "500"],
        ["scrollintoview", "#footer"],
        ["drag", "#source", "#target"],
        ["upload", "input[type=file]", "README.md"],
    ]:
        assert parser.parse_args(argv).command == argv[0]


def test_parser_has_get_and_is_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["get", "title"]).command == "get"
    assert parser.parse_args(["get", "text", "#main"]).get_command == "text"
    assert parser.parse_args(["get", "attr", "a.login", "href"]).get_command == "attr"
    assert parser.parse_args(["is", "visible", "#submit"]).is_command == "visible"
    assert parser.parse_args(["is", "hidden", "#submit"]).is_command == "hidden"
    assert parser.parse_args(["is", "enabled", "#submit"]).is_command == "enabled"


def test_parser_has_find_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["find", "role", "button"]).find_command == "role"
    assert parser.parse_args(["find", "text", "Sign in"]).find_command == "text"
    assert parser.parse_args(["find", "nth", ".card", "2"]).find_command == "nth"


def test_parser_has_tab_frame_and_navigation_aliases():
    parser = cli.build_parser()
    assert parser.parse_args(["open", "https://example.com"]).command == "open"
    assert parser.parse_args(["goto", "https://example.com"]).command == "goto"
    assert parser.parse_args(["close"]).command == "close"
    assert parser.parse_args(["tab", "new", "https://docs.example.com"]).tab_command == "new"
    assert parser.parse_args(["tab", "close", "docs"]).tab_command == "close"
    assert parser.parse_args(["window", "new"]).window_command == "new"
    assert parser.parse_args(["frame", "main"]).frame_target == "main"
    assert parser.parse_args(["frame", "payment-frame"]).frame_target == "payment-frame"
    assert parser.parse_args(["back"]).command == "back"
    assert parser.parse_args(["forward"]).command == "forward"
    assert parser.parse_args(["reload"]).command == "reload"
    assert parser.parse_args(["pushstate", "/dashboard"]).command == "pushstate"


def test_frame_action_accepts_named_frame_target():
    parser = cli.build_parser()

    action, params, as_json = cli.action_request_from_args(parser.parse_args(["frame", "payment-frame"]))

    assert action == "frame"
    assert params == {"frame_target": "payment-frame"}
    assert as_json is True


def test_frame_main_dispatches_named_frame_target(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(cli.daemon_client, "ensure_daemon", lambda api_port, ws_port: "http://daemon")
    monkeypatch.setattr(cli.daemon_client, "daemon_url", lambda port=None: "http://daemon")

    def fake_call_action(action, params, base_url, timeout=None):
        calls.append((action, params, base_url))
        return {"status": "success", "frame": params["frame_target"]}

    monkeypatch.setattr(cli.daemon_client, "call_action", fake_call_action)

    assert cli.main(["--no-start", "frame", "payment-frame"]) == 0

    assert calls == [("frame", {"frame_target": "payment-frame"}, "http://daemon")]
    assert json.loads(capsys.readouterr().out)["frame"] == "payment-frame"


def test_history_navigation_commands_accept_tab_id():
    parser = cli.build_parser()

    for argv in [
        ["back", "--tab-id", "tab-123"],
        ["forward", "--tab-id", "tab-123"],
        ["reload", "--tab-id", "tab-123"],
        ["pushstate", "/dashboard", "--tab-id", "tab-123"],
    ]:
        args = parser.parse_args(argv)
        assert args.switch_tab_id == "tab-123"


def test_history_navigation_actions_forward_tab_id():
    parser = cli.build_parser()

    cases = [
        (["back", "--tab-id", "tab-123"], "back", {"switch_tab_id": "tab-123"}),
        (["forward", "--tab-id", "tab-123"], "forward", {"switch_tab_id": "tab-123"}),
        (["reload", "--tab-id", "tab-123"], "reload", {"switch_tab_id": "tab-123"}),
        (["pushstate", "/dashboard", "--tab-id", "tab-123"], "pushstate", {"url": "/dashboard", "switch_tab_id": "tab-123"}),
    ]
    for argv, expected_action, expected_params in cases:
        action, params, as_json = cli.action_request_from_args(parser.parse_args(argv))
        assert action == expected_action
        assert params == expected_params
        assert as_json is True


def test_parser_has_mouse_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["mouse", "click", "--x", "100", "--y", "200"]).mouse_command == "click"
    assert parser.parse_args(["mouse", "move", "--x", "50", "--y", "60"]).mouse_command == "move"
    assert parser.parse_args(["mouse", "scroll", "--x", "100", "--y", "200", "--dy", "500"]).mouse_command == "scroll"
    assert parser.parse_args(["mouse", "drag", "--from-x", "10", "--from-y", "20", "--to-x", "100", "--to-y", "200"]).mouse_command == "drag"


def test_parser_has_dom_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["dom", "visible"]).dom_command == "visible"
    assert parser.parse_args(["dom", "click", "n1"]).dom_command == "click"
    assert parser.parse_args(["dom", "dblclick", "n1"]).dom_command == "dblclick"
    assert parser.parse_args(["dom", "scroll", "n1", "--dy", "800"]).dom_command == "scroll"


def test_parser_has_console_network_cdp_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["console", "logs"]).console_command == "logs"
    assert parser.parse_args(["console", "errors"]).console_command == "errors"
    assert parser.parse_args(["console", "clear"]).console_command == "clear"
    assert parser.parse_args(["dialog", "logs"]).dialog_command == "logs"
    assert parser.parse_args(["dialog", "clear"]).dialog_command == "clear"
    assert parser.parse_args(["dialog", "handle", "accept"]).dialog_command == "handle"
    assert parser.parse_args(["dialog", "handle", "dismiss"]).choice == "dismiss"
    assert parser.parse_args(["dialog", "handle", "accept", "--text", "hello"]).text == "hello"
    assert parser.parse_args(["network", "logs"]).network_command == "logs"
    assert parser.parse_args(["network", "summary"]).network_command == "summary"
    assert parser.parse_args(["network", "start"]).network_command == "start"
    assert parser.parse_args(["network", "stop"]).network_command == "stop"
    assert parser.parse_args(["network", "clear"]).network_command == "clear"
    assert parser.parse_args(["cdp", "Runtime.evaluate"]).method == "Runtime.evaluate"


def test_dialog_actions_forward_tab_id_and_acceptance():
    parser = cli.build_parser()

    cases = [
        (["dialog", "logs", "--tab-id", "tab-123"], "dialog_logs", {"tab_id": "tab-123"}),
        (["dialog", "clear", "--tab-id", "tab-123"], "dialog_clear", {"tab_id": "tab-123"}),
        (["dialog", "handle", "accept", "--tab-id", "tab-123"], "dialog_handle", {"tab_id": "tab-123", "accept": True}),
        (["dialog", "handle", "dismiss", "--tab-id", "tab-123"], "dialog_handle", {"tab_id": "tab-123", "accept": False}),
        (["dialog", "handle", "accept", "--text", "hello", "--tab-id", "tab-123"], "dialog_handle", {"tab_id": "tab-123", "accept": True, "prompt_text": "hello"}),
    ]
    for argv, expected_action, expected_params in cases:
        action, params, as_json = cli.action_request_from_args(parser.parse_args(argv))
        assert action == expected_action
        assert params == expected_params
        assert as_json is True


def test_parser_has_clipboard_viewport_assets_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["clipboard", "read"]).clipboard_command == "read"
    assert parser.parse_args(["clipboard", "write", "hello"]).clipboard_command == "write"
    assert parser.parse_args(["viewport", "get"]).viewport_command == "get"
    assert parser.parse_args(["viewport", "set", "1280", "720"]).viewport_command == "set"
    assert parser.parse_args(["assets", "list"]).assets_command == "list"
    assert parser.parse_args(["assets", "export", "-o", "out.zip"]).assets_command == "export"


def test_parser_has_browser_session_record_trace_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["browser", "list"]).browser_command == "list"
    assert parser.parse_args(["browser", "current"]).browser_command == "current"
    assert parser.parse_args(["browser", "claim", "tab-1"]).browser_command == "claim"
    assert parser.parse_args(["browser", "release", "tab-1"]).browser_command == "release"
    assert parser.parse_args(["session", "name", "checkout"]).session_command == "name"
    assert parser.parse_args(["session", "list"]).session_command == "list"
    assert parser.parse_args(["record", "start"]).record_command == "start"
    assert parser.parse_args(["record", "stop"]).record_command == "stop"
    assert parser.parse_args(["replay", "flow.json"]).flow_file == "flow.json"
    assert parser.parse_args(["trace", "start"]).trace_command == "start"
    assert parser.parse_args(["trace", "stop"]).trace_command == "stop"


def test_replay_cli_extracts_actions_from_recorded_flow(tmp_path, monkeypatch):
    flow_path = tmp_path / "flow.json"
    actions_list = [{"action": "get", "params": {"kind": "title", "switch_tab_id": "tab-1"}}]
    flow_path.write_text(json.dumps({"actions": actions_list}), encoding="utf-8")
    captured = {}

    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")
    monkeypatch.setattr(
        cli.daemon_client,
        "call_action",
        lambda action, params, base_url, **kwargs: captured.update(action=action, params=params, base_url=base_url) or {"status": "success"},
    )

    assert cli.main(["replay", str(flow_path)]) == 0
    assert captured == {
        "action": "replay",
        "params": {"flow": actions_list},
        "base_url": "http://127.0.0.1:18764",
    }


def test_parser_has_visibility_commands():
    parser = cli.build_parser()
    assert parser.parse_args(["visibility", "status"]).visibility_command == "status"
    assert parser.parse_args(["visibility", "set", "headless"]).visibility_command == "set"
    assert parser.parse_args(["visibility", "set", "headless"]).mode == "headless"
    assert parser.parse_args(["visibility", "launch", "headless", "--user-data-dir", "/tmp/test"]).visibility_command == "launch"


def test_wait_parser_supports_p1_modes():
    parser = cli.build_parser()
    assert parser.parse_args(["wait", "#ready"]).wait_target == "#ready"
    assert parser.parse_args(["wait", "500"]).wait_target == "500"
    assert parser.parse_args(["wait", "--text", "Welcome"]).text == "Welcome"
    assert parser.parse_args(["wait", "--url", "/dashboard"]).url == "/dashboard"
    assert parser.parse_args(["wait", "--load"]).load == "load"
    assert parser.parse_args(["wait", "--load", "--timeout", "5"]).load == "load"
    assert parser.parse_args(["wait", "--load", "domcontentloaded"]).load == "domcontentloaded"
    assert parser.parse_args(["wait", "--fn", "window.ready === true"]).fn == "window.ready === true"
    assert parser.parse_args(["wait", "#spinner", "--state", "hidden"]).state == "hidden"


def test_read_default_prints_content_not_python_dict(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")

    def fake_call_action(action, params, base_url):
        assert action == "read"
        assert params == {"url": "https://example.com", "screens": 5, "switch_tab_id": ""}
        assert base_url == "http://127.0.0.1:18764"
        return {"status": "success", "content": "# Title\n> https://example.com/\n\nBody\n"}

    monkeypatch.setattr(cli.daemon_client, "call_action", fake_call_action)

    exit_code = cli.main(["read", "https://example.com"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == "# Title\n> https://example.com/\n\nBody\n\n"
    assert "{'status'" not in captured.out


def test_snapshot_default_prints_content_not_python_dict(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")

    def fake_call_action(action, params, base_url):
        assert action == "snapshot"
        assert params == {
            "interactive": True,
            "compact": False,
            "max_depth": None,
            "selector": "",
            "include_urls": False,
            "switch_tab_id": "tab-1",
        }
        assert base_url == "http://127.0.0.1:18764"
        return {"status": "success", "content": '@e1 [button] "Submit"\n# DOM Popup Controls\n'}

    monkeypatch.setattr(cli.daemon_client, "call_action", fake_call_action)

    exit_code = cli.main(["snapshot", "-i", "--tab-id", "tab-1"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == '@e1 [button] "Submit"\n# DOM Popup Controls\n\n'
    assert "{'status'" not in captured.out


def test_snapshot_default_keeps_errors_structured(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")
    monkeypatch.setattr(
        cli.daemon_client,
        "call_action",
        lambda action, params, base_url: {"status": "error", "msg": "No browser tabs connected."},
    )

    exit_code = cli.main(["snapshot", "-i", "--tab-id", "tab-1"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert json.loads(captured.out) == {
        "status": "error",
        "error_code": "NO_BROWSER_TABS",
        "msg": "No browser tabs connected.",
    }


def test_cli_preserves_daemon_error_code_and_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")
    monkeypatch.setattr(
        cli.daemon_client,
        "call_action",
        lambda action, params, base_url: {
            "status": "error",
            "error_code": "EXTENSION_DISCONNECTED",
            "msg": "Browser extension is not connected.",
        },
    )

    exit_code = cli.main(["get", "title", "--tab-id", "tab-1"])

    assert exit_code == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "EXTENSION_DISCONNECTED"


def test_cli_classifies_browser_no_tab_error(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")
    monkeypatch.setattr(
        cli.daemon_client,
        "call_action",
        lambda action, params, base_url: {
            "status": "error",
            "msg": "No tab with given id 123.",
        },
    )

    assert cli.main(["get", "title", "--tab-id", "123"]) == 1
    assert json.loads(capsys.readouterr().out)["error_code"] == "TAB_NOT_FOUND"


def test_heavy_command_timeout_is_used_for_daemon_request_not_action_params(monkeypatch, capsys):
    calls = {}
    monkeypatch.setattr(cli, "_base_url", lambda args: "http://127.0.0.1:18764")

    def fake_call_action(action, params, base_url, timeout=60):
        calls["action"] = action
        calls["params"] = params
        calls["base_url"] = base_url
        calls["timeout"] = timeout
        return {"status": "success", "content": "# Title\n"}

    monkeypatch.setattr(cli.daemon_client, "call_action", fake_call_action)

    exit_code = cli.main(["read", "https://example.com", "--timeout", "120"])

    assert exit_code == 0
    assert calls == {
        "action": "read",
        "params": {"url": "https://example.com", "screens": 5, "switch_tab_id": ""},
        "base_url": "http://127.0.0.1:18764",
        "timeout": 120,
    }


def test_full_scan_command_is_removed():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["full-scan"])


def test_parser_rejects_explore_command():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["explore"])
    with pytest.raises(SystemExit):
        parser.parse_args(["explore", "run", "https://example.com", "--goal", "search products"])


def test_skills_parser_rejects_generated_site_options():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["skills", "install", "--agent", "opencode", "--site", "xhs"])
    with pytest.raises(SystemExit):
        parser.parse_args(["skills", "install", "--agent", "opencode", "--all-sites"])
    with pytest.raises(SystemExit):
        parser.parse_args(["skills", "list-sites"])


def test_mouse_drag_cli_accepts_realistic_flags():
    parser = cli.build_parser()
    args = parser.parse_args([
        "mouse", "drag",
        "--from-x", "10", "--from-y", "20",
        "--to-x", "100", "--to-y", "200",
        "--duration-ms", "1200",
        "--steps", "80",
        "--jitter", "1.5",
        "--overshoot", "4",
        "--tab-id", "123",
    ])
    assert args.mouse_command == "drag"
    assert args.duration_ms == 1200
    assert args.steps == 80
    assert args.jitter == 1.5
    assert args.overshoot == 4
    assert args.fast is False


def test_mouse_drag_cli_fast_flag_defaults_false_and_can_be_set():
    parser = cli.build_parser()
    default_args = parser.parse_args([
        "mouse", "drag",
        "--from-x", "0", "--from-y", "0", "--to-x", "1", "--to-y", "1",
    ])
    assert default_args.fast is False

    fast_args = parser.parse_args([
        "mouse", "drag",
        "--from-x", "0", "--from-y", "0", "--to-x", "1", "--to-y", "1",
        "--fast",
    ])
    assert fast_args.fast is True


def test_mouse_drag_action_request_maps_realistic_params():
    parser = cli.build_parser()
    args = parser.parse_args([
        "mouse", "drag",
        "--from-x", "10", "--from-y", "20",
        "--to-x", "100", "--to-y", "200",
        "--duration-ms", "900",
        "--steps", "60",
        "--jitter", "2.0",
        "--overshoot", "5",
        "--fast",
        "--tab-id", "tab-9",
    ])
    action, params, as_json = cli.action_request_from_args(args)
    assert action == "mouse_drag"
    assert params == {
        "from_x": 10.0, "from_y": 20.0,
        "to_x": 100.0, "to_y": 200.0,
        "duration_ms": 900,
        "steps": 60,
        "jitter": 2.0,
        "overshoot": 5.0,
        "fast": True,
        "switch_tab_id": "tab-9",
    }
    assert as_json is True


def test_mouse_drag_action_request_defaults_when_flags_omitted():
    parser = cli.build_parser()
    args = parser.parse_args([
        "mouse", "drag",
        "--from-x", "0", "--from-y", "0", "--to-x", "1", "--to-y", "1",
    ])
    action, params, _ = cli.action_request_from_args(args)
    assert action == "mouse_drag"
    # Omitted flags must map to None so the action falls back to its own defaults.
    assert params["duration_ms"] is None
    assert params["steps"] is None
    assert params["jitter"] is None
    assert params["overshoot"] is None
    assert params["fast"] is False
