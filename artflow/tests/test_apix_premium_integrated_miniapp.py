from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"


def test_vite_no_longer_uses_string_transform_plugins() -> None:
    config = (WEBAPP / "vite.config.js").read_text(encoding="utf-8")

    assert "feed-pinterest-transform" not in config
    assert "replaceRequired" not in config
    assert "plugins: [react()]" in config


def test_miniapp_entrypoint_uses_premium_component() -> None:
    entry = (WEBAPP / "src" / "main.jsx").read_text(encoding="utf-8")

    assert 'import App from "./apix/App.jsx";' in entry
    assert 'import "./apix/apix.css";' in entry
    assert "createRoot" in entry


def test_premium_app_is_integrated_with_real_api_contract() -> None:
    app = (WEBAPP / "src" / "apix" / "App.jsx").read_text(encoding="utf-8")
    api = (WEBAPP / "src" / "apix" / "api.js").read_text(encoding="utf-8")

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


def test_premium_ui_contains_target_visual_system() -> None:
    css = (WEBAPP / "src" / "apix" / "apix.css").read_text(encoding="utf-8")
    app = (WEBAPP / "src" / "apix" / "App.jsx").read_text(encoding="utf-8")

    assert "--bg:#07050c" in css
    assert "--pink:#ff48c6" in css
    assert "--violet:#8a36ff" in css
    assert "--cyan:#27e9ff" in css
    assert ".feedGrid{display:grid;grid-template-columns:repeat(2" in css
    assert ".bottomNav" in css
    assert ".apixHero" in css
    assert "APIX" in app
    assert "AI-искусство нового поколения" in app


def test_demo_mode_is_compact_and_not_empty_light_placeholder() -> None:
    css = (WEBAPP / "src" / "apix" / "apix.css").read_text(encoding="utf-8")
    app = (WEBAPP / "src" / "apix" / "App.jsx").read_text(encoding="utf-8")

    assert "demoNotice" in app
    assert "По этому фильтру пока ничего нет" not in app
    assert "background:#050408" in css
    assert "светлая" not in css.lower()
