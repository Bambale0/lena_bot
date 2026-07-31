from pathlib import Path


WEBAPP = Path("webapp")
API = Path("api")
APP = WEBAPP / "src" / "v2" / "VelvetApp.jsx"
STYLES = WEBAPP / "src" / "v2" / "velvet-neon.css"


def test_feed_uses_velvet_neon_masonry_and_filters():
    app = APP.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    for label in ("Для тебя", "Популярное", "Фото", "Видео", "Арт"):
        assert label in app

    assert "FEED_FILTERS" in app
    assert "vnFilterRail" in app
    assert "vnMasonry" in app
    assert "column-count: 2" in styles
    assert "break-inside: avoid" in styles
    assert "position: sticky" in styles


def test_feed_cards_use_lazy_preview_only():
    app = APP.read_text(encoding="utf-8")

    assert "generationPreviewUrls(item)" in app
    assert 'loading="lazy"' in app
    assert 'decoding="async"' in app
    assert "function FeedMedia" in app
    assert "openTelegramLink(url)" not in app


def test_images_open_in_internal_miniapp_viewer():
    app = APP.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "function FeedViewer" in app
    assert 'role="dialog"' in app
    assert "vnViewerStage" in app
    assert "display.webp?index=" in app
    assert "setViewer({ item: selected, index: mediaIndex })" in app
    assert ".vnViewer { position: fixed" in styles
    assert "100dvh" in styles


def test_card_actions_stay_compact_and_explicit():
    app = APP.read_text(encoding="utf-8")
    styles = STYLES.read_text(encoding="utf-8")

    assert "Повторить" in app
    assert 'aria-label="Нравится"' in app
    assert 'aria-label="Поделиться"' in app
    assert "vnCardActions" in app
    assert "grid-template-columns: 1fr auto auto auto" in styles


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


def test_front_v2_limits_feed_and_removes_string_transforms():
    main = (WEBAPP / "src" / "main.jsx").read_text(encoding="utf-8")
    config = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")

    assert "/feed?source=recent&limit=60" in app
    assert "20260801-velvet-neon-front-v2" in main
    assert "feedPinterestMiniApp" not in config
    assert "feedFirstMiniApp" not in config
    assert "plugins: [react()]" in config
