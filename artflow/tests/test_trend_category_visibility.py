from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api import miniapp_routes
from api.trends_routes import _get_public_trend, list_trends
from api.web import prompts as web_prompts
from db.models import PromptCategory, PromptStatus


def _library_prompt(prompt_id: int, *, trend: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=prompt_id,
        title=f"Prompt {prompt_id}",
        description="Description",
        prompt_text=f"secret recipe {prompt_id}",
        category=PromptCategory.photo,
        tags=["trend", "trend-category:portrait"] if trend else ["photo"],
        trend_category_id=3 if trend else None,
        uses_count=0,
        likes=0,
        status=PromptStatus.approved,
        is_public=True,
        preview_url=None,
        model="nano-banana-pro",
        author_id=2,
        reject_reason=None,
        ai_moderation_decision=None,
        ai_moderation_risk=None,
        ai_moderation_reason=None,
        ai_moderation_recommendation=None,
        ai_moderated_at=None,
        created_at=None,
    )


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


@pytest.mark.asyncio
async def test_miniapp_prompt_list_excludes_hidden_category_trends(monkeypatch):
    ordinary = _library_prompt(1, trend=False)
    hidden = _library_prompt(2, trend=True)
    monkeypatch.setattr(
        "db.prompt_repository.get_approved_prompts",
        AsyncMock(return_value=[ordinary, hidden]),
    )
    monkeypatch.setattr("db.prompt_repository.count_approved_prompts", AsyncMock(return_value=2))
    monkeypatch.setattr(
        miniapp_routes,
        "filter_public_prompt_library_items",
        AsyncMock(return_value=[ordinary]),
        raising=False,
    )

    payload = await miniapp_routes.list_prompts(
        category=None,
        source="catalog",
        tag=None,
        page=1,
        limit=40,
        session=SimpleNamespace(),
        _=SimpleNamespace(id=1),
    )

    assert [item["id"] for item in payload["items"]] == [ordinary.id]
    assert "secret recipe 2" not in str(payload)


@pytest.mark.asyncio
async def test_web_prompt_list_excludes_hidden_category_trends(monkeypatch):
    ordinary = _library_prompt(1, trend=False)
    hidden = _library_prompt(2, trend=True)
    monkeypatch.setattr(web_prompts, "get_approved_prompts", AsyncMock(return_value=[ordinary, hidden]))
    monkeypatch.setattr(web_prompts, "count_approved_prompts", AsyncMock(return_value=2))
    monkeypatch.setattr(
        web_prompts,
        "filter_public_prompt_library_items",
        AsyncMock(return_value=[ordinary]),
        raising=False,
    )
    monkeypatch.setattr(
        web_prompts,
        "_prompt_cards",
        AsyncMock(side_effect=lambda _session, items, **_kwargs: [
            {"id": item.id, "prompt_text": item.prompt_text} for item in items
        ]),
    )

    payload = await web_prompts.prompts(
        source="catalog",
        tag=None,
        category=None,
        page=1,
        limit=40,
        session=SimpleNamespace(),
        user=None,
    )

    assert [item["id"] for item in payload["data"]["items"]] == [ordinary.id]
    assert "secret recipe 2" not in str(payload)


@pytest.mark.asyncio
async def test_miniapp_prompt_detail_and_use_reject_hidden_category_trend(monkeypatch):
    hidden = _library_prompt(2, trend=True)
    monkeypatch.setattr("db.prompt_repository.get_prompt_by_id", AsyncMock(return_value=hidden))
    use_prompt = AsyncMock(return_value=(hidden, {}))
    monkeypatch.setattr("db.prompt_repository.use_prompt", use_prompt)
    monkeypatch.setattr(
        miniapp_routes,
        "public_prompt_library_item_is_visible",
        AsyncMock(return_value=False),
        raising=False,
    )

    with pytest.raises(HTTPException) as detail_exc:
        await miniapp_routes.get_prompt(2, SimpleNamespace(), SimpleNamespace(id=1))
    with pytest.raises(HTTPException) as use_exc:
        await miniapp_routes.use_prompt_web(2, SimpleNamespace(), SimpleNamespace(id=1))

    assert detail_exc.value.status_code == 404
    assert use_exc.value.status_code == 404
    use_prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_web_prompt_detail_and_use_reject_hidden_category_trend(monkeypatch):
    hidden = _library_prompt(2, trend=True)
    monkeypatch.setattr(web_prompts, "get_prompt_by_id", AsyncMock(return_value=hidden))
    use_prompt = AsyncMock(return_value=(hidden, {}))
    monkeypatch.setattr(web_prompts, "use_prompt", use_prompt)
    monkeypatch.setattr(
        web_prompts,
        "public_prompt_library_item_is_visible",
        AsyncMock(return_value=False),
        raising=False,
    )

    detail = await web_prompts.prompt_detail(2, SimpleNamespace(), None)
    used = await web_prompts.prompt_use(2, SimpleNamespace(), SimpleNamespace(id=1))

    assert detail.status_code == 404
    assert used.status_code == 404
    use_prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_catalog_and_stale_callback_reject_hidden_category_trend(monkeypatch):
    from bot.handlers import trends as bot_trends

    hidden = _library_prompt(2, trend=True)
    monkeypatch.setattr(bot_trends, "get_prompts_by_tag", AsyncMock(return_value=[hidden]))
    monkeypatch.setattr(
        bot_trends,
        "filter_public_prompt_library_items",
        AsyncMock(return_value=[]),
        raising=False,
    )
    edit = AsyncMock()
    monkeypatch.setattr(bot_trends, "safe_edit_message", edit)
    holder = SimpleNamespace()

    await bot_trends._show(holder, SimpleNamespace(), None, trend_id=hidden.id)

    assert "secret recipe 2" not in str(edit.await_args)
    assert "Prompt 2" not in str(edit.await_args)
    assert "не опубликовал" in edit.await_args.args[1]

    monkeypatch.setattr(bot_trends, "get_prompt_by_id", AsyncMock(return_value=hidden))
    monkeypatch.setattr(
        bot_trends,
        "public_prompt_library_item_is_visible",
        AsyncMock(return_value=False),
        raising=False,
    )
    call = SimpleNamespace(
        data="trends:use:2",
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    await bot_trends.use_trend(
        call, SimpleNamespace(), AsyncMock(), SimpleNamespace(id=1), AsyncMock()
    )

    call.message.answer.assert_not_awaited()
    assert call.answer.await_args.kwargs["show_alert"] is True
