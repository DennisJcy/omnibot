from omnibot import visibility


def test_visibility_modes_are_explicit_and_ordered_by_isolation():
    assert visibility.VISIBILITY_MODES == ["visible", "background", "dedicated-profile", "headless"]


def test_normalize_visibility_mode_rejects_unknown_value():
    assert visibility.normalize_mode("visible") == "visible"
    try:
        visibility.normalize_mode("invisible")
    except ValueError as exc:
        assert "Unsupported visibility mode" in str(exc)
    else:
        raise AssertionError("normalize_mode should reject unsupported modes")


def test_headless_launch_args_include_remote_debugging_and_user_data_dir(tmp_path):
    args = visibility.headless_launch_args("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", tmp_path, 9222)
    assert args[0].endswith("Google Chrome")
    assert "--headless=new" in args
    assert "--remote-debugging-port=9222" in args
    assert f"--user-data-dir={tmp_path}" in args


def test_mode_capabilities_document_real_browser_limitations():
    caps = visibility.mode_capabilities("headless")
    assert caps["uses_user_current_browser"] is False
    assert caps["requires_dedicated_profile"] is True
    assert "extension support depends on Chromium headless extension behavior" in caps["warnings"]


def test_visible_mode_is_default():
    caps = visibility.mode_capabilities(None)
    assert caps["mode"] == "visible"
    assert caps["uses_user_current_browser"] is True
