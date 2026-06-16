from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.config import settings
from db.models import PricePlan

RUB_TO_USDT = 90.0


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

    currency_texts = {
        "usd": "💸 Lava" if settings.lava_is_enabled() else ("💵 Доллар" if lang == "ru" else "💵 Dollar"),
        "rub": "₽ Рубль" if lang == "ru" else "₽ Ruble",
        "crypto": "🪙 Крипта" if lang == "ru" else "🪙 Crypto",
    }
    for key in ("usd", "rub", "crypto"):
        builder.row(InlineKeyboardButton(text=currency_texts[key], callback_data=f"topup:{key}"))
    builder.row(
        InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="promo:enter"),
    )
    builder.row(InlineKeyboardButton(text=back_text, callback_data="menu:balance"))
    return builder.as_markup()


def rub_methods_kb(lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    builder.row(
        InlineKeyboardButton(
            text="💳 " + ("Карта / СБП" if lang == "ru" else "Card / SBP"),
            callback_data="topup:tbank",
        )
    )
    if settings.TELEGRAM_STARS_ENABLED:
        builder.row(InlineKeyboardButton(text="⭐ Telegram Stars", callback_data="topup:stars"))
    if settings.lava_is_enabled():
        builder.row(InlineKeyboardButton(text="💸 Lava", callback_data="topup:lava"))
    builder.row(InlineKeyboardButton(text=back_text, callback_data="menu:topup"))
    return builder.as_markup()


def rub_plans_kb(plans: list[PricePlan], lang: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    for plan in plans:
        builder.row(
            InlineKeyboardButton(
                text=f"💳 {plan.label} — {int(plan.credits) if float(plan.credits).is_integer() else _fmt_amount(plan.credits)} 💋 · {_fmt_amount(plan.price_rub)}₽",
                callback_data=f"topup:rub:{plan.key}",
            )
        )
    builder.row(InlineKeyboardButton(text=back_text, callback_data="topup:rub"))
    return builder.as_markup()


def crypto_plans_kb(plans: list[PricePlan], lang: str = "ru", currency: str = "usdt") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    for plan in plans:
        amount = plan.price_rub / RUB_TO_USDT
        price_text = f"${_fmt_amount(amount)}" if currency == "usd" else f"{_fmt_amount(amount)} USDT"
        builder.row(
            InlineKeyboardButton(
                text=f"🌕 {plan.label} — {int(plan.credits) if float(plan.credits).is_integer() else _fmt_amount(plan.credits)} 💋 · {price_text}",
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


def lava_plans_kb(plans: list[PricePlan], lang: str = "ru", currency: str = "rub") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    back_text = "← " + ("Назад" if lang == "ru" else "Back")
    back_cb = "topup:usd" if currency == "usd" else "menu:topup"
    for plan in plans:
        amount = plan.price_rub / RUB_TO_USDT
        price_text = f"${_fmt_amount(amount)}" if currency == "usd" else f"{_fmt_amount(plan.price_rub)}₽"
        builder.row(
            InlineKeyboardButton(
                text=f"💸 {plan.label} — {int(plan.credits) if float(plan.credits).is_integer() else _fmt_amount(plan.credits)} 💋 · {price_text}",
                callback_data=f"topup:lava_plan:{plan.key}",
            )
        )
    builder.row(InlineKeyboardButton(text=back_text, callback_data=back_cb))
    return builder.as_markup()
