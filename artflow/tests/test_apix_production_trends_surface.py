from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBAPP = ROOT / "webapp"
SRC = WEBAPP / "src"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_production_uses_modular_typescript_entry() -> None:
    index = read(WEBAPP / "index.html")
    main = read(SRC / "main.tsx")
    package = read(WEBAPP / "package.json")

    assert '/src/main.tsx' in index
    assert 'production-trends-entry.js' not in index
    assert 'window.__APIX_EARLY_URL__' in index
    assert 'import { App } from "@/app/App"' in main
    assert 'get("legacy") === "1"' in main
    assert 'import("./main.jsx")' in main
    assert '"typescript"' in package
    assert '"@tailwindcss/vite"' in package
    assert '"sonner"' in package


def test_shadcn_configuration_and_theme_are_present() -> None:
    config = read(WEBAPP / "components.json")
    css = read(SRC / "styles/globals.css")

    assert '"style": "new-york"' in config
    assert '"tsx": true' in config
    assert '"iconLibrary": "lucide"' in config
    assert '@import "tailwindcss";' in css
    assert 'env(safe-area-inset-bottom)' in css
    assert '.apix-bottom-nav' in css
    assert '.apix-media-grid' in css
    assert 'columns: 4' in css


def test_iphone_layout_uses_safe_areas_and_dense_navigation() -> None:
    css = read(SRC / "styles/globals.css")
    shell = read(SRC / "components/app-shell.tsx")
    input_source = read(SRC / "components/ui/input.tsx")
    select_source = read(SRC / "components/ui/select.tsx")
    textarea_source = read(SRC / "components/ui/textarea.tsx")

    assert 'calc(70px + env(safe-area-inset-bottom))' in css
    assert 'bottom: max(3px, env(safe-area-inset-bottom))' in css
    assert '@media (min-width: 390px)' in css
    assert '-webkit-overflow-scrolling: touch' in css
    assert 'scroll-snap-type: x proximity' in css
    assert 'max-h-[calc(100dvh-env(safe-area-inset-top)-4px)]' in read(SRC / "components/ui/sheet.tsx")
    assert 'min-h-12 min-w-[74px]' in shell
    assert 'role="tablist"' in shell
    assert 'min-h-14 min-w-[68px]' not in shell
    assert 'text-base' in input_source
    assert 'text-base' in select_source
    assert 'text-base' in textarea_source


def test_secondary_help_is_collapsed_and_primary_surfaces_are_dense() -> None:
    css = read(SRC / "styles/globals.css")
    app = read(SRC / "app/App.tsx")
    generation = read(SRC / "features/generation-screen.tsx")
    feed = read(SRC / "features/feed-screen.tsx")
    profile = read(SRC / "features/profile-screen.tsx")
    trends = read(SRC / "features/trends-screen.tsx")
    services = read(SRC / "features/services-screen.tsx")

    assert '.apix-help' in css
    assert 'activeTab === "feed" || activeTab === "studio"' in app
    assert 'import { StudioScreen }' not in app
    assert '<details className="apix-help' in generation
    assert '<details className="apix-help' in feed
    assert '<details className="apix-help' in trends
    assert '<details className="apix-help' in services
    assert 'Выложенные работы' in profile
    assert 'Все работы' in profile
    assert 'text-3xl font-bold' not in app
    assert 'sm:text-5xl' not in app
    assert 'apix-launch-bar' in generation


def test_telegram_auth_is_resilient_and_never_uses_demo_balance() -> None:
    telegram = read(SRC / "lib/telegram.ts")
    app = read(SRC / "app/App.tsx")
    locked = read(SRC / "components/locked-screen.tsx")

    assert 'tgWebAppData' in telegram
    assert 'window.__APIX_EARLY_URL__' in telegram
    assert 'apix:telegram-init-data:v2' in telegram
    assert 'waitForTelegramInitData(8_000)' in app
    assert 'setMode("locked")' in app
    assert 'Баланс и задачи не подменяются демо-данными' in locked
    assert 'fallbackUser' not in app


def test_trends_use_state_and_prepare_endpoint_not_dom_clicks() -> None:
    app = read(SRC / "app/App.tsx")
    api = read(SRC / "lib/api.ts")
    trends = read(SRC / "features/trends-screen.tsx")

    assert 'prepareTrend' in app
    assert '`/trends/${id}/prepare`' in api
    assert 'applyPreparedTrend' in app
    assert 'setActiveTab("video")' in app
    assert 'setActiveTab("photo")' in app
    assert 'Повторить' in trends
    assert 'findTrendsButton' not in app
    assert 'button.click()' not in app


def test_feed_is_first_tab_and_repeat_is_inside_feed() -> None:
    app = read(SRC / "app/App.tsx")
    feed = read(SRC / "features/feed-screen.tsx")
    shell = read(SRC / "components/app-shell.tsx")

    assert 'useState<AppTab>("feed")' in app
    assert 'label: "Лента"' in shell
    assert 'label: "Повторы"' not in shell
    assert 'title="Повторы"' not in app
    assert 'repeatFirst' not in app
    assert '<h1 className="text-lg font-bold tracking-tight sm:text-xl">Лента</h1>' in feed
    assert 'Повторить' in feed
    assert 'Карточки выводятся порциями' in feed


