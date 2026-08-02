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

    assert 'calc(68px + env(safe-area-inset-bottom))' in css
    assert 'bottom: max(3px, env(safe-area-inset-bottom))' in css
    assert 'max-h-[calc(100dvh-env(safe-area-inset-top)-4px)]' in read(SRC / "components/ui/sheet.tsx")
    assert 'min-h-12 min-w-[54px]' in shell
    assert 'min-h-14 min-w-[68px]' not in shell
    assert 'text-base' in input_source
    assert 'text-base' in select_source
    assert 'text-base' in textarea_source


def test_secondary_help_is_collapsed_and_primary_surfaces_are_dense() -> None:
    css = read(SRC / "styles/globals.css")
    studio = read(SRC / "features/studio-screen.tsx")
    generation = read(SRC / "features/generation-screen.tsx")
    feed = read(SRC / "features/feed-screen.tsx")
    trends = read(SRC / "features/trends-screen.tsx")
    services = read(SRC / "features/services-screen.tsx")

    assert '.apix-help' in css
    assert '<details className="apix-help' in studio
    assert '<details className="apix-help' in generation
    assert '<details className="apix-help' in feed
    assert '<details className="apix-help' in trends
    assert '<details className="apix-help' in services
    assert 'text-3xl font-bold' not in studio
    assert 'sm:text-5xl' not in studio
    assert 'apix-launch-bar' in generation
    assert 'grid-cols-5' in studio


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
