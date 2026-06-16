from __future__ import annotations

from types import SimpleNamespace

import pytest

from payments import lava


def test_lava_extractors_accept_current_webhook_shapes() -> None:
    payload = {
        "eventType": "payment.success",
        "data": {
            "invoiceId": "invoice-1",
            "status": "completed",
            "paymentUrl": "https://pay.lava.test/invoice-1",
        },
    }

    assert lava.extract_invoice_id(payload) == "invoice-1"
    assert lava.extract_payment_url(payload) == "https://pay.lava.test/invoice-1"
    assert lava.is_success_webhook(payload) is True


@pytest.mark.asyncio
async def test_lava_create_invoice_uses_v2_endpoint(monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    async def fake_request(method: str, path: str, *, json_payload: dict | None = None) -> dict:
        calls.append((method, path, json_payload or {}))
        return {"id": "invoice-1", "paymentUrl": "https://pay.lava.test/invoice-1"}

    monkeypatch.setenv("LAVA_OFFER_ID_CREDITS_100", "offer-1")
    monkeypatch.setattr(lava, "_request", fake_request)
    monkeypatch.setattr(lava, "_store_link", lambda *_args: None)

    plan = SimpleNamespace(key="credits_100", label="100 credits", price_rub=1000.0, credits=100.0)

    invoice = await lava.create_invoice(plan, user_id=7)

    assert invoice.invoice_id == "invoice-1"
    assert invoice.payment_url == "https://example.test/pay/lava/invoice-1"
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/api/v2/invoice"
    assert calls[0][2]["offerId"] == "offer-1"
    assert calls[0][2]["currency"] == "RUB"
    assert calls[0][2]["clientUtm"]["user_id"] == "7"
