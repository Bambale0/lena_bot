# bot/handlers/start.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from bot.ui.router import render_screen
from bot.utils.deep_links import parse_start_payload
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db import repository as repo
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="start")


def _welcome_text(lang: str) -> str:
    return (
        t("welcome", lang, name="{name}") + "\n\n"
        "🎨 <b>" + ("Изображения" if lang == "ru" else "Images") + "</b> — Nano Banana, WAN, GPT Image, Seedream, Qwen\n"
        "🎬 <b>" + ("Видео" if lang == "ru" else "Video") + "</b> — Kling, Veo, Grok, Seedance\n"
        "🖌️ <b>Midjourney</b> — Imagine, Blend, Describe, Action, Video\n"
        "🤖 <b>AI-ассистент</b> — идеи, промпты, помощь по боту\n\n"
        + t("balance_credits", lang, credits="{credits}")
        .replace("Kisses", "💋")
        .replace("Поцелуи", "💋")
        + "\n\n"
        + ("Выбери, что хочешь создать:" if lang == "ru" else "Choose what to create:")
    )


def _onboarding_text(db_user: User, lang: str) -> str:
    name = (db_user.full_name or db_user.username or "").strip()
    greeting = (f"Привет, {name}!" if name else "Привет!") if lang == "ru" else (f"Hi, {name}!" if name else "Hi!")
    if lang == "en":
        return (
            f"👋 <b>{greeting}</b>\n\n"
            "APIX creates images, videos and music, edits references and helps prepare prompts.\n\n"
            "<b>How to start:</b>\n"
            "1. Choose what you want to create.\n"
            "2. Describe the result in plain language.\n"
            "3. Review the price and launch generation.\n\n"
            f"Your balance: <b>{db_user.credits} credits</b>. The price is always shown before launch.\n\n"
            "Choose your first goal:"
        )
    return (
        f"👋 <b>{greeting}</b>\n\n"
        "APIX создаёт изображения, видео и музыку, редактирует референсы и помогает составлять промпты.\n\n"
        "<b>Как начать:</b>\n"
        "1. Выбери, что хочешь получить.\n"
        "2. Опиши результат обычными словами.\n"
        "3. Проверь стоимость и запусти генерацию.\n\n"
        f"На балансе: <b>{db_user.credits} кредитов</b>. Стоимость всегда показывается до запуска.\n\n"
        "Выбери первую задачу:"
    )


