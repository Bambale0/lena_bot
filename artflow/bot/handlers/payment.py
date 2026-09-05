# bot/handlers/payment.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from bot.keyboards.payment import (
    crypto_pay_kb,
    crypto_plans_kb,
    lava_plans_kb,
    payment_link_kb,
    rub_methods_kb,
    rub_plans_kb,
    topup_kb,
    tribute_plans_kb,
)
from bot.states import PromoFSM
from core.config import settings
from db import repository as repo
from db.models import PaymentProvider, PromoRewardType, TransactionStatus, User
from payments import cryptobot, lava, tbank, tribute

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


def _promo_discount_amount(price_rub: float, redemption) -> float:
    if not redemption:
        return 0.0
    value = float(getattr(redemption, "value", 0) or 0)
    if redemption.reward_type == PromoRewardType.discount_percent:
        discount = price_rub * max(0.0, min(value, 100.0)) / 100.0
    elif redemption.reward_type == PromoRewardType.discount_amount:
        discount = max(0.0, value)
    else:
        return 0.0
    return min(discount, max(0.0, price_rub - 1.0))


async def _active_discount_text(session: AsyncSession, user_id: int, price_rub: float) -> tuple[float, str, object | None]:
    redemption = await repo.get_active_discount_redemption(session, user_id)
    discount = _promo_discount_amount(price_rub, redemption)
    if not redemption or discount <= 0:
        return price_rub, "", None
    final_amount = max(1.0, price_rub - discount)
    text = (
        f"\n🎟 Промокод применён: -{_fmt_amount(discount)} ₽"
        f"\nК оплате: <b>{_fmt_amount(final_amount)} ₽</b>"
    )
    return final_amount, text, redemption


def _promo_success_text(result: repo.PromoRedeemResult) -> str:
    promo = result.promo
    if result.discount_reserved:
        if promo.reward_type == PromoRewardType.discount_percent:
            value = f"{_fmt_amount(promo.value)}%"
        else:
            value = f"{_fmt_amount(promo.value)} ₽"
        return (
            "✅ <b>Промокод активирован</b>\n\n"
            f"Скидка: <b>{value}</b>\n"
            "Она применится к следующей оплате T-Bank, CryptoBot или Tribute."
        )
    return (
        "✅ <b>Промокод активирован</b>\n\n"
        f"Начислено: <b>+{_fmt_amount(result.credits_added)} 💋</b>\n"
        f"Баланс: <b>{_fmt_amount(result.balance_after or 0)} 💋</b>"
    )


async def _confirm_paid_transaction(session: AsyncSession, tx) -> float | None:
    if not tx:
        return None
    new_balance = await repo.add_credits(
        session,
        tx.user_id,
        tx.credits,
        entry_type="payment_credit",
        source_type="transaction",
        source_id=str(tx.id),
        note=f"Payment confirmed via {tx.provider}",
    )
    user = await repo.get_user_by_id(session, tx.user_id)
    if user:
        from main import _accrue_referral_commissions
        await _accrue_referral_commissions(session, user, tx.amount_rub, None)
    return new_balance


