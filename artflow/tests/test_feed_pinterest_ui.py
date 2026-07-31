from pathlib import Path


WEBAPP = Path("webapp")
API = Path("api")


def test_feed_uses_compact_masonry_and_filters():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")
    styles = (WEBAPP / "src" / "feed-pinterest.css").read_text(encoding="utf-8")

    for label in ("Для тебя", "Новые", "Популярные", "Повторы"):
        assert label in block
    for label in ("Все", "Фото", "Видео"):
        assert label in block

    assert "feedSortRail" in block
    assert "feedTypeTabs" in block
    assert "feedMineToggle" in block
    assert "column-count: 2" in styles
    assert "break-inside: avoid" in styles
    assert "position: sticky" in styles


def test_feed_cards_use_lazy_preview_only():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")

    assert "function feedTileUrls" in block
    assert 'loading="lazy"' in block
    assert 'decoding="async"' in block
    assert 'fetchPriority="low"' in block
    assert "generationResultUrls(item)" not in block
    assert "openExternalUrl" not in block


def test_images_open_in_internal_miniapp_viewer():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")
    styles = (WEBAPP / "src" / "feed-pinterest.css").read_text(encoding="utf-8")

    assert "function FeedViewer" in block
    assert 'role="dialog"' in block
    assert "feedViewerStage" in block
    assert "display.webp?index=" in block
    assert "setViewer({ item: openedItem, index: mediaIndex })" in block
    assert "position: fixed" in styles
    assert "100dvh" in styles


def test_card_actions_stay_compact_and_explicit():
    block = (WEBAPP / "feed-pinterest.block.jsx").read_text(encoding="utf-8")
    styles = (WEBAPP / "src" / "feed-pinterest.css").read_text(encoding="utf-8")

    assert "Повторить" in block
    assert 'aria-label="Нравится"' in block
    assert 'aria-label="Поделиться"' in block
    assert "feedCardActionRow" in block
    assert "grid-template-columns: minmax(0, 1fr) 36px 36px auto" in styles


def test_all_image_feed_media_is_served_as_webp():
    viewer = (API / "feed_media_viewer.py").read_text(encoding="utf-8")
    bootstrap = (API / "__init__.py").read_text(encoding="utf-8")

    assert "FEED_TILE_MAX_SIZE = 480" in viewer
    assert "FEED_VIEW_MAX_SIZE = 1280" in viewer
    assert 'media_type="image/webp"' in viewer
    assert 'preview.webp?index=' in viewer
    assert 'payload["result_url"] = ""' in viewer
    assert 'payload["result_urls"] = []' in viewer
    assert "install_feed_media_viewer(module)" in bootstrap


def test_initial_feed_is_limited_and_build_id_is_bumped():
    config = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")
    transform = (WEBAPP / "feed-pinterest-transform.js").read_text(encoding="utf-8")

    assert "/feed?source=recent&limit=60" in config
    assert "feedPinterestMiniApp" in config
    assert 'import "./feed-pinterest.css"' in transform
    assert "feed-webp-viewer-v4" in transform
