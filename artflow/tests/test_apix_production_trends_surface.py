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
    # Feed descriptions remain secondary, explicitly expandable content.
    # The former hidden implementation-help paragraph is no longer product UI.
    assert '<details className="feed-trend-description">' in feed
    assert '<summary>Описание</summary>' in feed
    assert '<details className="feed-trend-description" open' not in feed
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
    assert '<h1>Лента</h1>' in feed
    assert 'Повторить' in feed
    assert 'onRemix(item, mediaUrls[0])' in feed
    assert 'disabled={remixing}' in feed


def test_feed_controls_are_semantic_and_repeat_has_a_readable_caption() -> None:
    feed = read(SRC / "features/feed-screen.tsx")
    css = read(SRC / "styles/feed-gallery.css")

    assert 'apix-feed-toolbar' in feed
    for label in ("Содержимое ленты", "Тип работ", "Сортировка работ"):
        assert f'role="group" aria-label="{label}"' in feed
    assert 'aria-pressed={contentMode === tab.value}' in feed
    assert 'aria-pressed={workFilter === filter.value}' in feed
    assert 'aria-pressed={source === filter.value}' in feed
    assert 'sticky top-[48px]' not in feed
    assert 'grid grid-cols-2 gap-1 rounded-lg bg-muted/45 p-1' not in feed
    assert 'className="apix-feed-media feed-card-media"' in feed
    assert 'className="feed-card-caption"' in feed
    assert 'className="apix-focus-ring feed-card-repeat"' in feed
    assert '<span>{remixing ? "Запуск" : "Повторить"}</span>' in feed
    assert 'aria-label="Лайк"' in feed
    assert 'onLike(item)' in feed
    assert '<RepeatCount count={item.remixes}' in feed
    assert 'event.stopPropagation();' in feed
    caption = css.split('.feed-card-caption {', 1)[1].split('}', 1)[0]
    repeat = css.split('.feed-card-repeat {', 1)[1].split('}', 1)[0]
    icons = css.split('.feed-card-icon-button {', 1)[1].split('}', 1)[0]
    assert 'display: grid' in caption
    assert 'position: absolute' not in caption
    assert 'min-height: 44px' in repeat
    assert 'width: 44px' in icons and 'height: 44px' in icons
    # tests/ux2/feed-gallery.spec.ts proves caption/action geometry below media,
    # readable metadata and hit targets above navigation at 320/390/1440px.


def test_infinite_feed_uses_intersection_observer_and_growing_limit() -> None:
    app = read(SRC / "app/App.tsx")
    feed = read(SRC / "features/feed-screen.tsx")
    api = read(SRC / "lib/api.ts")
    css = read(SRC / "styles/globals.css")

    assert 'export const FEED_PAGE_SIZE = 96' in api
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
    assert 'function FeedPreview' in feed
    assert 'eager={index < 4}' in feed
    assert 'eager = false' in feed
    assert 'loading={eager ? "eager" : "lazy"}' in feed
    assert 'decoding="async"' in feed
    assert 'fetchPriority={eager ? "high" : "auto"}' in feed


def test_feed_media_opens_inside_app_viewer_not_browser() -> None:
    feed = read(SRC / "features/feed-screen.tsx")
    css = read(SRC / "styles/feed-gallery.css")

    assert 'interface MediaViewerState' in feed
    assert 'function MediaViewer' in feed
    assert 'apix-media-viewer feed-gallery-viewer' in feed
    assert 'createPortal(' in feed
    assert 'document.body' in feed
    assert 'role="dialog" aria-modal="true" aria-label="Просмотр работы"' in feed
    assert 'openViewer(item, 0, event.currentTarget)' in feed
    assert 'Открыть внутри приложения' in feed
    assert 'openExternalUrl' not in feed
    viewer = css.split('.feed-gallery-viewer {', 1)[1].split('}', 1)[0]
    assert 'position: fixed' in viewer and 'inset: 0' in viewer
    assert 'z-index: 1100' in viewer
    assert 'event.key === "Tab"' in feed
    assert 'event.key === "Escape"' in feed
    assert 'event.defaultPrevented || anotherDialogOpen()' in feed
    assert 'dialog.inert = next' in feed
    assert 'returnTarget.focus({ preventScroll: true })' in feed
    # The gallery browser regression exercises focus trapping, Sheet ownership
    # and restoration to the exact opener, beyond these structural guards.


