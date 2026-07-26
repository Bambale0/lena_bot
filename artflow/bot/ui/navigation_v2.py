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
        InlineKeyboardButton(text="🤖 " + ("Подобрать через AI" if lang == "ru" else "Choose with AI"), callback_data="menu:assistant"),
    )
    if is_admin:
        builder.row(InlineKeyboardButton(text="🖌️ Midjourney", callback_data="menu:mj"))
    builder.row(InlineKeyboardButton(text="🏠 " + ("На главную" if lang == "ru" else "Home"), callback_data="menu:main"))

    if lang == "ru":
        text = (
            "✨ <b>Что будем создавать?</b>\n\n"
            "Выбери не нейросеть, а нужный результат — подходящие модели и параметры появятся дальше.\n\n"
            "🖼 <b>Изображение</b>\n"
            "С нуля по описанию, редактирование фото, замена деталей, стили, карточки товаров и работа с несколькими референсами.\n\n"
            "🎬 <b>Видео</b>\n"
            "Текст в видео, оживление фото, видео по референсам, движение камеры, персонажи и генерация со звуком.\n\n"
            "🎵 <b>Музыка</b>\n"
            "Полноценный трек, инструментал или песня по идее, настроению и жанру.\n\n"
            "🤖 <b>Подобрать через AI</b>\n"
            "Подойдёт, если пока есть только задумка. Ассистент поможет сформулировать запрос и выбрать сценарий.\n\n"
            "Стоимость и итоговые параметры будут показаны до запуска."
        )
    else:
        text = (
            "✨ <b>What do you want to create?</b>\n\n"
            "Choose the result, not the model. APIX will show compatible tools and settings next.\n\n"
            "🖼 <b>Image</b> — generate, edit, restyle and work with references.\n"
            "🎬 <b>Video</b> — text-to-video, animate photos, control motion and create with sound.\n"
            "🎵 <b>Music</b> — make a complete track from an idea, mood or genre.\n"
            "🤖 <b>Choose with AI</b> — turn a rough idea into the right workflow.\n\n"
            "Price and final settings are always shown before launch."
        )
    return ScreenRender(text=text, reply_markup=builder.as_markup())


def render_more_hub(lang: str = "ru", *, is_admin: bool = False) -> ScreenRender:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📚 " + ("Библиотека промптов" if lang == "ru" else "Prompt library"), callback_data="menu:prompts"),
        InlineKeyboardButton(text="👥 " + ("Партнёрка" if lang == "ru" else "Partners"), callback_data="menu:referral"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ " + ("Настройки" if lang == "ru" else "Settings"), callback_data="menu:settings"),
        InlineKeyboardButton(text="❓ " + ("Как пользоваться" if lang == "ru" else "How it works"), callback_data="menu:help"),
    )
    builder.row(
        InlineKeyboardButton(
            text="📱 " + ("Открыть Mini App" if lang == "ru" else "Open Mini App"),
            web_app=WebAppInfo(url=f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app"),
        )
    )
    builder.row(InlineKeyboardButton(text="🧑‍💻 @chillcreative", url="https://t.me/chillcreative"))
    if is_admin:
        builder.row(InlineKeyboardButton(text="👑 " + ("Админ-панель" if lang == "ru" else "Admin panel"), callback_data="menu:admin"))
    builder.row(InlineKeyboardButton(text="🏠 " + ("На главную" if lang == "ru" else "Home"), callback_data="menu:main"))

    if lang == "ru":
        text = (
            "☰ <b>Инструменты и возможности APIX</b>\n\n"
            "📚 <b>Библиотека промптов</b>\n"
            "Готовые идеи и рабочие шаблоны. Можно взять основу и сразу запустить свою генерацию.\n\n"
            "👥 <b>Партнёрская программа</b>\n"
            "Приглашай пользователей, получай бонусы и комиссию с пополнений.\n\n"
            "⚙️ <b>Настройки</b>\n"
            "Язык интерфейса и персональные параметры.\n\n"
            "❓ <b>Как пользоваться</b>\n"
            "Короткая инструкция по изображениям, видео, музыке, оплате и работе с AI.\n\n"
            "🧑‍💻 <b>Разработчик</b>\n"
            "Технические вопросы, интеграции и доработка проекта: @chillcreative\n\n"
            "Mini App также доступен прямо отсюда — там удобнее работать с большим количеством моделей и референсов."
        )
    else:
        text = (
            "☰ <b>APIX tools and features</b>\n\n"
            "📚 <b>Prompt library</b> — ready ideas and reusable templates.\n"
            "👥 <b>Partner program</b> — invite users and earn rewards.\n"
            "⚙️ <b>Settings</b> — language and personal options.\n"
            "❓ <b>How it works</b> — a quick guide to creation, payments and AI.\n"
            "🧑‍💻 <b>Developer</b> — technical questions and integrations: @chillcreative.\n\n"
            "Open the Mini App here when you need the full visual workspace."
        )
    return ScreenRender(text=text, reply_markup=builder.as_markup())
