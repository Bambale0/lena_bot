from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import payment
from bot.keyboards.payment import plan_payment_methods_kb, topup_kb


def _callbacks(markup) -> list[str | None]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_main_topup_package_routes_to_payment_method_choice() -> None:
    plan = SimpleNamespace(label="Профи", credits=100, price_rub=1000.0, key="credits_100_999")
    buttons = [button for row in topup_kb([plan]).inline_keyboard for button in row]
    assert buttons[0].callback_data == "topup:plan:credits_100_999"


def test_plan_payment_methods_include_tbank_tribute_and_crypto_without_stars(monkeypatch) -> None:
    plan = SimpleNamespace(label="Профи", credits=100, price_rub=1000.0, key="credits_100_999")
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TRIBUTE_API_KEY", "tribute", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.CRYPTOBOT_TOKEN", "crypto", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.LAVA_API_KEY", "", raising=False)

    markup = plan_payment_methods_kb(plan)
    callbacks = _callbacks(markup)
    texts = [button.text for row in markup.inline_keyboard for button in row]

    assert "topup:rub:credits_100_999" in callbacks
    assert "topup:tribute_plan:credits_100_999" in callbacks
    assert "topup:crypto_plan:credits_100_999" in callbacks
    assert all("stars" not in str(callback or "").lower() for callback in callbacks)
    assert any(text.startswith("💵 USD · $12") for text in texts)


@pytest.mark.asyncio
async def test_main_package_click_opens_method_choice_without_creating_tbank_invoice(monkeypatch) -> None:
    plan = SimpleNamespace(
        key="credits_100_999",
        label="Профи",
        credits=100.0,
        price_rub=1000.0,
        is_active=True,
    )
    message = SimpleNamespace(edit_text=AsyncMock())
    call = SimpleNamespace(data="topup:plan:credits_100_999", message=message, answer=AsyncMock())
    monkeypatch.setattr(payment.repo, "get_price_plan_by_key", AsyncMock(return_value=plan))
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TRIBUTE_API_KEY", "tribute", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.CRYPTOBOT_TOKEN", "crypto", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.LAVA_API_KEY", "", raising=False)
    create_payment = AsyncMock()
    monkeypatch.setattr(payment.tbank, "create_payment", create_payment)

    await payment.cb_topup_plan_methods(call, AsyncMock(), SimpleNamespace(id=7, language="ru"))

    create_payment.assert_not_awaited()
    message.edit_text.assert_awaited_once()
    markup = message.edit_text.await_args.kwargs["reply_markup"]
    callbacks = _callbacks(markup)
    assert "topup:rub:credits_100_999" in callbacks
    assert "topup:tribute_plan:credits_100_999" in callbacks
    call.answer.assert_awaited_once()
