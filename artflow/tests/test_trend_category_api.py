from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from api.trends_routes import (
    TrendCreateRequest,
    TrendUpdateRequest,
    admin_create_trend,
    admin_update_trend,
    list_trend_categories,
    list_trend_category_items,
)
from db import trend_category_repository
from db.models import PromptCategory, PromptStatus, TrendCategory, UserPrompt
from db.prompt_repository import _normalize_tags
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


def _prompt(prompt_id: int, category_id: int | None, created_at: datetime | None):
    return SimpleNamespace(
        id=prompt_id,
        author_id=1,
        title=f"Trend {prompt_id}",
        description="Description",
        prompt_text="hidden",
        preview_url=f"https://cdn.test/{prompt_id}.mp4",
        model="video-model",
        tags=[
            "trend",
            "trend-video",
            *(["trend-category:portrait"] if category_id is None else []),
        ],
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
        self.statements = []

    async def execute(self, statement):
        self.execute_count += 1
        self.statements.append(statement)
        return _Rows(self._results.pop(0))


def test_opaque_cursors_round_trip_and_reject_invalid_payloads():
    category_cursor = encode_category_cursor(12, 45)
    assert decode_category_cursor(category_cursor) == (12, 45)

    created_at = datetime(2026, 10, 26, 12, 30, tzinfo=UTC)
    trend_cursor = encode_trend_cursor(created_at, 99)
    assert decode_trend_cursor(trend_cursor) == (created_at, 99)
    null_cursor = encode_trend_cursor(None, 98)
    assert decode_trend_cursor(null_cursor) == (None, 98)

    for value in ("", "not-base64", "e30", "a" * 513):
        with pytest.raises(ValueError):
            decode_category_cursor(value)
        with pytest.raises(ValueError):
            decode_trend_cursor(value)


def test_legacy_mirror_keeps_the_full_maximum_category_key():
    key = "a" * 32
    assert _normalize_tags([f"trend-category:{key}"]) == [f"trend-category:{key}"]


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

    preview_sql = str(
        session.statements[1].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).upper()
    assert "CREATED_AT DESC NULLS LAST" in preview_sql
    assert "USER_PROMPTS.TREND_CATEGORY_ID IS NULL" in preview_sql
    assert "TREND-CATEGORY:" in preview_sql

    shelf_sql = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).upper()
    assert "USER_PROMPTS.TREND_CATEGORY_ID IS NULL" in shelf_sql
    assert "TREND-CATEGORY:" in shelf_sql


@pytest.mark.asyncio
async def test_shelf_preview_keeps_legacy_tag_prompt_created_during_rolling_deploy():
    category = _category(2, "portrait", 1)
    legacy = _prompt(21, None, datetime(2026, 10, 26, 12, tzinfo=UTC))
    session = _ScriptedSession([(category, 1)], [(legacy, 1)])

    page = await get_public_category_shelves(
        session, limit=1, cursor=None, preview_limit=5
    )

    assert page.items[0].trend_count == 1
    assert [item.id for item in page.items[0].previews] == [21]


