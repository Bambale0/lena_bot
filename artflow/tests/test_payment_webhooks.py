from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

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
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=SimpleNamespace(**{
        **tx.__dict__,
        "status": TransactionStatus.pending,
    })))
    monkeypatch.setattr(
        main,
        "lava_get_invoice",
        AsyncMock(return_value={"id": "invoice-1", "status": "completed", "amount": 500.0, "currency": "RUB"}),
    )
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


@pytest.mark.asyncio
async def test_lava_webhook_does_not_confirm_without_server_side_paid_invoice(monkeypatch) -> None:
    tx = SimpleNamespace(
        id=12,
        user_id=7,
        amount_rub=500.0,
        credits=50.0,
        provider=PaymentProvider.lava,
        status=TransactionStatus.pending,
    )
    confirm_and_add = AsyncMock()

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=tx))
    monkeypatch.setattr(main, "lava_get_invoice", AsyncMock(return_value={"id": "invoice-1", "status": "pending"}))
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", confirm_and_add)

    payload = {
        "eventType": "payment.success",
        "data": {"invoiceId": "invoice-1", "status": "completed"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/lava", json=payload)

    assert response.status_code == 200
    assert response.text == "OK"
    confirm_and_add.assert_not_awaited()

def _tribute_signed_body(payload: dict, secret: str = "tribute-secret") -> tuple[bytes, str]:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, signature


@pytest.mark.asyncio
async def test_tribute_webhook_confirms_paid_order_atomically(monkeypatch) -> None:
    pending_tx = SimpleNamespace(
        id=21,
        user_id=7,
        amount_rub=199.0,
        credits=100.0,
        provider=PaymentProvider.tribute,
        status=TransactionStatus.pending,
    )
    paid_tx = SimpleNamespace(**{**pending_tx.__dict__, "status": TransactionStatus.paid})
    confirm_and_add = AsyncMock(return_value=(paid_tx, 250.0))
    accrue = AsyncMock()

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(main, "bot", None)
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=pending_tx))
    monkeypatch.setattr(main, "tribute_get_order_status", AsyncMock(return_value="paid"))
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", confirm_and_add)
    monkeypatch.setattr(main.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, tg_id=123)))
    monkeypatch.setattr(main, "_accrue_referral_commissions", accrue)

    payload = {
        "name": "shop_order",
        "payload": {
            "uuid": "tribute-order-1",
            "amount": 19900,
            "currency": "rub",
            "status": "paid",
        },
    }
    body, signature = _tribute_signed_body(payload)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute",
            content=body,
            headers={"content-type": "application/json", "trbt-signature": signature},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    confirm_and_add.assert_awaited_once_with(
        ANY,
        "tribute-order-1",
        note="Payment confirmed via tribute",
    )
    accrue.assert_awaited_once()


@pytest.mark.asyncio
async def test_tribute_webhook_rejects_invalid_signature(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    payload = {"name": "shop_order", "payload": {"uuid": "tribute-order-1"}}
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute",
            content=body,
            headers={"content-type": "application/json", "trbt-signature": "wrong"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_tribute_webhook_does_not_credit_amount_mismatch(monkeypatch) -> None:
    pending_tx = SimpleNamespace(
        id=21,
        user_id=7,
        amount_rub=199.0,
        credits=100.0,
        provider=PaymentProvider.tribute,
        status=TransactionStatus.pending,
    )
    confirm_and_add = AsyncMock()

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=pending_tx))
    monkeypatch.setattr(main, "tribute_get_order_status", AsyncMock(return_value="paid"))
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", confirm_and_add)

    payload = {
        "name": "shop_order",
        "payload": {
            "uuid": "tribute-order-1",
            "amount": 9900,
            "currency": "rub",
            "status": "paid",
        },
    }
    body, signature = _tribute_signed_body(payload)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute",
            content=body,
            headers={"content-type": "application/json", "trbt-signature": signature},
        )

    assert response.status_code == 200
    confirm_and_add.assert_not_awaited()


@pytest.mark.asyncio
async def test_tribute_refund_reverses_paid_credits_once(monkeypatch) -> None:
    paid_tx = SimpleNamespace(
        id=21,
        user_id=7,
        amount_rub=199.0,
        credits=100.0,
        provider=PaymentProvider.tribute,
        status=TransactionStatus.paid,
    )
    refunded_tx = SimpleNamespace(**{**paid_tx.__dict__, "status": TransactionStatus.refunded})
    add_credits = AsyncMock()
    reverse_referrals = AsyncMock()

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=paid_tx))
    monkeypatch.setattr(main.repo, "set_transaction_status", AsyncMock(return_value=refunded_tx))
    monkeypatch.setattr(main.repo, "add_credits", add_credits)
    monkeypatch.setattr(main.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, tg_id=123)))
    monkeypatch.setattr(main, "_reverse_referral_commissions", reverse_referrals)

    payload = {
        "name": "shop_order_refunded",
        "payload": {"uuid": "tribute-order-1", "amount": 19900, "currency": "rub", "status": "refunded"},
    }
    body, signature = _tribute_signed_body(payload)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute",
            content=body,
            headers={"content-type": "application/json", "trbt-signature": signature},
        )

    assert response.status_code == 200
    add_credits.assert_awaited_once()
    assert add_credits.await_args.args[1:3] == (7, -100.0)
    reverse_referrals.assert_awaited_once_with(ANY, ANY, 199.0)
