from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.trends_routes import list_trend_categories, list_trend_category_items
from db.models import PromptCategory, PromptStatus, TrendCategory, UserPrompt
from db.trend_category_repository import (
    decode_category_cursor,
    decode_trend_cursor,
    encode_category_cursor,
    encode_trend_cursor,
    get_public_category_shelves,
    get_public_category_trends,
    hydrate_trend_categories,
)


def _category(category_id: int, key: str, order: int):
    return SimpleNamespace(
        id=category_id,
        key=key,
        title=key.title(),
        sort_order=order,
        is_visible=True,
    )


def _prompt(prompt_id: int, category_id: int, created_at: datetime):
    return SimpleNamespace(
        id=prompt_id,
        author_id=1,
        title=f"Trend {prompt_id}",
        description="Description",
        prompt_text="hidden",
        preview_url=f"https://cdn.test/{prompt_id}.mp4",
        model="video-model",
        tags=["trend", "trend-video"],
        trend_user_fields=[],
        trend_category_id=category_id,
        trend_category_record=None,
        likes=0,
        uses_count=0,
        is_public=True,
        status=SimpleNamespace(value="approved"),
        created_at=created_at,
    )


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class _ScriptedSession:
    def __init__(self, *results):
        self._results = list(results)
        self.execute_count = 0

    async def execute(self, _statement):
        self.execute_count += 1
        return _Rows(self._results.pop(0))


def test_opaque_cursors_round_trip_and_reject_invalid_payloads():
    category_cursor = encode_category_cursor(12, 45)
    assert decode_category_cursor(category_cursor) == (12, 45)

    created_at = datetime(2026, 10, 26, 12, 30, tzinfo=UTC)
    trend_cursor = encode_trend_cursor(created_at, 99)
    assert decode_trend_cursor(trend_cursor) == (created_at, 99)

    for value in ("", "not-base64", "e30", "a" * 513):
        with pytest.raises(ValueError):
            decode_category_cursor(value)
        with pytest.raises(ValueError):
            decode_trend_cursor(value)


@pytest.mark.asyncio
async def test_shelves_use_two_bounded_queries_not_one_query_per_category():
    categories = [
        (_category(1, "featured", 0), 9),
        (_category(2, "portrait", 1), 3),
        (_category(3, "animals", 2), 1),
    ]
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    previews = [
        (_prompt(11, 1, now), 1),
        (_prompt(10, 1, now - timedelta(seconds=1)), 2),
        (_prompt(20, 2, now), 1),
        (_prompt(30, 3, now), 1),
    ]
    session = _ScriptedSession(categories, previews)

    page = await get_public_category_shelves(session, limit=3, cursor=None, preview_limit=5)

    assert session.execute_count == 2
    assert [item.category.key for item in page.items] == ["featured", "portrait", "animals"]
    assert [item.trend_count for item in page.items] == [9, 3, 1]
    assert [item.id for item in page.items[0].previews] == [11, 10]
    assert page.has_more is False
    assert page.next_cursor is None


@pytest.mark.asyncio
async def test_folder_uses_stable_created_id_cursor_and_reports_more():
    category = _category(2, "portrait", 1)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    prompts = [
        (_prompt(30, 2, now),),
        (_prompt(29, 2, now),),
        (_prompt(28, 2, now - timedelta(seconds=1)),),
    ]
    session = _ScriptedSession([(category,)], prompts)

    page = await get_public_category_trends(
        session,
        key="portrait",
        limit=2,
        cursor=encode_trend_cursor(now + timedelta(seconds=1), 99),
    )

    assert session.execute_count == 2
    assert page is not None
    assert [item.id for item in page.items] == [30, 29]
    assert page.has_more is True
    assert decode_trend_cursor(page.next_cursor) == (now, 29)


@pytest.mark.asyncio
async def test_existing_trends_can_be_hydrated_with_dynamic_category_title():
    category = TrendCategory(id=9, key="cat_custom", title="Новая папка", sort_order=8)
    prompt = UserPrompt(
        id=41,
        author_id=1,
        title="Trend",
        description="Description",
        category=PromptCategory.other,
        prompt_text="hidden",
        tags=["trend", "trend-category:cat_custom"],
        trend_category_id=9,
        status=PromptStatus.approved,
        is_public=True,
    )
    session = _ScriptedSession([(category,)])

    hydrated = await hydrate_trend_categories(session, [prompt])

    assert session.execute_count == 1
    assert hydrated[0].trend_category_record.title == "Новая папка"


@pytest.mark.asyncio
async def test_category_route_payload_is_bounded_and_contains_no_price(monkeypatch):
    category = _category(1, "featured", 0)
    prompt = _prompt(11, 1, datetime(2026, 10, 26, tzinfo=UTC))
    page = SimpleNamespace(
        items=[SimpleNamespace(category=category, trend_count=1, previews=[prompt])],
        has_more=False,
        next_cursor=None,
    )

    async def fake_shelves(_session, *, limit, cursor, preview_limit):
        assert limit == 24
        assert cursor is None
        assert preview_limit == 5
        return page

    monkeypatch.setattr("api.trends_routes.get_public_category_shelves", fake_shelves)
    result = await list_trend_categories(
        limit=24,
        cursor=None,
        session=SimpleNamespace(),
        user=SimpleNamespace(id=7),
    )

    assert result["items"][0]["key"] == "featured"
    assert result["items"][0]["trend_count"] == 1
    assert result["items"][0]["preview_items"][0]["id"] == 11
    assert "cost_credits" not in result["items"][0]["preview_items"][0]
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_folder_route_translates_bad_cursor_to_422(monkeypatch):
    async def invalid_page(*_args, **_kwargs):
        raise ValueError("Invalid trend cursor")

    monkeypatch.setattr("api.trends_routes.get_public_category_trends", invalid_page)
    with pytest.raises(HTTPException) as exc:
        await list_trend_category_items(
            key="featured",
            limit=48,
            cursor="broken",
            session=SimpleNamespace(),
            user=SimpleNamespace(id=7),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_folder_route_returns_category_items_and_composite_cursor(monkeypatch):
    category = _category(2, "portrait", 1)
    prompt = _prompt(21, 2, datetime(2026, 10, 26, tzinfo=UTC))
    page = SimpleNamespace(
        category=category,
        items=[prompt],
        has_more=True,
        next_cursor=encode_trend_cursor(prompt.created_at, prompt.id),
    )

    async def fake_page(_session, *, key, limit, cursor):
        assert (key, limit, cursor) == ("portrait", 48, None)
        return page

    monkeypatch.setattr("api.trends_routes.get_public_category_trends", fake_page)
    result = await list_trend_category_items(
        key="portrait",
        limit=48,
        cursor=None,
        session=SimpleNamespace(),
        user=SimpleNamespace(id=7),
    )
    assert result["category"]["key"] == "portrait"
    assert result["items"][0]["category_title"] == "Portrait"
    assert result["has_more"] is True
    assert decode_trend_cursor(result["next_cursor"]) == (prompt.created_at, prompt.id)
