from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from core.config import settings
from db.models import PricePlan

logger = logging.getLogger(__name__)
_LAVA_LINK_CACHE = Path("data/lava_invoice_links.json")


def _load_link_cache() -> dict[str, str]:
    try:
        return json.loads(_LAVA_LINK_CACHE.read_text())
    except Exception:
        return {}


def _store_link(invoice_id: str, payment_url: str) -> None:
    data = _load_link_cache()
    data[str(invoice_id)] = str(payment_url)
    _LAVA_LINK_CACHE.parent.mkdir(parents=True, exist_ok=True)
    _LAVA_LINK_CACHE.write_text(json.dumps(data, ensure_ascii=False))


def cached_payment_url(invoice_id: str) -> str:
    return str(_load_link_cache().get(str(invoice_id), ""))


class LavaError(RuntimeError):
    pass


@dataclass(slots=True)
class LavaInvoice:
    invoice_id: str
    payment_url: str
    status: str = "pending"


def _extract_first(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    for container_name in ("data", "result", "invoice", "payload"):
        container = payload.get(container_name)
        if isinstance(container, dict):
            for key in keys:
                value = container.get(key)
                if value:
                    return str(value)
    return ""


def extract_invoice_id(payload: dict[str, Any]) -> str:
    return _extract_first(payload, "id", "invoiceId", "invoice_id", "contractId", "contract_id")


def extract_payment_url(payload: dict[str, Any]) -> str:
    return _extract_first(payload, "paymentUrl", "payment_url", "paymentLink", "payment_link", "url", "link")


def webhook_contract_id(payload: dict[str, Any]) -> str:
    return extract_invoice_id(payload)


def public_invoice_url(invoice_id: str) -> str:
    base = (getattr(settings, "WEBHOOK_URL", "") or settings.LAVA_API_BASE_URL).rstrip("/")
    return f"{base}/pay/lava/{invoice_id}"


def is_success_webhook(payload: dict[str, Any]) -> bool:
    event = _extract_first(payload, "eventType", "event_type", "type", "event").strip().lower()
    status = _extract_first(payload, "status").strip().lower()
    return event in {"payment.success", "invoice.paid"} and (not status or status in {"completed", "success", "paid"})


async def _request(method: str, path: str, *, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if not settings.LAVA_API_KEY:
        raise LavaError("Lava API key is not configured")
    headers = {
        "X-Api-Key": settings.LAVA_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    base_url = settings.LAVA_API_BASE_URL.rstrip("/") + "/"
    async with httpx.AsyncClient(base_url=base_url, headers=headers, timeout=30.0) as client:
        response = await client.request(method.upper(), path.lstrip("/"), json=json_payload)
        raw_text = response.text
        try:
            data = response.json()
        except Exception:
            data = {"raw": raw_text}
        if response.status_code >= 400:
            raise LavaError(f"Lava API error {response.status_code}: {raw_text[:500]}")
    if not isinstance(data, dict):
        raise LavaError("Unexpected Lava response format")
    return data


async def create_invoice(plan: PricePlan, user_id: int, *, amount_rub: float | None = None, email: str | None = None) -> LavaInvoice:
    offer_id = settings.lava_offer_id_for_plan(plan.key)
    if not offer_id:
        raise LavaError(f"Lava offer id is not configured for plan {plan.key}")

    payload: dict[str, Any] = {
        "email": (email or settings.LAVA_DEFAULT_EMAIL or "buyer@example.com"),
        "offerId": offer_id,
        "currency": "RUB",
        "buyerLanguage": "RU",
        "clientUtm": {
            "source": "artflow",
            "user_id": str(user_id),
            "plan_key": plan.key,
        },
    }
    if amount_rub is not None:
        payload["amount"] = float(amount_rub)

    data = await _request("POST", "/api/v2/invoice", json_payload=payload)
    invoice_id = extract_invoice_id(data)
    payment_url = extract_payment_url(data)
    if not invoice_id or not payment_url:
        raise LavaError("Lava response does not contain invoice id or payment url")
    _store_link(invoice_id, payment_url)
    logger.info("Lava invoice created: invoice_id=%s user_id=%s plan=%s", invoice_id, user_id, plan.key)
    return LavaInvoice(invoice_id=invoice_id, payment_url=public_invoice_url(invoice_id), status=str(data.get("status", "pending")))


async def get_invoice(invoice_id: str) -> dict[str, Any]:
    return await _request("GET", f"/api/v2/invoices/{invoice_id}")
