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


@dataclass(frozen=True, slots=True)
class TributeDigitalProduct:
    plan_key: str
    product_id: int
    payment_url: str


TRIBUTE_DIGITAL_PRODUCTS: dict[str, TributeDigitalProduct] = {
    "credits_15": TributeDigitalProduct("credits_15", 152362, "https://web.tribute.tg/p/DDs"),
    "credits_25": TributeDigitalProduct("credits_25", 152363, "https://web.tribute.tg/p/DDt"),
    "credits_50": TributeDigitalProduct("credits_50", 152364, "https://web.tribute.tg/p/DDu"),
    "credits_100_999": TributeDigitalProduct("credits_100_999", 152365, "https://web.tribute.tg/p/DDv"),
    "credits_200": TributeDigitalProduct("credits_200", 152366, "https://web.tribute.tg/p/DDw"),
    "credits_500": TributeDigitalProduct("credits_500", 152367, "https://web.tribute.tg/p/DDx"),
}
TRIBUTE_DIGITAL_PRODUCTS_BY_ID: dict[int, TributeDigitalProduct] = {
    item.product_id: item for item in TRIBUTE_DIGITAL_PRODUCTS.values()
}


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


def digital_product_for_plan(plan_key: str) -> TributeDigitalProduct | None:
    return TRIBUTE_DIGITAL_PRODUCTS.get(str(plan_key))


def digital_product_for_id(product_id: int | str) -> TributeDigitalProduct | None:
    try:
        parsed = int(product_id)
    except (TypeError, ValueError):
        return None
    return TRIBUTE_DIGITAL_PRODUCTS_BY_ID.get(parsed)


def digital_product_plan_keys() -> set[str]:
    return set(TRIBUTE_DIGITAL_PRODUCTS)


def digital_purchase_external_id(purchase_id: int | str) -> str:
    return f"digital:{int(purchase_id)}"


async def get_product(product_id: int) -> dict[str, Any]:
    return await _request("GET", f"/products/{int(product_id)}")


async def get_digital_product_checkout(plan: Any) -> TributeDigitalProduct:
    mapping = digital_product_for_plan(str(plan.key))
    if mapping is None:
        raise RuntimeError(f"No Tribute digital product mapped for plan {plan.key}")

    data = await get_product(mapping.product_id)
    try:
        product_id = int(data.get("id"))
        amount_minor = int(data.get("amount"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Tribute digital product returned invalid id/amount") from exc

    if product_id != mapping.product_id:
        raise RuntimeError("Tribute digital product id mismatch")
    if str(data.get("type") or "").strip().lower() != "digital":
        raise RuntimeError("Tribute product is not digital")
    if str(data.get("status") or "").strip().lower() != "approved":
        raise RuntimeError("Tribute digital product is not approved")
    if str(data.get("currency") or "").strip().lower() != "rub":
        raise RuntimeError("Tribute digital product currency must be RUB")
    if data.get("starsAmountEnabled") is True:
        raise RuntimeError("Tribute digital product must have Stars payments disabled")

    expected_amount_minor = int(round(float(plan.price_rub) * 100))
    if amount_minor != expected_amount_minor:
        raise RuntimeError(
            f"Tribute digital product price mismatch for {plan.key}: "
            f"expected {expected_amount_minor}, got {amount_minor}"
        )

    web_link = str(data.get("webLink") or "").strip()
    if web_link and web_link.rstrip("/") != mapping.payment_url.rstrip("/"):
        raise RuntimeError("Tribute digital product web link mismatch")
    return mapping


def webhook_product_id(data: dict[str, Any]) -> int | None:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("product_id"))
    except (TypeError, ValueError):
        return None


def webhook_purchase_id(data: dict[str, Any]) -> int | None:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("purchase_id"))
    except (TypeError, ValueError):
        return None


def webhook_telegram_user_id(data: dict[str, Any]) -> int | None:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("telegram_user_id"))
    except (TypeError, ValueError):
        return None


def webhook_telegram_username(data: dict[str, Any]) -> str | None:
    payload = data.get("payload")
    if not isinstance(payload, dict):
        return None
    value = str(payload.get("telegram_username") or "").strip().lstrip("@")
    return value or None


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
