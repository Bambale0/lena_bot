from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
APX = WEBAPP / "src" / "apix"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_structural_pass_is_loaded_last_without_dom_patch() -> None:
    entry = read(WEBAPP / "src" / "main.jsx")

    assert 'import "./apix/apix.archive.css";' in entry
    assert 'import "./apix/apix.final-pass.css";' in entry
    assert 'import "./apix/apix.structural.css";' in entry
    assert "apix.final-pass.js" not in entry
    assert entry.index("apix.structural.css") > entry.index("apix.final-pass.css")
    assert not (APX / "apix.final-pass.js").exists()


def test_final_pass_removes_demo_overlay_and_bulky_studio_wrapper() -> None:
    css = read(APX / "apix.final-pass.css")
    structural = read(APX / "apix.structural.css")

    assert ".demoNotice," in css
    assert ".apixMicroBar" in css
    assert "display: none !important" in css
    assert ".studioCard" in css
    assert "background: transparent !important" in css
    assert "box-shadow: none !important" in css
    assert "border-radius: 0 !important" in css
    assert ".studioFlow" in structural
    assert "background: transparent" in structural


def test_bottom_nav_is_component_owned_not_dom_relabelled() -> None:
    app = read(APX / "App.jsx")

    assert 'key: "create-tab"' in app
    assert 'label: "Создать"' in app
    assert 'label: "Промпты"' in app
    assert 'label: "Профиль"' in app
    assert "Тренды" not in app
    assert 'label: "AI"' not in app
    assert "MutationObserver" not in app
    assert "centerCreate.click()" not in app
    assert "function Icon" in app


def test_video_cards_do_not_render_webp_previews_as_video() -> None:
    app = read(APX / "App.jsx")

    assert "function isPlayableVideoUrl" in app
    assert "const playableVideo = isPlayableVideoUrl(first);" in app
    assert "playableVideo ? <video" in app
    assert "isPlayableVideoUrl(urls[0]) ? <video" in app
    assert "isVideo(item, first);" in app


def test_final_pass_has_real_glassmorphism_without_new_bulky_blocks() -> None:
    css = read(APX / "apix.final-pass.css")

    assert "--apx-glass-bg: rgba(18, 14, 24, .54)" in css
    assert "--apx-glass-blur: blur(22px) saturate(1.32)" in css
    assert "-webkit-backdrop-filter: var(--apx-glass-blur)" in css
    assert "backdrop-filter: var(--apx-glass-blur)" in css
    assert "inset 0 1px 0 rgba(255, 255, 255, .08)" in css
    assert "linear-gradient(115deg, rgba(255,255,255,.13)" in css
    assert ".sheetOverlay," in css
    assert "backdrop-filter: blur(18px) saturate(1.1)" in css
    assert "background: transparent !important" in css


def test_structural_layer_controls_media_and_svg_icons() -> None:
    structural = read(APX / "apix.structural.css")

    assert ".feedMedia img," in structural
    assert "object-fit: cover !important" in structural
    assert ".feedTile.tall .feedMedia" in structural
    assert ".bottomNav svg" in structural
    assert ".modeSwitch svg" in structural
    assert ".createIntro" in structural
    assert ".studioFlow" in structural
