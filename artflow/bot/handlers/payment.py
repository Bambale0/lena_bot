# bot/handlers/payment.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.payment import crypto_pay_kb, crypto_plans_kb, payment_link_kb, topup_kb
from bot.keyboards.main_menu import back_to_menu_kb
from core.config import settings
from db import repository as repo
from db.models import PaymentProvider, TransactionStatus, User
from payments import cryptobot, tbank

logger = logging.getLogger(__name__)
router = Router(name="payment")

# Примерный курс RUB/USDT (в проде получать динамически)
RUB_TO_USDT = 90.0

TBANK_FINAL_FAILURE_STATUSES = {
    "CANCELED",
    "CANCELLED",
    "REJECTED",
    "DEADLINE_EXPIRED",
    "AUTH_FAIL",
}


@router.callback_query(F.data == "menu:topup")
async def cb_topup(call: CallbackQuery, session: AsyncSession) -> None:
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        "💳 <b>Пополнение баланса</b>\n\nВыбери тариф:",
        reply_markup=topup_kb(plans),
    )
    await call.answer()


# ─── T-Bank / рубли ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("topup:rub:"))
async def cb_topup_rub(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer("Тариф не найден", show_alert=True)
        return

    if not settings.TBANK_TERMINAL_KEY or not settings.TBANK_PASSWORD:
        await call.answer("T-Банк не настроен", show_alert=True)
        return

    try:
        payment = await tbank.create_payment(plan, db_user.id)
    except Exception as e:
        logger.error("T-Bank payment error: %s", e)
        await call.answer("Ошибка создания платежа. Попробуй позже.", show_alert=True)
        return

    await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.tbank,
        external_id=payment.payment_id,
    )

    await call.message.edit_text(  # type: ignore[union-attr]
        f"🏦 <b>Оплата через T-Банк</b>\n\n"
        f"Тариф: {plan.label}\n"
        f"Сумма: <b>{plan.price_rub:.0f} ₽</b>\n\n"
        f"Открой ссылку для оплаты картой или через СБП.\n"
        f"<i>После успешной оплаты кредиты зачислятся автоматически.</i>",
        reply_markup=payment_link_kb("💳 Перейти к оплате", payment.payment_url),
    )
    await call.answer()


async def _cancel_tbank_transaction(
    *,
    session: AsyncSession,
    db_user: User,
    payment_id: str,
) -> tuple[bool, str]:
    tx = await repo.get_last_tbank_transaction(session, db_user.id)
    if not tx or tx.external_id != payment_id:
        return False, "Можно отменить только последний T-Банк платёж."

    if tx.status == TransactionStatus.refunded:
        return False, "Этот платёж уже отменён."
    if tx.status == TransactionStatus.failed:
        return False, "Этот платёж уже завершён как неуспешный."

    state = await tbank.get_payment_state(payment_id)
    provider_status = str(state.get("Status", "")).upper()

    if provider_status in TBANK_FINAL_FAILURE_STATUSES:
        await repo.set_transaction_status(session, payment_id, TransactionStatus.failed)
        return True, "Платёж уже был отменён на стороне T-Банка."

    if provider_status in {"REFUNDED", "REVERSED", "PARTIAL_REVERSED"}:
        await repo.set_transaction_status(session, payment_id, TransactionStatus.refunded)
        return True, "Платёж уже был возвращён."

    await tbank.cancel_payment(payment_id)

    new_status = TransactionStatus.refunded if tx.status == TransactionStatus.paid else TransactionStatus.failed
    await repo.set_transaction_status(session, payment_id, new_status)

    if new_status == TransactionStatus.refunded:
        return True, "Последний платёж отменён и помечен как возврат."
    return True, "Последний платёж отменён."


@router.callback_query(F.data == "topup:tbank:cancel_last")
async def cb_tbank_cancel_last(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    tx = await repo.get_last_cancellable_tbank_transaction(session, db_user.id)
    if not tx or not tx.external_id:
        await call.answer("Нет последнего T-Банк платежа для отмены.", show_alert=True)
        return

    try:
        ok, text = await _cancel_tbank_transaction(
            session=session,
            db_user=db_user,
            payment_id=tx.external_id,
        )
    except Exception as e:
        logger.error("T-Bank cancel-last error: user_id=%s payment_id=%s error=%s", db_user.id, tx.external_id, e)
        await call.answer("Не удалось отменить платёж. Попробуй ещё раз.", show_alert=True)
        return

    await call.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("topup:tbank:cancel:"))
async def cb_tbank_cancel_payment(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    payment_id = call.data.split(":")[-1]  # type: ignore[union-attr]
    if not payment_id:
        await call.answer("Платёж не найден.", show_alert=True)
        return

    try:
        ok, text = await _cancel_tbank_transaction(
            session=session,
            db_user=db_user,
            payment_id=payment_id,
        )
    except Exception as e:
        logger.error("T-Bank cancel error: user_id=%s payment_id=%s error=%s", db_user.id, payment_id, e)
        await call.answer("Не удалось отменить платёж. Попробуй ещё раз.", show_alert=True)
        return

    if ok:
        await call.message.edit_text(  # type: ignore[union-attr]
            "↩️ <b>Платёж отменён</b>\n\n"
            "Если захочешь, можно создать новый платёж из меню пополнения.",
            reply_markup=back_to_menu_kb(),
        )
    await call.answer(text, show_alert=True)


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
