from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
APX = WEBAPP / "src" / "apix"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_v4_shell_replaces_legacy_css_stack() -> None:
    entry = read(WEBAPP / "src" / "main.jsx")

    assert 'import App from "./apix/AppV4.jsx";' in entry
    assert 'import "./apix/apix.v4.css";' in entry
    assert "apix.final-pass.js" not in entry
    assert "apix.structural.css" not in entry
    assert "apix.v3.css" not in entry
    assert (APX / "AppV4.jsx").exists()
    assert (APX / "apix.v4.css").exists()


def test_v4_bottom_nav_is_component_owned() -> None:
    app = read(APX / "AppV4.jsx")

    assert "function BottomNav" in app
    assert 'key: "create"' in app
    assert 'key: "magic"' in app
    assert 'label: "Создать"' in app
    assert 'label: "Промпты"' in app
    assert 'label: "Профиль"' in app
    assert "Тренды" not in app
    assert 'label: "AI"' not in app
    assert "MutationObserver" not in app
    assert "centerCreate.click()" not in app


def test_v4_visual_reset_is_structurally_different() -> None:
    css = read(APX / "apix.v4.css")

    assert "APIX v4 clean shell" in css
    assert ".v4Header" in css
    assert ".v4Tabs" in css
    assert ".v4Filters" in css
    assert ".v4Grid" in css
    assert "column-count: 2" in css
    assert ".v4Card" in css
    assert ".v4CardMedia" in css
    assert ".v4Nav" in css
    assert "grid-template-columns: 1fr 1fr 72px 1fr 1fr" in css
    assert "--v4-grad" in css
    assert "--v4-blur" in css


def test_v4_create_screen_has_flow_not_single_studio_wrapper() -> None:
    app = read(APX / "AppV4.jsx")
    css = read(APX / "apix.v4.css")

    assert "function Create" in app
    assert "v4Create" in app
    assert "v4Segment" in app
    assert "v4Prompt" in app
    assert "v4Options" in app
    assert "v4Reference" in app
    assert "v4CreateActions" in app
    assert ".studioCard" not in css
    assert ".modeSwitch" not in css


def test_v4_video_cards_do_not_render_webp_previews_as_video() -> None:
    app = read(APX / "AppV4.jsx")

    assert "function playableVideo" in app
    assert "playableVideo(src) ? <video" in app
    assert "playableVideo(urls[0]) ? <video" not in app
    assert "item?.gen_type === \"video\" || playableVideo(url)" in app


def test_v4_glassmorphism_is_systemic_not_bulky_blocks() -> None:
    css = read(APX / "apix.v4.css")

    assert "--v4-glass: rgba(18, 15, 24, .54)" in css
    assert "--v4-blur: blur(26px) saturate(1.35)" in css
    assert "-webkit-backdrop-filter: var(--v4-blur)" in css
    assert "backdrop-filter: var(--v4-blur)" in css
    assert "inset 0 1px 0 rgba(255,255,255,.08)" in css
    assert "background: var(--v4-glass)" in css
    assert "border: 1px solid rgba(255,255,255,.12)" in css
