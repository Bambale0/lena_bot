from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
APX = WEBAPP / "src" / "apix"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_vite_no_longer_uses_string_transform_plugins() -> None:
    config = read(WEBAPP / "vite.config.js")

    assert "feed-pinterest-transform" not in config
    assert "replaceRequired" not in config
    assert "plugins: [react()]" in config


def test_miniapp_entrypoint_loads_archive_visual_pass_after_base_styles() -> None:
    entry = read(WEBAPP / "src" / "main.jsx")

    assert 'import App from "./apix/App.jsx";' in entry
    assert 'import "./apix/apix.tokens.css";' in entry
    assert 'import "./apix/apix.css";' in entry
    assert 'import "./apix/apix-art.css";' in entry
    assert 'import "./apix/apix.archive.css";' in entry
    assert entry.index('apix.archive.css') > entry.index('apix-art.css')
    assert "createRoot" in entry


def test_premium_app_is_integrated_with_real_api_contract() -> None:
    app = read(APX / "App.jsx")
    api = read(APX / "api.js")

    required_paths = [
        '"/me"',
        '"/feed?source=recent&limit=60"',
        '"/prompts?source=popular&limit=30"',
        '"/models/image"',
        '"/models/video"',
        '"/history?limit=40"',
        '"/plans"',
        '`/generate/${mode}`',
        '`/generations/${result.id}`',
        '`/feed/${item.id}/like`',
        '`/feed/${item.id}/link`',
        '`/generations/${item.id}/share`',
    ]

    for path in required_paths:
        assert path in app

    assert "X-Telegram-Init-Data" in api
    assert "X-Web-Auth-Token" in api
    assert 'fetch("/upload"' in api
    assert '`${API_BASE}/photo-prompt`' in api


def test_archive_visual_system_is_tokenized_and_content_first() -> None:
    tokens = read(APX / "apix.tokens.css")
    css = read(APX / "apix.archive.css")
    app = read(APX / "App.jsx")

    for token in [
        "--apx-bg: #08070c",
        "--apx-primary: #bb2cff",
        "--apx-violet: #7b4dff",
        "--apx-cyan: #00f0ff",
        "--apx-r-1",
        "--apx-s-1",
    ]:
        assert token in tokens

    assert ".apixHero { min-height: 0" in css
    assert "background: transparent !important" in css
    assert ".feedFeature { display: none !important" in css
    assert ".feedGrid { gap: 10px" in css
    assert ".bottomNav { width: min(396px" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "APIX" in app
    assert "AI-искусство нового поколения" in app


def test_demo_mode_is_compact_and_not_empty_light_placeholder() -> None:
    css = read(APX / "apix.archive.css")
    app = read(APX / "App.jsx")

    assert "demoNotice" in app
    assert "По этому фильтру пока ничего нет" not in app
    assert "#08070c" in css
    assert "светлая" not in css.lower()
    assert ".apixMicroBar { position: fixed" in css


def test_demo_feed_uses_archive_adapted_assets_not_empty_radial_bubbles() -> None:
    demo = read(APX / "demoData.js")
    assets = read(APX / "archiveAssets.js")
    css = read(APX / "apix.archive.css")

    assert "from \"./archiveAssets.js\"" in demo
    assert "preview_urls: []" not in demo
    assert "data:image/svg+xml" in assets
    for key in [
        "portraitNeon",
        "architecture",
        "fashion",
        "car",
        "abstractGlass",
        "product",
        "watch",
        "lounge",
        "editorialSculpture",
    ]:
        assert key in assets
        assert f'demoAsset("{key}")' in demo

    assert "radial-gradient(circle" not in css
    assert ".generatedArt::before, .generatedArt::after { display: none" in css


def test_ui_pass_enforces_touch_targets_and_motion_safety() -> None:
    css = read(APX / "apix.archive.css")

    assert "min-width: 44px" in css
    assert "min-height: 44px" in css
    assert "transition:" in css
    assert "touch-action: manipulation" in css
    assert "prefers-reduced-motion" in css


def test_feed_starts_fast_without_duplicate_rectangular_blocks() -> None:
    css = read(APX / "apix.archive.css")

    assert "/* Content-first rule: the feed is the hero." in css
    assert ".apixHeroCta { display: none; }" in css
    assert ".apixHero { min-height: 0" in css
    assert ".feedFeature { display: none !important; }" in css
    assert "border-radius: 0" in css
    assert "box-shadow: none" in css
    assert "padding: 6px 2px 4px" in css