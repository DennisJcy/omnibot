from omnibot import page_assets


def test_collect_assets_script_reads_images_styles_fonts_and_media():
    script = page_assets.collect_assets_script()
    assert "performance.getEntriesByType" in script
    assert "document.images" in script
    assert "stylesheets" in script


def test_normalize_asset_keeps_type_url_and_size():
    asset = page_assets.normalize_asset({"type": "image", "url": "https://example.com/a.png", "transferSize": 123})
    assert asset == {"type": "image", "url": "https://example.com/a.png", "size": 123}


def test_normalize_assets_deduplicates_urls_and_prefers_nonzero_size():
    assets = page_assets.normalize_assets(
        [
            {"type": "img", "url": "https://example.com/logo.svg", "transferSize": 630},
            {"type": "image", "url": "https://example.com/logo.svg", "transferSize": 0},
            {"type": "stylesheet", "url": "https://example.com/styles.css", "transferSize": 0},
            {"type": "link", "url": "https://example.com/styles.css", "transferSize": 378},
        ]
    )

    assert assets == [
        {"type": "img", "url": "https://example.com/logo.svg", "size": 630},
        {"type": "link", "url": "https://example.com/styles.css", "size": 378},
    ]
