from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKGROUND_JS = ROOT / "browser-extension" / "background.js"


def test_group_status_does_not_duplicate_tab_groups_group_command():
    source = BACKGROUND_JS.read_text(encoding="utf-8")

    assert "const isTabGroupsGroupCommand = codeObj && codeObj.cmd === 'tabGroups' && codeObj.method === 'group';" in source
    assert "if (!isTabGroupsGroupCommand) {" in source
    assert "handleExtMessage({cmd:'tabGroups', method:'group', tabId: statusTabId, title: data.groupStatus}, {})" in source


def test_tab_groups_get_returns_current_group_metadata():
    source = BACKGROUND_JS.read_text(encoding="utf-8")

    assert "} else if (msg.method === 'get') {" in source
    assert "const group = await callChromeApi(chrome.tabGroups.get, [tab.groupId], chrome.tabGroups);" in source
    assert "title: group.title" in source
    assert "favIconUrl: tab.favIconUrl || null" in source


def test_favicon_restore_falls_back_to_browser_favicon_url_when_dom_links_missing():
    source = BACKGROUND_JS.read_text(encoding="utf-8")

    assert "const originalTab = await chrome.tabs.get(tabId);" in source
    assert "favIconUrl: originalTab.favIconUrl || null" in source
    assert "if (!originals || !originals.length)" in source
    assert "favIconUrl === 'data:,' ? BLANK_FAVICON_SVG : favIconUrl" in source
    assert "appendFallbackFavicon(state.favIconUrl);" in source


def test_favicon_restore_without_saved_state_does_not_install_blank_icon():
    source = BACKGROUND_JS.read_text(encoding="utf-8")

    assert "if (!originals) {" in source
    no_state_block = source[source.find("if (!originals) {"):source.find("return;", source.find("if (!originals) {"))]
    assert "restoreTabFavicon" not in no_state_block
    assert "BLANK_FAVICON_SVG" not in no_state_block


def test_tab_status_cleanup_clears_group_glow_and_favicon_together():
    source = BACKGROUND_JS.read_text(encoding="utf-8")

    assert "if (msg.cmd === 'tabStatus')" in source
    assert "msg.method === 'cleanup'" in source
    assert "await cleanupTabStatus(tabId)" in source
    assert "async function cleanupTabStatus(tabId)" in source
    assert "await chrome.tabs.ungroup(tabId)" in source
    assert "await sendOperationGlow(tabId, 'hide', '')" in source
    assert "await _restoreTabFavicon(tabId)" in source
    assert "tab already gone" in source


def test_completed_statuses_do_not_switch_favicon_to_done_icon():
    source = BACKGROUND_JS.read_text(encoding="utf-8")
    completed_statuses = [
        "已读取",
        "已导航",
        "等待完成",
        "已截图",
        "已操作",
        "已下滑",
        "已上滑",
        "已点击",
        "已执行",
        "已创建",
    ]

    for status in completed_statuses:
        assert f"'{status}': 'done'" not in source


def test_completed_statuses_still_hide_operation_glow():
    source = BACKGROUND_JS.read_text(encoding="utf-8")

    assert "const COMPLETED_STATUSES = new Set([" in source
    assert "const isDone = COMPLETED_STATUSES.has(data.groupStatus);" in source
    assert "sendOperationGlow(statusTabId, isDone ? 'hide' : 'show', data.groupStatus)" in source
