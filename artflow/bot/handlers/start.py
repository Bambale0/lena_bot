# bot/handlers/start.py
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from core.config import settings
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="start")

WELCOME_TEXT = (
    "👋 Добро пожаловать в <b>ArtFlow AI</b>!\n\n"
    "Генерируй изображения и видео с помощью лучших AI-моделей.\n\n"
    "🎁 На твой счёт зачислено <b>{credits} стартовых кредитов</b>!\n\n"
    "Выбери действие:"
)

HELP_TEXT = (
    "❓ <b>Помощь</b>\n\n"
    "🎨 <b>Изображение</b> — генерация фото по промпту\n"
    "🎬 <b>Видео</b> — генерация видео (text/image to video)\n"
    "💎 <b>Баланс</b> — текущий баланс кредитов\n"
    "💳 <b>Пополнить</b> — покупка кредитов\n"
    "👥 <b>Рефералы</b> — пригласи друзей и получай бонусы\n\n"
    "📌 <b>Стоимость генерации:</b>\n"
    "• Изображение: 2–4 кредита\n"
    "• Видео: 30–40 кредитов\n\n"
    f"🎁 Реферальная программа:\n"
    f"• L1 (прямой): +{settings.REFERRAL_L1_CREDITS} кр\n"
    f"• L2 (реферал реферала): +{settings.REFERRAL_L2_CREDITS} кр"
)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        WELCOME_TEXT.format(credits=db_user.credits),
        reply_markup=main_menu_kb(),
    )


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(call: CallbackQuery, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(  # type: ignore[union-attr]
        WELCOME_TEXT.format(credits=db_user.credits),
        reply_markup=main_menu_kb(),
    )
    await call.answer()


@router.callback_query(F.data == "menu:help")
async def cb_help(call: CallbackQuery) -> None:
    await call.message.edit_text(HELP_TEXT, reply_markup=back_to_menu_kb())  # type: ignore[union-attr]
    await call.answer()
