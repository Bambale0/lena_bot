from pathlib import Path


WEBAPP = Path("webapp")
SRC = WEBAPP / "src"
APP = SRC / "v2" / "VelvetApp.jsx"
API = SRC / "v2" / "api.js"
CSS = SRC / "v2" / "velvet-neon.css"


def test_front_v2_is_the_only_vite_entry() -> None:
    main = (SRC / "main.jsx").read_text(encoding="utf-8")
    vite = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")

    assert 'import VelvetApp from "./v2/VelvetApp.jsx"' in main
    assert "20260801-velvet-neon-front-v2" in main
    assert "feedPinterestMiniApp" not in vite
    assert "feedFirstMiniApp" not in vite
    assert "plugins: [react()]" in vite


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

    assert "function FeedViewer" in source
    assert "function GenerationViewer" in source
    assert '`/api/v1/feed/${item.id}/display.webp?index=${safeIndex}`' in source
    assert "setViewer({ item: selected, index: mediaIndex })" in source
    assert "window.open" not in source


def test_velvet_neon_design_tokens_and_mobile_layout_exist() -> None:
    source = CSS.read_text(encoding="utf-8")

    assert "--vn-purple: #812cff" in source
    assert "--vn-cyan: #00e7df" in source
    assert ".vnMasonry" in source
    assert "column-count: 2" in source
    assert ".vnBottomNav" in source
    assert "env(safe-area-inset-bottom)" in source
    assert "@media (max-width: 360px)" in source


def test_api_layer_preserves_telegram_auth_and_uploads() -> None:
    source = API.read_text(encoding="utf-8")

    assert '"X-Telegram-Init-Data": telegramInitData()' in source
    assert 'fetch("/upload"' in source
    assert "generationFromRealtime" in source
    assert "useResource" in source
