# bot/keyboards/main_menu.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb(
    *,
    balance: int | None = None,
    has_active_image_session: bool = False,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """Legacy-compatible builder that mirrors the UX v2 home contract."""
    builder = InlineKeyboardBuilder()
    if has_active_image_session:
        builder.row(
            InlineKeyboardButton(text="🔥 Продолжить работу", callback_data="menu:image"),
            InlineKeyboardButton(text="🆕 Новая работа", callback_data="img_session:new"),
        )
    builder.row(
        InlineKeyboardButton(text="✨ Создать", callback_data="menu:create"),
        InlineKeyboardButton(text="🤖 AI-ассистент", callback_data="menu:assistant"),
    )
    builder.row(
        InlineKeyboardButton(text="📂 Мои работы", callback_data="menu:history"),
        InlineKeyboardButton(text="🔥 Лента", callback_data="menu:feed"),
    )
    balance_label = f"💎 Баланс · {balance}" if balance is not None else "💎 Баланс"
    builder.row(
        InlineKeyboardButton(text=balance_label, callback_data="menu:balance"),
        InlineKeyboardButton(text="☰ Ещё", callback_data="menu:more"),
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def balance_screen_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Пополнить", callback_data="menu:topup"))
    builder.row(InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="promo:enter"))
    builder.row(InlineKeyboardButton(text="👥 Партнёрская программа", callback_data="menu:referral"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()
