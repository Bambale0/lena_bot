from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
APX = WEBAPP / "src" / "apix"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v4_entrypoint_is_clean_and_does_not_import_legacy_layers() -> None:
    entry = read(WEBAPP / "src" / "main.jsx")

    assert 'import App from "./apix/AppV4.jsx";' in entry
    assert 'import "./apix/apix.v4.css";' in entry
    assert "createRoot" in entry

    for forbidden in [
        "./apix/App.jsx",
        "apix.tokens.css",
        "apix.css",
        "apix-art.css",
        "apix.archive.css",
        "apix.final-pass.css",
        "apix.structural.css",
        "apix.v3.css",
    ]:
        assert forbidden not in entry


def test_v4_app_keeps_real_api_contracts_and_telegram_auth() -> None:
    app = read(APX / "AppV4.jsx")
    api = read(APX / "api.js")

    for path in [
        'api("/me")',
        'api("/feed?source=recent&limit=60")',
        'api("/prompts?source=popular&limit=30")',
        'api("/models/image")',
        'api("/models/video")',
        'api("/history?limit=40")',
        'api("/plans")',
        "api(`/generate/${mode}`",
        "api(`/generations/${result.id}`)",
        "api(`/feed/${item.id}/like`",
        "api(`/feed/${item.id}/link`)",
        "api(`/generations/${item.id}/share`",
    ]:
        assert path in app

    assert "X-Telegram-Init-Data" in api
    assert "X-Web-Auth-Token" in api
    assert 'fetch("/upload"' in api
    assert "`${API_BASE}/photo-prompt`" in api
    assert "webapp.ready?.()" in api
    assert "webapp.expand?.()" in api


def test_v4_media_handling_does_not_render_webp_as_video() -> None:
    app = read(APX / "AppV4.jsx")

    assert "function playableVideo" in app
    assert "/\\.(mp4|mov|webm)(?:$|\\?)/i.test(url)" in app
    assert "item?.gen_type === \"video\" || playableVideo(url)" in app
    assert "playableVideo(src) ? <video" in app
    assert "<img src={src}" in app


def test_v4_visual_system_is_tokenized_touch_safe_and_telegram_safe() -> None:
    css = read(APX / "apix.v4.css")

    for token in [
        "--v4-bg:",
        "--v4-text:",
        "--v4-glass:",
        "--v4-pink:",
        "--v4-violet:",
        "--v4-cyan:",
        "--v4-grad:",
        "--v4-blur:",
    ]:
        assert token in css

    assert "env(safe-area-inset-top)" in css
    assert "env(safe-area-inset-bottom)" in css
    assert "touch-action: manipulation" in css
    assert "backdrop-filter" in css
    assert "-webkit-backdrop-filter" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "overflow-x: hidden" in css


def test_v4_profile_uses_professional_visual_pass() -> None:
    css = read(APX / "apix.v4.css")

    assert "Profile v4 professional pass" in css
    assert ".v4Profile { display: grid; gap: 14px; }" in css
    assert ".v4ProfileCard::before" in css
    assert "grid-template-areas:" in css
    assert ".v4MiniGrid::before" in css
    assert "content: \"Работы\"" in css
    assert "v4MiniGrid div:first-of-type" in css


def test_v4_has_no_legacy_visual_classes_or_labels() -> None:
    app = read(APX / "AppV4.jsx")
    css = read(APX / "apix.v4.css")
    combined = app + "\n" + css

    for forbidden in [
        "apixHero",
        "studioCard",
        "bottomNav",
        "feedFeature",
        "demoNotice",
        "apix.archive",
        "Тренды",
        'label: "AI"',
    ]:
        assert forbidden not in combined

    assert "v4App" in app
    assert "v4Header" in css
    assert "v4Grid" in css
    assert "v4Nav" in css


def test_v4_demo_assets_are_isolated_from_production_contract() -> None:
    app = read(APX / "AppV4.jsx")
    demo = read(APX / "demoData.js")
    assets = read(APX / "archiveAssets.js")

    assert "demoFeed" in app
    assert "demo: !anyReal || !isTelegramRuntime()" in app
    assert "from \"./archiveAssets.js\"" in demo
    assert "data:image/webp;base64" in assets
    assert "data:image/svg+xml" not in assets
