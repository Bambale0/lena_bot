from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from bot.handlers.admin import cmd_admin_promo
from db.models import PromoRewardType
from tests.factories import make_message


@pytest.mark.asyncio
async def test_admin_promo_discount_rub_with_separate_percent_becomes_percent() -> None:
    message = make_message("/admin_promo Lena discount_rub 20 % 100")
    promo = SimpleNamespace(
        code="LENA",
        reward_type=PromoRewardType.discount_percent,
        value=20,
        max_uses=100,
        uses_count=0,
    )

    upsert = AsyncMock(return_value=promo)
    with patch("bot.handlers.admin.repo.upsert_promo_code", upsert):
        await cmd_admin_promo(message, AsyncMock())

    assert upsert.await_args.kwargs["reward_type"] == PromoRewardType.discount_percent
    assert upsert.await_args.kwargs["value"] == 20
    assert upsert.await_args.kwargs["max_uses"] == 100
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_promo_discount_rub_with_inline_percent_becomes_percent() -> None:
    message = make_message("/admin_promo Lena discount_rub 20% 100")
    promo = SimpleNamespace(
        code="LENA",
        reward_type=PromoRewardType.discount_percent,
        value=20,
        max_uses=100,
        uses_count=0,
    )

    upsert = AsyncMock(return_value=promo)
    with patch("bot.handlers.admin.repo.upsert_promo_code", upsert):
        await cmd_admin_promo(message, AsyncMock())

    assert upsert.await_args.kwargs["reward_type"] == PromoRewardType.discount_percent
    assert upsert.await_args.kwargs["value"] == 20


@pytest.mark.asyncio
async def test_admin_promo_discount_rub_without_percent_stays_rub() -> None:
    message = make_message("/admin_promo Lena discount_rub 300 100")
    promo = SimpleNamespace(
        code="LENA",
        reward_type=PromoRewardType.discount_amount,
        value=300,
        max_uses=100,
        uses_count=0,
    )

    upsert = AsyncMock(return_value=promo)
    with patch("bot.handlers.admin.repo.upsert_promo_code", upsert):
        await cmd_admin_promo(message, AsyncMock())

    assert upsert.await_args.kwargs["reward_type"] == PromoRewardType.discount_amount
    assert upsert.await_args.kwargs["value"] == 300


@pytest.mark.asyncio
async def test_admin_promo_rejects_percent_over_100() -> None:
    message = make_message("/admin_promo Lena discount_rub 120% 100")

    upsert = AsyncMock()
    with patch("bot.handlers.admin.repo.upsert_promo_code", upsert):
        await cmd_admin_promo(message, AsyncMock())

    upsert.assert_not_awaited()
    text = message.answer.await_args.args[0]
    assert "от 1 до 100" in text
