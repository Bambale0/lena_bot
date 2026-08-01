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


def test_miniapp_entrypoint_uses_clean_v4_shell_only() -> None:
    entry = read(WEBAPP / "src" / "main.jsx")

    assert 'import App from "./apix/AppV4.jsx";' in entry
    assert 'import "./apix/apix.v4.css";' in entry
    for legacy in [
        "./apix/App.jsx",
        "apix.tokens.css",
        "apix.css",
        "apix-art.css",
        "apix.archive.css",
        "apix.final-pass.css",
        "apix.structural.css",
        "apix.v3.css",
        "apix.final-pass.js",
    ]:
        assert legacy not in entry
    assert "createRoot" in entry


def test_v4_app_is_integrated_with_real_api_contract() -> None:
    app = read(APX / "AppV4.jsx")
    api = read(APX / "api.js")

    required_paths = [
        '"/me"',
        '"/feed?source=recent&limit=60"',
        '"/prompts?source=popular&limit=30"',
        '"/models/image"',
        '"/models/video"',
        '"/history?limit=40"',
        '"/plans"',
        "`/generate/${mode}`",
        "`/generations/${result.id}`",
        "`/feed/${item.id}/like`",
        "`/feed/${item.id}/link`",
        "`/generations/${item.id}/share`",
    ]

    for path in required_paths:
        assert path in app

    assert "X-Telegram-Init-Data" in api
    assert "X-Web-Auth-Token" in api
    assert 'fetch("/upload"' in api
    assert "`${API_BASE}/photo-prompt`" in api


def test_v4_visual_system_is_not_the_legacy_override_stack() -> None:
    app = read(APX / "AppV4.jsx")
    css = read(APX / "apix.v4.css")

    assert "20260801-apix-v4-clean-shell" in app
    assert "APIX v4 clean shell" in css
    assert ".v4App" in css
    assert ".v4Grid" in css
    assert "column-count: 2" in css
    assert ".v4Nav" in css
    assert "blur(26px) saturate(1.35)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".apixHero" not in css
    assert ".bottomNav" not in css
    assert ".studioCard" not in css


def test_v4_demo_media_is_guarded_against_broken_inline_assets() -> None:
    demo = read(APX / "demoData.js")
    app = read(APX / "AppV4.jsx")

    assert "verifiedDemoAssetKey" in demo
    assert "archiveAssets[verifiedDemoAssetKey(key)]" in demo
    assert "function playableVideo" in app
    assert "playableVideo(src) ? <video" in app
    assert "loading={index < 2 ? \"eager\" : \"lazy\"}" in app


def test_v4_accessibility_and_touch_basics() -> None:
    css = read(APX / "apix.v4.css")
    app = read(APX / "AppV4.jsx")

    assert "button:focus-visible" in css
    assert "button:disabled" in css
    assert "touch-action: manipulation" in css
    assert "role=\"dialog\"" in app
    assert "aria-modal=\"true\"" in app
    assert "aria-label=\"Основная навигация\"" in app
