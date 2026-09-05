from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import settings


@dataclass(frozen=True, slots=True)
class TributeOrder:
    order_uuid: str
    payment_url: str


def _api_base_url() -> str:
    return settings.TRIBUTE_API_BASE_URL.rstrip("/")


def _headers() -> dict[str, str]:
    if not settings.TRIBUTE_API_KEY:
        raise RuntimeError("Tribute API key is not configured")
    return {
        "Api-Key": settings.TRIBUTE_API_KEY,
        "Accept": "application/json",
    }


async def _request(
    method: str,
    path: str,
    *,
    json_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{_api_base_url()}{path}"
    async with httpx.AsyncClient(timeout=settings.TRIBUTE_HTTP_TIMEOUT) as client:
        response = await client.request(method, url, headers=_headers(), json=json_payload)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Tribute response")
    return data


def _return_url(kind: str) -> str:
    explicit = settings.TRIBUTE_SUCCESS_URL if kind == "success" else settings.TRIBUTE_FAIL_URL
    if explicit:
        return explicit
    return f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app"


async def get_shop() -> dict[str, Any]:
    return await _request("GET", "/shop")


async def ensure_non_stars_shop() -> dict[str, Any]:
    shop = await get_shop()
    if shop.get("onlyStars") is True:
        raise RuntimeError("Tribute shop is configured for Stars-only payments")
    try:
        status = int(shop.get("status", 0))
    except (TypeError, ValueError):
        status = 0
    if status != 1:
        raise RuntimeError("Tribute shop is not active")

    expected_callback = f"{settings.WEB_PUBLIC_URL.rstrip('/')}{settings.TRIBUTE_WEBHOOK_PATH}".rstrip("/")
    actual_callback = str(shop.get("callbackUrl") or "").strip().rstrip("/")
    if not actual_callback or actual_callback != expected_callback:
        raise RuntimeError(f"Tribute webhook URL must be configured as {expected_callback}")
    return shop


def _order_title(label: str) -> str:
    return f"APIX · {label}"[:100]


def _order_description(credits: float) -> str:
    credits_text = int(credits) if float(credits).is_integer() else credits
    return f"Пополнение баланса APIX: {credits_text} 💋"[:300]


async def create_order(
    plan: Any,
    user_id: int,
    *,
    amount_rub: float | None = None,
) -> TributeOrder:
    amount = float(plan.price_rub if amount_rub is None else amount_rub)
    amount_minor = int(round(amount * 100))
    if amount_minor <= 0:
        raise ValueError("Tribute order amount must be positive")

    await ensure_non_stars_shop()

    payload: dict[str, Any] = {
        "amount": amount_minor,
        "currency": "rub",
        "title": _order_title(str(plan.label)),
        "description": _order_description(float(plan.credits)),
        "successUrl": _return_url("success"),
        "failUrl": _return_url("fail"),
        "customerId": f"apix:{user_id}:{plan.key}",
        "period": "onetime",
    }
    data = await _request("POST", "/shop/orders", json_payload=payload)
    order_uuid = str(data.get("uuid") or "").strip()
    payment_url = str(data.get("paymentUrl") or "").strip()
    if not order_uuid or not payment_url:
        raise RuntimeError("Tribute did not return order uuid/paymentUrl")
    return TributeOrder(order_uuid=order_uuid, payment_url=payment_url)


async def get_order_status(order_uuid: str) -> str:
    data = await _request("GET", f"/shop/orders/{order_uuid}/status")
    return str(data.get("status") or "").strip().lower()


def verify_webhook_signature(api_key: str, body: bytes, signature: str) -> bool:
    if not api_key or not signature:
        return False
    supplied = signature.strip()
    if supplied.lower().startswith("sha256="):
        supplied = supplied.split("=", 1)[1].strip()

    digest = hmac.new(api_key.encode("utf-8"), body, hashlib.sha256).digest()
    expected_hex = digest.hex()
    expected_b64 = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(supplied.lower(), expected_hex.lower()) or hmac.compare_digest(supplied, expected_b64)


def webhook_order_uuid(data: dict[str, Any]) -> str:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("uuid") or "").strip()


def webhook_amount_rub(data: dict[str, Any]) -> float | None:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    raw = payload.get("amount")
    if raw is None:
        return None
    try:
        return int(raw) / 100.0
    except (TypeError, ValueError):
        return None


def webhook_currency(data: dict[str, Any]) -> str:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("currency") or "").strip().lower()


def webhook_status(data: dict[str, Any]) -> str:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("status") or "").strip().lower()
