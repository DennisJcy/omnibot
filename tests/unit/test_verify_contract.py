"""Contract tests for the verify module (human-verification / captcha inspection)."""
from types import SimpleNamespace

import pytest

from omnibot import actions, cli, verify


class FakeDriver:
    def __init__(self, probe_result=None):
        self.calls = []
        self._probe_result = probe_result or {}

    def get_context(self, token=None):
        return SimpleNamespace(
            sessions={"tab-1": SimpleNamespace(created_by_tool=False)},
            tool_created_tabs=set(),
            refs=SimpleNamespace(resolve=lambda ref: None),
        )

    def get_all_sessions(self, token=None):
        return [{"id": "tab-1", "tab_id": "111", "client_id": "edge-x"}]

    def _cancel_tab_close(self, tab_id, token=None):
        pass

    def _schedule_tab_close(self, tab_id, timeout=0, token=None, close=False):
        pass

    def _raw_tab_id(self, tab_id, token=None):
        return str(tab_id)


# ---------------------------------------------------------------------------
# Detection: pure function over a DOM probe result
# ---------------------------------------------------------------------------

def test_classify_detects_yidun_slider_jigsaw():
    probe = {
        "yidun": True,
        "yidun_classes": "yidun yidun--jigsaw",
        "has_jigsaw_img": True,
        "has_bg_img": True,
        "has_slider": True,
    }
    info = verify.classify(probe)
    assert info["provider"] == "netease_yidun"
    assert info["type"] == "slider_jigsaw"
    assert info["action_type"] == "drag"


def test_classify_detects_yidun_text_click():
    probe = {
        "yidun": True,
        "yidun_classes": "yidun yidun--click",
        "has_jigsaw_img": False,
        "has_bg_img": True,
        "has_slider": False,
        "instruction": "请依次点击：红 苹果 飞",
    }
    info = verify.classify(probe)
    assert info["provider"] == "netease_yidun"
    assert info["type"] == "text_click"
    assert info["action_type"] == "click_sequence"


def test_classify_uses_trial_url_when_widget_is_collapsed():
    probe = {
        "yidun": True,
        "url": "https://dun.163.com/trial/icon-click",
        "yidun_classes": "yidun yidun--float",
        "has_jigsaw_img": False,
        "has_slider": False,
    }
    info = verify.classify(probe)
    assert info["type"] == "icon_click"
    assert info["action_type"] == "click_sequence"


def test_classify_returns_none_when_no_captcha():
    probe = {"yidun": False}
    info = verify.classify(probe)
    assert info is None


def test_classify_detects_unknown_yidun_as_generic():
    probe = {
        "yidun": True,
        "yidun_classes": "yidun yidun--something-new",
        "has_jigsaw_img": False,
        "has_bg_img": False,
        "has_slider": False,
    }
    info = verify.classify(probe)
    assert info["provider"] == "netease_yidun"
    assert info["type"] == "unknown"
    assert info["action_type"] == "unknown"


# ---------------------------------------------------------------------------
# Coordinate mapping
# ---------------------------------------------------------------------------

def test_image_to_viewport_maps_correctly():
    box = {"x": 600, "y": 500, "width": 320, "height": 160}
    image_w, image_h = 480, 240
    vx, vy = verify.image_to_viewport(240, 120, box, image_w, image_h)
    # 240/480 * 320 = 160 -> 600+160 = 760
    assert vx == 760
    # 120/240 * 160 = 80 -> 500+80 = 580
    assert vy == 580


def test_capture_clip_adds_page_scroll_to_viewport_box():
    box = {"x": 600, "y": 500, "width": 320, "height": 160}
    clip = verify.capture_clip_from_viewport_box(box, scroll_x=10, scroll_y=290)
    assert clip == {"x": 610, "y": 790, "width": 320, "height": 160, "scale": 1}


def test_panel_image_to_viewport_map_uses_device_pixel_ratio():
    panel = {"x": 785.5, "y": 331, "width": 320, "height": 175}
    mapping = verify.panel_image_coordinate_map(panel, device_pixel_ratio=2)
    assert mapping["panel_image_width"] == 640
    assert mapping["panel_image_height"] == 350
    assert mapping["panel_image_to_viewport_scale_x"] == 0.5
    assert mapping["panel_image_to_viewport_scale_y"] == 0.5
    assert mapping["panel_box"] == panel


# ---------------------------------------------------------------------------
# Action contract
# ---------------------------------------------------------------------------

def test_verify_inspect_action_returns_not_found_when_no_captcha(monkeypatch):
    driver = FakeDriver()

    monkeypatch.setattr(
        "omnibot.verify.probe_page",
        lambda driver, tab_id, token=None: {"yidun": False},
    )

    result = actions.verify_inspect(driver, tab_id="tab-1")
    assert result["status"] == "success"
    assert result["found"] is False


def test_verify_inspect_action_returns_metadata_for_jigsaw(monkeypatch, tmp_path):
    driver = FakeDriver()
    probe = {
        "yidun": True,
        "yidun_classes": "yidun yidun--jigsaw",
        "has_jigsaw_img": True,
        "has_bg_img": True,
        "has_slider": True,
        "instruction": None,
        "bg_img": {"src": "https://x/bg.jpg", "box": {"x": 600, "y": 500, "width": 320, "height": 160}, "natural_width": 480, "natural_height": 240},
        "jigsaw_img": {"src": "https://x/p.png", "box": {"x": 600, "y": 500, "width": 61, "height": 160}, "natural_width": 91, "natural_height": 240},
        "slider": {"box": {"x": 600, "y": 700, "width": 40, "height": 38}},
        "state": "ready",
        "device_pixel_ratio": 2,
    }

    monkeypatch.setattr("omnibot.verify.probe_page", lambda driver, tab_id, token=None: probe)
    monkeypatch.setattr(
        "omnibot.verify.capture_panel_image",
        lambda driver, tab_id, box, token=None: "BASE64PNG",
    )

    result = actions.verify_inspect(driver, tab_id="tab-1")

    assert result["status"] == "success"
    assert result["found"] is True
    assert result["provider"] == "netease_yidun"
    assert result["type"] == "slider_jigsaw"
    assert result["action_type"] == "drag"
    assert result["coordinate_map"]["image_to_viewport_scale_x"] == pytest.approx(320 / 480, rel=1e-3)
    assert result["coordinate_map"]["panel_image_width"] == 640
    assert result["coordinate_map"]["panel_image_to_viewport_scale_x"] == 0.5
    assert result["images"]["panel_base64"] == "BASE64PNG"


# ---------------------------------------------------------------------------
# CLI contract
# ---------------------------------------------------------------------------

def test_verify_inspect_parser_accepts_tab_id_and_image_flags():
    parser = cli.build_parser()
    args = parser.parse_args(["verify", "inspect", "--tab-id", "123"])
    assert args.command == "verify"
    assert args.verify_command == "inspect"
    assert args.tab_id == "123"
    assert args.no_image is False


def test_verify_inspect_parser_supports_no_image_flag():
    parser = cli.build_parser()
    args = parser.parse_args(["verify", "inspect", "--tab-id", "5", "--no-image"])
    assert args.no_image is True


def test_verify_inspect_action_request_maps_correctly():
    parser = cli.build_parser()
    args = parser.parse_args(["verify", "inspect", "--tab-id", "tab-9", "--no-image"])
    action, params, as_json = cli.action_request_from_args(args)
    assert action == "verify_inspect"
    assert params == {"tab_id": "tab-9", "no_image": True}
    assert as_json is True
