from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from tribute_fixtures import catalog_offer

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
    await _assert_atomic_refund(monkeypatch, "tbank", "pay-1", 50000, "rub")


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
    await _assert_atomic_refund(monkeypatch, "shop", "tribute-order-1", 19900, "rub")


@pytest.mark.asyncio
async def test_tribute_digital_product_webhook_credits_mapped_purchase_atomically(monkeypatch) -> None:
    user = SimpleNamespace(id=7, tg_id=12321321, username="buyer")
    plan = SimpleNamespace(key="credits_15", label="мини", credits=15.0, price_rub=150.0, is_active=True)
    pending_tx = SimpleNamespace(
        id=91, user_id=7, amount_rub=150.0, credits=15.0,
        provider=PaymentProvider.tribute, external_id="digital:78901", status=TransactionStatus.pending,
    )
    paid_tx = SimpleNamespace(**{**pending_tx.__dict__, "status": TransactionStatus.paid})
    create_transaction = AsyncMock(return_value=pending_tx)
    confirm_and_add = AsyncMock(return_value=(paid_tx, 118.0))
    accrue = AsyncMock()

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(main, "bot", None)
    monkeypatch.setattr(main.repo, "get_price_plan_by_key", AsyncMock(return_value=plan))
    monkeypatch.setattr(main.repo, "get_user_by_tg_id", AsyncMock(return_value=user))
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=None))
    monkeypatch.setattr(main.repo, "create_transaction", create_transaction)
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", confirm_and_add)
    monkeypatch.setattr(main, "_accrue_referral_commissions", accrue)

    payload = {
        "name": "new_digital_product",
        "payload": {
            "product_id": 152362,
            "product_name": "Mini",
            "amount": 200,
            "currency": "usd",
            "telegram_user_id": 12321321,
            "telegram_username": "buyer",
            "purchase_id": 78901,
            "transaction_id": 234567,
        },
    }
    body, signature = _tribute_signed_body(payload)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute", content=body,
            headers={"content-type": "application/json", "trbt-signature": signature},
        )

    assert response.status_code == 200
    create_transaction.assert_awaited_once_with(
        ANY, user_id=7, amount_rub=150.0, credits=15.0,
        provider=PaymentProvider.tribute, external_id="digital:78901",
        provider_amount_minor=200, provider_currency="usd",
    )
    confirm_and_add.assert_awaited_once_with(
        ANY, "digital:78901", note="Payment confirmed via tribute digital product",
    )
    accrue.assert_awaited_once_with(ANY, user, paid_tx, None)


@pytest.mark.asyncio
async def test_tribute_digital_product_webhook_creates_missing_apix_user(monkeypatch) -> None:
    created_user = SimpleNamespace(id=8, tg_id=12321321, username="buyer")
    plan = SimpleNamespace(key="credits_15", label="мини", credits=15.0, price_rub=150.0, is_active=True)
    pending_tx = SimpleNamespace(
        id=92, user_id=8, amount_rub=150.0, credits=15.0,
        provider=PaymentProvider.tribute, external_id="digital:78902", status=TransactionStatus.pending,
    )
    create_user = AsyncMock(return_value=created_user)

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(main.settings, "WELCOME_BONUS_CREDITS", 3)
    monkeypatch.setattr(main, "bot", None)
    monkeypatch.setattr(main.repo, "get_price_plan_by_key", AsyncMock(return_value=plan))
    monkeypatch.setattr(main.repo, "get_user_by_tg_id", AsyncMock(return_value=None))
    monkeypatch.setattr(main.repo, "create_user", create_user)
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=None))
    monkeypatch.setattr(main.repo, "create_transaction", AsyncMock(return_value=pending_tx))
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", AsyncMock(return_value=(pending_tx, 18.0)))
    monkeypatch.setattr(main, "_accrue_referral_commissions", AsyncMock())

    payload = {
        "name": "new_digital_product",
        "payload": {
            "product_id": 152362, "amount": 200, "currency": "usd",
            "telegram_user_id": 12321321, "telegram_username": "buyer", "purchase_id": 78902,
        },
    }
    body, signature = _tribute_signed_body(payload)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute", content=body,
            headers={"content-type": "application/json", "trbt-signature": signature},
        )

    assert response.status_code == 200
    create_user.assert_awaited_once_with(
        ANY, tg_id=12321321, username="buyer", full_name=None, welcome_credits=3,
    )


