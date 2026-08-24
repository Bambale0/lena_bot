from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERFORMANCE_CSS = ROOT / "webapp" / "src" / "styles" / "performance.css"
FEED_SOURCE = ROOT / "webapp" / "src" / "features" / "feed-screen.tsx"
WEBAPP_API = ROOT / "webapp" / "src" / "lib" / "api.ts"
TELEGRAM_SOURCE = ROOT / "webapp" / "src" / "lib" / "telegram.ts"
WEBAPP_MAIN = ROOT / "webapp" / "src" / "main.tsx"
VIDEO_STABILIZER = ROOT / "webapp" / "src" / "lib" / "feed-video-stabilizer.ts"
API_BOOTSTRAP = ROOT / "api" / "__init__.py"
KLING_VISIBILITY = ROOT / "api" / "kling_motion_visibility.py"


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


def test_feed_media_filters_do_not_dead_end_on_a_tiny_server_page() -> None:
    api = read(WEBAPP_API)
    feed = read(FEED_SOURCE)

    # Photo/video filters are applied after the API response, so the first fetch
    # is broad and an empty local filter keeps backfilling while more data exists.
    assert "export const FEED_PAGE_SIZE = 96" in api
    assert 'workFilter === "all"' in feed
    assert "visibleItems.length > 0" in feed
    assert "!hasMore" in feed
    assert "!onLoadMore" in feed
    assert "onLoadMore();" in feed
    assert "Ищем работы по фильтру…" in feed


def test_shared_feed_link_prefers_fresh_query_target_over_stale_webview_storage() -> None:
    telegram = read(TELEGRAM_SOURCE)

    assert 'const DIRECT_START_TARGETS = ["feed", "remix", "prompt", "trend", "task", "profile"]' in telegram
    assert "directStartTargetFromUrl(current)" in telegram
    assert "directStartTargetFromUrl(early)" in telegram
    assert "return `${kind}_${value}`" in telegram
    assert telegram.index("directStartTargetFromUrl(current)") < telegram.index("storedValue(START_PARAM_STORAGE_KEY)")


def test_shared_feed_link_hydrates_the_exact_generation_before_rendering_feed() -> None:
    api = read(WEBAPP_API)

    assert "parseStartTarget(readStartParam())" in api
    assert 'startTarget?.kind === "feed"' in api
    assert "const requestedFeedId = Number(startTarget.value)" in api
    assert "await this.getPublicFeedItem(requestedFeedId, signal)" in api
    assert "fetch(`/api/web/feed/${id}`" in api
    assert "feed = [exactItem, ...feed.filter((item) => item.id !== exactItem.id)]" in api
    assert "feed = [alreadyLoaded, ...feed.filter((item) => item.id !== requestedFeedId)]" in api


def test_telegram_webview_video_tiles_prime_a_real_frame_near_viewport() -> None:
    main = read(WEBAPP_MAIN)
    stabilizer = read(VIDEO_STABILIZER)

    assert "installFeedVideoStabilizer" in main
    assert 'video[preload="metadata"]:not([controls])' in stabilizer
    assert 'rootMargin: "720px 0px"' in stabilizer
    assert 'video.preload = "auto"' in stabilizer
    assert "video.currentTime = target" in stabilizer


def test_kling_30_motion_is_self_healed_before_video_catalog_reads() -> None:
    bootstrap = read(API_BOOTSTRAP)
    visibility = read(KLING_VISIBILITY)

    assert "install_kling_motion_visibility(repository)" in bootstrap
    assert 'KLING_30_MOTION = "kling-3.0/motion-control"' in visibility
    assert 'resolution="720p"' in visibility
    assert 'resolution="1080p"' in visibility
    assert "row.is_active = True" in visibility
