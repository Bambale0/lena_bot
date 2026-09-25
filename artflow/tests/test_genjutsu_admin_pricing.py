from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.genjutsu_pricing import (
    DISPLAY_NAMES,
    MOTION_MODEL,
    OBJECT_MODEL,
)
from bot.handlers import admin
from core.model_pricing import pricing_variant_key
from db.models import GenerationType
from tests.factories import make_callback, make_message


def _cost(model_key: str, credits: float, display_name: str | None = None):
    return SimpleNamespace(
        model_key=model_key,
        display_name=display_name or model_key,
        credits=credits,
        gen_type=GenerationType.video,
        is_active=True,
    )


def _callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_admin_menu_exposes_genjutsu_pricing() -> None:
    markup = admin.admin_menu_kb()
    callbacks = _callbacks(markup)
    labels = _labels(markup)

    assert "adm:genjutsu_prices" in callbacks
    assert "🥷 Genjutsu цены" in labels


@pytest.mark.asyncio
async def test_cb_genjutsu_prices_shows_both_modes_and_resolutions(monkeypatch) -> None:
    call = make_callback(data="adm:genjutsu_prices")
    call.message.edit_text = AsyncMock()
    call.answer = AsyncMock()
    costs = [
        _cost(MOTION_MODEL, 16, DISPLAY_NAMES[MOTION_MODEL]),
        _cost(pricing_variant_key(MOTION_MODEL, resolution="480p"), 16),
        _cost(pricing_variant_key(MOTION_MODEL, resolution="720p"), 35),
        _cost(OBJECT_MODEL, 18, DISPLAY_NAMES[OBJECT_MODEL]),
        _cost(pricing_variant_key(OBJECT_MODEL, resolution="480p"), 18),
        _cost(pricing_variant_key(OBJECT_MODEL, resolution="720p"), 39),
    ]
    monkeypatch.setattr(
        admin.repo,
        "get_all_model_costs",
        AsyncMock(return_value=costs),
    )

    await admin.cb_genjutsu_prices(call, AsyncMock())

    markup = call.message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = _callbacks(markup)
    labels = _labels(markup)
    assert callbacks[:4] == [
        "adm:gjp:motion:480p",
        "adm:gjp:motion:720p",
        "adm:gjp:object:480p",
        "adm:gjp:object:720p",
    ]
    assert any("Перенос движения · 480p — 16 кр/сек" in label for label in labels)
    assert any("Перенос движения · 720p — 35 кр/сек" in label for label in labels)
    assert any("Замена объекта · 480p — 18 кр/сек" in label for label in labels)
    assert any("Замена объекта · 720p — 39 кр/сек" in label for label in labels)


@pytest.mark.asyncio
async def test_cb_genjutsu_price_edit_starts_fsm() -> None:
    call = make_callback(data="adm:gjp:object:720p")
    call.message.answer = AsyncMock()
    call.answer = AsyncMock()
    state = AsyncMock()

    await admin.cb_genjutsu_price_edit(call, state)

    state.set_state.assert_awaited_once_with(admin.AdminFSM.edit_genjutsu_credits)
    state.update_data.assert_awaited_once_with(
        genjutsu_model_key=OBJECT_MODEL,
        genjutsu_resolution="720p",
    )
    assert "кр/сек" in call.message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_handle_genjutsu_price_updates_resolution_and_default_base(monkeypatch) -> None:
    message = make_message(text="21,5")
    message.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "genjutsu_model_key": MOTION_MODEL,
            "genjutsu_resolution": "480p",
        }
    )
    set_price = AsyncMock(return_value=2)
    monkeypatch.setattr(admin.repo, "set_model_resolution_cost", set_price)

    await admin.handle_genjutsu_price(message, AsyncMock(), state)

    set_price.assert_awaited_once_with(
        pytest.ANY,
        MOTION_MODEL,
        "480p",
        21.5,
        sync_base=True,
    )
    state.clear.assert_awaited_once()
    assert "21.5 кр/сек" in message.answer.await_args.args[0]