@pytest.mark.asyncio
async def test_tribute_digital_product_duplicate_paid_purchase_is_idempotent(monkeypatch) -> None:
    user = SimpleNamespace(id=7, tg_id=12321321)
    plan = SimpleNamespace(key="credits_15", credits=15.0, price_rub=150.0, is_active=True)
    paid_tx = SimpleNamespace(
        id=91, user_id=7, amount_rub=150.0, credits=15.0,
        provider=PaymentProvider.tribute, external_id="digital:78901", status=TransactionStatus.paid,
    )
    confirm_and_add = AsyncMock()
    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(main.repo, "get_price_plan_by_key", AsyncMock(return_value=plan))
    monkeypatch.setattr(main.repo, "get_user_by_tg_id", AsyncMock(return_value=user))
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=paid_tx))
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", confirm_and_add)

    payload = {
        "name": "new_digital_product",
        "payload": {
            "product_id": 152362, "amount": 200, "currency": "usd",
            "telegram_user_id": 12321321, "purchase_id": 78901,
        },
    }
    body, signature = _tribute_signed_body(payload)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute", content=body,
            headers={"content-type": "application/json", "trbt-signature": signature},
        )

    assert response.status_code == 200
    confirm_and_add.assert_not_awaited()


@pytest.mark.asyncio
async def test_tribute_digital_product_refund_reverses_purchase_once(monkeypatch) -> None:
    await _assert_atomic_refund(monkeypatch, "digital", "digital:78901", 200, "usd")


@pytest.mark.asyncio
async def test_tribute_digital_product_unknown_product_requests_retry(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(main.repo, "confirm_transaction_and_add_credits", AsyncMock())
    payload = {
        "name": "new_digital_product",
        "payload": {
            "product_id": 999999, "amount": 200, "currency": "usd",
            "telegram_user_id": 12321321, "purchase_id": 78901,
        },
    }
    body, signature = _tribute_signed_body(payload)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhook/tribute", content=body,
            headers={"content-type": "application/json", "trbt-signature": signature},
        )
    assert response.status_code == 503


@pytest.fixture(autouse=True)
def _synthetic_catalog_read(monkeypatch):
    async def lookup(_session, product_id):
        return catalog_offer() if product_id == 152362 else None
    monkeypatch.setattr(main, "tribute_digital_product_for_id", lookup)


async def _assert_atomic_refund(monkeypatch, kind, external_id, amount, currency):
    from db.payment_refunds import RefundResult
    from payments import refund_settlement
    provider = PaymentProvider.tbank if kind == "tbank" else PaymentProvider.tribute
    atomic = AsyncMock(return_value=RefundResult(21, TransactionStatus.refunded, True, 50))
    unsafe_add, unsafe_status = AsyncMock(), AsyncMock()
    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main, "verify_notification_token", lambda *_args: True)
    monkeypatch.setattr(main.settings, "TRIBUTE_API_KEY", "tribute-secret")
    monkeypatch.setattr(refund_settlement, "apply_payment_refund", atomic)
    monkeypatch.setattr(main.repo, "add_credits", unsafe_add)
    monkeypatch.setattr(main.repo, "set_transaction_status", unsafe_status)
    monkeypatch.setattr(main.repo, "get_transaction_by_external_id", AsyncMock(return_value=SimpleNamespace(id=21, user_id=7, credits=50, provider=provider, status=TransactionStatus.paid)))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if kind == "tbank":
            response = await client.post("/webhook/tbank", json={"Success": True, "Status": "REFUNDED", "PaymentId": external_id, "Amount": amount})
        else:
            body, signature = _tribute_signed_body({
                "name": "digital_product_refunded" if kind == "digital" else "shop_order_refunded",
                "payload": {"uuid": external_id, "purchase_id": 78901, "product_id": 152362, "amount": amount, "currency": currency, "status": "refunded"},
            })
            response = await client.post("/webhook/tribute", content=body, headers={"trbt-signature": signature, "content-type": "application/json"})
    assert response.status_code == 200
    if kind == "tbank":
        atomic.assert_awaited_once_with(ANY, external_id, provider, remaining_amount_minor=None, currency="rub")
    else:
        atomic.assert_awaited_once_with(ANY, external_id, provider, original_amount_minor=amount, currency=currency)
    unsafe_add.assert_not_awaited()
    unsafe_status.assert_not_awaited()
