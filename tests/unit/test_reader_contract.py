from omnibot import reader


def test_format_read_document_adds_title_url_body_and_footnotes():
    extracted = {
        "title": "Example Domain",
        "url": "https://example.com/",
        "blocks": [
            {"type": "heading", "text": "Example Domain", "level": 1},
            {"type": "paragraph", "parts": [{"text": "Learn more", "href": "https://iana.org/domains/example"}]},
        ],
    }

    result = reader.format_read_document(extracted)

    assert result["content"] == "# Example Domain\n> https://example.com/\n\n**Example Domain**\n---\nLearn more [1]\n\n[1] https://iana.org/domains/example\n"
    assert result["links"] == [{"index": 1, "text": "Learn more", "href": "https://iana.org/domains/example"}]


def test_format_read_document_reuses_footnote_for_duplicate_links():
    extracted = {
        "title": "Links",
        "url": "https://site.test/",
        "blocks": [
            {"type": "paragraph", "parts": [{"text": "Profile", "href": "https://x.com/user"}]},
            {"type": "paragraph", "parts": [{"text": "Profile", "href": "https://x.com/user"}]},
        ],
    }

    result = reader.format_read_document(extracted)

    assert result["content"].count("Profile [1]") == 1
    assert result["content"].count("https://x.com/user") == 1
    assert result["links"] == [{"index": 1, "text": "Profile", "href": "https://x.com/user"}]


def test_format_read_document_filters_transient_and_emoji_media_links():
    extracted = {
        "title": "Links",
        "url": "https://x.com/home",
        "blocks": [
            {
                "type": "paragraph",
                "parts": [
                    {"text": "crown", "href": "https://abs.twimg.com/emoji/v2/svg/1f451.svg"},
                    {"text": "video", "href": "blob:https://x.com/abc"},
                    {"text": "inline", "href": "data:image/png;base64,abc"},
                    {"text": "image", "href": "https://pbs.twimg.com/media/example.jpg"},
                ],
            }
        ],
    }

    result = reader.format_read_document(extracted)

    assert "abs.twimg.com/emoji" not in result["content"]
    assert "blob:https://x.com" not in result["content"]
    assert "data:image" not in result["content"]
    assert result["links"] == [{"index": 1, "text": "image", "href": "https://pbs.twimg.com/media/example.jpg"}]


def test_format_read_document_filters_malformed_http_links_and_keeps_protocol_relative_links():
    extracted = {
        "title": "Link Edge Cases",
        "url": "https://example.test/articles/index.html",
        "blocks": [{
            "type": "paragraph",
            "parts": [
                {"text": "Broken scheme only", "href": "http://"},
                {"text": "Broken host", "href": "https:///missing-host"},
                {"text": "Protocol relative", "href": "//cdn.example.test/asset.html"},
            ],
        }],
    }

    result = reader.format_read_document(extracted)

    assert result["links"] == [{
        "index": 1,
        "text": "Protocol relative",
        "href": "https://cdn.example.test/asset.html",
    }]


def test_format_read_document_uses_raw_href_before_browser_resolution():
    extracted = {
        "title": "Raw Href",
        "url": "https://example.test/index.html",
        "blocks": [{
            "type": "paragraph",
            "parts": [{
                "text": "Broken host",
                "href": "https://missing-host/",
                "rawHref": "https:///missing-host",
            }],
        }],
    }

    result = reader.format_read_document(extracted)

    assert result["links"] == []


def test_format_read_document_preserves_browser_resolution_for_base_relative_links():
    extracted = {
        "title": "Base Links",
        "url": "https://example.test/index.html",
        "blocks": [{
            "type": "paragraph",
            "parts": [{
                "text": "Topic",
                "href": "https://example.test/base/topic.html?x=1#part",
                "rawHref": "topic.html?x=1#part",
            }],
        }],
    }

    result = reader.format_read_document(extracted)

    assert result["links"] == [{
        "index": 1,
        "text": "Topic",
        "href": "https://example.test/base/topic.html?x=1#part",
    }]


