# bot/keyboards/main_menu.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb(
    *,
    balance: int | None = None,
    has_active_image_session: bool = False,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    """Use the same app/trends/admin navigation as the primary home renderer."""
    from bot.ui.main_menu import build_main_menu_keyboard

    return build_main_menu_keyboard(
        has_active_image_session=has_active_image_session, is_admin=is_admin,
    )


def back_to_menu_kb(*, back_cb: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if back_cb:
        builder.row(InlineKeyboardButton(text="← Назад", callback_data=back_cb))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def balance_screen_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Пополнить", callback_data="menu:topup"))
    builder.row(InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="promo:enter"))
    builder.row(InlineKeyboardButton(text="👥 Партнёрская программа", callback_data="menu:referral"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()
