# payments/cryptobot.py
"""
CryptoBot (pay.crypt.bot) интеграция.
Создаём инвойс → отдаём пользователю ссылку → получаем webhook → зачисляем.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_CRYPTOBOT_HEADERS = {
    "Crypto-Pay-API-Token": settings.CRYPTOBOT_TOKEN,
    "Content-Type": "application/json",
}


@dataclass
class CryptoBotInvoice:
    invoice_id: int
    pay_url: str
    bot_invoice_url: str


async def create_invoice(
    credits: int,
    amount_usd: float,
    plan_key: str,
    user_id: int,
) -> CryptoBotInvoice:
    """
    Создаёт инвойс в CryptoBot.
    amount_usd — примерная конвертация рублей в USDT (храните курс в конфиге или получайте динамически).
    """
    payload = {
        "asset": "USDT",
        "amount": f"{amount_usd:.2f}",
        "description": f"ArtFlow AI — {credits} кредитов",
        "payload": f"{plan_key}:{user_id}",
        "paid_btn_name": "callback",
        "paid_btn_url": f"https://t.me/{settings.BOT_TOKEN.split(':')[0]}",  # будет перекрыто webhook
        "allow_comments": False,
        "allow_anonymous": False,
    }
    async with httpx.AsyncClient(base_url=settings.CRYPTOBOT_BASE_URL, headers=_CRYPTOBOT_HEADERS) as client:
        resp = await client.post("/createInvoice", json=payload)
        resp.raise_for_status()
        data = resp.json()["result"]

    logger.info("CryptoBot invoice created: %s for user %s", data["invoice_id"], user_id)
    return CryptoBotInvoice(
        invoice_id=data["invoice_id"],
        pay_url=data["pay_url"],
        bot_invoice_url=data.get("bot_invoice_url", data["pay_url"]),
    )


async def get_invoice(invoice_id: int) -> dict:
    async with httpx.AsyncClient(base_url=settings.CRYPTOBOT_BASE_URL, headers=_CRYPTOBOT_HEADERS) as client:
        resp = await client.get(f"/getInvoices?invoice_ids={invoice_id}")
        resp.raise_for_status()
        items = resp.json()["result"]["items"]
        return items[0] if items else {}


def verify_webhook_signature(token: str, body: bytes, check_hash: str) -> bool:
    """Проверяем HMAC подпись CryptoBot webhook."""
    import hashlib
    import hmac
    secret = hashlib.sha256(token.encode()).digest()
    computed = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, check_hash)