def test_format_read_document_filters_hacker_news_vote_action_links():
    extracted = {
        "title": "Hacker News",
        "url": "https://news.ycombinator.com/",
        "blocks": [
            {
                "type": "paragraph",
                "parts": [
                    {
                        "text": "https://news.ycombinator.com/vote?id=48838876&how=up&goto=news",
                        "href": "https://news.ycombinator.com/vote?id=48838876&how=up&goto=news",
                    },
                    {
                        "text": "John Deere owners will get the right to repair equipment under FTC settlement",
                        "href": "https://apnews.com/article/john-deere-right-to-repair-agriculture-equipment-cb7514ffedb95c130a976af661f2bc02",
                    },
                ],
            }
        ],
    }

    result = reader.format_read_document(extracted)

    assert "news.ycombinator.com/vote" not in result["content"]
    assert result["links"] == [
        {
            "index": 1,
            "text": "John Deere owners will get the right to repair equipment under FTC settlement",
            "href": "https://apnews.com/article/john-deere-right-to-repair-agriculture-equipment-cb7514ffedb95c130a976af661f2bc02",
        }
    ]


def test_format_read_document_filters_hacker_news_hide_action_links():
    extracted = {
        "title": "Hacker News",
        "url": "https://news.ycombinator.com/",
        "blocks": [
            {
                "type": "paragraph",
                "parts": [
                    {"text": "hide", "href": "https://news.ycombinator.com/hide?id=48838876&goto=news"},
                    {"text": "42 comments", "href": "https://news.ycombinator.com/item?id=48838876"},
                ],
            }
        ],
    }

    result = reader.format_read_document(extracted)

    assert "news.ycombinator.com/hide" not in result["content"]
    assert result["links"] == [
        {"index": 1, "text": "42 comments", "href": "https://news.ycombinator.com/item?id=48838876"}
    ]


def test_format_read_document_falls_back_to_x_title_for_x_home():
    extracted = {"title": "Untitled", "url": "https://x.com/home", "blocks": []}

    result = reader.format_read_document(extracted)

    assert result["content"].startswith("# X\n> https://x.com/home")


def test_format_read_document_labels_x_analytics_counts():
    extracted = {
        "title": "X",
        "url": "https://x.com/home",
        "blocks": [
            {
                "type": "article",
                "parts": [
                    {"text": "Post body"},
                    {"text": "5"},
                    {"text": "6"},
                    {"text": "23"},
                    {"text": "4186 views", "href": "https://x.com/user/status/1/analytics"},
                ],
            }
        ],
    }

    result = reader.format_read_document(extracted)

    assert "5 Replies 6 reposts 23 Likes 4186 views [1]" in result["content"]
    assert "5 6 23 4186 views" not in result["content"]


def test_format_read_document_keeps_quote_prefixes():
    extracted = {
        "title": "Thread",
        "url": "https://x.com/home",
        "blocks": [
            {"type": "quote", "parts": [{"text": "Claude @claudeai · 17h"}]},
            {"type": "quote", "parts": [{"text": "Introducing Claude Fable 5"}]},
        ],
    }

    result = reader.format_read_document(extracted)

    assert "> Claude @claudeai · 17h" in result["content"]
    assert "> Introducing Claude Fable 5" in result["content"]


def test_format_read_document_separates_articles_with_rules():
    extracted = {
        "title": "Home / X",
        "url": "https://x.com/home",
        "blocks": [
            {"type": "article", "parts": [{"text": "Google AI @GoogleAI · 19h"}]},
            {"type": "article", "parts": [{"text": "Miguel @Miguel07Code · 15h"}]},
        ],
    }

    result = reader.format_read_document(extracted)

    assert "Google AI @GoogleAI · 19h\n---\nMiguel @Miguel07Code · 15h" in result["content"]


def test_read_extraction_script_contains_main_content_and_x_timeline_heuristics():
    script = reader.read_extraction_script(screens=5)

    assert "for (let i = 0; i < screens; i++)" in script
    assert "document.querySelectorAll('article')" in script
    assert "querySelector('main, article, [role=main]')" in script
    assert "querySelectorAll('article, main, section, div, table, tbody')" in script
    assert "el.tagName === 'IMG'" in script
    assert "el.tagName === 'VIDEO'" in script
    assert "el.tagName === 'AUDIO'" in script
    assert "'NAV','HEADER','FOOTER','FORM'" in script
    assert "extractEngagement" in script
    assert "normalizeEngagementLabel" in script
    assert "meaningfulTitle" in script
    assert "href.includes('/analytics')" in script
    assert "getAttribute('href')" in script
    assert "rawHref" in script
    assert "xPhotoHref" in script
    assert "findCdnMediaNear" in script
    assert "findPageCdnMedia" in script
    assert "appendPagePhotoMediaFallback" in script
    assert "photoMediaWaitDeadline" in script
    assert "backgroundImage" in script
    assert "pbs.twimg.com" in script
    assert "tr" in script


