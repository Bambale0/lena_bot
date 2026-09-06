from __future__ import annotations

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from bot.handlers import payment
from db.models import PaymentProvider, TransactionStatus
from payments import tribute


def test_tribute_signature_accepts_hmac_hex_and_rejects_wrong_secret() -> None:
    body = b'{"name":"shop_order"}'
    signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()

    assert tribute.verify_webhook_signature("secret", body, signature) is True
    assert tribute.verify_webhook_signature("wrong", body, signature) is False


@pytest.mark.asyncio
async def test_tribute_create_order_uses_shop_api_and_kopecks(monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    async def fake_request(method: str, path: str, *, json_payload: dict | None = None) -> dict:
        calls.append((method, path, json_payload or {}))
        if path == "/shop":
            return {"id": 1, "status": 1, "onlyStars": False, "callbackUrl": "https://apixbotai.com/webhook/tribute"}
        return {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "paymentUrl": "https://web.tribute.tg/shop/pay/order",
            "webappPaymentUrl": "https://t.me/tribute/app?startapp=order",
        }

    monkeypatch.setattr(tribute, "_request", fake_request)
    monkeypatch.setattr(tribute.settings, "WEB_PUBLIC_URL", "https://apixbotai.com")
    monkeypatch.setattr(tribute.settings, "TRIBUTE_SUCCESS_URL", "")
    monkeypatch.setattr(tribute.settings, "TRIBUTE_FAIL_URL", "")
    plan = SimpleNamespace(key="credits_100", label="100 💋", price_rub=199.5, credits=100.0)

    order = await tribute.create_order(plan, user_id=7, amount_rub=149.25)

    assert order.order_uuid == "550e8400-e29b-41d4-a716-446655440000"
    assert order.payment_url == "https://web.tribute.tg/shop/pay/order"
    assert not hasattr(order, "webapp_payment_url")
    assert calls == [
        ("GET", "/shop", {}),
        (
            "POST",
            "/shop/orders",
            {
                "amount": 14925,
                "currency": "rub",
                "title": "APIX · 100 💋",
                "description": "Пополнение баланса APIX: 100 💋",
                "successUrl": "https://apixbotai.com/app",
                "failUrl": "https://apixbotai.com/app",
                "customerId": "apix:7:credits_100",
                "period": "onetime",
            },
        )
    ]


def test_tribute_webhook_extractors_use_shop_order_payload() -> None:
    data = {
        "name": "shop_order",
        "payload": {
            "uuid": "order-1",
            "amount": 19900,
            "currency": "rub",
            "status": "paid",
        },
    }
    assert tribute.webhook_order_uuid(data) == "order-1"
    assert tribute.webhook_amount_rub(data) == 199.0
    assert tribute.webhook_currency(data) == "rub"
    assert tribute.webhook_status(data) == "paid"

@pytest.mark.asyncio
async def test_tribute_manual_reconcile_credits_atomically(monkeypatch) -> None:
    tx = SimpleNamespace(
        id=77,
        user_id=7,
        amount_rub=199.0,
        credits=100.0,
        provider=PaymentProvider.tribute,
        external_id="tribute-order-77",
        status=TransactionStatus.pending,
    )
    paid_tx = SimpleNamespace(**{**tx.__dict__, "status": TransactionStatus.paid})
    atomic_confirm = AsyncMock(return_value=(paid_tx, 321.0))
    accrue = AsyncMock()

    monkeypatch.setattr(payment.tribute, "get_order_status", AsyncMock(return_value="paid"))
    monkeypatch.setattr(payment.repo, "confirm_transaction_and_add_credits", atomic_confirm)
    monkeypatch.setattr(payment.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, tg_id=123)))
    monkeypatch.setattr("main._accrue_referral_commissions", accrue)

    status, balance = await payment._reconcile_transaction_status(object(), tx)

    assert status == TransactionStatus.paid
    assert balance == 321.0
    atomic_confirm.assert_awaited_once_with(ANY, "tribute-order-77", note="Payment confirmed via tribute")
    accrue.assert_awaited_once_with(ANY, ANY, 199.0, None)

