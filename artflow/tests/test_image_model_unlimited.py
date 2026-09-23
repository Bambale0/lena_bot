from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from db import repository


@pytest.mark.asyncio
async def test_charge_image_generation_unlimited_skips_credit_spend(monkeypatch) -> None:
    session = AsyncMock()
    spend = AsyncMock(return_value=True)
    monkeypatch.setattr(repository, "has_unlimited_image_model", AsyncMock(return_value=True), raising=False)
    monkeypatch.setattr(repository, "spend_credits", spend)

    charge = await repository.charge_image_generation(
        session,
        user_id=42,
        model_key="nano-banana-2",
        amount=7.5,
        source_type="image_generation",
        source_id="test",
    )

    assert charge.allowed is True
    assert charge.unlimited is True
    assert charge.charged_credits == 0
    spend.assert_not_awaited()


@pytest.mark.asyncio
async def test_charge_image_generation_regular_user_spends_tariff(monkeypatch) -> None:
    session = AsyncMock()
    spend = AsyncMock(return_value=True)
    monkeypatch.setattr(repository, "has_unlimited_image_model", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(repository, "spend_credits", spend)

    charge = await repository.charge_image_generation(
        session,
        user_id=42,
        model_key="seedream/5-pro-text-to-image",
        amount=6,
        source_type="image_generation",
        source_id="test",
    )

    assert charge.allowed is True
    assert charge.unlimited is False
    assert charge.charged_credits == 6
    spend.assert_awaited_once()


@pytest.mark.asyncio
async def test_charge_image_generation_insufficient_balance_returns_not_allowed(monkeypatch) -> None:
    session = AsyncMock()
    spend = AsyncMock(return_value=False)
    monkeypatch.setattr(repository, "has_unlimited_image_model", AsyncMock(return_value=False), raising=False)
    monkeypatch.setattr(repository, "spend_credits", spend)

    charge = await repository.charge_image_generation(
        session,
        user_id=42,
        model_key="gpt-image-2-text-to-image",
        amount=9,
    )

    assert charge.allowed is False
    assert charge.unlimited is False
    assert charge.charged_credits == 0


@pytest.mark.asyncio
async def test_set_unlimited_rejects_non_image_model(monkeypatch) -> None:
    session = AsyncMock()
    monkeypatch.setattr(
        repository,
        "get_model_cost_by_id",
        AsyncMock(return_value=SimpleNamespace(id=9, gen_type=SimpleNamespace(value="video"))),
        raising=False,
    )

    with pytest.raises(ValueError, match="image"):
        await repository.set_user_image_model_unlimited(
            session,
            user_id=42,
            model_cost_id=9,
            enabled=True,
            admin_tg_id=100500,
        )
