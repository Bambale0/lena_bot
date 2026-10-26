from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.trends_routes import _get_public_trend, list_trends
from db.models import PromptStatus


@pytest.mark.asyncio
async def test_hidden_category_blocks_direct_public_trend(monkeypatch):
    prompt = SimpleNamespace(
        id=41,
        status=PromptStatus.approved,
        is_public=True,
        tags=["trend", "trend-category:portrait"],
        trend_category_id=3,
    )
    monkeypatch.setattr("api.trends_routes.get_prompt_by_id", AsyncMock(return_value=prompt))
    visibility = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "api.trends_routes.get_visible_trend_category_for_prompt",
        visibility,
        raising=False,
    )

    with pytest.raises(HTTPException) as exc:
        await _get_public_trend(SimpleNamespace(), prompt.id)

    assert exc.value.status_code == 404
    visibility.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_list_excludes_trends_from_hidden_categories(monkeypatch):
    visible = SimpleNamespace(
        id=1,
        title="Visible",
        description="",
        preview_url=None,
        tags=["trend", "trend-category:featured"],
        trend_category_id=1,
        trend_category_record=SimpleNamespace(key="featured", title="Тренды"),
        trend_user_fields=[],
        status=SimpleNamespace(value="approved"),
        is_public=True,
        uses_count=0,
        likes=0,
        created_at=None,
    )
    hidden = SimpleNamespace(id=2, trend_category_id=2)
    monkeypatch.setattr(
        "api.trends_routes.get_prompts_by_tag", AsyncMock(return_value=[visible, hidden])
    )
    hydrate = AsyncMock(return_value=[visible])
    monkeypatch.setattr(
        "api.trends_routes.hydrate_visible_trend_categories", hydrate, raising=False
    )

    payload = await list_trends(
        kind=None,
        limit=80,
        session=SimpleNamespace(),
        user=SimpleNamespace(id=7),
    )

    assert [item["id"] for item in payload] == [1]
    hydrate.assert_awaited_once()


@pytest.mark.asyncio
async def test_bot_admin_accepts_dynamic_visible_category(monkeypatch):
    from bot.handlers import trends as bot_trends

    call = SimpleNamespace(
        data="trends:category:cat_dynamic",
        from_user=SimpleNamespace(id=111),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data.return_value = {"kind": "image"}
    category = SimpleNamespace(id=9, key="cat_dynamic", title="Динамическая")
    model = SimpleNamespace(
        model_key="image-model",
        display_name="Image model",
        gen_type=SimpleNamespace(value="image"),
        is_active=True,
    )
    monkeypatch.setattr(
        bot_trends,
        "get_visible_trend_category",
        AsyncMock(return_value=category),
        raising=False,
    )
    monkeypatch.setattr(bot_trends.repo, "get_all_model_costs", AsyncMock(return_value=[model]))
    monkeypatch.setattr(bot_trends, "visible_model_costs", AsyncMock(return_value=[model]))
    monkeypatch.setattr(bot_trends, "safe_answer_callback", AsyncMock())

    await bot_trends.trend_category_pick(call, state, SimpleNamespace())

    state.update_data.assert_awaited_with(category="cat_dynamic")
    assert "trends:model:image-model" in {
        button.callback_data
        for row in call.message.answer.await_args.kwargs["reply_markup"].inline_keyboard
        for button in row
        if button.callback_data
    }
