from __future__ import annotations

from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import t
from bot.services.session_service import MainMenuContext
from bot.ui.common import ScreenRender
from core.config import settings


def render_main_menu(context: MainMenuContext, lang: str = "ru") -> ScreenRender:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📱 " + ("Открыть приложение" if lang == "ru" else "Open App"),
            web_app=WebAppInfo(url=f"{settings.WEBHOOK_URL.rstrip('/')}/app"),
        ),
    )

    builder.row(
        InlineKeyboardButton(text=f"{t('balance_credits', lang, credits=context.balance)}", callback_data="menu:balance"),
    )

    if context.active_image_session:
        session = context.active_image_session
        quality = session.quality or "basic"
        ratio = session.aspect_ratio or "default"
        count = session.count or 1

        builder.row(
            InlineKeyboardButton(
                text="🔥 " + ("Продолжить серию" if lang == "ru" else "Continue series"),
                callback_data="menu:image",
            ),
            InlineKeyboardButton(
                text="🆕 " + ("Новая серия" if lang == "ru" else "New series"),
                callback_data="img_session:new",
            ),
        )

        text = t("main_menu_with_session", lang,
                 model=session.model, ratio=ratio, quality=quality, count=count)
    else:
        text = t("main_menu", lang)

    # Creation
    builder.row(
        InlineKeyboardButton(text="🎨 " + ("Фото" if lang == "ru" else "Photo"), callback_data="menu:image"),
        InlineKeyboardButton(text="🎬 " + ("Видео" if lang == "ru" else "Video"), callback_data="menu:video"),
    )
    builder.row(
        InlineKeyboardButton(text="🎵 " + ("Песня" if lang == "ru" else "Song"), callback_data="menu:music"),
    )

    # Content
    builder.row(
        InlineKeyboardButton(text="🔥 " + ("Лента" if lang == "ru" else "Feed"), callback_data="menu:feed"),
        InlineKeyboardButton(text="📚 " + ("Библиотека" if lang == "ru" else "Library"), callback_data="menu:prompts"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 " + ("История" if lang == "ru" else "History"), callback_data="menu:history"),
    )

    # Account
    builder.row(
        InlineKeyboardButton(text="👥 " + ("Рефералы" if lang == "ru" else "Referrals"), callback_data="menu:referral"),
        InlineKeyboardButton(text="❓ " + ("Помощь" if lang == "ru" else "Help"), callback_data="menu:help"),
    )
    builder.row(
        InlineKeyboardButton(text="💳 " + ("Пополнить" if lang == "ru" else "Top up"), callback_data="menu:topup"),
    )

    if context.is_admin:
        builder.row(
            InlineKeyboardButton(text="👑 " + ("Админ" if lang == "ru" else "Admin"), callback_data="menu:admin"),
        )

    # Settings / Language
    builder.row(
        InlineKeyboardButton(text="⚙️ " + ("Настройки" if lang == "ru" else "Settings"), callback_data="menu:settings"),
    )

    return ScreenRender(text=text, reply_markup=builder.as_markup())