@pytest.mark.asyncio
async def test_legacy_trend_query_filters_visible_categories_before_limit():
    category = TrendCategory(
        id=9,
        key="cat_dynamic",
        title="Dynamic",
        sort_order=8,
        is_visible=True,
    )
    prompt = UserPrompt(
        id=41,
        author_id=1,
        title="Trend 41",
        description="Description",
        category=PromptCategory.other,
        prompt_text="hidden",
        tags=["trend", "trend-video", "trend-category:cat_dynamic"],
        trend_category_id=None,
        status=PromptStatus.approved,
        is_public=True,
        created_at=datetime(2026, 10, 26, 12, tzinfo=UTC),
    )
    session = _ScriptedSession([(prompt, category)])

    items = await trend_category_repository.get_visible_trends(session, limit=1)

    assert [item.id for item in items] == [41]
    assert items[0].trend_category_record is category
    assert session.execute_count == 1
    sql = str(
        session.statements[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).upper()
    assert "JOIN TREND_CATEGORIES" in sql
    assert "TREND_CATEGORIES.IS_VISIBLE IS TRUE" in sql
    assert "USER_PROMPTS.TREND_CATEGORY_ID IS NULL" in sql
    assert "TREND-CATEGORY:" in sql
    assert "LIMIT" in sql


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
async def test_folder_cursor_paginates_null_timestamps_without_duplicates():
    category = _category(2, "portrait", 1)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)

    first_session = _ScriptedSession(
        [(category,)],
        [(_prompt(30, 2, now),), (_prompt(29, 2, None),)],
    )
    first = await get_public_category_trends(
        first_session, key="portrait", limit=1, cursor=None
    )
    assert first is not None
    assert [item.id for item in first.items] == [30]
    assert decode_trend_cursor(first.next_cursor) == (now, 30)

    second_session = _ScriptedSession(
        [(category,)],
        [(_prompt(29, 2, None),), (_prompt(28, 2, None),)],
    )
    second = await get_public_category_trends(
        second_session, key="portrait", limit=1, cursor=first.next_cursor
    )
    assert second is not None
    assert [item.id for item in second.items] == [29]
    assert decode_trend_cursor(second.next_cursor) == (None, 29)

    third_session = _ScriptedSession(
        [(category,)],
        [(_prompt(28, 2, None),)],
    )
    third = await get_public_category_trends(
        third_session, key="portrait", limit=1, cursor=second.next_cursor
    )
    assert third is not None
    assert [item.id for item in third.items] == [28]
    assert third.has_more is False
    assert third.next_cursor is None

    first_sql = str(
        first_session.statements[1].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    ).upper()
    second_sql = str(
        second_session.statements[1].compile(dialect=postgresql.dialect())
    ).upper()
    third_sql = str(
        third_session.statements[1].compile(dialect=postgresql.dialect())
    ).upper()
    assert "CREATED_AT DESC NULLS LAST" in first_sql
    assert "USER_PROMPTS.TREND_CATEGORY_ID IS NULL" in first_sql
    assert "TREND-CATEGORY:PORTRAIT" in first_sql
    assert "CREATED_AT IS NULL" in second_sql
    assert "CREATED_AT IS NULL" in third_sql
    assert "USER_PROMPTS.ID <" in third_sql


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


@pytest.mark.asyncio
async def test_web_admin_create_dual_writes_category_relation_and_legacy_tag(monkeypatch):
    category = _category(6, "animals", 4)
    prompt = SimpleNamespace(id=70, trend_user_fields=None)
    create = AsyncMock(return_value=prompt)
    monkeypatch.setattr("api.trends_routes.settings.ADMIN_IDS", [111])
    monkeypatch.setattr("api.trends_routes._validated_model", AsyncMock())
    monkeypatch.setattr("api.trends_routes.create_prompt", create)
    monkeypatch.setattr("api.trends_routes.approve_prompt", AsyncMock(return_value=prompt))
    monkeypatch.setattr("api.trends_routes.trend_admin_payload", lambda item: {"id": item.id})
    monkeypatch.setattr(
        "api.trends_routes.require_existing_trend_category",
        AsyncMock(return_value=category),
        raising=False,
    )
    session = SimpleNamespace(commit=AsyncMock())

    await admin_create_trend(
        TrendCreateRequest(
            kind="image",
            title="Animal trend",
            description="",
            prompt_template="hidden",
            preview_url="https://cdn.test/animal.webp",
            model="image-model",
            settings={"category": "animals"},
        ),
        session=session,
        user=SimpleNamespace(id=1, tg_id=111),
    )

    assert create.await_args.kwargs["trend_category_id"] == 6
    assert "trend-category:animals" in create.await_args.kwargs["tags"]


