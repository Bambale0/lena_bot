from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from db import repository
from db.models import GenerationType, UserModelEntitlement


@pytest.mark.asyncio
async def test_effective_image_generation_credits_returns_zero_for_entitled_user(monkeypatch) -> None:
    monkeypatch.setattr(
        repository,
        "is_user_image_model_unlimited",
        AsyncMock(return_value=True),
    )

    credits = await repository.effective_image_generation_credits(
        AsyncMock(),
        user_id=7,
        model_key="nano-banana-2",
        configured_credits=12.5,
    )

    assert credits == 0.0


@pytest.mark.asyncio
async def test_effective_image_generation_credits_keeps_configured_price_without_entitlement(monkeypatch) -> None:
    monkeypatch.setattr(
        repository,
        "is_user_image_model_unlimited",
        AsyncMock(return_value=False),
    )

    credits = await repository.effective_image_generation_credits(
        AsyncMock(),
        user_id=7,
        model_key="nano-banana-2",
        configured_credits=12.5,
    )

    assert credits == 12.5


@pytest.mark.asyncio
async def test_set_user_image_model_unlimited_creates_entitlement() -> None:
    model_result = MagicMock()
    model_result.scalar_one_or_none.return_value = SimpleNamespace(
        gen_type=GenerationType.image,
        model_key="nano-banana-2",
    )
    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = None
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[model_result, existing_result]),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    enabled = await repository.set_user_image_model_unlimited(
        session,
        user_id=42,
        model_key="nano-banana-2",
        enabled=True,
        created_by_tg_id=1001,
    )

    assert enabled is True
    session.add.assert_called_once()
    entitlement = session.add.call_args.args[0]
    assert isinstance(entitlement, UserModelEntitlement)
    assert entitlement.user_id == 42
    assert entitlement.model_key == "nano-banana-2"
    assert entitlement.is_unlimited is True
    assert entitlement.created_by_tg_id == 1001
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_key", "gen_type"),
    [
        ("kling-3.0/video", GenerationType.video),
        ("nano-banana-2__quality=4K", GenerationType.image),
        ("legacy::image", GenerationType.image),
    ],
)
async def test_set_user_image_model_unlimited_rejects_non_base_image_models(model_key, gen_type) -> None:
    model_result = MagicMock()
    model_result.scalar_one_or_none.return_value = SimpleNamespace(
        gen_type=gen_type,
        model_key=model_key,
    )
    session = SimpleNamespace(
        execute=AsyncMock(return_value=model_result),
        add=MagicMock(),
        commit=AsyncMock(),
    )

    with pytest.raises(ValueError, match="Only base image models"):
        await repository.set_user_image_model_unlimited(
            session,
            user_id=42,
            model_key=model_key,
            enabled=True,
        )

    session.commit.assert_not_awaited()
