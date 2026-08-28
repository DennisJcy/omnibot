import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tests" / "e2e" / "vision_solver.py"
spec = importlib.util.spec_from_file_location("vision_solver", MODULE_PATH)
solver = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules["vision_solver"] = solver
spec.loader.exec_module(solver)


def test_parse_llm_response_extracts_final_valid_actions_after_invalid_examples():
    content = """
    Example: {"actions": [{"type": "drag", "from_x": slider_x, "from_y": slider_y}]}
    Final answer:
    {"actions": [{"type": "drag", "from_x": 25, "from_y": 330, "to_x": 495, "to_y": 330}]}
    """

    result = solver.parse_llm_response(content)

    assert result == {
        "status": "success",
        "actions": [{"type": "drag", "from_x": 25, "from_y": 330, "to_x": 495, "to_y": 330}],
    }


def test_parse_llm_response_extracts_json_from_markdown_fence():
    content = '```json\n{"actions": [{"type": "click", "x": 10, "y": 20}]}\n```'

    result = solver.parse_llm_response(content)

    assert result == {"status": "success", "actions": [{"type": "click", "x": 10, "y": 20}]}


def test_parse_llm_response_extracts_gap_x_for_jigsaw():
    content = 'The gap center is at approximately x=320. {"gap_x": 318}'

    result = solver.parse_llm_response(content)

    assert result == {"status": "success", "data": {"gap_x": 318.0}}


def test_build_jigsaw_action_uses_dom_slider_and_vision_gap():
    api_result = {"status": "success", "data": {"gap_x": 318.0}}
    elements = {
        "slider": {"x": 786.5, "y": 797, "width": 40, "height": 38},
    }
    coord_map = {
        "panel_box": {"x": 785.5, "y": 621, "width": 320, "height": 175},
        "panel_image_to_viewport_scale_x": 0.5,
    }

    result = solver._build_jigsaw_action_from_gap(api_result, elements, coord_map)

    assert result["status"] == "success"
    action = result["actions"][0]
    assert action["type"] == "drag"
    # Slider center from DOM (exact)
    assert action["from_x"] == 806.5
    assert action["from_y"] == 816.0
    # Gap from vision: panel.x + gap_x_img * scale_x = 785.5 + 318 * 0.5 = 944.5
    assert action["to_x"] == 944.5
    assert action["to_y"] == 816.0


def test_parse_verification_response_accepts_success_green_arrow():
    result = solver.parse_verification_response('{"result": "success_green_arrow", "reason": "green arrow visible"}')

    assert result == {"status": "success", "result": "success_green_arrow", "reason": "green arrow visible"}


def test_parse_verification_response_accepts_reset_new_image():
    result = solver.parse_verification_response('The captcha reset. {"result": "reset_new_image", "reason": "new puzzle displayed"}')

    assert result == {"status": "success", "result": "reset_new_image", "reason": "new puzzle displayed"}


def test_parse_verification_response_rejects_unknown_label():
    result = solver.parse_verification_response('{"result": "maybe", "reason": "not allowed"}')

    assert result["status"] == "error"
    assert "unsupported" in result["msg"]


def test_solve_routes_verify_mode(monkeypatch, tmp_path):
    image = tmp_path / "after.png"
    image.write_bytes(b"png")
    before = tmp_path / "before.png"
    before.write_bytes(b"before")

    def fake_verify(path, before_path=None):
        assert path == str(image)
        assert before_path == str(before)
        return {"status": "success", "result": "success_green_arrow", "reason": "green arrow"}

    monkeypatch.setattr(solver, "verify_captcha_result", fake_verify)

    result = solver.solve({"mode": "verify", "after_image_path": str(image), "before_image_path": str(before)})

    assert result == {"status": "success", "result": "success_green_arrow", "reason": "green arrow"}