def onboarding_kb(lang: str = "ru"):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎨 " + ("Создать изображение" if lang == "ru" else "Create image"), callback_data="menu:image"),
        InlineKeyboardButton(text="🎬 " + ("Создать видео" if lang == "ru" else "Create video"), callback_data="menu:video"),
    )
    builder.row(
        InlineKeyboardButton(text="🎵 " + ("Создать музыку" if lang == "ru" else "Create music"), callback_data="menu:music"),
        InlineKeyboardButton(text="🤖 " + ("Спросить AI" if lang == "ru" else "Ask AI"), callback_data="menu:assistant"),
    )
    builder.row(
        InlineKeyboardButton(
            text="📱 " + ("Открыть приложение" if lang == "ru" else "Open App"),
            web_app=WebAppInfo(url=f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app"),
        )
    )
    builder.row(
        InlineKeyboardButton(text="Пропустить →" if lang == "ru" else "Skip →", callback_data="onboarding:skip")
    )
    return builder.as_markup()


def _stars_help_text(lang: str) -> str:
    if not settings.TELEGRAM_STARS_ENABLED:
        if lang == "en":
            return "⭐ <b>Telegram Stars</b>\n\nStars top-up is not available yet. Please use T-Bank or CryptoBot for now."
        return "⭐ <b>Telegram Stars</b>\n\nПополнение через Stars пока недоступно. Сейчас используй T-Bank или CryptoBot."
    if lang == "en":
        return (
            "⭐ <b>Telegram Stars</b>\n\nTop up opens directly inside Telegram.\n"
            "Choose <b>Top up → Telegram Stars</b>, select a pack and confirm payment.\n\n"
            "If payment succeeds, credits arrive automatically."
        )
    return (
        "⭐ <b>Telegram Stars</b>\n\nПополнение открывается прямо внутри Telegram.\n"
        "Выбери <b>Пополнение → Telegram Stars</b>, укажи пакет и подтверди оплату.\n\n"
        "Если платёж прошёл успешно, 💋 начислятся автоматически."
    )


def _help_text(lang: str) -> str:
    if lang == "en":
        return (
            "❓ <b>Help — How to use APIX</b>\n\n"
            "📱 <b>Open App</b> — the fastest way to work with references, feed and payments.\n"
            "In chat, choose the result you want; APIX selects the correct internal route automatically.\n\n"
            "🎨 <b>Images</b>\nChoose a task and a model family. Send text to create from scratch or attach an image to edit it. You do not need to choose a separate Edit model.\n\n"
            "🎬 <b>Video</b>\nChoose a task, add source media if needed, review settings and price, then launch.\n\n"
            "🎵 <b>Music</b>\nSuno creates a track from your description. Cost depends on the active model.\n\n"
            "🤖 <b>AI Assistant</b>\nUse /assistant for prompt ideas, content planning and quick bot help.\n\n"
            "💬 <b>Support</b>\nSupport: @LeLu88\n"
            "🧑‍💻 <b>Developer</b>\nTechnical questions and development: @chillcreative"
        )
    return (
        "❓ <b>Помощь — как пользоваться APIX</b>\n\n"
        "📱 <b>Открыть приложение</b> — самый удобный способ работать с референсами, лентой и оплатой.\n"
        "В боте сначала выбирай результат, а внутренний режим APIX определит сам.\n\n"
        "🎨 <b>Изображения</b>\nВыбери задачу и семейство модели. Отправь текст для создания с нуля или приложи фото для редактирования. Отдельную модель Edit выбирать не нужно.\n\n"
        "🎬 <b>Видео</b>\nВыбери задачу, добавь исходные материалы при необходимости, проверь параметры и стоимость, затем запусти генерацию.\n\n"
        "🎵 <b>Музыка</b>\nSuno делает трек по описанию. Стоимость зависит от активной модели.\n\n"
        "🤖 <b>AI-ассистент</b>\nКоманда /assistant помогает с идеями, промптами и вопросами по боту.\n\n"
        "💬 <b>Поддержка</b>\nСаппорт: @LeLu88\n"
        "🧑‍💻 <b>Разработчик</b>\nТехнические вопросы и разработка: @chillcreative"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    parts = (message.text or "").split(maxsplit=1)
    start_payload = parse_start_payload(parts[1] if len(parts) == 2 else None)
    if start_payload.target_kind == "feed" and start_payload.target_id is not None:
        from bot.handlers.feed import show_feed_card_by_id
        await show_feed_card_by_id(message=message, session=session, gen_id=start_payload.target_id)
        return
    if start_payload.target_kind == "prompt" and start_payload.target_id is not None:
        from bot.handlers.marketplace import show_prompt_card_by_id
        await show_prompt_card_by_id(message=message, session=session, prompt_id=start_payload.target_id)
        return

    history = await repo.get_user_history(session, db_user.id, limit=1)
    if not history:
        lang = db_user.language or "ru"
        await message.answer(_onboarding_text(db_user, lang), reply_markup=onboarding_kb(lang))
        return

    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await message.answer(screen.text, reply_markup=screen.reply_markup)


@router.callback_query(F.data == "onboarding:skip")
async def cb_onboarding_skip(call: CallbackQuery, db_user: User, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user, extra={"force_main_text": True})
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: User, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await message.answer(screen.text, reply_markup=screen.reply_markup)


@router.message(Command("help"))
async def cmd_help(message: Message, db_user: User) -> None:
    lang = db_user.language or "ru"
    await message.answer(_help_text(lang), reply_markup=back_to_menu_kb())


@router.message(Command("starshelp"))
async def cmd_stars_help(message: Message, db_user: User) -> None:
    lang = db_user.language or "ru"
    await message.answer(_stars_help_text(lang), reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(call: CallbackQuery, db_user: User, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user, extra={"force_main_text": True})
    message = call.message
    if message is not None and any((
        getattr(message, "photo", None), getattr(message, "video", None), getattr(message, "animation", None),
        getattr(message, "document", None), getattr(message, "sticker", None),
    )):
        await message.answer(screen.text, reply_markup=screen.reply_markup)
    else:
        try:
            await safe_edit_message(message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]
        except TelegramBadRequest:
            await message.answer(screen.text, reply_markup=screen.reply_markup)  # type: ignore[union-attr]
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:help")
async def cb_help(call: CallbackQuery, db_user: User) -> None:
    lang = db_user.language or "ru"
    await safe_edit_message(call.message, _help_text(lang), reply_markup=back_to_menu_kb())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await safe_answer_callback(call)
