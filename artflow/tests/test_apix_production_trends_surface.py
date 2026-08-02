from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
SRC = WEBAPP / "src"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_production_loads_trends_entry_and_surface_css() -> None:
    index = read(WEBAPP / "index.html")
    style = read(SRC / "style.css")
    assert '/src/main.jsx' in index
    assert '/src/production-trends-entry.js' in index
    assert '@import "./production-trends.css";' in style


def test_header_is_removed_from_in_app_surface() -> None:
    css = read(SRC / "production-trends.css")
    assert ".header" in css
    assert "display: none" in css
    assert "Telegram chrome already has app title" in css


def test_trends_are_compact_masonry_not_big_rectangles() -> None:
    css = read(SRC / "production-trends.css")
    assert "Pinterest-like" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "grid-auto-flow: dense" in css
    assert "aspect-ratio: 4 / 5" in css
    assert "aspect-ratio: 3 / 4" in css
    assert "max-height: 310px" in css
    assert "max-height: 380px" in css
    assert "font-size: 0" in css  # Repeat button text is compacted to a controlled label.
    assert "Повторить" in css


def test_first_visible_surface_uses_existing_trends_navigation() -> None:
    entry = read(SRC / "production-trends-entry.js")
    assert "apix:production-trends-entry:v1" in entry
    assert "findTrendsButton" in entry
    assert "тренды работ" in entry
    assert "button.click()" in entry
    assert "no_trends_entry" in entry


def test_full_runtime_is_still_the_four_theme_production_app() -> None:
    main = read(SRC / "main.jsx")
    assert "20260731-compact-feed-v3" in main
    assert "function Trends(" in main
    assert "function TrendAdminForm(" in main
    assert 'api("/trends?limit=80")' in main
    assert '{ value: "system", label: "Системная" }' in main
    assert '{ value: "dark", label: "Темная" }' in main
    assert '{ value: "light", label: "Светлая" }' in main
    assert '{ value: "mintpink", label: "Салатово-розовая" }' in main
    assert "./apix/AppV4.jsx" not in main
    assert "./apix-v5/App.jsx" not in main
