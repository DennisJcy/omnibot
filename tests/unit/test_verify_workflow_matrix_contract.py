import base64
import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tests" / "e2e" / "verify_workflow_matrix_test.py"
spec = importlib.util.spec_from_file_location("verify_workflow_matrix_test", MODULE_PATH)
matrix = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["verify_workflow_matrix_test"] = matrix
spec.loader.exec_module(matrix)


def test_cases_cover_requested_yidun_trial_types():
    assert set(matrix.CASES) == {"jigsaw", "picture_click", "word_group", "avoid", "icon_click"}
    assert matrix.CASES["jigsaw"].url.endswith("/trial/jigsaw")
    assert matrix.CASES["picture_click"].url.endswith("/trial/picture-click")
    assert matrix.CASES["word_group"].url.endswith("/trial/word-group")
    assert matrix.CASES["avoid"].url.endswith("/trial/avoid")
    assert matrix.CASES["icon_click"].url.endswith("/trial/icon-click")


def test_normalize_solver_output_accepts_single_action():
    output = matrix.normalize_solver_output({"type": "click", "x": 10, "y": 20})
    assert output == {"status": "success", "actions": [{"type": "click", "x": 10, "y": 20}]}


def test_normalize_solver_output_rejects_unknown_action():
    output = matrix.normalize_solver_output({"actions": [{"type": "keyboard", "key": "A"}]})
    assert output["status"] == "error"
    assert "unsupported" in output["msg"]


def test_normalize_solver_output_preserves_skip():
    output = matrix.normalize_solver_output({"status": "skip", "reason": "needs vision"})
    assert output == {"status": "skip", "reason": "needs vision"}


def test_save_panel_image_writes_png(tmp_path):
    encoded = base64.b64encode(b"png-bytes").decode()
    path = matrix.save_panel_image({"images": {"panel_base64": encoded}}, tmp_path, "jigsaw", 3)
    assert path is not None
    assert Path(path).name == "jigsaw-003-panel.png"
    assert Path(path).read_bytes() == b"png-bytes"


def test_summarize_scores_attempted_cases_only():
    results = [
        matrix.IterationResult("jigsaw", 1, "passed"),
        matrix.IterationResult("jigsaw", 2, "failed"),
        matrix.IterationResult("jigsaw", 3, "inspect_only"),
        matrix.IterationResult("icon_click", 1, "skipped"),
    ]
    summary = matrix.summarize(results)
    assert summary["cases"]["jigsaw"]["attempted"] == 2
    assert summary["cases"]["jigsaw"]["score"] == 0.5
    assert summary["cases"]["icon_click"]["attempted"] == 0
    assert summary["cases"]["icon_click"]["score"] is None


def test_wait_for_registered_tab_matches_raw_tab_id(monkeypatch):
    monkeypatch.setattr(matrix.time, "sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        matrix,
        "run_omnibot",
        lambda *_args, **_kwargs: {"tabs": [{"id": "client:123", "tab_id": "123", "url": "https://dun.163.com/trial/jigsaw"}]},
    )
    assert matrix.wait_for_registered_tab("https://dun.163.com/trial/jigsaw", "client:123", token="t") == "client:123"


def test_real_trial_page_validation_rejects_wrong_host_and_path():
    case = matrix.CASES["jigsaw"]

    ok, error = matrix.validate_real_trial_page(case, {"url": "https://example.com/trial/jigsaw"})
    assert not ok
    assert "dun.163.com" in error

    ok, error = matrix.validate_real_trial_page(case, {"url": "https://dun.163.com/trial/icon-click"})
    assert not ok
    assert "/trial/jigsaw" in error


def test_real_trial_page_validation_accepts_expected_yidun_page():
    case = matrix.CASES["jigsaw"]

    ok, error = matrix.validate_real_trial_page(case, {"url": "https://dun.163.com/trial/jigsaw?foo=1"})
    assert ok
    assert error is None


def test_visual_artifact_validation_requires_nonempty_page_and_panel_images(tmp_path):
    page = tmp_path / "page.png"
    panel = tmp_path / "panel.png"
    page.write_bytes(b"page-bytes")
    panel.write_bytes(b"panel-bytes")

    ok, error = matrix.validate_visual_artifacts(str(page), str(panel))
    assert ok
    assert error is None


def test_visual_artifact_validation_rejects_missing_screenshots(tmp_path):
    panel = tmp_path / "panel.png"
    panel.write_bytes(b"panel-bytes")

    ok, error = matrix.validate_visual_artifacts(None, str(panel))
    assert not ok
    assert "page screenshot" in error

    ok, error = matrix.validate_visual_artifacts(str(tmp_path / "missing-page.png"), str(panel))
    assert not ok
    assert "page screenshot" in error


def test_visual_artifact_validation_rejects_missing_panel_image(tmp_path):
    page = tmp_path / "page.png"
    page.write_bytes(b"page-bytes")

    ok, error = matrix.validate_visual_artifacts(str(page), None)
    assert not ok
    assert "panel image" in error


