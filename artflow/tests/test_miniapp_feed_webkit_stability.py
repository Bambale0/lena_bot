from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE_CSS = ROOT / "webapp" / "src" / "styles" / "performance.css"
FEED_SOURCE = ROOT / "webapp" / "src" / "features" / "feed-screen.tsx"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_mounted_feed_cards_are_not_browser_virtualized() -> None:
    css = read(PERFORMANCE_CSS)
    feed = read(FEED_SOURCE)

    # React already bounds the feed DOM, so WebKit content skipping must stay off.
    assert "const WORK_RENDER_BATCH = 30" in feed
    assert "content-visibility: visible !important" in css
    assert "contain-intrinsic-size: none !important" in css


def test_infinite_feed_uses_stable_grid_instead_of_balanced_columns() -> None:
    css = read(PERFORMANCE_CSS)

    assert "columns: auto !important" in css
    assert "display: grid !important" in css
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in css
    assert "perspective: none !important" in css


def test_ios_feed_avoids_expensive_scroll_compositor_effects() -> None:
    css = read(PERFORMANCE_CSS)

    assert ".backdrop-blur," in css
    assert "backdrop-filter: none !important" in css
    assert "-webkit-backdrop-filter: none !important" in css
    assert "animation: none !important" in css
    assert ".apix-feed-media img" in css
    assert ".apix-feed-media video" in css
    assert "transition: none !important" in css
    assert "transform: none !important" in css