def test_infinite_feed_uses_intersection_observer_and_growing_limit() -> None:
    app = read(SRC / "app/App.tsx")
    feed = read(SRC / "features/feed-screen.tsx")
    api = read(SRC / "lib/api.ts")
    css = read(SRC / "styles/globals.css")

    assert 'export const FEED_PAGE_SIZE = 24' in api
    assert '`/feed?source=${source}&limit=${limit}`' in api
    assert 'feedLimit + FEED_PAGE_SIZE' in app
    assert 'setFeedHasMore(feed.length >= nextLimit)' in app
    assert 'loadingMore={feedLoadingMore}' in app
    assert 'hasMore={feedHasMore}' in app
    assert 'onLoadMore={() => void loadMoreFeed()}' in app
    assert 'new IntersectionObserver' in feed
    assert 'rootMargin: "640px 0px"' in feed
    assert 'sentinelRef' in feed
    assert 'apix-feed-card' in feed
    assert '.apix-feed-card' in css
    assert '@keyframes apix-feed-card-in' in css


def test_feed_render_window_keeps_loaded_items_from_overloading_dom() -> None:
    feed = read(SRC / "features/feed-screen.tsx")

    assert 'const WORK_RENDER_BATCH = 30' in feed
    assert 'const TREND_RENDER_BATCH = 24' in feed
    assert 'visibleWorkCount' in feed
    assert 'renderedItems' in feed
    assert 'canRevealMoreWorks' in feed
    assert 'setVisibleWorkCount((current) => Math.min(current + WORK_RENDER_BATCH, visibleItems.length))' in feed
    assert 'visibleTrendCount' in feed
    assert 'renderedTrends' in feed
    assert 'loading={index < 4 ? "eager" : "lazy"}' in feed
    assert 'decoding="async"' in feed
    assert 'fetchPriority={index < 2 ? "high" : "auto"}' in feed


def test_feed_media_opens_inside_app_viewer_not_browser() -> None:
    feed = read(SRC / "features/feed-screen.tsx")
    css = read(SRC / "styles/globals.css")

    assert 'interface MediaViewerState' in feed
    assert 'function MediaViewer' in feed
    assert 'apix-media-viewer fixed inset-0' in feed
    assert 'onClick={() => openViewer(item)}' in feed
    assert 'Открыть внутри приложения' in feed
    assert 'openExternalUrl' not in feed
    assert '.apix-media-viewer' in css
    assert '@keyframes apix-media-viewer-in' in css


def test_feed_uses_mosaic_cards_instead_of_monotone_grid() -> None:
    feed = read(SRC / "features/feed-screen.tsx")
    css = read(SRC / "styles/globals.css")

    assert 'function cardMediaShape' in feed
    assert 'index % 10 === 0' in feed
    assert 'index % 7 === 0' in feed
    assert 'apix-feed-mosaic' in feed
    assert 'apix-feed-card-featured' in feed
    assert 'выбор' in feed
    assert '.apix-feed-mosaic' in css
    assert '.apix-feed-card-featured' in css


def test_feed_has_categorized_trends_tab() -> None:
    feed = read(SRC / "features/feed-screen.tsx")

    assert 'type ContentMode = "works" | "trends"' in feed
    assert 'type TrendKindFilter = "all" | "image" | "video"' in feed
    assert 'const [contentMode, setContentMode]' in feed
    assert 'const [trendCategory, setTrendCategory]' in feed
    assert 'trendCategories' in feed
    assert 'trendCategoryKey' in feed
    assert 'Работы' in feed and 'Тренды' in feed
    assert 'category_emoji' in feed
    assert 'Повторить тренд' in feed
    assert '`/api/v1/trends/${trend.id}/prepare`' in feed
    assert '"/api/v1/generate/video"' in feed
    assert '"/api/v1/generate/image"' in feed


def test_repeat_feed_uses_filters_and_safe_video_remix_payload() -> None:
    app = read(SRC / "app/App.tsx")
    feed = read(SRC / "features/feed-screen.tsx")
    api = read(SRC / "lib/api.ts")

    assert 'remixingId' in app
    assert 'mode: videoMedia ? "text" : "image"' in app
    assert 'source_image_url: media && !videoMedia ? media : null' in app
    assert 'video_url: null' in app
    assert 'type WorkFilter = "all" | "image" | "video" | "mine"' in feed
    assert 'visibleItems' in feed
    assert 'Все' in feed and 'Фото' in feed and 'Видео' in feed and 'Мои' in feed
    assert 'const HISTORY_LIMIT = 100' in api


def test_workflows_have_polling_and_secure_task_actions() -> None:
    app = read(SRC / "app/App.tsx")
    detail = read(SRC / "components/task-detail-sheet.tsx")

    assert 'window.setInterval(() => void refreshCore(), 5_000)' in app
    assert 'window.setInterval(async () =>' in app
    assert 'api.getGeneration(selectedTask.id)' in app
    assert 'api.shareGeneration(task.id)' in app
    assert 'api.savePrompt(task.id)' in app
    assert 'task.prompt_hidden' in detail
    assert 'prompt_actions_allowed' in detail
