# bot/handlers/start.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
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
        "🖌️ <b>Midjourney</b> — Imagine, Blend, Describe, Video\n\n"
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
            "🎨 <b>Images</b>\n"
            "Pick a model → add reference (optional) → enter prompt → get result.\n"
            "Write prompts in <b>English</b> for best results.\n\n"
            "🎬 <b>Video</b>\n"
            "Pick a model → mode (text or image) → prompt → wait 1–5 min.\n\n"
            "🖌️ <b>Midjourney</b>\n"
            "• <b>Imagine</b> — generate 4 image variations\n"
            "• <b>Blend</b> — mix 2–5 photos\n"
            "• <b>Describe</b> — get prompt from photo\n"
            "• <b>Video</b> — animate image\n\n"
            "💡 <b>Prompt tips:</b>\n"
            "• Add style: <i>cinematic, anime, oil painting</i>\n"
            "• Mention lighting: <i>golden hour, neon glow, studio light</i>\n"
            "• Mention quality: <i>8k, sharp focus, highly detailed</i>\n\n"
            "📌 <b>Cost:</b>\n"
            "• Image: 1–12 cr\n"
            "• Video: 3–70 cr\n"
            "• Midjourney: 3–15 cr\n\n"
            f"👥 <b>Referral program:</b>\n"
            f"• Bonus per referral: +{settings.REFERRAL_L1_CREDITS} cr\n"
            f"• Commission: {int(settings.REFERRAL_COMMISSION_L1 * 100)}% / "
            f"{int(settings.REFERRAL_COMMISSION_L2 * 100)}% / "
            f"{int(settings.REFERRAL_COMMISSION_L3 * 100)}%"
        )
    return (
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
        "• Изображение: 1–12 cr\n"
        "• Видео: 3–70 cr\n"
        "• Midjourney: 3–15 cr\n\n"
        f"👥 <b>Реферальная программа:</b>\n"
        f"• Бонус за реферала: +{settings.REFERRAL_L1_CREDITS} cr\n"
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
