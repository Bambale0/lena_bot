from __future__ import annotations

from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.ui.common import ScreenRender
from core.config import settings


def render_create_hub(lang: str = "ru", *, is_admin: bool = False) -> ScreenRender:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🖼 " + ("Изображение" if lang == "ru" else "Image"), callback_data="menu:image"),
        InlineKeyboardButton(text="🎬 " + ("Видео" if lang == "ru" else "Video"), callback_data="menu:video"),
    )
    builder.row(
        InlineKeyboardButton(text="🎵 " + ("Музыка" if lang == "ru" else "Music"), callback_data="menu:music"),
        InlineKeyboardButton(text="🤖 " + ("Через AI" if lang == "ru" else "Via AI"), callback_data="menu:assistant"),
    )
    if is_admin:
        builder.row(InlineKeyboardButton(text="🖌️ Midjourney", callback_data="menu:mj"))
    builder.row(InlineKeyboardButton(text="🏠 " + ("Главная" if lang == "ru" else "Home"), callback_data="menu:main"))

    text = (
        "✨ <b>Создать</b>\n\n"
        "Выбери результат — APIX покажет только подходящие модели и настройки."
        if lang == "ru"
        else "✨ <b>Create</b>\n\nChoose the result. APIX will show only compatible models and settings."
    )
    return ScreenRender(text=text, reply_markup=builder.as_markup())


def render_more_hub(lang: str = "ru", *, is_admin: bool = False) -> ScreenRender:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📚 " + ("Библиотека" if lang == "ru" else "Library"), callback_data="menu:prompts"),
        InlineKeyboardButton(text="👥 " + ("Партнёры" if lang == "ru" else "Partners"), callback_data="menu:referral"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ " + ("Настройки" if lang == "ru" else "Settings"), callback_data="menu:settings"),
        InlineKeyboardButton(text="❓ " + ("Помощь" if lang == "ru" else "Help"), callback_data="menu:help"),
    )
    builder.row(
        InlineKeyboardButton(
            text="📱 " + ("Открыть приложение" if lang == "ru" else "Open App"),
            web_app=WebAppInfo(url=f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app?v=1778285569"),
        )
    )
    if is_admin:
        builder.row(InlineKeyboardButton(text="👑 " + ("Админ" if lang == "ru" else "Admin"), callback_data="menu:admin"))
    builder.row(InlineKeyboardButton(text="🏠 " + ("Главная" if lang == "ru" else "Home"), callback_data="menu:main"))

    text = (
        "☰ <b>Ещё</b>\n\n"
        "Второстепенные разделы собраны здесь, чтобы главное меню оставалось простым."
        if lang == "ru"
        else "☰ <b>More</b>\n\nSecondary sections live here so the home screen stays simple."
    )
    return ScreenRender(text=text, reply_markup=builder.as_markup())
