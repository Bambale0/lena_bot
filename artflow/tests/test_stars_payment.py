from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import stars_payment
from db.models import PaymentProvider


@pytest.mark.asyncio
async def test_stars_plan_creates_xtr_invoice(monkeypatch) -> None:
    monkeypatch.setattr("bot.handlers.stars_payment.settings.TELEGRAM_STARS_ENABLED", True)

    call = SimpleNamespace(
        data="topup:stars_plan:credits_100",
        from_user=SimpleNamespace(id=12345),
        answer=AsyncMock(),
    )
    session = AsyncMock()
    db_user = SimpleNamespace(id=7, language="ru")
    bot = AsyncMock()
    plan = SimpleNamespace(key="credits_100", label="Профи", price_rub=999.0, price_stars=120, credits=100)
    tx = SimpleNamespace(id=55)

    monkeypatch.setattr("bot.handlers.stars_payment.repo.get_price_plan_by_key", AsyncMock(return_value=plan))
    create_transaction = AsyncMock(return_value=tx)
    monkeypatch.setattr("bot.handlers.stars_payment.repo.create_transaction", create_transaction)

    await stars_payment.cb_stars_plan(call, session, db_user, bot)

    create_transaction.assert_awaited_once()
    assert create_transaction.await_args.kwargs["provider"] == PaymentProvider.telegram_stars
    bot.send_invoice.assert_awaited_once()
    assert bot.send_invoice.await_args.kwargs["currency"] == "XTR"
    assert bot.send_invoice.await_args.kwargs["provider_token"] == ""
    assert bot.send_invoice.await_args.kwargs["payload"] == "stars:55:credits_100"
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_successful_stars_payment_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr("bot.handlers.stars_payment.settings.TELEGRAM_STARS_ENABLED", True)

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
    add_credits.assert_awaited_once_with(session, db_user.id, tx.credits)
    accrue.assert_awaited_once_with(session, db_user, tx.amount_rub, bot)
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_stars_plan_is_blocked_when_feature_disabled(monkeypatch) -> None:
    monkeypatch.setattr("bot.handlers.stars_payment.settings.TELEGRAM_STARS_ENABLED", False)
    create_transaction = AsyncMock()
    monkeypatch.setattr("bot.handlers.stars_payment.repo.create_transaction", create_transaction)

    call = SimpleNamespace(
        data="topup:stars_plan:credits_100",
        from_user=SimpleNamespace(id=12345),
        answer=AsyncMock(),
    )

    await stars_payment.cb_stars_plan(call, AsyncMock(), SimpleNamespace(id=7, language="ru"), AsyncMock())

    create_transaction.assert_not_awaited()
    call.answer.assert_awaited_once()
    assert call.answer.await_args.kwargs["show_alert"] is True
