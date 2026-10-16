# bot/handlers/payment.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from bot.keyboards.payment import (
    crypto_pay_kb,
    crypto_plans_kb,
    lava_plans_kb,
    payment_link_kb,
    plan_payment_methods_kb,
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


async def _payment_return_context(
    state: FSMContext | None,
) -> tuple[str | None, str | None]:
    if state is None:
        return None, None
    data = await state.get_data()
    callback = str(data.get("payment_return_callback") or "").strip() or None
    label = str(data.get("payment_return_label") or "").strip() or None
    return callback, label


def _payment_complete_kb(
    return_callback: str | None,
    return_label: str | None,
    *,
    lang: str,
) -> InlineKeyboardMarkup:
    if not return_callback:
        return back_to_menu_kb()
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=return_label or ("▶️ Продолжить" if lang == "ru" else "▶️ Continue"),
                    callback_data=return_callback,
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню" if lang == "ru" else "🏠 Home",
                    callback_data="menu:main",
                )
            ],
        ]
    )


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
            "Она применится к следующей оплате картой, CryptoBot или USD."
        )
    return (
        "✅ <b>Промокод активирован</b>\n\n"
        f"Начислено: <b>+{_fmt_amount(result.credits_added)} 💋</b>\n"
        f"Баланс: <b>{_fmt_amount(result.balance_after or 0)} 💋</b>"
    )


async def _confirm_paid_transaction(session: AsyncSession, external_id: str) -> float | None:
    confirmed = await repo.confirm_transaction_and_add_credits(session, external_id)
    tx = confirmed[0] if confirmed else await repo.get_transaction_by_external_id(session, external_id)
    if tx and tx.status == TransactionStatus.paid:
        user = await repo.get_user_by_id(session, tx.user_id)
        if user:
            from main import _accrue_referral_commissions
            await _accrue_referral_commissions(session, user, tx, None)
    return confirmed[1] if confirmed else None


async def _reconcile_transaction_status(
    session: AsyncSession, tx,
) -> tuple[TransactionStatus, float | None]:
    # Release the read transaction before the provider boundary. No locks or
    # pooled connection should be held during a network request.
    external_id, provider, local_status = tx.external_id, tx.provider, tx.status
    amount_rub = tx.amount_rub
    if not external_id or local_status == TransactionStatus.refunded:
        return local_status, None
    await session.commit()
    balance = None
    if provider == PaymentProvider.tbank:
        state = await tbank.get_payment_state(external_id)
        if str(state.get("PaymentId", external_id)) != external_id:
            raise ValueError("Payment state identity mismatch")
        status = str(state.get("Status", "")).upper()
        if status == "CONFIRMED":
            balance = await _confirm_paid_transaction(session, external_id)
        elif status in TBANK_FINAL_FAILURE_STATUSES | {"REVERSED"}:
            await repo.set_transaction_status(session, external_id, TransactionStatus.failed)
        elif status in {"REFUNDED", "PARTIAL_REFUNDED"}:
            from payments.refund_settlement import settle_tbank_refund
            result = await settle_tbank_refund(session, external_id, status, state.get("Amount"))
            return result.status, None
    elif provider == PaymentProvider.cryptobot:
        invoice = await cryptobot.get_invoice(int(external_id))
        status = str(invoice.get("status", "")).lower()
        if status == "paid":
            balance = await _confirm_paid_transaction(session, external_id)
        elif status in {"expired", "invalid", "cancelled"}:
            await repo.set_transaction_status(session, external_id, TransactionStatus.failed)
    elif provider == PaymentProvider.lava:
        invoice = await lava.get_invoice(external_id)
        status = str(invoice.get("status", "")).lower()
        if lava.is_paid_invoice(invoice):
            balance = await _confirm_paid_transaction(session, external_id)
        elif status in {"failed", "cancelled", "canceled", "expired"}:
            await repo.set_transaction_status(session, external_id, TransactionStatus.failed)
    elif provider == PaymentProvider.tribute and not external_id.startswith("digital:"):
        status = await tribute.get_order_status(external_id)
        if status == "paid":
            balance = await _confirm_paid_transaction(session, external_id)
        elif status == "failed":
            await repo.set_transaction_status(session, external_id, TransactionStatus.failed)
        elif status == "refunded":
            from db.payment_refunds import money_minor
            from payments.refund_settlement import settle_tribute_refund
            result = await settle_tribute_refund(
                session, external_id, amount_minor=money_minor(amount_rub), currency="rub", digital=False,
            )
            return result.status, None
    current = await repo.get_transaction_by_external_id(session, external_id)
    return (current.status if current else local_status), balance


