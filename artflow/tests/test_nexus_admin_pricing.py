from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import admin
from db import repository as repo
from db.models import GenerationType
from tests.factories import make_callback, make_message


def _cost(model_key: str, display_name: str, credits: float) -> SimpleNamespace:
    return SimpleNamespace(
        model_key=model_key,
        display_name=display_name,
        credits=credits,
        gen_type=GenerationType.image,
        is_active=True,
    )


def test_admin_menu_exposes_dedicated_nexus_pricing() -> None:
    markup = admin.admin_menu_kb()
    callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert "adm:nexus_models" in callbacks
    assert "adm:models" in callbacks


def test_nexus_pricing_keyboard_has_exact_six_commercial_models() -> None:
    costs = [
        _cost("nano-banana-pro", "Nano Banana Pro", 2),
        _cost("nano-banana-2", "Banana 2", 1.5),
        _cost("seedream/5-pro-text-to-image", "Seedream 5 Pro", 2),
        _cost("gpt-image-2-text-to-image", "GPT 2", 2),
        _cost("nano-banana-pro-vip", "Нана Банано Про ВИП", 8),
        _cost("gpt-image-2-vip", "ГПТ 2 ВИП", 5),
    ]
    markup = admin._nexus_models_kb(costs)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    model_callbacks = [value for value in callbacks if value and value.startswith("adm:nx:")]
    assert model_callbacks == [
        "adm:nx:nano_pro",
        "adm:nx:banana2",
        "adm:nx:seedream5",
        "adm:nx:gpt2",
        "adm:nx:nano_pro_vip",
        "adm:nx:gpt2_vip",
    ]


def test_nexus_price_summary_shows_quality_range_without_technical_keys() -> None:
    costs = [
        _cost("nano-banana-pro", "Nano Banana Pro", 2),
        _cost("nano-banana-pro__quality=2K", "Nano Banana Pro 2K", 2),
        _cost("nano-banana-pro__quality=4K", "Nano Banana Pro 4K", 3),
    ]
    assert admin._nexus_price_summary(costs, ("nano-banana-pro",)) == "2–3 кр"


@pytest.mark.asyncio
async def test_cb_nexus_models_renders_current_prices() -> None:
    call = make_callback(data="adm:nexus_models")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    costs = [
        _cost("nano-banana-pro", "Nano Banana Pro", 2),
        _cost("nano-banana-pro__quality=4K", "Nano Banana Pro 4K", 3),
        _cost("nano-banana-pro-vip", "Нана Банано Про ВИП", 8),
    ]
    with patch.object(admin.repo, "get_all_model_costs", AsyncMock(return_value=costs)):
        await admin.cb_nexus_models(call, AsyncMock())

    call.message.edit_text.assert_awaited_once()
    markup = call.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any("Nano Banana Pro — 2–3 кр" in text for text in labels)
    assert any("Нана Банано Про ВИП — 8 кр" in text for text in labels)


@pytest.mark.asyncio
async def test_nexus_price_input_accepts_decimal_comma_and_updates_whole_seedream_family() -> None:
    message = make_message(text="2,5")
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"edit_nexus_model_slug": "seedream5"})
    session = AsyncMock()
    set_family = AsyncMock(return_value=6)

    with patch.object(admin.repo, "set_model_family_costs", set_family):
        await admin.handle_nexus_model_credits(message, session, state)

    set_family.assert_awaited_once_with(
        session,
        ("seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image"),
        2.5,
    )
    state.clear.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "2.5 кр" in text
    assert "Синхронизировано ценовых позиций: <b>6</b>" in text


@pytest.mark.asyncio
async def test_nexus_price_rejects_zero_without_touching_database() -> None:
    message = make_message(text="0")
    message.answer = AsyncMock()
    state = AsyncMock()
    set_family = AsyncMock()
    with patch.object(admin.repo, "set_model_family_costs", set_family):
        await admin.handle_nexus_model_credits(message, AsyncMock(), state)
    set_family.assert_not_awaited()
    assert "больше нуля" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_repository_bulk_model_price_update_is_single_transaction() -> None:
    result = MagicMock()
    result.scalars.return_value.all.return_value = [11, 12, 13, 14]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    updated = await repo.set_model_family_costs(
        session,
        ("gpt-image-2-text-to-image", "gpt-image-2-image-to-image"),
        2.5,
    )

    assert updated == 4
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
