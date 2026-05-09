from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def feed_card_kb(
    gen_id: int,
    *,
    index: int,
    source: str = "feed",
    has_next: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="❤️", callback_data=f"feed:like:{gen_id}:{source}:{index}"),
        InlineKeyboardButton(text="📤", callback_data=f"feed:share:{gen_id}"),
        InlineKeyboardButton(
            text="➡️",
            callback_data=f"feed:next:{source}:{index + 1}" if has_next else f"feed:next:{source}:0",
        ),
    )
    builder.row(
        InlineKeyboardButton(text="🔁 Повторить", callback_data=f"feed:use:{gen_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📚 Библиотека промптов", callback_data="menu:prompts"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="menu:main"),
    )
    return builder.as_markup()


def empty_feed_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎨 Создать изображение", callback_data="menu:image"))
    builder.row(InlineKeyboardButton(text="📚 Библиотека промптов", callback_data="menu:prompts"))
    builder.row(InlineKeyboardButton(text="🏠 Главная", callback_data="menu:main"))
    return builder.as_markup()


def get_generation_result_keyboard(generation_id: int) -> InlineKeyboardMarkup:
    """Buttons shown directly under generated media."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✨ Ремикс", callback_data=f"feed:remix:{generation_id}"),
        InlineKeyboardButton(text="📚 В библиотеку", callback_data=f"feed:publish:{generation_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🔁 Ещё вариант", callback_data=f"feed:again:{generation_id}"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    )
    return builder.as_markup()