def test_solver_actions_are_converted_from_panel_image_to_viewport_coordinates():
    inspect = {
        "coordinate_map": {
            "panel_box": {"x": 100, "y": 200, "width": 320, "height": 175},
            "panel_image_to_viewport_scale_x": 0.5,
            "panel_image_to_viewport_scale_y": 0.5,
        }
    }
    actions = [
        {"type": "drag", "from_x": 40, "from_y": 300, "to_x": 420, "to_y": 300, "duration_ms": 800},
        {"type": "click", "x": 200, "y": 100},
        {"type": "wait", "seconds": 1},
    ]

    converted = matrix.convert_solver_actions_to_viewport(actions, inspect)

    assert converted[0]["from_x"] == 120
    assert converted[0]["from_y"] == 350
    assert converted[0]["to_x"] == 310
    assert converted[0]["to_y"] == 350
    assert converted[0]["duration_ms"] == 800
    assert converted[0]["steps"] == matrix.MAX_VISION_DRAG_STEPS
    assert converted[1]["x"] == 200
    assert converted[1]["y"] == 250
    assert converted[2] == {"type": "wait", "seconds": 1}


def test_default_solver_requires_vision_api_key(monkeypatch):
    monkeypatch.delenv("VISION_API_KEY", raising=False)

    command, error = matrix.resolve_effective_solver(None)

    assert command is None
    assert "VISION_API_KEY" in error


def test_prepare_and_inspect_clicks_collapsed_control_for_drag_case(monkeypatch):
    calls = []
    responses = [
        {
            "status": "success",
            "found": True,
            "panel_visible": False,
            "elements": {"control": {"x": 10, "y": 20, "width": 100, "height": 40}},
        },
        {
            "status": "success",
            "found": True,
            "panel_visible": False,
            "elements": {"control": {"x": 10, "y": 20, "width": 100, "height": 40}},
        },
        {"status": "success", "found": True, "panel_visible": True},
    ]

    def fake_run(args, **_kwargs):
        calls.append(args)
        if args[:2] == ["verify", "inspect"]:
            return responses.pop(0)
        return {"status": "success"}

    monkeypatch.setattr(matrix, "run_omnibot", fake_run)
    monkeypatch.setattr(matrix.time, "sleep", lambda *_args, **_kwargs: None)

    result = matrix.prepare_and_inspect(matrix.CASES["jigsaw"], "tab-1", token="t", attempts=2)

    assert result["panel_visible"] is True
    assert ["scrollintoview", ".yidun", "--tab-id", "tab-1"] in calls
    assert ["mouse", "move", "--x", "60.0", "--y", "40.0", "--tab-id", "tab-1"] in calls
    assert ["mouse", "click", "--x", "60.0", "--y", "40.0", "--tab-id", "tab-1"] in calls


def test_execute_solver_actions_uses_extended_timeout_for_drag(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return {"status": "success"}

    monkeypatch.setattr(matrix, "run_omnibot", fake_run)

    ok, error = matrix.execute_solver_actions(
        [{"type": "drag", "from_x": 1, "from_y": 2, "to_x": 3, "to_y": 4, "duration_ms": 800, "steps": 100}],
        "tab-1",
        token="t",
    )

    assert ok
    assert error is None
    assert calls[0][1]["timeout"] == matrix.MOUSE_ACTION_TIMEOUT_S


def test_score_visual_verification_labels():
    assert matrix.score_visual_verification({"status": "success", "result": "success_green_arrow"}) == "passed"
    assert matrix.score_visual_verification({"status": "success", "result": "reset_new_image"}) == "failed"
    assert matrix.score_visual_verification({"status": "success", "result": "unclear"}) == "needs_visual_review"
    assert matrix.score_visual_verification({"status": "error", "msg": "bad"}) == "error"


def test_call_visual_verifier_uses_raw_solver_output(monkeypatch):
    captured = {}

    def fake_call(command, payload, *, timeout):
        captured["payload"] = payload
        return {"status": "success", "result": "success_green_arrow", "reason": "green arrow"}

    monkeypatch.setattr(matrix, "call_solver_raw", fake_call)

    result = matrix.call_visual_verifier("/tmp/after.png", before_image_path="/tmp/before.png")

    assert captured["payload"] == {"mode": "verify", "after_image_path": "/tmp/after.png", "before_image_path": "/tmp/before.png"}
    assert result == {"status": "success", "result": "success_green_arrow", "reason": "green arrow"}


def test_wait_for_post_action_stability_polls_until_not_loading(monkeypatch):
    calls = []
    responses = [
        {"status": "success", "state": "loading", "found": True},
        {"status": "success", "state": "ready", "found": True},
    ]

    def fake_run(args, **_kwargs):
        calls.append(args)
        return responses.pop(0)

    monkeypatch.setattr(matrix, "run_omnibot", fake_run)
    monkeypatch.setattr(matrix.time, "sleep", lambda *_args, **_kwargs: None)

    result = matrix.wait_for_post_action_stability("tab-1", token="t")

    assert result["state"] == "ready"
    assert len(calls) == 2


def test_wait_for_post_action_stability_waits_through_error_state(monkeypatch):
    responses = [
        {"status": "success", "state": "loading", "found": True},
        {"status": "success", "state": "error", "found": True},
        {"status": "success", "state": "ready", "found": True},
    ]

    monkeypatch.setattr(matrix, "run_omnibot", lambda *_args, **_kwargs: responses.pop(0))
    monkeypatch.setattr(matrix.time, "sleep", lambda *_args, **_kwargs: None)

    result = matrix.wait_for_post_action_stability("tab-1", token="t")

    assert result["state"] == "ready"
