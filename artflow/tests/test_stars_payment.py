from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import stars_payment


def test_stars_are_not_advertised_even_with_legacy_flag_enabled(monkeypatch) -> None:
    from api.web import billing
    from bot.keyboards.payment import rub_methods_kb

    monkeypatch.setattr(billing.settings, "TELEGRAM_STARS_ENABLED", True, raising=False)
    monkeypatch.setattr(billing.settings, "TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr(billing.settings, "TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr(billing.settings, "CRYPTOBOT_TOKEN", "crypto", raising=False)
    monkeypatch.setattr("bot.keyboards.payment.settings.TELEGRAM_STARS_ENABLED", True, raising=False)

    method_keys = [item["key"] for item in billing.enabled_payment_methods()]
    keyboard_callbacks = [
        button.callback_data
        for row in rub_methods_kb().inline_keyboard
        for button in row
    ]

    assert "stars" not in method_keys
    assert "topup:stars" not in keyboard_callbacks


@pytest.mark.asyncio
async def test_stars_plan_is_blocked_after_checkout_retirement(monkeypatch) -> None:
    create_transaction = AsyncMock()
    monkeypatch.setattr("bot.handlers.stars_payment.repo.create_transaction", create_transaction)

    call = SimpleNamespace(
        data="topup:stars_plan:credits_100",
        from_user=SimpleNamespace(id=12345),
        answer=AsyncMock(),
    )

    await stars_payment.cb_stars_plan(
        call, AsyncMock(), SimpleNamespace(id=7, language="ru"), AsyncMock()
    )

    create_transaction.assert_not_awaited()
    call.answer.assert_awaited_once()
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_stars_root_callback_is_blocked_after_checkout_retirement(monkeypatch) -> None:
    get_plans = AsyncMock()
    monkeypatch.setattr("bot.handlers.stars_payment.repo.get_active_price_plans", get_plans)
    call = SimpleNamespace(data="topup:stars", answer=AsyncMock())

    await stars_payment.cb_topup_stars(
        call, AsyncMock(), SimpleNamespace(id=7, language="ru")
    )

    get_plans.assert_not_awaited()
    call.answer.assert_awaited_once()
    assert call.answer.await_args.kwargs["show_alert"] is True


@pytest.mark.asyncio
async def test_successful_legacy_stars_payment_is_still_idempotent(monkeypatch) -> None:
    payment = SimpleNamespace(
        currency="XTR",
        invoice_payload="stars:55:credits_100",
        telegram_payment_charge_id="tg_charge_1",
    )
    message = SimpleNamespace(successful_payment=payment, answer=AsyncMock())
    session = AsyncMock()
    db_user = SimpleNamespace(id=7, language="ru")
    bot = AsyncMock()
    tx = SimpleNamespace(id=55, amount_rub=999.0, credits=100)

    confirm_transaction_by_id = AsyncMock(side_effect=[tx, None])
    add_credits = AsyncMock(return_value=250)
    accrue = AsyncMock()

    monkeypatch.setattr("bot.handlers.stars_payment.repo.confirm_transaction_by_id", confirm_transaction_by_id)
    monkeypatch.setattr("bot.handlers.stars_payment.repo.add_credits", add_credits)
    monkeypatch.setattr("main._accrue_referral_commissions", accrue)

    await stars_payment.on_successful_payment(message, session, db_user, bot)
    await stars_payment.on_successful_payment(message, session, db_user, bot)

    assert confirm_transaction_by_id.await_count == 2
    add_credits.assert_awaited_once()
    assert add_credits.await_args.args == (session, db_user.id, tx.credits)
    assert add_credits.await_args.kwargs == {
        "entry_type": "payment_credit",
        "source_type": "transaction",
        "source_id": str(tx.id),
        "note": "Telegram Stars payment",
    }
    accrue.assert_awaited_once_with(session, db_user, tx.amount_rub, bot)
    message.answer.assert_awaited_once()
