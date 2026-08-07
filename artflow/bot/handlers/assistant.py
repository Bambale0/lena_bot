from __future__ import annotations

import hashlib
import html
import logging
import re
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant_service import (
    generate_assistant_reply,
    generate_freeform_prompt_moderation_review,
)
from api.public_files import get_static_upload_directory, mirror_telegram_file, public_upload_url
from bot.services.assistant_moderator import is_admin_tg_id, try_handle_admin_request
from bot.states import AssistantFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="assistant")

_MAX_ASSISTANT_FILE_BYTES = 20 * 1024 * 1024
_MAX_TELEGRAM_REPLY_CHARS = 3300
_ALLOWED_FILE_SUFFIXES = {
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".json",
    ".xml",
    ".html",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".ppt",
    ".pptx",
}
_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

_PROMPT_MODERATION_PATTERNS = (
    re.compile(r"^\s*(?:проверь|проверить|оцени|оценить|разбери|check|moderate)\s+(?:этот\s+)?(?:промпт|prompt)(?:\s+на\s+модерацию)?\s*[:\-]\s*(.+)$", re.I | re.S),
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
    capability_text = (
        "Работаю на GPT‑5.6 и понимаю текст, фото и документы. Веб-поиск включён в auto-режиме.\n"
        "Режимы: <code>/fast</code>, <code>/deep</code>, <code>/xhigh</code>, <code>/max</code>, "
        "<code>/web</code>, <code>/noweb</code>."
    )
    if is_admin:
        return (
            "🤖 <b>AI-ассистент модератора</b>\n\n"
            f"{capability_text}\n\n"
            "Могу помогать модерировать бот: показывать статистику, очередь промптов, заявки на вывод, "
            "искать пользователей, банить, разбанивать, начислять 💋 и разбирать спорные промпты.\n\n"
            "Примеры: <code>статистика</code>, <code>забань 123456789</code>, "
            "<code>проверь промпт 42</code>, <code>/max проверь архитектуру...</code>."
        )
    return (
        "🤖 <b>AI-ассистент</b>\n\n"
        f"{capability_text}\n\n"
        "Пиши любые рабочие вопросы, присылай фото с вопросом или документ для разбора. "
        "Могу помочь с промптами, идеями, сценариями генерации, референсами, актуальным поиском и обычными задачами.\n\n"
        "Для проверки промпта: <code>проверь промпт на модерацию: ...</code>."
    )


async def _download_telegram_document(bot: Bot, file_id: str) -> bytes:
    telegram_file = await bot.get_file(file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    return downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)


async def _mirror_assistant_document(message: Message, bot: Bot) -> tuple[str, str]:
    document = message.document
    if document is None:
        raise ValueError("document is required")
    if document.file_size and document.file_size > _MAX_ASSISTANT_FILE_BYTES:
        raise ValueError("Файл слишком большой. Максимум — 20 МБ.")

    mime_type = str(document.mime_type or "").lower()
    if mime_type in _IMAGE_MIME_TYPES:
        return await mirror_telegram_file(bot, document.file_id), "input_image"

    suffix = Path(document.file_name or "").suffix.lower()
    if suffix not in _ALLOWED_FILE_SUFFIXES:
        raise ValueError("Поддерживаются PDF, TXT/MD/CSV/JSON/XML/HTML, DOC/DOCX, XLS/XLSX и PPT/PPTX.")

    raw = await _download_telegram_document(bot, document.file_id)
    digest = hashlib.sha256(raw).hexdigest()[:32]
    rel = Path("assistant") / f"{digest}{suffix}"
    path = get_static_upload_directory() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return public_upload_url(str(rel)), "input_file"


def _chunks(text: str, size: int = _MAX_TELEGRAM_REPLY_CHARS) -> list[str]:
    source = str(text or "").strip() or "Готово. Чем ещё помочь?"
    chunks: list[str] = []
    while source:
        if len(source) <= size:
            chunks.append(source)
            break
        split_at = source.rfind("\n", 0, size)
        if split_at < size // 2:
            split_at = source.rfind(" ", 0, size)
        if split_at < size // 2:
            split_at = size
        chunks.append(source[:split_at].rstrip())
        source = source[split_at:].lstrip()
    return chunks


async def _deliver_reply(wait: Message, source: Message, reply: str, *, is_admin: bool) -> None:
    parts = _chunks(reply)
    first_markup = assistant_kb(is_admin=is_admin) if len(parts) == 1 else None
    await wait.edit_text(
        f"🤖 <b>AI-ассистент</b>\n\n{html.escape(parts[0])}",
        reply_markup=first_markup,
    )
    for index, part in enumerate(parts[1:], start=1):
        await source.answer(
            html.escape(part),
            reply_markup=assistant_kb(is_admin=is_admin) if index == len(parts) - 1 else None,
        )


async def _run_assistant_turn(
    *,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    content: str | list[dict[str, Any]],
    plain_text: str = "",
    allow_admin_commands: bool = False,
) -> None:
    is_admin = is_admin_tg_id(db_user.tg_id)
    data = await state.get_data()
    history = list(data.get("assistant_history") or [])
    history.append({"role": "user", "content": content})

    wait = await message.answer("🤔 Думаю...")
    try:
        moderation_prompt = _extract_prompt_for_moderation(plain_text) if plain_text else None
        admin_outcome = None
        if moderation_prompt:
            if len(moderation_prompt) < 8:
                reply = "Пришли промпт целиком после двоеточия — сейчас текста слишком мало для проверки."
            else:
                reply = await generate_freeform_prompt_moderation_review(prompt_text=moderation_prompt)
        else:
            if is_admin and allow_admin_commands and plain_text:
                admin_outcome = await try_handle_admin_request(
                    plain_text,
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
    await _deliver_reply(wait, message, reply, is_admin=is_admin)


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
        "🧹 <b>Диалог очищен.</b>\n\nНапиши новый вопрос или пришли фото/документ.",
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
    await _run_assistant_turn(
        message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        content=user_text,
        plain_text=user_text,
        allow_admin_commands=True,
    )


@router.message(AssistantFSM.waiting_message, F.photo)
async def handle_assistant_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    best = max(message.photo, key=lambda item: item.file_size or 0)
    try:
        image_url = await mirror_telegram_file(bot, best.file_id)
    except Exception as exc:
        logger.exception("assistant photo mirror failed: %s", exc)
        await message.answer("Не удалось загрузить фото для анализа. Попробуй другое изображение.")
        return
    caption = (message.caption or "").strip() or "Проанализируй это изображение. Опиши важное и помоги с тем, что на нём видно."
    content = [
        {"type": "input_text", "text": caption},
        {"type": "input_image", "image_url": image_url},
    ]
    await _run_assistant_turn(
        message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        content=content,
        plain_text=caption,
    )


@router.message(AssistantFSM.waiting_message, F.document)
async def handle_assistant_document(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    try:
        file_url, input_type = await _mirror_assistant_document(message, bot)
    except ValueError as exc:
        await message.answer(str(exc), reply_markup=assistant_kb(is_admin=is_admin_tg_id(db_user.tg_id)))
        return
    except Exception as exc:
        logger.exception("assistant document mirror failed: %s", exc)
        await message.answer("Не удалось загрузить документ для анализа. Попробуй другой файл.")
        return

    caption = (message.caption or "").strip() or "Проанализируй этот файл, выдели главное и ответь по существу."
    block = {"type": input_type}
    if input_type == "input_image":
        block["image_url"] = file_url
    else:
        block["file_url"] = file_url
    content = [{"type": "input_text", "text": caption}, block]
    await _run_assistant_turn(
        message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        content=content,
        plain_text=caption,
    )


@router.message(AssistantFSM.waiting_message)
async def handle_assistant_non_text(message: Message, db_user: User) -> None:
    await message.answer(
        "Ассистент принимает текст, фотографии и документы (PDF, TXT, DOCX, XLSX, PPTX и др.).",
        reply_markup=assistant_kb(is_admin=is_admin_tg_id(db_user.tg_id)),
    )