def test_read_extraction_script_targets_xhs_note_overlay_containers():
    script = reader.read_extraction_script(screens=1)

    assert "#noteContainer" in script
    assert ".note-content" in script
    assert "#detail-desc" in script
    assert ".comments-container" in script
    assert "overlayPriorityContainer" in script
    assert "isXhsPage" in script


def test_read_extraction_script_targets_markdown_readme_containers():
    script = reader.read_extraction_script(screens=1)

    assert ".markdown-body" in script
    assert ".entry-content" in script
    assert "contentPriorityContainer" in script
    assert "hasReadableText" in script


def test_read_extraction_script_waits_for_priority_content_containers():
    script = reader.read_extraction_script(screens=1)

    assert "priorityContentSelector" in script
    assert "document.querySelector(priorityContentSelector)" in script
    assert "articleWaitStart" in script
    assert "document.readyState === 'complete'" in script
    assert "preferPriorityContent" in script
    assert "priorityWaitMs" in script


def test_read_extraction_script_supports_table_row_pages_like_hn():
    script = reader.read_extraction_script(screens=1)

    assert "const selector = 'h1,h2,h3,p,li,blockquote,pre,figure,article,section,tr,a[href]," in script
    assert "p,li,tr,article,blockquote,h1,h2,h3" in script


def test_read_extraction_script_collects_direct_links_under_main():
    script = reader.read_extraction_script(screens=1)

    assert "const selector = 'h1,h2,h3,p,li,blockquote,pre,figure,article,section,tr,a[href]," in script


def test_read_extraction_script_traverses_open_and_closed_shadow_roots():
    script = reader.read_extraction_script(screens=1)

    assert "el.shadowRoot || el.__omnibotClosedShadowRoot" in script
    assert "const shadowHosts = Array.from(root.querySelectorAll('*'))" in script


def test_read_extraction_script_supports_div_based_note_text():
    script = reader.read_extraction_script(screens=1)

    assert "h1,h2,h3,p,li,blockquote,pre,figure,article,section,tr,a[href],[id=\"detail-desc\"],[class*=\"note-content\"],[class*=\"desc\"]" in script


def test_read_extraction_script_falls_back_to_visible_body_text_for_div_heavy_pages():
    script = reader.read_extraction_script(screens=1)

    assert "appendBodyTextFallback" in script
    assert "document.body.innerText" in script
    assert "blockTextLength" in script


def test_format_read_document_outputs_cdn_media_before_x_photo_fallback():
    extracted = {
        "title": "Home / X",
        "url": "https://x.com/home",
        "blocks": [
            {
                "type": "article",
                "parts": [
                    {"text": "Post body"},
                    {"text": "Image", "href": "https://pbs.twimg.com/media/example?format=jpg&name=large", "media": "img"},
                    {"text": "Image", "href": "https://x.com/user/status/1/photo/1"},
                ],
            }
        ],
    }

    result = reader.format_read_document(extracted)

    assert "https://pbs.twimg.com/media/example?format=jpg&name=large" in result["content"]
    assert "https://x.com/user/status/1/photo/1" in result["content"]


def test_read_extraction_script_clamps_negative_screens_to_zero():
    script = reader.read_extraction_script(screens=-3)

    assert "const screens = 0;" in script


def test_frame_read_extraction_script_is_sync_and_returns_structured_content():
    script = reader.frame_read_extraction_script()

    assert "document.querySelectorAll('body')" in script
    assert "bodyScore" in script
    assert "selectedBodyIndex" in script
    assert "cloneNode(true)" in script
    assert "script,style,noscript,template" in script
    assert "document.querySelectorAll('a[href]')" in script
    assert "frame: true" in script
    assert "await " not in script


from types import SimpleNamespace

from omnibot import actions


def test_read_without_url_requires_explicit_or_token_default_tab(monkeypatch):
    ctx = SimpleNamespace(sessions={}, tool_created_tabs=set(), explicit_target_tabs=set())

    class Driver:
        def get_context(self, token=None):
            return ctx

        def get_all_sessions(self, token=None):
            return [{"id": "edge:100", "tab_id": "100", "url": "https://example.com"}]

    result = actions.read(Driver(), screens=1)

    assert result == {"status": "error", "msg": "tab_id is required. Pass --tab-id <TAB_ID>."}


