from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import trends


@pytest.mark.asyncio
async def test_trend_category_uses_model_key_when_gen_type_metadata_is_missing(monkeypatch) -> None:
    model = SimpleNamespace(
        model_key="kling-3.0/video",
        display_name="Kling 3.0",
        gen_type=None,
        is_active=True,
    )
    monkeypatch.setattr(trends.repo, "get_all_model_costs", AsyncMock(return_value=[model]))

    call = SimpleNamespace(
        data="trends:category:featured",
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"kind": "video"})

    await trends.trend_category_pick(call, state, AsyncMock())

    state.clear.assert_not_awaited()
    state.update_data.assert_awaited_once_with(category="featured")
    state.set_state.assert_awaited_once_with(trends.TrendAdminFSM.model)
    text = call.message.answer.await_args.args[0]
    assert text == "Выбери модель:"
    assert call.message.answer.await_args.kwargs["reply_markup"] is not None
    call.answer.assert_awaited()


@pytest.mark.asyncio
async def test_trend_category_keeps_wizard_state_when_models_are_temporarily_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(trends.repo, "get_all_model_costs", AsyncMock(return_value=[]))

    call = SimpleNamespace(
        data="trends:category:featured",
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"kind": "video"})

    await trends.trend_category_pick(call, state, AsyncMock())

    state.clear.assert_not_awaited()
    state.set_state.assert_not_awaited()
    call.message.answer.assert_awaited_once()
    assert "не нашёл" in call.message.answer.await_args.args[0].lower()
    call.answer.assert_awaited()
