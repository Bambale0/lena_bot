"""Telegram Stars payment integration."""
from __future__ import annotations

import logging
import math

from aiogram import F, Router, Bot
from aiogram.types import CallbackQuery, Message, LabeledPrice, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from core.config import settings
from db import repository as repo
from db.models import PaymentProvider, User

logger = logging.getLogger(__name__)
router = Router(name="stars_payment")

_TELEGRAM_STARS_RUB_PER_STAR = 195.99 / 100

def _plan_stars_price(plan) -> int:
    explicit = getattr(plan, "price_stars", None)
    if explicit is not None:
        try:
            return max(1, int(explicit))
        except (TypeError, ValueError):
            pass
    return max(1, math.ceil(float(plan.price_rub) / _TELEGRAM_STARS_RUB_PER_STAR))


@router.callback_query(F.data == "topup:stars")
async def cb_topup_stars(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    lang = db_user.language or "ru"
    if not settings.TELEGRAM_STARS_ENABLED:
        await call.answer(t("error_not_available", lang), show_alert=True)
        return

    plans = await repo.get_active_price_plans(session)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    for plan in plans:
        stars = _plan_stars_price(plan)
        builder.button(
            text=f"⭐ {plan.label} — {int(plan.credits) if float(plan.credits).is_integer() else plan.credits} 💋 · {stars} ⭐",
            callback_data=f"topup:stars_plan:{plan.key}",
        )
    builder.button(text="← " + ("Назад" if lang == "ru" else "Back"), callback_data="menu:topup")
    builder.adjust(1)
    await call.message.edit_text(
        t("topup_stars_title", lang) + "\n\n" + t("topup_select_plan", lang),
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("topup:stars_plan:"))
async def cb_stars_plan(
    call: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    """Create Telegram Stars invoice."""
    lang = db_user.language or "ru"
    if not settings.TELEGRAM_STARS_ENABLED:
        await call.answer(t("error_not_available", lang), show_alert=True)
        return

    plan_key = call.data.split(":")[-1]
    plan = await repo.get_price_plan_by_key(session, plan_key)

    if not plan:
        await call.answer(t("error_not_found", lang), show_alert=True)
        return

    stars = _plan_stars_price(plan)

    tx = await repo.create_transaction(
        session,
        user_id=db_user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.telegram_stars,
        external_id=f"stars_pending:{db_user.id}:{plan_key}",
    )

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"⭐ {plan.label}",
        description=t("topup_stars_desc", lang, label=plan.label, stars=stars),
        payload=f"stars:{tx.id}:{plan_key}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"{plan.credits} credits", amount=stars)],
    )
    await call.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(
    message: Message, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    lang = db_user.language or "ru"
    if not settings.TELEGRAM_STARS_ENABLED:
        logger.warning("Stars successful_payment ignored while feature is disabled")
        return

    payment = message.successful_payment
    if not payment or payment.currency != "XTR":
        return
    parts = payment.invoice_payload.split(":")
    if len(parts) < 2 or parts[0] != "stars":
        logger.warning("Unknown Stars payload: %s", payment.invoice_payload)
        return
    tx_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    if not tx_id:
        return
    tx = await repo.confirm_transaction_by_id(
        session,
        tx_id,
        external_id=payment.telegram_payment_charge_id,
    )
    if not tx:
        logger.info("Stars payment already processed or missing tx_id=%s", tx_id)
        return
    new_balance = await repo.add_credits(session, db_user.id, tx.credits, entry_type="payment_credit", source_type="transaction", source_id=str(tx.id), note="Telegram Stars payment")
    from main import _accrue_referral_commissions
    await _accrue_referral_commissions(session, db_user, tx.amount_rub, bot)
    await message.answer(
        t("topup_success", lang, credits=tx.credits, balance=new_balance),
        reply_markup=back_to_menu_kb(),
    )
