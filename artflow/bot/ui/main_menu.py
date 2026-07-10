from __future__ import annotations

from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import t
from bot.services.session_service import MainMenuContext
from bot.ui.common import ScreenRender
from core.config import settings

_IMAGE_MODEL_LABELS = {
    "grok-imagine/text-to-image": "Grok Imagine",
    "grok-imagine/image-to-image": "Grok Imagine Edit",
    "qwen/text-to-image": "Qwen",
    "qwen/image-to-image": "Qwen Edit",
    "qwen/image-edit": "Qwen Edit Pro",
    "qwen2/text-to-image": "Qwen2",
    "qwen2/image-edit": "Qwen2 Edit",
    "seedream/5-pro-text-to-image": "Seedream 5.0 Pro",
    "seedream/5-pro-image-to-image": "Seedream 5.0 Pro Edit",
    "seedream/4.5-text-to-image": "Seedream 4.5",
    "seedream/4.5-edit": "Seedream 4.5 Edit",
    "wan/2-7-image": "WAN 2.7",
    "wan/2-7-image-pro": "WAN 2.7 Pro",
    "gpt-image-2-text-to-image": "GPT Image 2",
    "gpt-image-2-image-to-image": "GPT Image 2 Edit",
    "google/nano-banana": "Nano Banana",
    "nano-banana-pro": "Nano Banana Pro",
    "nano-banana-2": "Nano Banana 2",
}


def _pretty_image_model(model_key: str) -> str:
    return _IMAGE_MODEL_LABELS.get(model_key, model_key.replace('-', ' ').replace('/', ' · ').title())


def _pretty_ratio(value: str | None, lang: str) -> str:
    if not value or value in {"default", "auto"}:
        return "Авто" if lang == "ru" else "Auto"
    return value


def _pretty_quality(value: str | None, lang: str) -> str:
    if not value or value == "basic":
        return "Стандарт" if lang == "ru" else "Standard"
    if value == "high":
        return "Высокое" if lang == "ru" else "High"
    return value.upper() if value.lower() in {"1k", "2k", "4k"} else value


def _pretty_count(value: int, lang: str) -> str:
    if lang != "ru":
        return "1 image" if value == 1 else f"{value} images"
    if value == 1:
        return "1 фото"
    return f"{value} фото"


def render_main_menu(context: MainMenuContext, lang: str = "ru", *, force_main_text: bool = False) -> ScreenRender:
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(
            text="📱 " + ("Открыть приложение" if lang == "ru" else "Open App"),
            web_app=WebAppInfo(url=f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app?v=1778285569"),
        ),
    )

    builder.row(
        InlineKeyboardButton(text=f"{t('balance_credits', lang, credits=context.balance)}", callback_data="menu:balance"),
    )

    if context.active_image_session:
        session = context.active_image_session
        quality = _pretty_quality(session.quality, lang)
        ratio = _pretty_ratio(session.aspect_ratio, lang)
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

        if force_main_text:
            text = t("main_menu", lang)
        else:
            text = t(
                "main_menu_with_session",
                lang,
                model=_pretty_image_model(session.model),
                ratio=ratio,
                quality=quality,
                count=_pretty_count(count, lang),
            )
    else:
        text = t("main_menu", lang)

    # Creation
    builder.row(
        InlineKeyboardButton(text="🎨 " + ("Фото" if lang == "ru" else "Photo"), callback_data="menu:image"),
        InlineKeyboardButton(text="🎬 " + ("Видео" if lang == "ru" else "Video"), callback_data="menu:video"),
    )
    if context.is_admin:
        builder.row(
            InlineKeyboardButton(text="🎵 " + ("Песня" if lang == "ru" else "Song"), callback_data="menu:music"),
            InlineKeyboardButton(text="🖌️ Midjourney", callback_data="menu:mj"),
        )
    else:
        builder.row(
            InlineKeyboardButton(text="🎵 " + ("Песня" if lang == "ru" else "Song"), callback_data="menu:music"),
        )
    builder.row(
        InlineKeyboardButton(text="🤖 " + ("AI-ассистент" if lang == "ru" else "AI Assistant"), callback_data="menu:assistant"),
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
