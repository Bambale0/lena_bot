from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.handlers import admin
from db import repository as repo
from db.models import GenerationType
from db.seed import DEFAULT_MODEL_COSTS
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


def test_nano_pro_summary_keeps_2k_and_4k_separate() -> None:
    costs = [
        _cost("nano-banana-pro", "Nano Banana Pro", 2),
        _cost("nano-banana-pro__quality=2K", "Nano Banana Pro 2K", 2),
        _cost("nano-banana-pro__quality=4K", "Nano Banana Pro 4K", 3),
    ]
    config = admin._NEXUS_ADMIN_GROUPS["nano_pro"]
    assert admin._nexus_price_summary(costs, config) == "2K 2 кр / 4K 3 кр"


def test_nano_pro_card_has_distinct_2k_and_4k_price_buttons() -> None:
    costs = [
        _cost("nano-banana-pro", "Nano Banana Pro", 2),
        _cost("nano-banana-pro__quality=2K", "Nano Banana Pro 2K", 2),
        _cost("nano-banana-pro__quality=4K", "Nano Banana Pro 4K", 3),
    ]
    markup = admin._nexus_model_kb("nano_pro", costs)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "adm:nxq:nano_pro:2K" in callbacks
    assert "adm:nxq:nano_pro:4K" in callbacks
    assert "adm:nxp:nano_pro" not in callbacks


def test_seedream_card_separates_public_1k_and_2k_prices() -> None:
    costs = [
        _cost("seedream/5-pro-text-to-image__quality=basic", "Seedream 1K", 2),
        _cost("seedream/5-pro-image-to-image__quality=basic", "Seedream Edit 1K", 2),
        _cost("seedream/5-pro-text-to-image__quality=high", "Seedream 2K", 3),
        _cost("seedream/5-pro-image-to-image__quality=high", "Seedream Edit 2K", 3),
    ]
    markup = admin._nexus_model_kb("seedream5", costs)
    buttons = [button for row in markup.inline_keyboard for button in row]
    by_callback = {button.callback_data: button.text for button in buttons}
    assert by_callback["adm:nxq:seedream5:basic"] == "✏️ 1K — 2 кр"
    assert by_callback["adm:nxq:seedream5:high"] == "✏️ 2K — 3 кр"


def test_nano_pro_vip_card_separates_public_2k_and_1k_prices() -> None:
    costs = [
        _cost("nano-banana-pro-vip", "Нана Банано Про ВИП", 8),
        _cost("nano-banana-pro-vip__quality=2K", "VIP 2K", 8),
        _cost("nano-banana-pro-vip__quality=1K", "VIP 1K", 6),
    ]
    markup = admin._nexus_model_kb("nano_pro_vip", costs)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "adm:nxq:nano_pro_vip:2K" in callbacks
    assert "adm:nxq:nano_pro_vip:1K" in callbacks


def test_gpt2_keeps_single_price_control() -> None:
    costs = [
        _cost("gpt-image-2-text-to-image", "GPT 2", 2),
        _cost("gpt-image-2-image-to-image", "GPT 2 Edit", 2),
    ]
    markup = admin._nexus_model_kb("gpt2", costs)
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert "adm:nxp:gpt2" in callbacks
    assert not any(value and value.startswith("adm:nxq:gpt2:") for value in callbacks)


@pytest.mark.asyncio
async def test_cb_nexus_models_renders_quality_prices() -> None:
    call = make_callback(data="adm:nexus_models")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    costs = [
        _cost("nano-banana-pro", "Nano Banana Pro", 2),
        _cost("nano-banana-pro__quality=2K", "Nano Banana Pro 2K", 2),
        _cost("nano-banana-pro__quality=4K", "Nano Banana Pro 4K", 3),
        _cost("gpt-image-2-vip", "ГПТ 2 ВИП", 5),
    ]
    with patch.object(admin.repo, "get_all_model_costs", AsyncMock(return_value=costs)):
        await admin.cb_nexus_models(call, AsyncMock())

    markup = call.message.edit_text.await_args.kwargs["reply_markup"]
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert any("Nano Banana Pro — 2K 2 кр / 4K 3 кр" in text for text in labels)
    assert any("ГПТ 2 ВИП — 5 кр" in text for text in labels)