def test_feed_uses_stable_responsive_grid_and_consistent_media_shape() -> None:
    feed = read(SRC / "features/feed-screen.tsx")
    css = read(SRC / "styles/feed-gallery.css")
    main = read(SRC / "main.tsx")

    assert 'import "@/styles/feed-gallery.css"' in main
    assert 'feed-gallery-grid' in feed
    grid = css.split('.apix-feed-gallery .feed-gallery-grid {', 1)[1].split('}', 1)[0]
    assert 'display: grid' in grid
    assert 'grid-template-columns: minmax(0, 1fr)' in grid
    assert 'grid-auto-flow: row' in grid
    assert 'columns: auto' in grid
    for breakpoint, columns in ((380, 2), (700, 3), (1100, 4)):
        rule = css.split(f'@media (min-width: {breakpoint}px) {{', 1)[1].split('}', 1)[0]
        assert f'grid-template-columns: repeat({columns}, minmax(0, 1fr))' in rule
    assert 'max-width: 1600px' in css
    media = css.split('.apix-feed-gallery .feed-card-media {', 1)[1].split('}', 1)[0]
    assert 'aspect-ratio: 4 / 5' in media
    assert 'function cardMediaShape' not in feed
    assert 'isFeatured' not in feed
    assert 'apix-feed-card-featured' not in feed
    assert 'выбор' not in feed


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
    assert 'openTrendRunner(trend)' in feed
    assert '`/api/v1/trends/${trend.id}/prepare`' not in feed
    assert '"/api/v1/generate/video"' not in feed
    assert '"/api/v1/generate/image"' not in feed


def test_repeat_feed_uses_filters_safe_video_payload_and_normalized_media_urls() -> None:
    app = read(SRC / "app/App.tsx")
    feed = read(SRC / "features/feed-screen.tsx")
    api = read(SRC / "lib/api.ts")
    runner = read(SRC / "features/feed-remix-runner.tsx")
    utils = read(SRC / "lib/utils.ts")

    assert 'remixingId' in app
    assert 'remixFeedItem(item, sourceMediaUrl)' in app
    # Repeat payload moved to the prelaunch runner, where user-selected media
    # and mode (not the source filename alone) determine safe video inputs.
    # Creator text-only videos must replay with text mode and no fake image/video inputs.
    assert 'const chosenMode = creatorTextOnly ? "text" : bucket === "video" ? mode : "image"' in runner
    assert 'source_has_video_reference' in runner
    assert 'image_url: primaryUserReference || (!sourceIsVideo ? sourceMedia || null : null)' in runner
    assert 'source_image_url: !sourceIsVideo ? sourceMedia || null : null' in runner
    # The historical editor may use published video, but a creator-input
    # replay must never smuggle the rendered MP4 into provider video inputs.
    assert 'video_url: creatorRecipeReplay ? null : sourceIsVideo && chosenMode === "video" ? sourceMedia || null : null' in runner
    assert 'typeof item?.source_has_video_reference === "boolean"' in runner
    assert 'if (bucket === "video" && modeOptions.includes("image")) setMode("image")' in runner
    assert 'const task = await apiJson<GenerationTask>(`/feed/${item.id}/remix`' in runner
    assert 'const url = new URL(value, window.location.origin)' in utils
    assert 'const url = safeExternalUrl(candidate)' in utils
    assert 'Invalid reference URL' not in app
    assert 'type WorkFilter = "all" | "image" | "video" | "mine"' in feed
    assert 'visibleItems' in feed
    assert 'Все' in feed and 'Фото' in feed and 'Видео' in feed and 'Мои' in feed
    assert 'const HISTORY_PAGE_SIZE = 100' in api


def test_profile_history_pages_through_all_generations_without_total_cap() -> None:
    api = read(SRC / "lib/api.ts")
    app = read(SRC / "app/App.tsx")
    routes = read(ROOT / "api/miniapp_routes.py")
    repository = read(ROOT / "db/repository.py")

    assert 'async getHistory(signal?: AbortSignal): Promise<GenerationTask[]>' in api
    assert '`/history?limit=${HISTORY_PAGE_SIZE}&offset=${offset}`' in api
    # Bounded loop: page ceiling + zero-new-ids break keep bootstrap from
    # hanging when offset is ignored (deploy skew / proxy strips query).
    assert 'export const MAX_HISTORY_PAGES' in api
    assert 'if (added === 0) break;' in api
    # Partial results survive a mid-stream page failure.
    assert 'keeping partial history' in api
    assert 'offset: int = Query(default=0, ge=0)' in routes
    assert 'limit=limit, offset=offset' in routes
    # Reconcile (provider polling) runs once for the first page, not per page.
    assert 'if offset == 0:' in routes
    assert 'offset: int = 0' in repository
    assert '.offset(offset)' in repository
    assert '.order_by(desc(Generation.created_at), desc(Generation.id))' in repository
    assert '`/history?limit=${HISTORY_PAGE_SIZE}&offset=0`' in api
    assert 'const freshTaskIds = new Set(core.recentTasks.map((task) => task.id));' in app
    assert '...current.recentTasks.filter((task) => !freshTaskIds.has(task.id))' in app
    # Behavioural coverage lives in tests/test_history_pagination.py.


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