async def _reconcile_transaction_status(
    session: AsyncSession,
    tx,
) -> tuple[TransactionStatus, float | None]:
    if tx.provider == PaymentProvider.tbank and tx.external_id:
        state = await tbank.get_payment_state(tx.external_id)
        status = str(state.get("Status", "")).upper()
        if status == "CONFIRMED":
            confirmed = await repo.confirm_transaction(session, tx.external_id)
            balance = await _confirm_paid_transaction(session, confirmed) if confirmed else None
            return TransactionStatus.paid, balance
        if status in TBANK_FINAL_FAILURE_STATUSES:
            await repo.set_transaction_status(session, tx.external_id, TransactionStatus.failed)
            return TransactionStatus.failed, None
        if status in {"REFUNDED", "REVERSED", "PARTIAL_REVERSED"}:
            await repo.set_transaction_status(session, tx.external_id, TransactionStatus.refunded)
            return TransactionStatus.refunded, None
        return TransactionStatus.pending, None

    if tx.provider == PaymentProvider.cryptobot and tx.external_id:
        invoice = await cryptobot.get_invoice(int(tx.external_id))
        status = str(invoice.get("status", "")).lower()
        if status == "paid":
            confirmed = await repo.confirm_transaction(session, tx.external_id)
            balance = await _confirm_paid_transaction(session, confirmed) if confirmed else None
            return TransactionStatus.paid, balance
        if status in {"expired", "invalid", "cancelled"}:
            await repo.set_transaction_status(session, tx.external_id, TransactionStatus.failed)
            return TransactionStatus.failed, None
        return TransactionStatus.pending, None

    if tx.provider == PaymentProvider.lava and tx.external_id:
        invoice = await lava.get_invoice(tx.external_id)
        status = str(invoice.get("status", "")).lower()
        event_type = str(invoice.get("eventType", "")).lower()
        if status in {"completed", "success", "paid"} or event_type == "payment.success":
            confirmed = await repo.confirm_transaction(session, tx.external_id)
            balance = await _confirm_paid_transaction(session, confirmed) if confirmed else None
            return TransactionStatus.paid, balance
        if status in {"failed", "cancelled", "canceled", "expired"}:
            await repo.set_transaction_status(session, tx.external_id, TransactionStatus.failed)
            return TransactionStatus.failed, None
        return TransactionStatus.pending, None

    if tx.provider == PaymentProvider.tribute and tx.external_id:
        status = await tribute.get_order_status(tx.external_id)
        if status == "paid":
            confirmed = await repo.confirm_transaction_and_add_credits(
                session,
                tx.external_id,
                note="Payment confirmed via tribute",
            )
            balance = None
            if confirmed:
                paid_tx, balance = confirmed
                user = await repo.get_user_by_id(session, paid_tx.user_id)
                if user:
                    from main import _accrue_referral_commissions

                    await _accrue_referral_commissions(session, user, paid_tx.amount_rub, None)
            return TransactionStatus.paid, balance
        if status == "failed":
            await repo.set_transaction_status(session, tx.external_id, TransactionStatus.failed)
            return TransactionStatus.failed, None
        return TransactionStatus.pending, None

    return tx.status, None


@router.callback_query(F.data == "menu:topup")
async def cb_topup(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        t("topup_title", lang),
        reply_markup=topup_kb(plans, lang=lang),
    )
    await call.answer()


@router.callback_query(F.data == "topup:rub")
async def cb_topup_rub_methods(call: CallbackQuery, db_user: User) -> None:
    lang = db_user.language or "ru"
    text = (
        "₽ <b>Оплата в рублях</b>\n\nВыбери способ оплаты."
        if lang == "ru"
        else "₽ <b>Pay in rubles</b>\n\nChoose a payment method."
    )
    await call.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=rub_methods_kb(lang=lang),
    )
    await call.answer()


@router.callback_query(F.data == "topup:tbank")
async def cb_topup_tbank_menu(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        t("topup_tbank_title", lang) + "\n\n" + t("topup_select_plan", lang),
        reply_markup=rub_plans_kb(plans, lang=lang),
    )
    await call.answer()


@router.callback_query(F.data == "topup:tribute")
async def cb_topup_tribute(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    if not settings.TRIBUTE_API_KEY:
        await call.answer("Tribute сейчас недоступен" if lang == "ru" else "Tribute is unavailable right now", show_alert=True)
        return
    plans = await repo.get_active_price_plans(session)
    text = (
        "🟣 <b>Оплата через Tribute</b>\n\nВыбери пакет. Оплата откроется на защищённой странице Tribute.\n\n" + t("topup_select_plan", lang)
        if lang == "ru"
        else "🟣 <b>Pay with Tribute</b>\n\nChoose a plan. Checkout opens on Tribute.\n\n" + t("topup_select_plan", lang)
    )
    await call.message.edit_text(text, reply_markup=tribute_plans_kb(plans, lang=lang))  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("topup:tribute_plan:"))
async def cb_topup_tribute_plan(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    if not settings.TRIBUTE_API_KEY:
        await call.answer("Tribute сейчас недоступен" if lang == "ru" else "Tribute is unavailable right now", show_alert=True)
        return
    plan_key = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    pay_amount, discount_text, discount_redemption = await _active_discount_text(session, db_user.id, plan.price_rub)
    try:
        order = await tribute.create_order(plan, db_user.id, amount_rub=pay_amount)
    except Exception as exc:
        logger.error("Tribute order error: %s", exc)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    tx = await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=pay_amount,
        credits=plan.credits,
        provider=PaymentProvider.tribute,
        external_id=order.order_uuid,
    )
    if discount_redemption:
        await repo.mark_promo_discount_consumed(session, discount_redemption.id, transaction_id=tx.id)

    await call.message.edit_text(  # type: ignore[union-attr]
        (
            f"🟣 <b>Tribute</b>\n\nПакет: <b>{plan.label}</b>\nК оплате: <b>{_fmt_amount(pay_amount)} ₽</b>"
            if lang == "ru"
            else f"🟣 <b>Tribute</b>\n\nPlan: <b>{plan.label}</b>\nTo pay: <b>{_fmt_amount(pay_amount)} ₽</b>"
        ) + discount_text,
        reply_markup=payment_link_kb(
            "🟣 " + ("Перейти к оплате" if lang == "ru" else "Pay now"),
            order.payment_url,
            order.order_uuid,
            lang=lang,
        ),
    )
    await call.answer()


