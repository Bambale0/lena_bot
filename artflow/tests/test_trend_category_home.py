from __future__ import annotations

from types import SimpleNamespace

from core.trends import (
    DEFAULT_TREND_CATEGORY,
    TREND_CATEGORIES,
    build_trend_tags,
    trend_category,
    trend_public_payload,
    trend_settings,
)
from db.models import PromptStatus


def _prompt(tags: list[str]):
    return SimpleNamespace(
        id=1,
        author_id=1,
        title="Lion portrait",
        description="Reference-driven portrait",
        prompt_text="SECRET",
        preview_url="https://cdn.example/trend.jpg",
        model="nano-banana-pro",
        tags=tags,
        likes=0,
        uses_count=3,
        status=PromptStatus.approved,
        is_public=True,
        created_at=None,
    )


def test_category_roundtrip_in_existing_tags_storage():
    item = _prompt(build_trend_tags("image", {"category": "animals", "ratio": "4:5"}))
    assert trend_category(item) == "animals"
    assert trend_settings(item)["category"] == "animals"
    payload = trend_public_payload(item)
    assert payload["category"] == "animals"
    assert payload["category_title"] == TREND_CATEGORIES["animals"]["title"]
    assert payload["category_emoji"] == TREND_CATEGORIES["animals"]["emoji"]
    assert "prompt_text" not in payload


def test_legacy_trend_without_category_uses_featured():
    item = _prompt(["trend"])
    assert trend_category(item) == DEFAULT_TREND_CATEGORY


def test_frontend_is_category_first_and_keeps_studio_as_action():
    source = open("webapp/src/main.jsx", encoding="utf-8").read()
    css = open("webapp/src/style.css", encoding="utf-8").read()
    bot = open("bot/handlers/trends.py", encoding="utf-8").read()

    assert "function TrendDiscoveryCard" in source
    assert "trendCategoryTabs" in source
    assert "trendDiscoveryRail" in source
    assert 'openStudioKind?.("image")' in source
    assert '["studio", "+", "Создать", "navCreate"]' in source
    assert "trend-category-home-v4" in source
    assert ".trendDiscoveryCard" in css
    assert ".nav .navCreate" in css
    assert "TrendAdminFSM.category" in bot
    assert 'settings_payload = {\n        "category"' in bot
