# bot/handlers/start.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="start")


def _welcome_text(lang: str) -> str:
    return (
        t("welcome", lang, name="{name}") + "\n\n"
        "🎨 <b>" + ("Изображения" if lang == "ru" else "Images") + "</b> — Gemini, WAN, GPT Image, Seedream\n"
        "🎬 <b>" + ("Видео" if lang == "ru" else "Video") + "</b> — Kling, Veo, Grok, Seedance\n"
        "🖌️ <b>Midjourney</b> — Imagine, Blend, Describe, Video\n"
        "🤖 <b>AI-ассистент</b> — идеи, промпты, помощь по боту\n\n"
        + t("balance_credits", lang, credits="{credits}")
        .replace("Kisses", "cr")
        .replace("Поцелуи", "cr")
        + "\n\n"
        + ("Выбери, что хочешь создать:" if lang == "ru" else "Choose what to create:")
    )


def _help_text(lang: str) -> str:
    if lang == "en":
        return (
            "❓ <b>Help — How to use APIX</b>\n\n"
            "📱 <b>Open App</b> — the fastest way to work with references, feed, themes and payments.\n"
            "In chat, you can also use the bot menus below.\n\n"
            "🎨 <b>Images</b>\n"
            "Choose a model → add a reference if needed → send a prompt → get the result.\n\n"
            "🎬 <b>Video</b>\n"
            "Choose a model → text or image mode → send a prompt → wait 1–5 min.\n\n"
            "🎵 <b>Music</b>\n"
            "Suno AI creates a track from your description. Cost: <b>20 💋</b>.\n\n"
            "🖌️ <b>Midjourney</b>\n"
            "Imagine, Blend, Describe and Video are available from the menu.\n\n"
            "🤖 <b>AI Assistant</b>\n"
            "Use /assistant for prompt ideas, content planning and quick bot help.\n\n"
            "💳 <b>Top up</b>\n"
            "Available methods: Telegram Stars, T-Bank and CryptoBot.\n\n"
            "💡 <b>Prompt tips</b>\n"
            "Best results usually come from English prompts with style, lighting and composition details.\n\n"
            f"👥 <b>Referral program</b>\n"
            f"• Bonus per referral: +{settings.REFERRAL_L1_CREDITS} 💋\n"
            f"• Payment commissions: {int(settings.REFERRAL_COMMISSION_L1 * 100)}% / "
            f"{int(settings.REFERRAL_COMMISSION_L2 * 100)}% / "
            f"{int(settings.REFERRAL_COMMISSION_L3 * 100)}%"
        )
    return (
        "❓ <b>Помощь — как пользоваться APIX</b>\n\n"
        "📱 <b>Открыть приложение</b> — самый удобный способ работать с референсами, лентой, темами и оплатой.\n"
        "Но и через меню в боте тоже можно всё основное.\n\n"
        "🎨 <b>Изображения</b>\n"
        "Выбери модель → при необходимости добавь референс → отправь промпт → получи результат.\n\n"
        "🎬 <b>Видео</b>\n"
        "Выбери модель → режим текст/изображение → отправь промпт → жди 1–5 минут.\n\n"
        "🎵 <b>Музыка</b>\n"
        "Suno AI делает трек по описанию. Стоимость: <b>20 💋</b>.\n\n"
        "🖌️ <b>Midjourney</b>\n"
        "В меню доступны Imagine, Blend, Describe и Video.\n\n"
        "🤖 <b>AI-ассистент</b>\n"
        "Команда /assistant помогает с идеями, промптами и быстрыми вопросами по боту.\n\n"
        "💳 <b>Пополнение</b>\n"
        "Доступны Telegram Stars, T-Bank и CryptoBot.\n\n"
        "💡 <b>Совет по промптам</b>\n"
        "Обычно лучший результат дают промпты на английском с указанием стиля, света и композиции.\n\n"
        f"👥 <b>Реферальная программа</b>\n"
        f"• Бонус за реферала: +{settings.REFERRAL_L1_CREDITS} 💋\n"
        f"• Комиссия с оплат: {int(settings.REFERRAL_COMMISSION_L1 * 100)}% / "
        f"{int(settings.REFERRAL_COMMISSION_L2 * 100)}% / "
        f"{int(settings.REFERRAL_COMMISSION_L3 * 100)}%"
    )


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    lang = db_user.language or "ru"
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("feed_"):
        gen_id_raw = parts[1].split("_", 1)[1]
        if gen_id_raw.isdigit():
            from bot.handlers.feed import show_feed_card_by_id
            await show_feed_card_by_id(message=message, session=session, gen_id=int(gen_id_raw))
            return
    if len(parts) == 2 and parts[1].startswith("prompt_"):
        prompt_id_raw = parts[1].split("_", 1)[1]
        if prompt_id_raw.isdigit():
            from bot.handlers.marketplace import show_prompt_card_by_id
            await show_prompt_card_by_id(message=message, session=session, prompt_id=int(prompt_id_raw))
            return
    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await message.answer(screen.text, reply_markup=screen.reply_markup)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: User, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await message.answer(screen.text, reply_markup=screen.reply_markup)


@router.message(Command("help"))
async def cmd_help(message: Message, db_user: User) -> None:
    lang = db_user.language or "ru"
    await message.answer(_help_text(lang), reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(
    call: CallbackQuery,
    db_user: User,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:help")
async def cb_help(call: CallbackQuery, db_user: User) -> None:
    lang = db_user.language or "ru"
    await safe_edit_message(call.message, _help_text(lang), reply_markup=back_to_menu_kb())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await safe_answer_callback(call)
