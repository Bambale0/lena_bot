from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"


def test_compact_chrome_stylesheet_is_loaded_after_entrypoint() -> None:
    html = (WEBAPP / "index.html").read_text(encoding="utf-8")

    entry_pos = html.index('/src/main.jsx')
    chrome_pos = html.index('/apix-compact-header.css')

    assert entry_pos < chrome_pos


def test_compact_chrome_does_not_reserve_poster_height() -> None:
    css = (WEBAPP / "public" / "apix-compact-header.css").read_text(encoding="utf-8")

    assert "max-height: 22px !important" in css
    assert "height: 22px !important" in css
    assert "min-height: 48px" in css
    assert "padding-top: 8px !important" in css
    assert "padding-bottom: 12px !important" in css


def test_compact_chrome_keeps_branded_micro_status_bar() -> None:
    css = (WEBAPP / "public" / "apix-compact-header.css").read_text(encoding="utf-8")

    assert "--apix-chrome-line" in css
    assert ".header::before" in css
    assert ".apix-statusbar" in css
    assert ".theme-statusbar" in css
