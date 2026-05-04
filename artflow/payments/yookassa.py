# payments/yookassa.py
"""
ЮKassa через Telegram Payments API (провайдер токен).
Создаём Telegram invoice, обрабатываем pre_checkout и successful_payment.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import LabeledPrice

from db.models import PricePlan

logger = logging.getLogger(__name__)


async def send_invoice(
    bot: Bot,
    chat_id: int,
    plan: PricePlan,
    provider_token: str,
) -> None:
    """Отправляет Telegram invoice для выбранного тарифа."""
    amount_kopecks = int(plan.price_rub * 100)  # ЮKassa работает в копейках
    await bot.send_invoice(
        chat_id=chat_id,
        title=f"Пополнение баланса: {plan.label}",
        description=f"Вы получите {plan.credits} кредитов на аккаунт APIX",
        payload=f"yookassa:{plan.key}",
        provider_token=provider_token,
        currency="RUB",
        prices=[LabeledPrice(label=plan.label, amount=amount_kopecks)],
        protect_content=True,
    )
    logger.info("Invoice sent to %s for plan %s", chat_id, plan.key)
