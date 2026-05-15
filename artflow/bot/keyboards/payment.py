from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.config import settings
from db.models import PricePlan


def _fmt_amount(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def topup_kb(plans: list[PricePlan], lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    for plan in plans:
        builder.row(
            InlineKeyboardButton(
                text=f"💳 {plan.label} — {int(plan.credits) if float(plan.credits).is_integer() else _fmt_amount(plan.credits)} 💋 · {_fmt_amount(plan.price_rub)}₽",
                callback_data=f"topup:rub:{plan.key}",
            )
        )
    if settings.TELEGRAM_STARS_ENABLED:
        builder.row(
            InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="topup:stars"),
        )
    builder.row(
        InlineKeyboardButton(text="🌕 " + ("Оплата криптой" if lang == "ru" else "Pay with crypto"), callback_data="topup:crypto"),
    )
    builder.row(InlineKeyboardButton(text=back_text, callback_data="menu:balance"))
    return builder.as_markup()


def crypto_plans_kb(plans: list[PricePlan], lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    for plan in plans:
        builder.row(
            InlineKeyboardButton(
                text=f"🌕 {plan.label} — {int(plan.credits) if float(plan.credits).is_integer() else _fmt_amount(plan.credits)} 💋 · ${_fmt_amount(plan.price_rub / 90)} USDT",
                callback_data=f"topup:crypto_plan:{plan.key}",
            )
        )
    builder.row(InlineKeyboardButton(text=back_text, callback_data="menu:topup"))
    return builder.as_markup()


def crypto_pay_kb(pay_url: str, external_id: str | None = None, lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    builder.row(InlineKeyboardButton(text="🌕 " + ("Оплатить в CryptoBot" if lang == "ru" else "Pay in CryptoBot"), url=pay_url))
    if external_id:
        builder.row(InlineKeyboardButton(text="✅ " + ("Проверить оплату" if lang == "ru" else "Check payment"), callback_data=f"topup:check:{external_id}"))
    builder.row(InlineKeyboardButton(text=back_text, callback_data="menu:topup"))
    return builder.as_markup()


def payment_link_kb(text: str, pay_url: str, external_id: str | None = None, lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    builder.row(InlineKeyboardButton(text=text, url=pay_url))
    if external_id:
        builder.row(InlineKeyboardButton(text="✅ " + ("Проверить оплату" if lang == "ru" else "Check payment"), callback_data=f"topup:check:{external_id}"))
    builder.row(InlineKeyboardButton(text=back_text, callback_data="menu:topup"))
    return builder.as_markup()
