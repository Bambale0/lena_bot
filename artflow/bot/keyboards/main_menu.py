# bot/keyboards/main_menu.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from core.config import settings


def main_menu_kb(
    *,
    balance: int | None = None,
    has_active_image_session: bool = False,
    is_admin: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 Открыть приложение", web_app=WebAppInfo(url=f"{settings.WEBHOOK_URL.rstrip('/')}/app?v=1778285568")),
    )
    if balance is not None:
        builder.row(
            InlineKeyboardButton(text=f"💋 Баланс: {balance}", callback_data="menu:balance"),
        )
    if has_active_image_session:
        builder.row(
            InlineKeyboardButton(text="🎨 Вернуться к серии", callback_data="menu:image"),
        )
    builder.row(
        InlineKeyboardButton(text="🎨 Изображение", callback_data="menu:image"),
        InlineKeyboardButton(text="🎬 Видео", callback_data="menu:video"),
    )
    builder.row(
        InlineKeyboardButton(text="🎵 Песня", callback_data="menu:music"),
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Лента", callback_data="menu:feed"),
        InlineKeyboardButton(text="👑 Топ дня", callback_data="menu:top_day"),
    )
    builder.row(
        InlineKeyboardButton(text="🧠 Midjourney", callback_data="menu:mj"),
    )
    builder.row(
        InlineKeyboardButton(text="📚 Библиотека промптов", callback_data="menu:prompts"),
        InlineKeyboardButton(text="📋 История", callback_data="menu:history"),
    )
    builder.row(
        InlineKeyboardButton(text="👥 Рефералы", callback_data="menu:referral"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help"),
    )
    builder.row(
        InlineKeyboardButton(text="💳 Пополнить", callback_data="menu:topup"),
    )
    if is_admin:
        builder.row(InlineKeyboardButton(text="👑 Админ", callback_data="menu:admin"))
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def balance_screen_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Пополнить", callback_data="menu:topup"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()
