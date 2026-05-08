from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import marketplace
from tests.factories import make_callback


@pytest.mark.asyncio
async def test_prompt_like_saves_first_like(monkeypatch) -> None:
    call = make_callback(data="prompt_like:7:best:0")
    prompt = SimpleNamespace(id=7, title="Prompt", likes=3)
    show_prompt_card = AsyncMock()

    monkeypatch.setattr("bot.handlers.marketplace.like_prompt", AsyncMock(return_value=(prompt, "liked")))
    monkeypatch.setattr("bot.handlers.marketplace._prompts_for_source", AsyncMock(return_value=[prompt]))
    monkeypatch.setattr("bot.handlers.marketplace._show_prompt_card", show_prompt_card)

    await marketplace.cb_prompt_like(
        call=call,
        session=AsyncMock(),
        db_user=SimpleNamespace(id=42),
    )

    show_prompt_card.assert_awaited_once()
    call.answer.assert_awaited_once_with("Лайк сохранён ❤️")


@pytest.mark.asyncio
async def test_prompt_like_rejects_duplicate_like(monkeypatch) -> None:
    call = make_callback(data="prompt_like:7:best:0")
    prompt = SimpleNamespace(id=7, title="Prompt", likes=3)
    show_prompt_card = AsyncMock()

    monkeypatch.setattr("bot.handlers.marketplace.like_prompt", AsyncMock(return_value=(prompt, "duplicate")))
    monkeypatch.setattr("bot.handlers.marketplace._show_prompt_card", show_prompt_card)

    await marketplace.cb_prompt_like(
        call=call,
        session=AsyncMock(),
        db_user=SimpleNamespace(id=42),
    )

    show_prompt_card.assert_not_awaited()
    call.answer.assert_awaited_once_with("Ты уже лайкал этот промпт")


@pytest.mark.asyncio
async def test_prompt_like_handles_unavailable_like_storage(monkeypatch) -> None:
    call = make_callback(data="prompt_like:7:best:0")
    prompt = SimpleNamespace(id=7, title="Prompt", likes=3)
    show_prompt_card = AsyncMock()

    monkeypatch.setattr("bot.handlers.marketplace.like_prompt", AsyncMock(return_value=(prompt, "unavailable")))
    monkeypatch.setattr("bot.handlers.marketplace._show_prompt_card", show_prompt_card)

    await marketplace.cb_prompt_like(
        call=call,
        session=AsyncMock(),
        db_user=SimpleNamespace(id=42),
    )

    show_prompt_card.assert_not_awaited()
    call.answer.assert_awaited_once_with("Лайки временно недоступны", show_alert=True)
