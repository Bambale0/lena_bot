from __future__ import annotations

from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.session_service import MainMenuContext
from bot.ui.common import ScreenRender
from core.config import settings

def render_main_menu(context: MainMenuContext) -> ScreenRender:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📱 Открыть приложение",
            web_app=WebAppInfo(url=f"{settings.WEBHOOK_URL.rstrip('/')}/app"),
        ),
    )
    builder.row(
        InlineKeyboardButton(text=f"💋 Баланс: {context.balance}", callback_data="menu:balance"),
    )

    if context.active_image_session:
        session = context.active_image_session
        quality = session.quality or "basic"
        ratio = session.aspect_ratio or "default"
        count = session.count or 1
        builder.row(
            InlineKeyboardButton(text="🔥 Продолжить", callback_data="menu:image"),
            InlineKeyboardButton(text="🆕 Новая серия", callback_data="img_session:new"),
        )
        text = (
            "👋 <b>Добро пожаловать в APIX</b>\n\n"
            "🎨 <b>Активная серия найдена</b>\n"
            f"<code>{session.model}</code>\n"
            f"{ratio} · {quality} · {count} фото\n\n"
            "Можно продолжить с текущими настройками или начать новую серию."
        )
    else:
        text = (
            "👋 <b>Добро пожаловать в APIX</b>\n\n"
            "Твой арсенал AI-генерации:\n"
            "🎨 <b>Изображения</b>\n"
            "🎬 <b>Видео</b>\n"
            "🎵 <b>Песня</b>\n"
            "🔥 <b>Лента ремиксов</b>\n"
            "🧠 <b>Midjourney</b>\n\n"
            "Листай, ремиксь, создавай:"
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
    if context.is_admin:
        builder.row(InlineKeyboardButton(text="👑 Админ", callback_data="menu:admin"))
    return ScreenRender(text=text, reply_markup=builder.as_markup())
