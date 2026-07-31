from pathlib import Path


WEBAPP = Path("webapp")
SRC = WEBAPP / "src"
APP = SRC / "v2" / "VelvetApp.jsx"
API = SRC / "v2" / "api.js"
CSS = SRC / "v2" / "velvet-neon.css"
LUXE_CSS = SRC / "v2" / "velvet-luxe.css"
LUXE_BLOCK = WEBAPP / "velvet-luxe.block.jsx"
LUXE_TRANSFORM = WEBAPP / "velvet-luxe-transform.js"


def test_front_v2_is_the_only_vite_entry() -> None:
    main = (SRC / "main.jsx").read_text(encoding="utf-8")
    vite = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")

    assert 'import VelvetApp from "./v2/VelvetApp.jsx"' in main
    assert 'import "./v2/velvet-luxe.css"' in main
    assert "20260801-velvet-luxe-concept-v3" in main
    assert "feedPinterestMiniApp" not in vite
    assert "feedFirstMiniApp" not in vite
    assert "velvetLuxeMiniApp" in vite
    assert "plugins: [velvetLuxeMiniApp(), react()]" in vite


def test_velvet_neon_has_complete_primary_navigation() -> None:
    source = APP.read_text(encoding="utf-8")

    for screen in ("feed", "create", "prompts", "profile"):
        assert f'["{screen}"' in source

    assert "FeedScreen" in source
    assert "CreateScreen" in source
    assert "PromptsScreen" in source
    assert "ProfileScreen" in source
    assert "BottomNavigation" in source


def test_front_v2_uses_existing_backend_contracts() -> None:
    source = APP.read_text(encoding="utf-8")

    required_contracts = (
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
        'api(`/generations/${generation.id}/share`',
        'api(`/generations/${generation.id}/share-library`',
        'api(`/generations/${pollId}`',
        '"/api/v1/ws/generations"',
    )
    for contract in required_contracts:
        assert contract in source


def test_feed_media_stays_inside_mini_app() -> None:
    source = APP.read_text(encoding="utf-8")
    block = LUXE_BLOCK.read_text(encoding="utf-8")

    assert "function FeedViewer" in source
    assert "function GenerationViewer" in source
    assert '`/api/v1/feed/${item.id}/display.webp?index=${safeIndex}`' in source
    assert '`/api/v1/feed/${item.id}/preview.webp?index=${index}`' in block
    assert "luxeViewer" in block
    assert "window.open" not in source


def test_velvet_luxe_design_tokens_and_mobile_layout_exist() -> None:
    base = CSS.read_text(encoding="utf-8")
    luxe = LUXE_CSS.read_text(encoding="utf-8")

    assert "--vn-purple: #812cff" in base
    assert "--luxe-purple: #8b2cff" in luxe
    assert "--luxe-cyan: #00e7df" in luxe
    assert "max-width: 460px" in luxe
    assert ".luxeMasonry" in luxe
    assert "column-count: 2" in luxe
    assert "grid-template-columns: 1fr 1fr 76px 1fr 1fr" in luxe
    assert ".luxeViewerStage" in luxe
    assert "env(safe-area-inset-bottom)" in luxe


def test_luxe_transform_replaces_only_named_components() -> None:
    source = LUXE_TRANSFORM.read_text(encoding="utf-8")

    for component in ("AppHeader", "BottomNavigation", "FeedMedia", "FeedCard", "FeedViewer", "FeedScreen"):
        assert f'replaceFunction(next, "{component}"' in source
    assert "Missing Velvet Luxe section" in source
    assert "AppHeader call target not found" in source


def test_api_layer_preserves_telegram_auth_and_uploads() -> None:
    source = API.read_text(encoding="utf-8")

    assert '"X-Telegram-Init-Data": telegramInitData()' in source
    assert 'fetch("/upload"' in source
    assert "generationFromRealtime" in source
    assert "useResource" in source
