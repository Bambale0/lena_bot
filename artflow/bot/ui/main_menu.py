from __future__ import annotations

from aiogram.types import InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.services.session_service import MainMenuContext
from bot.ui.common import ScreenRender
from bot.ui.model_labels import model_display_name
from core.config import settings


def _pretty_image_model(model_key: str) -> str:
    return model_display_name(model_key)


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
    return "1 фото" if value == 1 else f"{value} фото"


def _home_text(context: MainMenuContext, lang: str, *, show_session: bool) -> str:
    if lang == "en":
        base = (
            "✨ <b>APIX — your AI creative studio</b>\n\n"
            "Create images, animate photos, generate video with sound, make music and turn rough ideas into strong prompts.\n\n"
            "😊 <b>App</b> — the full visual workspace with models, references, feed and payments.\n"
            "✨ <b>Create</b> — a quick guided flow inside the bot.\n"
            "🤖 <b>AI Assistant</b> — describe the goal and let APIX help choose the path.\n\n"
            f"💋 Balance: <b>{context.balance} credits</b>. The exact price is shown before every launch."
        )
    else:
        base = (
            "✨ <b>APIX — твоя AI-студия</b>\n\n"
            "Создавай изображения, оживляй фото, генерируй видео со звуком, делай музыку и превращай сырые идеи в сильные промпты.\n\n"
            "😊 <b>Приложение</b> — полноценная визуальная студия с моделями, референсами, лентой и оплатой.\n"
            "✨ <b>Создать</b> — быстрый пошаговый запуск прямо в боте.\n"
            "🤖 <b>AI-ассистент</b> — опиши задачу обычными словами, и APIX поможет выбрать путь.\n\n"
            f"💋 На балансе: <b>{context.balance} кредитов</b>. Точную стоимость покажем до запуска."
        )

    if not show_session or not context.active_image_session:
        return base + ("\n\nВыбирай, с чего начнём 👇" if lang == "ru" else "\n\nChoose where to start 👇")

    session = context.active_image_session
    model = _pretty_image_model(session.model)
    ratio = _pretty_ratio(session.aspect_ratio, lang)
    quality = _pretty_quality(session.quality, lang)
    count = _pretty_count(session.count or 1, lang)
    active = (
        f"\n\n🔥 <b>У тебя есть активная серия</b>\n{model} · {ratio} · {quality} · {count}\n"
        "Продолжи её в том же стиле или начни новую работу."
        if lang == "ru"
        else f"\n\n🔥 <b>You have an active series</b>\n{model} · {ratio} · {quality} · {count}\nContinue it or start a new work."
    )
    return base + active


def render_main_menu(context: MainMenuContext, lang: str = "ru", *, force_main_text: bool = False) -> ScreenRender:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="😊 " + ("Приложение" if lang == "ru" else "App"),
            web_app=WebAppInfo(url=f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app"),
        )
    )

    if context.active_image_session:
        builder.row(
            InlineKeyboardButton(text="🔥 " + ("Продолжить" if lang == "ru" else "Continue"), callback_data="menu:image"),
            InlineKeyboardButton(text="🆕 " + ("Новая работа" if lang == "ru" else "New work"), callback_data="img_session:new"),
        )

    builder.row(
        InlineKeyboardButton(text="✨ " + ("Создать" if lang == "ru" else "Create"), callback_data="menu:create"),
        InlineKeyboardButton(text="🤖 " + ("AI-ассистент" if lang == "ru" else "AI Assistant"), callback_data="menu:assistant"),
    )
    builder.row(
        InlineKeyboardButton(text="📂 " + ("Мои работы" if lang == "ru" else "My work"), callback_data="menu:history"),
        InlineKeyboardButton(text="🔥 " + ("Лента идей" if lang == "ru" else "Ideas feed"), callback_data="menu:feed"),
    )
    builder.row(
        InlineKeyboardButton(text="👑 " + ("Тренды" if lang == "ru" else "Trends"), callback_data="menu:trends"),
    )
    builder.row(
        InlineKeyboardButton(text="💋 " + (f"Баланс · {context.balance}" if lang == "ru" else f"Balance · {context.balance}"), callback_data="menu:balance"),
        InlineKeyboardButton(text="☰ " + ("Ещё" if lang == "ru" else "More"), callback_data="menu:more"),
    )
    if context.is_admin:
        builder.row(
            InlineKeyboardButton(
                text="👑 " + ("Админ-панель" if lang == "ru" else "Admin panel"),
                callback_data="menu:admin",
            )
        )

    return ScreenRender(
        text=_home_text(context, lang, show_session=not force_main_text),
        reply_markup=builder.as_markup(),
    )
