from __future__ import annotations

import asyncio
import html
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import delete_public_file, save_public_file
from api.video_prompt_service import (
    VIDEO_PROMPT_MODEL_KEY,
    generate_prompt_from_video_url,
    is_supported_video_prompt_video,
)
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message, split_text_chunks
from db import repository as repo
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="video_prompt")

_VIDEO_PROMPT_CALLBACK = "vid:video2prompt"
_MAX_VIDEO_BYTES = 20 * 1024 * 1024
_ALLOWED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
}
_MAX_PROMPT_CHUNK_CHARS = 3000


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="vid:cancel_prompt")]]
    )


async def _download_telegram_file(bot: Bot, file_id: str) -> bytes:
    telegram_file = await bot.get_file(file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    return downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)


async def _video_prompt_cost(session: AsyncSession):
    model_cost = await repo.get_model_cost(session, VIDEO_PROMPT_MODEL_KEY)
    if model_cost is None or not getattr(model_cost, "is_active", True):
        return None
    return model_cost


def _result_messages(prompt: str, *, credits: float) -> list[str]:
    chunks = split_text_chunks(prompt, max_chars=_MAX_PROMPT_CHUNK_CHARS)
    total = len(chunks)
    messages: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        if index == 1:
            title = "🎬 <b>Видео → промпт готов</b>"
        else:
            title = f"🎬 <b>Видео → промпт · продолжение</b>"

        part = f"\n\n<i>Часть {index}/{total}</i>" if total > 1 else ""
        footer = (
            f"\n\nСписано: <b>{credits:g} 💋</b>. "
            "Нажми на текст, чтобы выделить и скопировать."
            if index == total
            else ""
        )
        messages.append(
            f"{title}\n\n<code>{html.escape(chunk, quote=False)}</code>{part}{footer}"
        )
    return messages


@router.callback_query(F.data == _VIDEO_PROMPT_CALLBACK)
async def cb_video_to_prompt(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    model_cost = await _video_prompt_cost(session)
    if model_cost is None:
        await call.answer("Цена функции не настроена", show_alert=True)
        return
    await state.set_state(VideoGenFSM.video_to_prompt)
    await state.update_data(video_prompt_cost=float(model_cost.credits))
    await safe_edit_message(
        call.message,
        "🎬 <b>Видео → промпт</b>\n\n"
        "Отправь короткое видео MP4, MOV или WebM до 20 МБ. "
        "Я разберу сцену, движение, камеру, свет и стиль, затем верну готовый промпт.\n\n"
        f"Стоимость анализа: <b>{float(model_cost.credits):g} 💋</b>.",
        reply_markup=_cancel_kb(),
    )
    await safe_answer_callback(call)


async def _analyse_video(
    *,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    file_id: str,
    mime_type: str,
    file_size: int | None,
) -> None:
    if file_size and file_size > _MAX_VIDEO_BYTES:
        await message.answer("Файл слишком большой. Telegram-бот может скачать максимум 20 МБ.", reply_markup=_cancel_kb())
        return
    if mime_type and mime_type.lower() not in _ALLOWED_VIDEO_MIME_TYPES:
        await message.answer("Пришли видео MP4, MOV или WebM.", reply_markup=_cancel_kb())
        return

    model_cost = await _video_prompt_cost(session)
    if model_cost is None:
        await message.answer("❌ Цена функции не настроена. Напиши администратору.", reply_markup=_cancel_kb())
        return
    credits = float(model_cost.credits or 0)
    if credits <= 0:
        await message.answer("❌ Цена функции не настроена. Напиши администратору.", reply_markup=_cancel_kb())
        return

    wait_msg = await message.answer("⏳ Анализирую видео, движение и камеру…")
    try:
        raw = await _download_telegram_file(bot, file_id)
        if len(raw) > _MAX_VIDEO_BYTES:
            await wait_msg.edit_text("Файл слишком большой. Telegram-бот может скачать максимум 20 МБ.", reply_markup=_cancel_kb())
            return
        if not is_supported_video_prompt_video(raw, mime_type):
            await wait_msg.edit_text("Пришли настоящее видео MP4, MOV или WebM.", reply_markup=_cancel_kb())
            return
        source_id = f"telegram-video:{file_id[:48]}"
        spent = await repo.spend_credits(
            session,
            db_user.id,
            credits,
            entry_type="video_prompt_spend",
            source_type=VIDEO_PROMPT_MODEL_KEY,
            source_id=source_id,
            note="Telegram video to prompt analysis",
        )
        if not spent:
            await wait_msg.edit_text(
                f"😔 Недостаточно 💋. Нужно <b>{credits:g}</b>, у тебя <b>{float(db_user.credits):g}</b>.",
                reply_markup=_cancel_kb(),
            )
            return
        video_url = await asyncio.to_thread(
            save_public_file,
            raw,
            mime_type or "video/mp4",
            subdir="video-prompt",
            unique=True,
        )
        result = await generate_prompt_from_video_url(video_url)
        prompt = result.text if hasattr(result, "text") else str(result)
    except Exception as exc:
        logger.exception("video_to_prompt failed for user=%s: %s", db_user.id, exc)
        if "spent" in locals() and spent:
            await repo.add_credits(
                session,
                db_user.id,
                credits,
                entry_type="video_prompt_refund",
                source_type=VIDEO_PROMPT_MODEL_KEY,
                source_id=locals().get("source_id"),
                note=f"Telegram video prompt refund: {type(exc).__name__}",
            )
        await wait_msg.edit_text(
            "❌ Не удалось проанализировать видео. Отправь другой файл или попробуй ещё раз.",
            reply_markup=_cancel_kb(),
        )
        return
    finally:
        if (
            "video_url" in locals()
            and video_url
            and not await asyncio.to_thread(delete_public_file, video_url)
        ):
            logger.warning("video_to_prompt temporary file cleanup failed user=%s", db_user.id)

    await state.clear()
    await wait_msg.delete()
    for result_message in _result_messages(prompt, credits=credits):
        await message.answer(result_message)


@router.message(VideoGenFSM.video_to_prompt, F.video)
async def handle_video_to_prompt_video(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    video = message.video
    await _analyse_video(
        message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        file_id=video.file_id,
        mime_type=video.mime_type or "video/mp4",
        file_size=video.file_size,
    )


@router.message(VideoGenFSM.video_to_prompt, F.document)
async def handle_video_to_prompt_document(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    document = message.document
    await _analyse_video(
        message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        file_id=document.file_id,
        mime_type=str(document.mime_type or "").lower(),
        file_size=document.file_size,
    )


@router.message(VideoGenFSM.video_to_prompt)
async def handle_invalid_video_prompt_input(message: Message) -> None:
    await message.answer("Нужно отправить видео MP4, MOV или WebM.", reply_markup=_cancel_kb())


@router.callback_query(F.data == "vid:cancel_prompt")
async def cb_cancel_video_prompt(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit_message(call.message, "❌ Видео → промпт отменён.")
    await safe_answer_callback(call)