@pytest.mark.asyncio
async def test_web_admin_update_dual_writes_changed_category_and_tag(monkeypatch):
    category = _category(6, "animals", 4)
    prompt = SimpleNamespace(
        id=70,
        title="Portrait trend",
        description="",
        prompt_text="hidden",
        preview_url="https://cdn.test/portrait.webp",
        model="image-model",
        tags=["trend", "trend-category:portrait"],
        trend_category_id=3,
        trend_category_record=None,
        trend_user_fields=[],
    )
    monkeypatch.setattr("api.trends_routes.settings.ADMIN_IDS", [111])
    monkeypatch.setattr("api.trends_routes.get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr("api.trends_routes.trend_admin_payload", lambda item: {"id": item.id})
    monkeypatch.setattr(
        "api.trends_routes.require_existing_trend_category",
        AsyncMock(return_value=category),
        raising=False,
    )
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    await admin_update_trend(
        70,
        TrendUpdateRequest(settings={"category": "animals"}),
        session=session,
        user=SimpleNamespace(id=1, tg_id=111),
    )

    assert prompt.trend_category_id == 6
    assert "trend-category:animals" in prompt.tags
    assert "trend-category:portrait" not in prompt.tags


@pytest.mark.asyncio
async def test_web_admin_update_preserves_unresolved_legacy_category(monkeypatch):
    prompt = SimpleNamespace(
        id=72,
        title="Legacy trend",
        description="",
        prompt_text="hidden",
        preview_url="https://cdn.test/legacy.webp",
        model="image-model",
        tags=["trend", "trend-category:legacy-special", "trend-ratio:1:1"],
        trend_category_id=1,
        trend_category_record=None,
        trend_user_fields=[],
    )
    monkeypatch.setattr("api.trends_routes.settings.ADMIN_IDS", [111])
    monkeypatch.setattr("api.trends_routes.get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr("api.trends_routes.trend_admin_payload", lambda item: {"id": item.id})
    monkeypatch.setattr(
        "api.trends_routes.get_existing_trend_category", AsyncMock(return_value=None)
    )
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    await admin_update_trend(
        72,
        TrendUpdateRequest(settings={"ratio": "4:5"}),
        session=session,
        user=SimpleNamespace(id=1, tg_id=111),
    )

    assert prompt.trend_category_id == 1
    assert "trend-category:legacy-special" in prompt.tags
    assert "trend-category:featured" not in prompt.tags


@pytest.mark.asyncio
async def test_telegram_admin_create_dual_writes_category_relation_and_tag(monkeypatch):
    from bot.handlers import trends as bot_trends

    category = _category(8, "cat_dynamic", 7)
    prompt = SimpleNamespace(id=71)
    create = AsyncMock(return_value=prompt)
    state = AsyncMock()
    state.get_data.return_value = {
        "kind": "image",
        "category": "cat_dynamic",
        "title": "Animal trend",
        "description": "",
        "prompt_template": "hidden",
        "preview_url": "https://cdn.test/animal.webp",
        "model": "image-model",
        "scenario": "image",
        "requires_reference": True,
    }
    call = SimpleNamespace(
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(bot_trends, "create_prompt", create)
    monkeypatch.setattr(bot_trends, "approve_prompt", AsyncMock())
    monkeypatch.setattr(bot_trends, "_show", AsyncMock())
    monkeypatch.setattr(bot_trends, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(
        bot_trends,
        "require_existing_trend_category",
        AsyncMock(return_value=category),
        raising=False,
    )

    await bot_trends.confirm_trend(
        call,
        state,
        session=SimpleNamespace(),
        db_user=SimpleNamespace(id=1),
    )

    assert create.await_args.kwargs["trend_category_id"] == 8
    assert "trend-category:cat_dynamic" in create.await_args.kwargs["tags"]
    assert "trend-category:featured" not in create.await_args.kwargs["tags"]
