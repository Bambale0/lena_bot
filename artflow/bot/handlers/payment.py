# bot/handlers/payment.py
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.payment import crypto_pay_kb, crypto_plans_kb, topup_kb
from bot.keyboards.main_menu import back_to_menu_kb
from core.config import settings
from db import repository as repo
from db.models import PaymentProvider, User
from payments import cryptobot, yookassa

logger = logging.getLogger(__name__)
router = Router(name="payment")

# Примерный курс RUB/USDT (в проде получать динамически)
RUB_TO_USDT = 90.0


@router.callback_query(F.data == "menu:topup")
async def cb_topup(call: CallbackQuery, session: AsyncSession) -> None:
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>Пополнение баланса</b>\n\nВыбери тариф:",
        reply_markup=topup_kb(plans),
    )
    await call.answer()


# ─── ЮKassa ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("topup:rub:"))
async def cb_topup_rub(
    call: CallbackQuery, session: AsyncSession, bot: Bot
) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    await yookassa.send_invoice(bot, call.from_user.id, plan, settings.YOOKASSA_PROVIDER_TOKEN)
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Всегда подтверждаем pre_checkout."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_payment(
    message: Message, session: AsyncSession, db_user: User
) -> None:
    payment = message.successful_payment  # type: ignore[union-attr]
    payload = payment.invoice_payload  # "yookassa:credits_100"
    plan_key = payload.split(":")[1]

    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        logger.error("Plan not found after payment: %s", plan_key)
        return

    await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.yookassa,
        external_id=payment.telegram_payment_charge_id,
    )
    new_balance = await repo.add_credits(session, db_user.id, plan.credits)

    await message.answer(
        f"✅ Оплата прошла успешно!\n\n"
        f"Зачислено: <b>+{plan.credits} кредитов</b>\n"
        f"Текущий баланс: <b>{new_balance} кредитов</b>",
        reply_markup=back_to_menu_kb(),
    )
    logger.info("Payment success: user=%s plan=%s credits=%s", db_user.tg_id, plan_key, plan.credits)


# ─── CryptoBot ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "topup:crypto")
async def cb_topup_crypto(call: CallbackQuery, session: AsyncSession) -> None:
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🪙 <b>Оплата криптовалютой (USDT)</b>\n\nВыбери тариф:",
        reply_markup=crypto_plans_kb(plans),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:crypto_plan:"))
async def cb_crypto_plan(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    amount_usd = plan.price_rub / RUB_TO_USDT

    try:
        invoice = await cryptobot.create_invoice(
            credits=plan.credits,
            amount_usd=amount_usd,
            plan_key=plan_key,
            user_id=db_user.id,
        )
    except Exception as e:
        logger.error("CryptoBot invoice error: %s", e)
        await call.answer("Ошибка создания инвойса. Попробуй позже.", show_alert=True)
        return

    # Сохраняем pending транзакцию
    await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.cryptobot,
        external_id=str(invoice.invoice_id),
    )

    await call.message.edit_text(  # type: ignore[union-attr]
        f"🪙 <b>Оплата криптой</b>\n\n"
        f"Тариф: {plan.label}\n"
        f"Сумма: <b>{amount_usd:.2f} USDT</b>\n\n"
        f"Нажми кнопку для оплаты в CryptoBot.\n"
        f"<i>После оплаты кредиты зачислятся автоматически.</i>",
        reply_markup=crypto_pay_kb(invoice.bot_invoice_url),
    )
    await call.answer()