def test_read_existing_tab_uses_resolved_tab_id_and_formats_content(monkeypatch):
    ctx = SimpleNamespace(sessions={}, tool_created_tabs=set(), explicit_target_tabs=set())
    calls = []

    class Driver:
        def get_context(self, token=None):
            return ctx

        def get_all_sessions(self, token=None):
            return [{"id": "edge:321", "tab_id": "321", "url": "https://example.com"}]

        def _cancel_tab_close(self, tab_id, token=None):
            calls.append(("cancel", tab_id))

        def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=False):
            calls.append(("schedule", tab_id, timeout, close))

        def _raw_tab_id(self, tab_id, token=None):
            return str(tab_id).rsplit(":", 1)[-1]

        def execute_js(self, script, timeout=15, token=None, group_status=None, session_id=None, status_tab_id=None):
            calls.append(("execute", session_id))
            return {"data": {"title": "Example", "url": "https://example.com/", "blocks": [{"type": "paragraph", "parts": [{"text": "Hello"}]}]}}

    result = actions.read(Driver(), screens=1, switch_tab_id="321")

    assert result["status"] == "success"
    assert result["content"].startswith("# Example\n> https://example.com/")
    assert result["metadata"]["tab_id"] == "edge:321"
    assert result["metadata"]["created_tab"] is False
    assert ("execute", "edge:321") in calls
    assert ("schedule", "edge:321", 8, False) in calls


def test_read_explicit_tab_id_takes_precedence_over_url(monkeypatch):
    ctx = SimpleNamespace(sessions={}, tool_created_tabs=set(), explicit_target_tabs=set())
    calls = []

    class Driver:
        def get_context(self, token=None):
            return ctx

        def get_all_sessions(self, token=None):
            return [{"id": "edge:321", "tab_id": "321", "url": "https://x.com/home"}]

        def new_tab(self, url, timeout=15, token=None):
            calls.append(("new_tab", url))
            return {"id": "edge:999", "tab_id": "999", "url": url}

        def _cancel_tab_close(self, tab_id, token=None):
            calls.append(("cancel", tab_id))

        def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=False):
            calls.append(("schedule", tab_id, timeout, close))

        def _raw_tab_id(self, tab_id, token=None):
            return str(tab_id).rsplit(":", 1)[-1]

        def execute_js(self, script, timeout=15, token=None, group_status=None, session_id=None, status_tab_id=None):
            calls.append(("execute", session_id))
            return {"data": {"title": "Home / X", "url": "https://x.com/home", "blocks": [{"type": "paragraph", "parts": [{"text": "Existing tab"}]}]}}

    result = actions.read(Driver(), url="https://x.com/home", screens=3, switch_tab_id="321")

    assert result["status"] == "success"
    assert result["metadata"]["tab_id"] == "edge:321"
    assert result["metadata"]["created_tab"] is False
    assert ("new_tab", "https://x.com/home") not in calls
    assert ("execute", "edge:321") in calls
    assert ("schedule", "edge:321", 8, False) in calls


def test_read_url_creates_tool_tab_and_schedules_close(monkeypatch):
    ctx = SimpleNamespace(sessions={}, tool_created_tabs=set(), explicit_target_tabs=set())
    calls = []

    class Driver:
        def get_context(self, token=None):
            return ctx

        def get_all_sessions(self, token=None):
            return [{"id": "edge:100", "tab_id": "100", "url": "https://start.test"}]

        def new_tab(self, url, timeout=15, token=None):
            calls.append(("new_tab", url))
            ctx.tool_created_tabs.add("edge:999")
            ctx.sessions["edge:999"] = SimpleNamespace(created_by_tool=True)
            return {"id": "edge:999", "tab_id": "999", "url": url}

        def _cancel_tab_close(self, tab_id, token=None):
            calls.append(("cancel", tab_id))

        def _schedule_tab_close(self, tab_id, timeout=60, token=None, close=False):
            calls.append(("schedule", tab_id, timeout, close))

        def _raw_tab_id(self, tab_id, token=None):
            return str(tab_id).rsplit(":", 1)[-1]

        def execute_js(self, script, timeout=15, token=None, group_status=None, session_id=None, status_tab_id=None):
            calls.append(("execute", session_id))
            return {"data": {"title": "X", "url": "https://x.com/home", "blocks": [{"type": "paragraph", "parts": [{"text": "Post"}]}]}}

    result = actions.read(Driver(), url="https://x.com/home", screens=5)

    assert result["status"] == "success"
    assert result["metadata"]["created_tab"] is True
    assert ("new_tab", "https://x.com/home") in calls
    assert ("execute", "edge:999") in calls
    assert ("schedule", "edge:999", actions.TOOL_CREATED_TAB_CLEANUP_TIMEOUT_SECONDS, True) in calls
