from __future__ import annotations

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.i18n import t
from bot.services.session_service import MainMenuContext
from bot.ui.common import ScreenRender

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
    return _IMAGE_MODEL_LABELS.get(model_key, model_key.replace("-", " ").replace("/", " · ").title())


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

    if context.active_image_session:
        session = context.active_image_session
        quality = _pretty_quality(session.quality, lang)
        ratio = _pretty_ratio(session.aspect_ratio, lang)
        count = session.count or 1
        builder.row(
            InlineKeyboardButton(
                text="🔥 " + ("Продолжить работу" if lang == "ru" else "Continue work"),
                callback_data="menu:image",
            ),
            InlineKeyboardButton(
                text="🆕 " + ("Новая работа" if lang == "ru" else "New work"),
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

    builder.row(
        InlineKeyboardButton(text="✨ " + ("Создать" if lang == "ru" else "Create"), callback_data="menu:create"),
        InlineKeyboardButton(text="🤖 " + ("AI-ассистент" if lang == "ru" else "AI Assistant"), callback_data="menu:assistant"),
    )
    builder.row(
        InlineKeyboardButton(text="📂 " + ("Мои работы" if lang == "ru" else "My work"), callback_data="menu:history"),
        InlineKeyboardButton(text="🔥 " + ("Лента" if lang == "ru" else "Feed"), callback_data="menu:feed"),
    )
    builder.row(
        InlineKeyboardButton(
            text="💎 " + (f"Баланс · {context.balance}" if lang == "ru" else f"Balance · {context.balance}"),
            callback_data="menu:balance",
        ),
        InlineKeyboardButton(text="☰ " + ("Ещё" if lang == "ru" else "More"), callback_data="menu:more"),
    )

    return ScreenRender(text=text, reply_markup=builder.as_markup())
