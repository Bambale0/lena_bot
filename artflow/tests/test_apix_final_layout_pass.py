from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
APX = WEBAPP / "src" / "apix"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_final_pass_is_loaded_after_archive_styles() -> None:
    entry = read(WEBAPP / "src" / "main.jsx")

    assert 'import "./apix/apix.archive.css";' in entry
    assert 'import "./apix/apix.final-pass.css";' in entry
    assert 'import "./apix/apix.final-pass.js";' in entry
    assert entry.index("apix.final-pass.css") > entry.index("apix.archive.css")


def test_final_pass_removes_demo_overlay_and_bulky_studio_wrapper() -> None:
    css = read(APX / "apix.final-pass.css")

    assert ".demoNotice," in css
    assert ".apixMicroBar" in css
    assert "display: none !important" in css
    assert ".studioCard" in css
    assert "background: transparent !important" in css
    assert "box-shadow: none !important" in css
    assert "border-radius: 0 !important" in css
    assert "min-height: 116px" in css


def test_final_nav_layer_replaces_legacy_labels() -> None:
    js = read(APX / "apix.final-pass.js")

    assert 'label: "Создать"' in js
    assert 'label: "Промпты"' in js
    assert '"Тренды"' not in js
    assert '"AI"' not in js
    assert "centerCreate.click()" in js
    assert "MutationObserver" in js


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
    assert "Do not use glass to create new large promo rectangles" not in css