@router.callback_query(F.data == "menu:topup")
async def cb_topup(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    plans = await repo.get_active_price_plans(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        t("topup_title", lang),
        reply_markup=topup_kb(plans, lang=lang),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:plan:"))
async def cb_topup_plan_methods(
    call: CallbackQuery, session: AsyncSession, db_user: User
) -> None:
    """Choose payment provider before creating any provider-side invoice."""
    lang = db_user.language or "ru"
    plan_key = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan or not plan.is_active:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    credits_text = _fmt_amount(float(plan.credits))
    text = (
        f"💋 <b>{plan.label}</b>\n\nПакет: <b>{credits_text} 💋</b>\n\nВыбери способ оплаты."
        if lang == "ru"
        else f"💋 <b>{plan.label}</b>\n\nPackage: <b>{credits_text} 💋</b>\n\nChoose a payment method."
    )
    await call.message.edit_text(  # type: ignore[union-attr]
        text,
        reply_markup=plan_payment_methods_kb(plan, lang=lang),
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
        await call.answer("Оплата в USD сейчас недоступна" if lang == "ru" else "USD payment is unavailable right now", show_alert=True)
        return
    plans = [plan for plan in await repo.get_active_price_plans(session)
             if tribute.digital_product_for_plan(plan) is not None]
    if not plans:
        await call.answer("Оплата в USD сейчас недоступна" if lang == "ru" else "USD payment is unavailable right now", show_alert=True)
        return
    text = (
        "💵 <b>Оплата в USD</b>\n\nВыбери пакет. Откроется защищённая страница оплаты, а 💋 начислятся автоматически после подтверждения платежа.\n\n" + t("topup_select_plan", lang)
        if lang == "ru"
        else "💵 <b>Pay in USD</b>\n\nChoose a plan. Secure checkout will open and credits are added automatically after payment confirmation.\n\n" + t("topup_select_plan", lang)
    )
    await call.message.edit_text(text, reply_markup=tribute_plans_kb(plans, lang=lang))  # type: ignore[union-attr]
    await call.answer()


@router.callback_query(F.data.startswith("topup:tribute_plan:"))
async def cb_topup_tribute_plan(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext | None = None,
) -> None:
    lang = db_user.language or "ru"
    if not settings.TRIBUTE_API_KEY:
        await call.answer("Оплата в USD сейчас недоступна" if lang == "ru" else "USD payment is unavailable right now", show_alert=True)
        return
    plan_key = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    plan = await repo.get_price_plan_by_key(session, plan_key)
    if not plan or not plan.is_active or tribute.digital_product_for_plan(plan) is None:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    try:
        product = await tribute.get_digital_product_checkout(plan)
    except Exception as exc:
        logger.error("Tribute digital product error plan=%s: %s", plan.key, exc)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    price_text = tribute.digital_product_price_text(plan) or f"{_fmt_amount(plan.price_rub)} ₽"
    return_callback, return_label = await _payment_return_context(state)
    await call.message.edit_text(  # type: ignore[union-attr]
        (
            f"💵 <b>USD</b>\n\nПакет: <b>{plan.label}</b>\nК оплате: <b>{price_text}</b>\n\nПосле оплаты 💋 начислятся автоматически."
            if lang == "ru"
            else f"💵 <b>USD</b>\n\nPlan: <b>{plan.label}</b>\nTo pay: <b>{price_text}</b>\n\nCredits are added automatically after payment."
        ),
        reply_markup=payment_link_kb(
            "💵 " + ("Перейти к оплате" if lang == "ru" else "Pay now"),
            product.payment_url,
            None,
            lang=lang,
            back_callback=return_callback or "menu:topup",
            back_text=return_label,
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
async def cb_topup_lava_plan(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext | None = None,
) -> None:
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

    return_callback, return_label = await _payment_return_context(state)
    await call.message.edit_text(  # type: ignore[union-attr]
        (f"💸 <b>Lava</b>\n\nПакет: <b>{plan.label}</b>\nСумма в ₽ на странице оплаты" if lang == "ru" else f"💸 <b>Lava</b>\n\nPlan: <b>{plan.label}</b>\nRUB amount at checkout"),
        reply_markup=payment_link_kb(
            "💸 " + ("Перейти к оплате" if lang == "ru" else "Pay now"),
            invoice.payment_url,
            invoice.invoice_id,
            lang=lang,
            back_callback=return_callback or "menu:topup",
            back_text=return_label,
        ),
    )
    await call.answer()


@router.callback_query(F.data == "topup:usd")
async def cb_topup_usd(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    """Backward-compatible alias for old bot messages: USD is Tribute, never Lava."""
    await cb_topup_tribute(call, session, db_user)


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
async def cb_topup_crypto_plan(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext | None = None,
) -> None:
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

    return_callback, return_label = await _payment_return_context(state)
    await call.message.edit_text(  # type: ignore[union-attr]
        (
            f"🪙 <b>CryptoBot</b>\n\nПакет: <b>{plan.label}</b>\nК оплате: <b>{_fmt_amount(amount_usdt)} USDT</b>"
            if lang == "ru"
            else f"🪙 <b>CryptoBot</b>\n\nPlan: <b>{plan.label}</b>\nTo pay: <b>{_fmt_amount(amount_usdt)} USDT</b>"
        ) + discount_text,
        reply_markup=crypto_pay_kb(
            invoice.pay_url,
            str(invoice.invoice_id),
            lang=lang,
            back_callback=return_callback or "menu:topup",
            back_text=return_label,
        ),
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
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext | None = None,
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

    return_callback, return_label = await _payment_return_context(state)
    await call.message.edit_text(  # type: ignore[union-attr]
        ((f"💳 <b>Карта | СБП</b>\n\nПакет: <b>{plan.label}</b>\nК оплате: <b>{_fmt_amount(pay_amount)} ₽</b>" if lang == "ru" else f"💳 <b>Card | SBP</b>\n\nPlan: <b>{plan.label}</b>\nTo pay: <b>{_fmt_amount(pay_amount)} ₽</b>") + discount_text),
        reply_markup=payment_link_kb(
            "💳 " + ("Перейти к оплате" if lang == "ru" else "Pay now"),
            payment.payment_url,
            payment.payment_id,
            lang=lang,
            back_callback=return_callback or "menu:topup",
            back_text=return_label,
        ),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:check:"))
async def cb_check_payment_status(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext | None = None,
) -> None:
    lang = db_user.language or "ru"
    external_id = call.data.split(":", 2)[-1]
    tx = await repo.get_transaction_by_external_id(session, external_id)
    if not tx or tx.user_id != db_user.id:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    try:
        status, balance = await _reconcile_transaction_status(session, tx)
    except Exception as e:
        from core.provider_logging import safe_identifier
        logger.error("Payment reconcile error payment_id=%s error_type=%s", safe_identifier(external_id), type(e).__name__)
        await call.answer(t("error_generic", lang), show_alert=True)
        return

    if status == TransactionStatus.paid:
        refreshed = await repo.get_transaction_by_external_id(session, external_id)
        credits = refreshed.credits if refreshed else tx.credits
        current_balance = balance if balance is not None else (await repo.get_user_by_id(session, db_user.id)).credits
        return_callback, return_label = await _payment_return_context(state)
        if refreshed and int(getattr(refreshed, "refunded_amount_minor", 0) or 0) > 0:
            reversed_credits = _fmt_amount(float(refreshed.refunded_credits or 0))
            status_text = (
                f"↩️ <b>Частичный возврат учтён</b>\n\nСписано за возвраты: <b>{reversed_credits} 💋</b>\nБаланс: <b>{current_balance} 💋</b>"
                if lang == "ru" else
                f"↩️ <b>Partial refund recorded</b>\n\nCredits removed for refunds: <b>{reversed_credits} 💋</b>\nBalance: <b>{current_balance} 💋</b>"
            )
        else:
            status_text = (
                "✅ <b>Оплата подтверждена</b>\n\n"
                + (f"Зачислено: <b>+{credits} 💋</b>\n" if lang == "ru" else f"Added: <b>+{credits} 💋</b>\n")
                + (f"Баланс: <b>{current_balance} 💋</b>" if lang == "ru" else f"Balance: <b>{current_balance} 💋</b>")
            )
        await call.message.edit_text(  # type: ignore[union-attr]
            status_text,
            reply_markup=_payment_complete_kb(
                return_callback,
                return_label,
                lang=lang,
            ),
        )
        await call.answer()
        return

    if status == TransactionStatus.refunded:
        await call.answer("Возврат платежа учтён" if lang == "ru" else "Payment refund recorded", show_alert=True)
        return
    if status == TransactionStatus.failed:
        await call.answer(
            "Платёж завершился без зачисления" if lang == "ru" else "Payment finished without credit",
            show_alert=True,
        )
        return

    await call.answer(
        "Платёж ещё в обработке" if lang == "ru" else "Payment is still pending",
        show_alert=True,
    )