@pytest.mark.asyncio
async def test_nexus_4k_price_input_updates_only_selected_quality() -> None:
    message = make_message(text="2,5")
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={"edit_nexus_model_slug": "nano_pro", "edit_nexus_model_quality": "4K"}
    )
    session = AsyncMock()
    set_quality = AsyncMock(return_value=1)
    set_family = AsyncMock()

    with patch.object(admin.repo, "set_model_family_quality_costs", set_quality), patch.object(
        admin.repo, "set_model_family_costs", set_family
    ):
        await admin.handle_nexus_model_credits(message, session, state)

    set_quality.assert_awaited_once_with(
        session,
        ("nano-banana-pro",),
        "4K",
        2.5,
        sync_base=False,
    )
    set_family.assert_not_awaited()
    assert "Nano Banana Pro · 4K" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_nexus_default_2k_price_syncs_base_fallback() -> None:
    message = make_message(text="1,5")
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={"edit_nexus_model_slug": "banana2", "edit_nexus_model_quality": "2K"}
    )
    session = AsyncMock()
    set_quality = AsyncMock(return_value=2)

    with patch.object(admin.repo, "set_model_family_quality_costs", set_quality):
        await admin.handle_nexus_model_credits(message, session, state)

    set_quality.assert_awaited_once_with(
        session,
        ("nano-banana-2",),
        "2K",
        1.5,
        sync_base=True,
    )


@pytest.mark.asyncio
async def test_seedream_2k_price_updates_text_and_image_routes_only_for_high_quality() -> None:
    message = make_message(text="4")
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={"edit_nexus_model_slug": "seedream5", "edit_nexus_model_quality": "high"}
    )
    session = AsyncMock()
    set_quality = AsyncMock(return_value=2)

    with patch.object(admin.repo, "set_model_family_quality_costs", set_quality):
        await admin.handle_nexus_model_credits(message, session, state)

    set_quality.assert_awaited_once_with(
        session,
        ("seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image"),
        "high",
        4.0,
        sync_base=False,
    )


@pytest.mark.asyncio
async def test_gpt2_single_price_still_updates_whole_internal_family() -> None:
    message = make_message(text="2,5")
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"edit_nexus_model_slug": "gpt2", "edit_nexus_model_quality": None})
    session = AsyncMock()
    set_family = AsyncMock(return_value=2)

    with patch.object(admin.repo, "set_model_family_costs", set_family):
        await admin.handle_nexus_model_credits(message, session, state)

    set_family.assert_awaited_once_with(
        session,
        ("gpt-image-2-text-to-image", "gpt-image-2-image-to-image"),
        2.5,
    )


@pytest.mark.asyncio
async def test_nexus_price_rejects_zero_without_touching_database() -> None:
    message = make_message(text="0")
    message.answer = AsyncMock()
    state = AsyncMock()
    set_family = AsyncMock()
    set_quality = AsyncMock()
    with patch.object(admin.repo, "set_model_family_costs", set_family), patch.object(
        admin.repo, "set_model_family_quality_costs", set_quality
    ):
        await admin.handle_nexus_model_credits(message, AsyncMock(), state)
    set_family.assert_not_awaited()
    set_quality.assert_not_awaited()
    assert "больше нуля" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_repository_quality_price_update_is_single_transaction() -> None:
    result = MagicMock()
    result.scalars.return_value.all.return_value = [11, 12, 13]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=result)

    updated = await repo.set_model_family_quality_costs(
        session,
        ("seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image"),
        "basic",
        2.5,
        sync_base=True,
    )

    assert updated == 3
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


def test_seed_adds_vip_quality_rows_for_existing_public_quality_choices() -> None:
    rows = {str(item["model_key"]): item for item in DEFAULT_MODEL_COSTS}
    assert rows["nano-banana-pro-vip__quality=2K"]["credits"] == 8
    assert rows["nano-banana-pro-vip__quality=1K"]["credits"] == 8
