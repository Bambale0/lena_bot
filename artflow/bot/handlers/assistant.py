from __future__ import annotations

import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant_service import generate_assistant_reply, generate_freeform_prompt_moderation_review
from bot.services.assistant_moderator import is_admin_tg_id, try_handle_admin_request
from bot.states import AssistantFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="assistant")


_PROMPT_MODERATION_PATTERNS = (
    re.compile(r"^\s*(?:проверь|проверить|оцени|оцени|разбери|check|moderate)\s+(?:этот\s+)?(?:промпт|prompt)(?:\s+на\s+модерацию)?\s*[:\-]\s*(.+)$", re.I | re.S),
    re.compile(r"^\s*(?:проверь|проверить|оцени|оценить|разбери|check|moderate)\s+на\s+модерацию\s*[:\-]\s*(.+)$", re.I | re.S),
)


def _extract_prompt_for_moderation(text: str) -> str | None:
    source = (text or "").strip()
    for pattern in _PROMPT_MODERATION_PATTERNS:
        match = pattern.match(source)
        if not match:
            continue
        prompt_text = (match.group(1) or "").strip()
        return prompt_text or None
    return None


def assistant_kb(*, is_admin: bool = False):
    builder = InlineKeyboardBuilder()
    if is_admin:
        builder.button(text="📊 Статистика", callback_data="adm:stats")
        builder.button(text="💸 Выводы", callback_data="adm:withdrawals")
        builder.button(text="🗂 Промпты", callback_data="adm:prompts")
        builder.button(text="🔧 Админка", callback_data="menu:admin")
    builder.button(text="🧹 Очистить диалог", callback_data="assistant:clear")
    builder.button(text="🏠 Меню", callback_data="assistant:exit")
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def _intro_text(*, is_admin: bool = False) -> str:
    if is_admin:
        return (
            "🤖 <b>AI-ассистент модератора</b>\n\n"
            "Я могу не только отвечать на вопросы, но и помогать модерировать бот: "
            "показывать статистику, очередь промптов, заявки на вывод, искать пользователей, "
            "банить, разбанивать, начислять 💋 и разбирать спорные промпты.\n\n"
            "Примеры: <code>статистика</code>, <code>забань 123456789</code>, <code>проверь промпт 42</code>, <code>проверь промпт на модерацию: a cinematic portrait...</code>."
        )
    return (
        "🤖 <b>AI-ассистент</b>\n\n"
        "Можешь писать сюда вопросы по боту, промптам, идеям для контента, сценариям генерации, референсам, оплатам и вообще любые рабочие вопросы.\n\n"
        "Ещё я умею быстро проверять текст промпта на модерационные риски. Формат: <code>проверь промпт на модерацию: ...</code>.\n\n"
        "Я держу короткий контекст диалога и отвечаю прямо в чате."
    )


@router.message(Command("assistant"))
async def cmd_assistant(message: Message, state: FSMContext, db_user: User) -> None:
    is_admin = is_admin_tg_id(db_user.tg_id)
    await state.set_state(AssistantFSM.waiting_message)
    await state.update_data(assistant_history=[])
    await message.answer(_intro_text(is_admin=is_admin), reply_markup=assistant_kb(is_admin=is_admin))


@router.callback_query(F.data == "menu:assistant")
async def cb_assistant(call: CallbackQuery, state: FSMContext, db_user: User) -> None:
    is_admin = is_admin_tg_id(db_user.tg_id)
    await state.set_state(AssistantFSM.waiting_message)
    await state.update_data(assistant_history=[])
    await safe_edit_message(
        call.message,
        _intro_text(is_admin=is_admin),
        reply_markup=assistant_kb(is_admin=is_admin),
    )  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "assistant:clear")
async def cb_assistant_clear(call: CallbackQuery, state: FSMContext, db_user: User) -> None:
    is_admin = is_admin_tg_id(db_user.tg_id)
    await state.set_state(AssistantFSM.waiting_message)
    await state.update_data(assistant_history=[])
    await safe_edit_message(
        call.message,
        "🧹 <b>Диалог очищен.</b>\n\nНапиши новый вопрос.",
        reply_markup=assistant_kb(is_admin=is_admin),
    )  # type: ignore[arg-type]
    await safe_answer_callback(call, "Контекст очищен")


@router.callback_query(F.data == "assistant:exit")
async def cb_assistant_exit(call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    await state.clear()
    screen = await render_screen(screen="main", session=session, db_user=db_user)
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(AssistantFSM.waiting_message, F.text)
async def handle_assistant_message(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    user_text = (message.text or "").strip()
    if not user_text:
        await message.answer("Напиши вопрос текстом 🙂", reply_markup=assistant_kb(is_admin=is_admin_tg_id(db_user.tg_id)))
        return

    is_admin = is_admin_tg_id(db_user.tg_id)
    data = await state.get_data()
    history = list(data.get("assistant_history") or [])
    history.append({"role": "user", "content": user_text})

    wait = await message.answer("🤔 Думаю...")
    try:
        moderation_prompt = _extract_prompt_for_moderation(user_text)
        admin_outcome = None
        if moderation_prompt:
            if len(moderation_prompt) < 8:
                reply = "Пришли промпт целиком после двоеточия — сейчас текста слишком мало для проверки."
            else:
                reply = await generate_freeform_prompt_moderation_review(prompt_text=moderation_prompt)
        else:
            if is_admin:
                admin_outcome = await try_handle_admin_request(
                    user_text,
                    session=session,
                    bot=bot,
                    admin_tg_id=db_user.tg_id,
                )
            reply = admin_outcome.text if admin_outcome else await generate_assistant_reply(history, admin_mode=is_admin)
    except Exception as exc:
        logger.exception("assistant reply error: %s", exc)
        await wait.edit_text(
            "⚠️ Не получилось ответить прямо сейчас. Попробуй ещё раз чуть позже.",
            reply_markup=assistant_kb(is_admin=is_admin),
        )
        return

    history.append({"role": "assistant", "content": reply})
    await state.update_data(assistant_history=history[-12:])
    await wait.edit_text(
        f"🤖 <b>AI-ассистент</b>\n\n{html.escape(reply)}",
        reply_markup=assistant_kb(is_admin=is_admin),
    )


@router.message(AssistantFSM.waiting_message)
async def handle_assistant_non_text(message: Message, db_user: User) -> None:
    await message.answer(
        "Пока ассистент принимает только текстовые сообщения. Напиши вопрос текстом.",
        reply_markup=assistant_kb(is_admin=is_admin_tg_id(db_user.tg_id)),
    )