@pytest.mark.asyncio
async def test_tribute_rejects_stars_only_shop_before_creating_order(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    async def fake_request(method: str, path: str, *, json_payload: dict | None = None) -> dict:
        calls.append((method, path))
        return {"id": 1, "status": 1, "onlyStars": True}

    monkeypatch.setattr(tribute, "_request", fake_request)
    plan = SimpleNamespace(key="credits_100", label="100 💋", price_rub=199.0, credits=100.0)

    with pytest.raises(RuntimeError, match="Stars-only"):
        await tribute.create_order(plan, user_id=7)

    assert calls == [("GET", "/shop")]

@pytest.mark.asyncio
async def test_tribute_rejects_shop_with_wrong_webhook_url(monkeypatch) -> None:
    monkeypatch.setattr(
        tribute,
        "_request",
        AsyncMock(return_value={"id": 1, "status": 1, "onlyStars": False, "callbackUrl": "https://wrong.example/webhook"}),
    )
    monkeypatch.setattr(tribute.settings, "WEB_PUBLIC_URL", "https://apixbotai.com")
    monkeypatch.setattr(tribute.settings, "TRIBUTE_WEBHOOK_PATH", "/webhook/tribute")
    plan = SimpleNamespace(key="credits_100", label="100 💋", price_rub=199.0, credits=100.0)

    with pytest.raises(RuntimeError, match="webhook URL must be configured"):
        await tribute.create_order(plan, user_id=7)


def test_tribute_digital_product_catalog_matches_supplied_links() -> None:
    assert {
        key: (item.product_id, item.payment_url)
        for key, item in tribute.TRIBUTE_DIGITAL_PRODUCTS.items()
    } == {
        "credits_15": (152362, "https://web.tribute.tg/p/DDs"),
        "credits_25": (152363, "https://web.tribute.tg/p/DDt"),
        "credits_50": (152364, "https://web.tribute.tg/p/DDu"),
        "credits_100_999": (152365, "https://web.tribute.tg/p/DDv"),
        "credits_200": (152366, "https://web.tribute.tg/p/DDw"),
        "credits_500": (152367, "https://web.tribute.tg/p/DDx"),
    }
    assert tribute.digital_product_for_id(152365).plan_key == "credits_100_999"
    assert tribute.digital_purchase_external_id(78901) == "digital:78901"


def test_tribute_digital_webhook_extractors() -> None:
    data = {
        "name": "new_digital_product",
        "payload": {
            "product_id": 152362,
            "purchase_id": 78901,
            "telegram_user_id": 12321321,
            "telegram_username": "durov",
            "amount": 15000,
            "currency": "rub",
        },
    }
    assert tribute.webhook_product_id(data) == 152362
    assert tribute.webhook_purchase_id(data) == 78901
    assert tribute.webhook_telegram_user_id(data) == 12321321
    assert tribute.webhook_telegram_username(data) == "durov"
    assert tribute.webhook_amount_rub(data) == 150.0


@pytest.mark.asyncio
async def test_tribute_digital_product_checkout_verifies_live_product(monkeypatch) -> None:
    plan = SimpleNamespace(key="credits_15", label="мини", credits=15.0, price_rub=150.0)
    monkeypatch.setattr(
        tribute,
        "get_product",
        AsyncMock(return_value={
            "id": 152362,
            "type": "digital",
            "status": "approved",
            "currency": "rub",
            "amount": 15000,
            "starsAmountEnabled": False,
            "webLink": "https://web.tribute.tg/p/DDs",
        }),
    )

    product = await tribute.get_digital_product_checkout(plan)

    assert product.plan_key == "credits_15"
    assert product.product_id == 152362
    assert product.payment_url == "https://web.tribute.tg/p/DDs"


@pytest.mark.asyncio
async def test_tribute_digital_product_checkout_rejects_price_drift(monkeypatch) -> None:
    plan = SimpleNamespace(key="credits_15", label="мини", credits=15.0, price_rub=150.0)
    monkeypatch.setattr(
        tribute,
        "get_product",
        AsyncMock(return_value={
            "id": 152362,
            "type": "digital",
            "status": "approved",
            "currency": "rub",
            "amount": 14900,
            "webLink": "https://web.tribute.tg/p/DDs",
        }),
    )

    with pytest.raises(RuntimeError, match="price mismatch"):
        await tribute.get_digital_product_checkout(plan)


@pytest.mark.asyncio
async def test_tribute_digital_product_checkout_rejects_stars_enabled(monkeypatch) -> None:
    plan = SimpleNamespace(key="credits_15", label="мини", credits=15.0, price_rub=150.0)
    monkeypatch.setattr(
        tribute,
        "get_product",
        AsyncMock(return_value={
            "id": 152362,
            "type": "digital",
            "status": "approved",
            "currency": "rub",
            "amount": 15000,
            "starsAmountEnabled": True,
            "webLink": "https://web.tribute.tg/p/DDs",
        }),
    )

    with pytest.raises(RuntimeError, match="Stars payments disabled"):
        await tribute.get_digital_product_checkout(plan)
