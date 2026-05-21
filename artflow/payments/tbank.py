from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from core.config import settings
from db.models import PricePlan

logger = logging.getLogger(__name__)


class TBankError(RuntimeError):
    pass


@dataclass(slots=True)
class TBankPayment:
    order_id: str
    payment_id: str
    payment_url: str
    status: str


def _stringify_token_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def make_token(data: dict[str, Any], password: str) -> str:
    token_fields = {
        key: _stringify_token_value(value)
        for key, value in data.items()
        if key != "Token" and value is not None and not isinstance(value, (dict, list, tuple))
    }
    token_fields["Password"] = password
    raw = "".join(token_fields[key] for key in sorted(token_fields))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_notification_token(payload: dict[str, Any], password: str) -> bool:
    received_token = str(payload.get("Token", ""))
    if not received_token:
        return False
    expected_token = make_token(payload, password)
    return hmac.compare_digest(expected_token, received_token)


async def _request(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = settings.TBANK_BASE_URL.rstrip("/") + "/"
    async with httpx.AsyncClient(base_url=base_url, timeout=20.0) as client:
        response = await client.post(method.lstrip("/"), json=payload)
        response.raise_for_status()
        data = response.json()

    if not data.get("Success"):
        error_code = str(data.get("ErrorCode", "")).strip()
        message = str(data.get("Message", "")).strip()
        details = str(data.get("Details", "")).strip()
        parts = [part for part in (message, details) if part]
        text = " | ".join(parts) if parts else "T-Bank API error"
        if error_code:
            text = f"[{error_code}] {text}"
        raise TBankError(text)

    return data


async def create_payment(plan: PricePlan, user_id: int) -> TBankPayment:
    order_id = uuid4().hex
    amount_kopecks = int(plan.price_rub * 100)
    notification_url = f"{settings.WEBHOOK_URL.rstrip('/')}/webhook/tbank"

    payload: dict[str, Any] = {
        "TerminalKey": settings.TBANK_TERMINAL_KEY,
        "Amount": amount_kopecks,
        "OrderId": order_id,
        "Description": f"APIX - {plan.label}",
        "PayType": "O",
        "Language": "ru",
        "NotificationURL": notification_url,
        "DATA": {
            "user_id": str(user_id),
            "plan_key": plan.key,
        },
    }
    if settings.TBANK_SUCCESS_URL:
        payload["SuccessURL"] = settings.TBANK_SUCCESS_URL
    if settings.TBANK_FAIL_URL:
        payload["FailURL"] = settings.TBANK_FAIL_URL

    payload["Token"] = make_token(payload, settings.TBANK_PASSWORD)
    data = await _request("Init", payload)

    payment_url = data.get("PaymentURL")
    payment_id = str(data.get("PaymentId", ""))
    if not payment_url or not payment_id:
        raise TBankError("T-Bank Init response does not contain PaymentURL or PaymentId")

    logger.info("T-Bank payment created: payment_id=%s user_id=%s order_id=%s", payment_id, user_id, order_id)
    return TBankPayment(
        order_id=order_id,
        payment_id=payment_id,
        payment_url=payment_url,
        status=str(data.get("Status", "")),
    )


async def get_payment_state(payment_id: str) -> dict[str, Any]:
    payload = {
        "TerminalKey": settings.TBANK_TERMINAL_KEY,
        "PaymentId": payment_id,
    }
    payload["Token"] = make_token(payload, settings.TBANK_PASSWORD)
    return await _request("GetState", payload)


async def cancel_payment(payment_id: str, amount_kopecks: int | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "TerminalKey": settings.TBANK_TERMINAL_KEY,
        "PaymentId": payment_id,
    }
    if amount_kopecks is not None:
        payload["Amount"] = amount_kopecks
    payload["Token"] = make_token(payload, settings.TBANK_PASSWORD)
    data = await _request("Cancel", payload)
    logger.info("T-Bank payment cancelled: payment_id=%s status=%s", payment_id, data.get("Status"))
    return data
