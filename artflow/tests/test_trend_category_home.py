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


def test_loaded_relation_is_authoritative_over_legacy_tag():
    item = _prompt(["trend", "trend-category:animals"])
    item.trend_category_record = SimpleNamespace(key="portrait", title="Портреты автора")
    assert trend_category(item) == "portrait"
    payload = trend_public_payload(item)
    assert payload["category"] == "portrait"
    assert payload["category_title"] == "Портреты автора"


def test_unknown_legacy_category_key_is_preserved_until_admin_resolution():
    item = _prompt(["trend", "trend-category:legacy-special"])
    assert trend_category(item) == "legacy-special"
    assert "trend-category:legacy-special" in item.tags


def test_frontend_is_category_first_and_keeps_studio_as_action():
    source = open("webapp/src/features/trends-screen.tsx", encoding="utf-8").read()
    shell = open("webapp/src/components/app-shell.tsx", encoding="utf-8").read()
    bot = open("bot/handlers/trends.py", encoding="utf-8").read()
    assert 'aria-label="Категории трендов"' in source
    assert 'setCategoryFilter(item.value)' in source
    assert 'function TrendGroup' in source and 'openTrendRunner(trend)' in source
    assert 'id: "create"' in shell
    assert 'TrendAdminFSM.category' in bot
