from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import trends_routes
from db.trend_category_repository import TrendCategoryConflict


def _admin():
    return SimpleNamespace(id=1, tg_id=111)


def _category(key: str = "cat_ab12", title: str = "Новая папка"):
    return SimpleNamespace(
        id=8,
        key=key,
        title=title,
        sort_order=7,
        is_visible=True,
        trend_count=2,
        published_count=2,
    )


@pytest.mark.asyncio
async def test_non_admin_cannot_read_or_mutate_category_catalog(monkeypatch):
    monkeypatch.setattr(trends_routes.settings, "ADMIN_IDS", [111])
    session = SimpleNamespace()

    with pytest.raises(HTTPException) as exc:
        await trends_routes.admin_list_trend_categories(
            session=session, user=SimpleNamespace(id=2, tg_id=222)
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_admin_create_returns_opaque_key_and_next_revision(monkeypatch):
    monkeypatch.setattr(trends_routes.settings, "ADMIN_IDS", [111])
    category = _category()
    create = AsyncMock(return_value=(category, 4))
    monkeypatch.setattr(trends_routes, "create_trend_category", create)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    result = await trends_routes.admin_create_trend_category(
        trends_routes.TrendCategoryCreateRequest(
            title="Новая папка", expected_revision=3
        ),
        session=session,
        user=_admin(),
    )

    assert result["revision"] == 4
    assert result["category"]["key"] == "cat_ab12"
    assert "новая" not in result["category"]["key"]
    session.commit.assert_awaited_once()
    create.assert_awaited_once_with(
        session,
        title="Новая папка",
        expected_revision=3,
        actor_tg_id=111,
        source="web",
    )


@pytest.mark.asyncio
async def test_stale_revision_is_409_and_rolls_back(monkeypatch):
    monkeypatch.setattr(trends_routes.settings, "ADMIN_IDS", [111])
    mutate = AsyncMock(side_effect=TrendCategoryConflict("Каталог уже изменился", 8))
    monkeypatch.setattr(trends_routes, "update_trend_category", mutate)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await trends_routes.admin_update_trend_category(
            "cat_ab12",
            trends_routes.TrendCategoryUpdateRequest(
                title="Другое название", expected_revision=7
            ),
            session=session,
            user=_admin(),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["revision"] == 8
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_reorder_requires_and_forwards_the_full_key_set(monkeypatch):
    monkeypatch.setattr(trends_routes.settings, "ADMIN_IDS", [111])
    reorder = AsyncMock(return_value=([_category()], 6))
    monkeypatch.setattr(trends_routes, "reorder_trend_categories", reorder)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    result = await trends_routes.admin_reorder_trend_categories(
        trends_routes.TrendCategoryReorderRequest(
            keys=["cat_ab12"], expected_revision=5
        ),
        session=session,
        user=_admin(),
    )

    assert result["revision"] == 6
    reorder.assert_awaited_once_with(
        session,
        keys=["cat_ab12"],
        expected_revision=5,
        actor_tg_id=111,
        source="web",
    )


@pytest.mark.asyncio
async def test_reassign_is_audited_through_shared_catalog_revision(monkeypatch):
    monkeypatch.setattr(trends_routes.settings, "ADMIN_IDS", [111])
    reassign = AsyncMock(return_value=(SimpleNamespace(id=91), _category(), 10))
    monkeypatch.setattr(trends_routes, "reassign_trend_prompt", reassign)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    result = await trends_routes.admin_reassign_trend_category(
        "cat_ab12",
        trends_routes.TrendCategoryReassignRequest(
            prompt_id=91, expected_revision=9
        ),
        session=session,
        user=_admin(),
    )

    assert result == {"ok": True, "prompt_id": 91, "category_key": "cat_ab12", "revision": 10}
    reassign.assert_awaited_once_with(
        session,
        prompt_id=91,
        target_key="cat_ab12",
        expected_revision=9,
        actor_tg_id=111,
        source="web",
    )


def test_admin_request_limits_are_explicit():
    with pytest.raises(ValueError):
        trends_routes.TrendCategoryCreateRequest(
            title="x" * 81, expected_revision=1
        )
    with pytest.raises(ValueError):
        trends_routes.TrendCategoryReorderRequest(
            keys=[f"cat_{index}" for index in range(101)], expected_revision=1
        )
