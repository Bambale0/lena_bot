from __future__ import annotations

import html
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant_service import generate_assistant_reply
from bot.states import AssistantFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="assistant")


def assistant_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🧹 Очистить диалог", callback_data="assistant:clear")
    builder.button(text="🏠 Меню", callback_data="assistant:exit")
    builder.adjust(2)
    return builder.as_markup()


def _intro_text() -> str:
    return (
        "🤖 <b>AI-ассистент</b>\n\n"
        "Можешь писать сюда вопросы по боту, промптам, идеям для контента, сценариям генерации, референсам, оплатам и вообще любые рабочие вопросы.\n\n"
        "Я держу короткий контекст диалога и отвечаю прямо в чате."
    )


@router.message(Command("assistant"))
async def cmd_assistant(message: Message, state: FSMContext) -> None:
    await state.set_state(AssistantFSM.waiting_message)
    await state.update_data(assistant_history=[])
    await message.answer(_intro_text(), reply_markup=assistant_kb())


@router.callback_query(F.data == "menu:assistant")
async def cb_assistant(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AssistantFSM.waiting_message)
    await state.update_data(assistant_history=[])
    await safe_edit_message(call.message, _intro_text(), reply_markup=assistant_kb())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "assistant:clear")
async def cb_assistant_clear(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AssistantFSM.waiting_message)
    await state.update_data(assistant_history=[])
    await safe_edit_message(
        call.message,
        "🧹 <b>Диалог очищен.</b>\n\nНапиши новый вопрос.",
        reply_markup=assistant_kb(),
    )  # type: ignore[arg-type]
    await safe_answer_callback(call, "Контекст очищен")


@router.callback_query(F.data == "assistant:exit")
async def cb_assistant_exit(call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(AssistantFSM.waiting_message, F.text)
async def handle_assistant_message(message: Message, state: FSMContext) -> None:
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("Напиши вопрос текстом 🙂", reply_markup=assistant_kb())
        return

    data = await state.get_data()
    history = list(data.get("assistant_history") or [])
    history.append({"role": "user", "content": user_text})

    wait = await message.answer("🤔 Думаю...")
    try:
        reply = await generate_assistant_reply(history)
    except Exception as exc:
        logger.exception("assistant reply error: %s", exc)
        await wait.edit_text(
            "⚠️ Не получилось ответить прямо сейчас. Попробуй ещё раз чуть позже.",
            reply_markup=assistant_kb(),
        )
        return

    history.append({"role": "assistant", "content": reply})
    await state.update_data(assistant_history=history[-12:])
    await wait.edit_text(
        f"🤖 <b>AI-ассистент</b>\n\n{html.escape(reply)}",
        reply_markup=assistant_kb(),
    )


@router.message(AssistantFSM.waiting_message)
async def handle_assistant_non_text(message: Message) -> None:
    await message.answer(
        "Пока ассистент принимает только текстовые сообщения. Напиши вопрос текстом.",
        reply_markup=assistant_kb(),
    )
