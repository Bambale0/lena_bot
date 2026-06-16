from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import main
from db.models import PaymentProvider, TransactionStatus
from main import app


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_tbank_confirmed_uses_atomic_credit_confirmation(monkeypatch) -> None:
    tx = SimpleNamespace(
        id=11,
        user_id=7,
        amount_rub=500.0,
        credits=50.0,
        provider=PaymentProvider.tbank,
        status=TransactionStatus.paid,
    )
    confirm_and_add = AsyncMock(return_value=(tx, 150.0))
    add_credits = AsyncMock()

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main, "verify_notification_token", lambda _data, _password: True)
    monkeypatch.setattr(main, "bot", None)
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", confirm_and_add)
    monkeypatch.setattr(main.repo, "add_credits", add_credits)
    monkeypatch.setattr(main.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, tg_id=123)))
    monkeypatch.setattr(main, "_accrue_referral_commissions", AsyncMock())

    payload = {"Success": True, "Status": "CONFIRMED", "PaymentId": "pay-1", "OrderId": "order-1"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/tbank", json=payload)

    assert response.status_code == 200
    assert response.text == "OK"
    confirm_and_add.assert_awaited_once()
    add_credits.assert_not_awaited()


@pytest.mark.asyncio
async def test_tbank_refund_reverses_credits_when_previous_status_was_paid(monkeypatch) -> None:
    paid_tx = SimpleNamespace(
        id=11,
        user_id=7,
        amount_rub=500.0,
        credits=50.0,
        provider=PaymentProvider.tbank,
        status=TransactionStatus.paid,
    )
    refunded_tx = SimpleNamespace(
        id=11,
        user_id=7,
        amount_rub=500.0,
        credits=50.0,
        provider=PaymentProvider.tbank,
        status=TransactionStatus.refunded,
    )
    add_credits = AsyncMock()

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main, "verify_notification_token", lambda _data, _password: True)
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=paid_tx))
    monkeypatch.setattr(main.repo, "set_transaction_status", AsyncMock(return_value=refunded_tx))
    monkeypatch.setattr(main.repo, "add_credits", add_credits)
    monkeypatch.setattr(main.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, tg_id=123)))
    monkeypatch.setattr(main, "_reverse_referral_commissions", AsyncMock())

    payload = {"Success": True, "Status": "REFUNDED", "PaymentId": "pay-1", "OrderId": "order-1"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/tbank", json=payload)

    assert response.status_code == 200
    assert response.text == "OK"
    add_credits.assert_awaited_once()
    assert add_credits.await_args.args[1:3] == (7, -50.0)


@pytest.mark.asyncio
async def test_lava_webhook_confirms_nested_invoice_id(monkeypatch) -> None:
    tx = SimpleNamespace(
        id=12,
        user_id=7,
        amount_rub=500.0,
        credits=50.0,
        provider=PaymentProvider.lava,
        status=TransactionStatus.paid,
    )
    confirm_and_add = AsyncMock(return_value=(tx, 150.0))

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main, "bot", None)
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", confirm_and_add)
    monkeypatch.setattr(main.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, tg_id=123)))
    monkeypatch.setattr(main, "_accrue_referral_commissions", AsyncMock())

    payload = {
        "eventType": "payment.success",
        "data": {"invoiceId": "invoice-1", "status": "completed"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/lava", json=payload)

    assert response.status_code == 200
    assert response.text == "OK"
    confirm_and_add.assert_awaited_once()
    assert confirm_and_add.await_args.args[1] == "invoice-1"
