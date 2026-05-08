# bot/keyboards/payment.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import PricePlan


def _fmt_amount(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def topup_kb(plans: list[PricePlan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.row(
            InlineKeyboardButton(
                text=f"💳 {plan.label} — {_fmt_amount(plan.price_rub)}₽",
                callback_data=f"topup:rub:{plan.key}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="🪙 Оплата криптой", callback_data="topup:crypto"),
    )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:balance"))
    return builder.as_markup()


def crypto_plans_kb(plans: list[PricePlan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.row(
            InlineKeyboardButton(
                text=f"🪙 {plan.label} — ${_fmt_amount(plan.price_rub / 90)} USDT",
                callback_data=f"topup:crypto_plan:{plan.key}",
            )
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:topup"))
    return builder.as_markup()


def crypto_pay_kb(pay_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💸 Оплатить в CryptoBot", url=pay_url))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:topup"))
    return builder.as_markup()


def payment_link_kb(text: str, pay_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=text, url=pay_url))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:topup"))
    return builder.as_markup()
