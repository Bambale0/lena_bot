# bot/handlers/start.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy.ext.asyncio import AsyncSession

from bot.i18n import t
from bot.keyboards.main_menu import back_to_menu_kb
from bot.ui.router import render_screen
from bot.utils.deep_links import parse_start_payload
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
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


def _stars_help_text(lang: str) -> str:
    if not settings.TELEGRAM_STARS_ENABLED:
        if lang == "en":
            return (
                "⭐ <b>Telegram Stars</b>\n\n"
                "Stars top-up is not available yet. Please use T-Bank or CryptoBot for now."
            )
        return (
            "⭐ <b>Telegram Stars</b>\n\n"
            "Пополнение через Stars пока недоступно. Сейчас используй T-Bank или CryptoBot."
        )

    if lang == "en":
        return (
            "⭐ <b>Telegram Stars</b>\n\n"
            "Top up opens directly inside Telegram.\n"
            "Choose <b>Top up → Telegram Stars</b>, select a pack and confirm payment.\n\n"
            "If payment succeeds, credits arrive automatically."
        )
    return (
        "⭐ <b>Telegram Stars</b>\n\n"
        "Пополнение открывается прямо внутри Telegram.\n"
        "Выбери <b>Пополнение → Telegram Stars</b>, укажи пакет и подтверди оплату.\n\n"
        "Если платёж прошёл успешно, 💋 начислятся автоматически."
    )


def _help_text(lang: str) -> str:
    if lang == "en":
        return (
            "❓ <b>Help — How to use APIX</b>\n\n"
            "📱 <b>Open App</b> — the fastest way to work with references, feed and payments.\n"
            "In chat, you can also use the bot menus below.\n\n"
            "🎨 <b>Images</b>\n"
            "Choose a model → add a reference if needed → send a prompt → get the result.\n\n"
            "🎬 <b>Video</b>\n"
            "Choose a model → text or image mode → send a prompt → wait 1–5 min.\n\n"
            "🎵 <b>Music</b>\n"
            "Suno AI creates a track from your description. Cost: <b>20 💋</b>.\n\n"
            "🖌️ <b>Midjourney</b>\n"
            "Imagine, Blend, Describe, Action and Video are available from the menu.\n\n"
            "🤖 <b>AI Assistant</b>\n"
            "Use /assistant for prompt ideas, content planning and quick bot help.\n\n"
            "💳 <b>Top up</b>\n"
            + (
                "Available methods: Telegram Stars, T-Bank and CryptoBot.\n"
                "⭐ Stars open directly inside Telegram.\n\n"
                if settings.TELEGRAM_STARS_ENABLED
                else "Available methods: T-Bank and CryptoBot.\n\n"
            )
            "💡 <b>Prompt tips</b>\n"
            "Short, clear prompts usually work best. If a model supports extra options, the bot will show them in the flow.\n\n"
            "💬 <b>Support</b>\n"
            "Contact: @LeLu88\n\n"
            f"👥 <b>Referral program</b>\n"
            f"• Bonus per referral: +{settings.REFERRAL_L1_CREDITS} 💋\n"
            f"• Payment commissions: {int(settings.REFERRAL_COMMISSION_L1 * 100)}% / "
            f"{int(settings.REFERRAL_COMMISSION_L2 * 100)}% / "
            f"{int(settings.REFERRAL_COMMISSION_L3 * 100)}%"
        )
    return (
        "❓ <b>Помощь — как пользоваться APIX</b>\n\n"
        "📱 <b>Открыть приложение</b> — самый удобный способ работать с референсами, лентой и оплатой.\n"
        "Но и через меню в боте тоже можно всё основное.\n\n"
        "🎨 <b>Изображения</b>\n"
        "Выбери модель → при необходимости добавь референс → отправь промпт → получи результат.\n\n"
        "🎬 <b>Видео</b>\n"
        "Выбери модель → режим текст/изображение → отправь промпт → жди 1–5 минут.\n\n"
        "🎵 <b>Музыка</b>\n"
        "Suno AI делает трек по описанию. Стоимость: <b>20 💋</b>.\n\n"
        "🖌️ <b>Midjourney</b>\n"
        "В меню доступны Imagine, Blend, Describe, Action и Video.\n\n"
        "🤖 <b>AI-ассистент</b>\n"
        "Команда /assistant помогает с идеями, промптами и быстрыми вопросами по боту.\n\n"
        "💳 <b>Пополнение</b>\n"
        + (
            "Доступны Telegram Stars, T-Bank и CryptoBot.\n"
            "⭐ Stars открываются прямо внутри Telegram.\n\n"
            if settings.TELEGRAM_STARS_ENABLED
            else "Сейчас доступны T-Bank и CryptoBot.\n\n"
        )
        "💡 <b>Совет по промптам</b>\n"
        "Обычно лучше всего работают короткие и понятные промпты. Если у модели есть дополнительные настройки, бот сам покажет их по ходу выбора.\n\n"
        "💬 <b>Поддержка</b>\n"
        "Саппорт: @LeLu88\n\n"
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
    start_payload = parse_start_payload(parts[1] if len(parts) == 2 else None)
    if start_payload.target_kind == "feed" and start_payload.target_id is not None:
        from bot.handlers.feed import show_feed_card_by_id
        await show_feed_card_by_id(message=message, session=session, gen_id=start_payload.target_id)
        return
    if start_payload.target_kind == "prompt" and start_payload.target_id is not None:
        from bot.handlers.marketplace import show_prompt_card_by_id
        await show_prompt_card_by_id(message=message, session=session, prompt_id=start_payload.target_id)
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


@router.message(Command("starshelp"))
async def cmd_stars_help(message: Message, db_user: User) -> None:
    lang = db_user.language or "ru"
    await message.answer(_stars_help_text(lang), reply_markup=back_to_menu_kb())


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(
    call: CallbackQuery,
    db_user: User,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.clear()
    screen = await render_screen(
        screen="main",
        session=session,
        db_user=db_user,
        extra={"force_main_text": True},
    )
    message = call.message
    if message is not None and any((
        getattr(message, "photo", None),
        getattr(message, "video", None),
        getattr(message, "animation", None),
        getattr(message, "document", None),
        getattr(message, "sticker", None),
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
