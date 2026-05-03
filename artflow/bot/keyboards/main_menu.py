# bot/keyboards/main_menu.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎨 Изображение", callback_data="menu:image"),
        InlineKeyboardButton(text="🎬 Видео", callback_data="menu:video"),
    )
    builder.row(
        InlineKeyboardButton(text="🖌️ Midjourney", callback_data="menu:mj"),
    )
    builder.row(
        InlineKeyboardButton(text="💎 Баланс", callback_data="menu:balance"),
        InlineKeyboardButton(text="💳 Пополнить", callback_data="menu:topup"),
    )
    builder.row(
        InlineKeyboardButton(text="🗂 Промпты", callback_data="menu:prompts"),
        InlineKeyboardButton(text="📋 История", callback_data="menu:history"),
    )
    builder.row(
        InlineKeyboardButton(text="👥 Рефералы", callback_data="menu:referral"),
        InlineKeyboardButton(text="❓ Помощь", callback_data="menu:help"),
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()
