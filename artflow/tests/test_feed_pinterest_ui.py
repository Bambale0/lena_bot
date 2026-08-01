from pathlib import Path


WEBAPP = Path("webapp")
SRC = WEBAPP / "src" / "concept"
API = Path("api")


def test_concept_entrypoint_has_no_string_transform_plugins() -> None:
    main = (WEBAPP / "src" / "main.jsx").read_text(encoding="utf-8")
    vite = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")

    assert 'import ConceptApp from "./concept/App.jsx"' in main
    assert "20260801-velvet-concept-v1" in main
    assert "plugins: [react()]" in vite
    assert "feedPinterestMiniApp" not in vite
    assert "feedFirstMiniApp" not in vite


def test_feed_matches_concept_composition() -> None:
    source = (SRC / "FeedScreen.jsx").read_text(encoding="utf-8")
    styles = (SRC / "concept.css").read_text(encoding="utf-8")

    for label in ("Для тебя", "Новые", "Популярные"):
        assert label in source
    for label in ("Все", "Фото", "Видео", "Мои"):
        assert label in source

    assert "cxMasonry" in source
    assert "cxFeedCard--" in source
    assert "column-count: 2" in styles
    assert "break-inside: avoid" in styles
    assert "aspect-ratio: .68" in styles
    assert "grid-template-columns: 1fr 1fr 72px 1fr 1fr" in styles


def test_media_stays_inside_mini_app_and_uses_webp_fallbacks() -> None:
    api_source = (SRC / "api.js").read_text(encoding="utf-8")
    components = (SRC / "components.jsx").read_text(encoding="utf-8")

    assert "feedPreviewCandidates" in api_source
    assert "preview.webp?index=" in api_source
    assert "display.webp?index=" in api_source
    assert "function MediaViewer" in components
    assert 'role="dialog"' in components
    assert "window.open" not in components
    assert "ProgressiveMedia" in components


def test_all_primary_product_screens_are_real_components() -> None:
    app = (SRC / "App.jsx").read_text(encoding="utf-8")

    for component in (
        "FeedScreen",
        "CreateScreen",
        "PromptsScreen",
        "ProfileScreen",
        "TopupModal",
    ):
        assert component in app

    for contract in (
        'api("/me")',
        'api("/models/image")',
        'api("/models/video")',
        'api("/feed?source=recent&limit=60")',
        'api("/prompts?limit=60")',
        'api("/history?limit=60")',
        'api("/me/feed?limit=100")',
        '"/generate/image"',
        '"/generate/video"',
        'api(`/feed/${remix.id}/remix`',
        '"/api/v1/ws/generations"',
    ):
        assert contract in app


def test_feed_backend_still_serves_webp_variants() -> None:
    viewer = (API / "feed_media_viewer.py").read_text(encoding="utf-8")
    bootstrap = (API / "__init__.py").read_text(encoding="utf-8")

    assert "FEED_TILE_MAX_SIZE = 480" in viewer
    assert "FEED_VIEW_MAX_SIZE = 1280" in viewer
    assert 'media_type="image/webp"' in viewer
    assert 'preview.webp?index=' in viewer
    assert "install_feed_media_viewer(module)" in bootstrap


def test_design_system_has_premium_hierarchy_and_accessibility() -> None:
    styles = (SRC / "concept.css").read_text(encoding="utf-8")

    assert '"Cormorant Garamond"' in styles
    assert '"Manrope"' in styles
    assert "width: min(100%, 460px)" in styles
    assert "prefers-reduced-motion" in styles
    assert "button:focus-visible" in styles
    assert "env(safe-area-inset-bottom)" in styles
