from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import seedance25_adapter as s25
from bot.handlers import seedance25_references as refs
from bot.keyboards.payment import payment_link_kb


def _callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]


def test_recommended_plan_is_smallest_active_package_covering_deficit() -> None:
    plans = [
        SimpleNamespace(key="p500", credits=500.0, price_rub=500.0, is_active=True, sort_order=2),
        SimpleNamespace(key="p100", credits=100.0, price_rub=100.0, is_active=True, sort_order=1),
        SimpleNamespace(key="p300", credits=300.0, price_rub=300.0, is_active=True, sort_order=3),
    ]

    plan = refs._recommended_checkout_plan(plans, 35.0)

    assert plan.key == "p100"


def test_recommended_plan_falls_back_to_largest_active_package() -> None:
    plans = [
        SimpleNamespace(key="p100", credits=100.0, price_rub=100.0, is_active=True, sort_order=1),
        SimpleNamespace(key="p300", credits=300.0, price_rub=300.0, is_active=True, sort_order=2),
    ]

    plan = refs._recommended_checkout_plan(plans, 999.0)

    assert plan.key == "p300"


@pytest.mark.asyncio
async def test_insufficient_seedance_balance_opens_inline_checkout(monkeypatch) -> None:
    call = SimpleNamespace(
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"wizard_review_enabled": True, "wizard_scenario": "advanced"})
    session = object()
    user = SimpleNamespace(id=7, credits=0.0, language="ru")
    model_cost = SimpleNamespace(credits=7.0)
    plan = SimpleNamespace(
        key="credits_100",
        label="100 💋",
        credits=100.0,
        price_rub=100.0,
        is_active=True,
        sort_order=1,
    )

    monkeypatch.setattr(refs.repo, "resolve_video_model_cost", AsyncMock(return_value=model_cost))
    monkeypatch.setattr(refs.repo, "get_active_price_plans", AsyncMock(return_value=[plan]))
    monkeypatch.setattr(refs.settings, "TBANK_TERMINAL_KEY", "terminal")
    monkeypatch.setattr(refs.settings, "TBANK_PASSWORD", "password")
    monkeypatch.setattr(refs.settings, "CRYPTOBOT_TOKEN", "")
    monkeypatch.setattr(refs.settings, "TRIBUTE_API_KEY", "")
    monkeypatch.setattr(type(refs.settings), "lava_is_enabled", lambda self: False)

    await refs.choose_seedance25(call, state, session, user)

    call.answer.assert_awaited_once()
    assert call.answer.await_args.kwargs.get("show_alert") is not True
    call.message.edit_text.assert_awaited_once()
    text = call.message.edit_text.await_args.args[0]
    markup = call.message.edit_text.await_args.kwargs["reply_markup"]
    assert "Нужно для 5 сек: <b>35 💋</b>" in text
    assert "Баланс: <b>0 💋</b>" in text
    assert "Не хватает: <b>35 💋</b>" in text
    assert "100 💋" in text
    assert "100 ₽" in text
    assert "topup:rub:credits_100" in _callbacks(markup)
    assert "s25pay:continue" in _callbacks(markup)
    state.update_data.assert_awaited_once()
    assert state.update_data.await_args.kwargs["payment_return_callback"] == "s25pay:continue"
    assert state.update_data.await_args.kwargs["payment_return_label"] == "🎬 Продолжить Seedance 2.5"


def test_payment_link_can_return_to_generation_context() -> None:
    markup = payment_link_kb(
        "💳 Перейти к оплате",
        "https://pay.example/1",
        "tx-1",
        back_callback="s25pay:continue",
        back_text="🎬 Продолжить Seedance 2.5",
    )

    callbacks = _callbacks(markup)
    assert "topup:check:tx-1" in callbacks
    assert "s25pay:continue" in callbacks
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert "🎬 Продолжить Seedance 2.5" in labels


@pytest.mark.asyncio
async def test_continue_after_payment_enters_seedance_flow(monkeypatch) -> None:
    call = SimpleNamespace(
        message=SimpleNamespace(edit_text=AsyncMock()),
        answer=AsyncMock(),
    )
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"wizard_review_enabled": True, "wizard_scenario": "advanced"})
    session = object()
    user = SimpleNamespace(id=7, credits=100.0, language="ru")
    model_cost = SimpleNamespace(credits=7.0)

    monkeypatch.setattr(refs.repo, "resolve_video_model_cost", AsyncMock(return_value=model_cost))

    await refs.continue_seedance25_after_payment(call, state, session, user)

    state.set_state.assert_awaited_once()
    update = state.update_data.await_args.kwargs
    assert update["model_key"] == s25.MODEL_KEY
    assert update["duration"] == 5
    assert update["resolution"] == "720p"
    assert update["payment_return_callback"] is None
    call.message.edit_text.assert_awaited_once()
