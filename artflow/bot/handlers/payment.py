# bot/handlers/payment.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.payment import crypto_pay_kb, crypto_plans_kb, payment_link_kb, topup_kb
from bot.keyboards.main_menu import back_to_menu_kb
from core.config import settings
from db import repository as repo
from db.models import PaymentProvider, TransactionStatus, User
from payments import cryptobot, tbank

logger = logging.getLogger(__name__)
router = Router(name="payment")

# Approximate RUB/USDT rate (in prod get dynamically)
RUB_TO_USDT = 90.0

TBANK_FINAL_FAILURE_STATUSES = {
    "CANCELED",
    "CANCELLED",
    "REJECTED",
    "DEADLINE_EXPIRED",
    "AUTH_FAIL",
}


def _fmt_amount(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


@router.callback_query(F.data == "menu:topup")
async def cb_topup(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        t("topup_title", lang),
        reply_markup=topup_kb(plans, lang=lang),
    )
    await call.answer()


# ─── T-Bank / rubles ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("topup:rub:"))
async def cb_topup_rub(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    lang = db_user.language or "ru"
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    if not settings.TBANK_TERMINAL_KEY or not settings.TBANK_PASSWORD:
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    try:
        payment = await tbank.create_payment(plan, db_user.id)
    except Exception as e:
        logger.error("T-Bank payment error: %s", e)
        await call.answer(t("error_generic", lang), show_alert=True)
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
        t("topup_tbank_desc", lang, label=plan.label, amount=_fmt_amount(plan.price_rub)),
        reply_markup=payment_link_kb(
            "💳 " + ("Перейти к оплате" if lang == "ru" else "Pay now"),
            payment.payment_url,
        ),
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
        return False, "Can only cancel last T-Bank payment."

    if tx.status == TransactionStatus.refunded:
        return False, "Payment already refunded."
    if tx.status == TransactionStatus.failed:
        return False, "Payment already failed."

    state = await tbank.get_payment_state(payment_id)
    provider_status = str(state.get("Status", "")).upper()

    if provider_status in TBANK_FINAL_FAILURE_STATUSES:
        await repo.set_transaction_status(session, payment_id, TransactionStatus.failed)
        return True, "Payment was already cancelled by T-Bank."

    if provider_status in {"REFUNDED", "REVERSED", "PARTIAL_REVERSED"}:
        await repo.set_transaction_status(session, payment_id, TransactionStatus.refunded)
        return True, "Payment was already refunded."

    await tbank.cancel_payment(payment_id)

    new_status = TransactionStatus.refunded if tx.status == TransactionStatus.paid else TransactionStatus.failed
    await repo.set_transaction_status(session, payment_id, new_status)

    if new_status == TransactionStatus.refunded:
        return True, "Payment cancelled and marked as refunded."
    return True, "Payment cancelled."


@router.callback_query(F.data == "topup:tbank:cancel_last")
async def cb_tbank_cancel_last(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    lang = db_user.language or "ru"
    tx = await repo.get_last_cancellable_tbank_transaction(session, db_user.id)
    if not tx or not tx.external_id:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    try:
        ok, text = await _cancel_tbank_transaction(
            session=session,
            db_user=db_user,
            payment_id=tx.external_id,
        )
    except Exception as e:
        logger.error("T-Bank cancel-last error: %s", e)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    await call.answer(text, show_alert=True)


@router.callback_query(F.data.startswith("topup:tbank:cancel:"))
async def cb_tbank_cancel_payment(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    lang = db_user.language or "ru"
    payment_id = call.data.split(":")[-1]  # type: ignore[union-attr]
    if not payment_id:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    try:
        ok, text = await _cancel_tbank_transaction(
            session=session,
            db_user=db_user,
            payment_id=payment_id,
        )
    except Exception as e:
        logger.error("T-Bank cancel error: %s", e)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    if ok:
        await call.message.edit_text(  # type: ignore[union-attr]
            "↩️ <b>" + ("Платёж отменён" if lang == "ru" else "Payment cancelled") + "</b>\n\n"
            + ("Можно создать новый платёж из меню пополнения." if lang == "ru" else "You can create a new payment from the top-up menu."),
            reply_markup=back_to_menu_kb(),
        )
    await call.answer(text, show_alert=True)


# ─── CryptoBot ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "topup:crypto")
async def cb_topup_crypto(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        t("topup_crypto_title", lang) + "\n\n" + t("topup_select_plan", lang),
        reply_markup=crypto_plans_kb(plans, lang=lang),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:crypto_plan:"))
async def cb_crypto_plan(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    lang = db_user.language or "ru"
    plan_key = call.data.split(":")[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer(t("error_not_found", lang), show_alert=True)
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
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.cryptobot,
        external_id=str(invoice.invoice_id),
    )

    await call.message.edit_text(  # type: ignore[union-attr]
        t("topup_crypto_desc", lang, label=plan.label, amount=_fmt_amount(amount_usd)),
        reply_markup=crypto_pay_kb(invoice.bot_invoice_url, lang=lang),
    )
    await call.answer()