@router.callback_query(F.data == "topup:lava")
async def cb_topup_lava(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = [plan for plan in await repo.get_active_price_plans(session) if settings.lava_offer_id_for_plan(plan.key)]
    if not plans:
        await call.answer("Lava сейчас недоступна" if lang == "ru" else "Lava is unavailable right now", show_alert=True)
        return
    text = (
        "💸 <b>Оплата через Lava</b>\n\nВыбери пакет, оплата откроется в Lava.\n\n" + t("topup_select_plan", lang)
        if lang == "ru"
        else "💸 <b>Pay with Lava</b>\n\nChoose a plan, checkout opens in Lava.\n\n" + t("topup_select_plan", lang)
    )
    await call.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=lava_plans_kb(plans, lang=lang, currency="rub"),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:lava_plan:"))
async def cb_topup_lava_plan(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plan_key = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan or not settings.lava_offer_id_for_plan(plan.key):
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    try:
        invoice = await lava.create_invoice(plan, db_user.id)
    except Exception as e:
        logger.error("Lava invoice error: %s", e)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.lava,
        external_id=invoice.invoice_id,
    )

    await call.message.edit_text(  # type: ignore[union-attr]
        (f"💸 <b>Lava</b>\n\nПакет: <b>{plan.label}</b>\nК оплате: <b>{_fmt_amount(plan.price_rub)} ₽</b>" if lang == "ru" else f"💸 <b>Lava</b>\n\nPlan: <b>{plan.label}</b>\nTo pay: <b>{_fmt_amount(plan.price_rub)} ₽</b>"),
        reply_markup=payment_link_kb(
            "💸 " + ("Перейти к оплате" if lang == "ru" else "Pay now"),
            invoice.payment_url,
            invoice.invoice_id,
            lang=lang,
        ),
    )
    await call.answer()


@router.callback_query(F.data == "topup:usd")
async def cb_topup_usd(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = [plan for plan in await repo.get_active_price_plans(session) if settings.lava_offer_id_for_plan(plan.key)]
    if not plans:
        await call.answer("Lava сейчас недоступна" if lang == "ru" else "Lava is unavailable right now", show_alert=True)
        return
    text = (
        "💸 <b>Оплата через Lava</b>\n\nВыбери пакет, оплата откроется в Lava.\n\n" + t("topup_select_plan", lang)
        if lang == "ru"
        else "💸 <b>Pay with Lava</b>\n\nChoose a plan, checkout opens in Lava.\n\n" + t("topup_select_plan", lang)
    )
    await call.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=lava_plans_kb(plans, lang=lang, currency="rub"),
    )
    await call.answer()


@router.callback_query(F.data == "topup:crypto")
async def cb_topup_crypto_menu(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = await repo.get_active_price_plans(session)
    text = (
        "🪙 <b>Оплата криптовалютой</b>\n\nВыбери пакет. Сумму покажем в USDT."
        if lang == "ru"
        else "🪙 <b>Pay with crypto</b>\n\nChoose a plan. The amount is shown in USDT."
    )
    await call.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=crypto_plans_kb(plans, lang=lang),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:crypto_plan:"))
async def cb_topup_crypto_plan(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plan_key = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return
    if not settings.CRYPTOBOT_TOKEN:
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    pay_amount, discount_text, discount_redemption = await _active_discount_text(session, db_user.id, plan.price_rub)
    amount_usdt = pay_amount / RUB_TO_USDT

    try:
        invoice = await cryptobot.create_invoice(
            int(plan.credits),
            amount_usdt,
            plan.key,
            db_user.id,
        )
    except Exception as exc:
        logger.error("CryptoBot invoice error: %s", exc)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    tx = await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=pay_amount,
        credits=plan.credits,
        provider=PaymentProvider.cryptobot,
        external_id=str(invoice.invoice_id),
    )
    if discount_redemption:
        await repo.mark_promo_discount_consumed(session, discount_redemption.id, transaction_id=tx.id)

    await call.message.edit_text(  # type: ignore[union-attr]
        (
            f"🪙 <b>CryptoBot</b>\n\nПакет: <b>{plan.label}</b>\nК оплате: <b>{_fmt_amount(amount_usdt)} USDT</b>"
            if lang == "ru"
            else f"🪙 <b>CryptoBot</b>\n\nPlan: <b>{plan.label}</b>\nTo pay: <b>{_fmt_amount(amount_usdt)} USDT</b>"
        ) + discount_text,
        reply_markup=crypto_pay_kb(invoice.pay_url, str(invoice.invoice_id), lang=lang),
    )
    await call.answer()


@router.callback_query(F.data == "promo:enter")
async def cb_enter_promo(call: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.set_state(PromoFSM.waiting_code)
    await call.message.answer(  # type: ignore[union-attr]
        "🎟 <b>Введи промокод</b>\n\n"
        "Промокод может дать 💋, скидку на оплату или бесплатную генерацию.",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(Command("promo"))
async def cmd_promo(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 1:
        await state.set_state(PromoFSM.waiting_code)
        await message.answer("🎟 Введи промокод одним сообщением.")
        return
    await _apply_promo_text(message, session, db_user, parts[1])


@router.message(PromoFSM.waiting_code)
async def handle_promo_code(message: Message, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await _apply_promo_text(message, session, db_user, message.text or "")
    await state.clear()


async def _apply_promo_text(message: Message, session: AsyncSession, db_user: User, raw_code: str) -> None:
    code = repo.normalize_promo_code(raw_code)
    if not code:
        await message.answer("Промокод пустой. Пришли код текстом.")
        return
    try:
        result = await repo.redeem_promo_code(session, user_id=db_user.id, code=code)
    except ValueError as exc:
        await message.answer(f"❌ {exc}", reply_markup=back_to_menu_kb())
        return
    await message.answer(_promo_success_text(result), reply_markup=back_to_menu_kb())


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

    pay_amount, discount_text, discount_redemption = await _active_discount_text(session, db_user.id, plan.price_rub)

    try:
        payment = await tbank.create_payment(plan, db_user.id, amount_rub=pay_amount)
    except Exception as e:
        logger.error("T-Bank payment error: %s", e)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    tx = await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=pay_amount,
        credits=plan.credits,
        provider=PaymentProvider.tbank,
        external_id=payment.payment_id,
    )
    if discount_redemption:
        await repo.mark_promo_discount_consumed(session, discount_redemption.id, transaction_id=tx.id)

    await call.message.edit_text(  # type: ignore[union-attr]
        ((f"💳 <b>T-Bank</b>\n\nПакет: <b>{plan.label}</b>\nК оплате: <b>{_fmt_amount(pay_amount)} ₽</b>" if lang == "ru" else f"💳 <b>T-Bank</b>\n\nPlan: <b>{plan.label}</b>\nTo pay: <b>{_fmt_amount(pay_amount)} ₽</b>") + discount_text),
        reply_markup=payment_link_kb(
            "💳 " + ("Перейти к оплате" if lang == "ru" else "Pay now"),
            payment.payment_url,
            payment.payment_id,
            lang=lang,
        ),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:check:"))
async def cb_check_payment_status(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> None:
    lang = db_user.language or "ru"
    external_id = call.data.split(":")[-1]
    tx = await repo.get_transaction_by_external_id(session, external_id)
    if not tx or tx.user_id != db_user.id:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    try:
        status, balance = await _reconcile_transaction_status(session, tx)
    except Exception as e:
        logger.error("Payment reconcile error: %s", e)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    if status == TransactionStatus.paid:
        refreshed = await repo.get_transaction_by_external_id(session, external_id)
        credits = refreshed.credits if refreshed else tx.credits
        current_balance = balance if balance is not None else (await repo.get_user_by_id(session, db_user.id)).credits
        await call.message.edit_text(  # type: ignore[union-attr]
            (
                "✅ <b>Оплата подтверждена</b>\n\n"
                + (f"Зачислено: <b>+{credits} 💋</b>\n" if lang == "ru" else f"Added: <b>+{credits} 💋</b>\n")
                + (f"Баланс: <b>{current_balance} 💋</b>" if lang == "ru" else f"Balance: <b>{current_balance} 💋</b>")
            ),
            reply_markup=back_to_menu_kb(),
        )
        await call.answer()
        return

    if status in {TransactionStatus.failed, TransactionStatus.refunded}:
        await call.answer(
            "Платёж завершился без зачисления" if lang == "ru" else "Payment finished without credit",
            show_alert=True,
        )
        return

    await call.answer(
        "Платёж ещё в обработке" if lang == "ru" else "Payment is still pending",
        show_alert=True,
    )
