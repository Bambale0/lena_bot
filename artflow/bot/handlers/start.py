# bot/handlers/start.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_to_menu_kb
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="start")

WELCOME_TEXT = (
    "👋 Добро пожаловать в <b>APIX</b>!\n\n"
    "Твой арсенал AI-генерации:\n"
    "🎨 <b>Изображения</b> — Gemini, WAN, GPT Image, Seedream\n"
    "🎬 <b>Видео</b> — Kling, Veo, Grok, Seedance и другие\n"
    "🖌️ <b>Midjourney</b> — Imagine, Blend, Describe, Video\n\n"
    "🎁 На твой счёт зачислено <b>{credits} 💋</b>!\n\n"
    "Выбери, что хочешь создать:"
)

HELP_TEXT = (
    "❓ <b>Помощь — как пользоваться APIX</b>\n\n"
    "🎨 <b>Изображение</b>\n"
    "Выбери модель → добавь референс (опционально) → введи промпт → получи результат.\n"
    "Пиши промпты на <b>английском</b> — так лучше работают все модели.\n\n"
    "🎬 <b>Видео</b>\n"
    "Выбери модель → реж (текст или с изображением) → промпт → жди 1–5 мин.\n\n"
    "🖌️ <b>Midjourney</b>\n"
    "• <b>Imagine</b> — генерация 4 вариантов изображения\n"
    "• <b>Blend</b> — смешивание 2–5 фотографий\n"
    "• <b>Describe</b> — получить промпт по фото\n"
    "• <b>Video</b> — оживить изображение\n\n"
    "💡 <b>Советы по промптам:</b>\n"
    "• Добавляй стиль: <i>cinematic, anime, oil painting</i>\n"
    "• Указывай освещение: <i>golden hour, neon glow, studio light</i>\n"
    "• Упоминай качество: <i>8k, sharp focus, highly detailed</i>\n\n"
    "📌 <b>Стоимость:</b>\n"
    "• Изображение: 2–10 💋\n"
    "• Видео: 20–50 💋\n"
    "• Midjourney: 5–15 💋\n\n"
    f"👥 <b>Реферальная программа:</b>\n"
    f"• Прямой реферал: +{settings.REFERRAL_L1_CREDITS} 💋\n"
    f"• Реферал реферала: +{settings.REFERRAL_L2_CREDITS} 💋"
)

@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
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
    await message.answer(
        screen.text,
        reply_markup=screen.reply_markup,
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(
    call: CallbackQuery,
    db_user: User,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        screen.text,
        reply_markup=screen.reply_markup,
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:help")
async def cb_help(call: CallbackQuery) -> None:
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        HELP_TEXT,
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery) -> None:
    await safe_answer_callback(call)
