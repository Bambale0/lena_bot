from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_telegram_trends_are_reachable() -> None:
    menu = source("bot/ui/main_menu.py")
    handlers = source("bot/handlers/feed.py")
    keyboard = source("bot/keyboards/feed.py")

    assert 'callback_data="menu:top_day"' in menu
    assert 'Command("trends")' in handlers
    assert 'source="top"' in handlers
    assert 'text="🔥 Все работы" if source == "top" else "👑 Тренды"' in keyboard


def test_miniapp_loads_and_displays_trends() -> None:
    app = source("webapp/src/main.jsx")
    api = source("api/miniapp_routes.py")

    assert '/feed?source=top_day&limit=10000' in app
    assert 'setFeedSource("top_day")' in app
    assert '>👑 Тренды</button>' in app
    assert 'source: str = Query(default="recent", pattern="^(recent|top_day|top)$")' in api
    assert 'repo.get_top_day_generations' in api


def test_miniapp_bundle_id_changes_with_trends_release() -> None:
    app = source("webapp/src/main.jsx")
    assert 'window.__APIX_MINIAPP_BUILD_ID__ = "20260731-trends-v1"' in app
