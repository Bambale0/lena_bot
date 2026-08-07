from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.minimax_h3_adapter import (
    MAX_REFERENCE_AUDIOS,
    MAX_REFERENCE_IMAGES,
    MAX_REFERENCE_VIDEOS,
    MAX_REFERENCE_VIDEO_SECONDS,
    REFERENCE_MODEL,
)
from api.public_files import mirror_telegram_file, save_public_file
from bot.keyboards.main_menu import back_to_menu_kb
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import User

router = Router(name="minimax_h3_references")


def _counts(data: dict) -> tuple[int, int, int]:
    images = len([item for item in (data.get("ref_file_ids") or []) if item])
    videos = len([item for item in _as_list(data.get("reference_video_url")) if item])
    audios = len([item for item in (data.get("audio_ids") or []) if item])
    return images, videos, audios


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]


def _collection_kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Референсы готовы", callback_data="h3ref:done"))
    builder.row(InlineKeyboardButton(text="🗑 Очистить", callback_data="h3ref:clear"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _status_text(data: dict) -> str:
    images, videos, audios = _counts(data)
    return (
        "🎛️ <b>MiniMax H3 Reference</b>\n\n"
        "Пришли референсы в любом порядке — модель может учитывать их одновременно:\n"
        f"• фото: <b>{images}/{MAX_REFERENCE_IMAGES}</b>\n"
        f"• видео: <b>{videos}/{MAX_REFERENCE_VIDEOS}</b> (каждое до {MAX_REFERENCE_VIDEO_SECONDS} сек)\n"
        f"• аудио/voice: <b>{audios}/{MAX_REFERENCE_AUDIOS}</b>\n\n"
        "Когда всё добавил, нажми <b>Референсы готовы</b>."
    )


@router.callback_query(VideoGenFSM.model_select, F.data == f"vid_model:{REFERENCE_MODEL}")
async def choose_h3_reference_model(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    model_cost = await repo.resolve_video_model_cost(
        session,
        REFERENCE_MODEL,
        duration=6,
        resolution=None,
    )
    if not model_cost:
        await safe_answer_callback(call, "Модель временно недоступна", show_alert=True)
        return
    minimum = float(model_cost.credits) * 6
    if float(db_user.credits) < minimum:
        await safe_answer_callback(
            call,
            f"Недостаточно 💋. Для 6 сек нужно минимум {minimum:g} 💋.",
            show_alert=True,
        )
        return

    old = await state.get_data()
    await state.set_state(VideoGenFSM.h3_reference_upload)
    await state.update_data(
        model_key=REFERENCE_MODEL,
        credits=float(model_cost.credits),
        duration=6,
        aspect_ratio="adaptive",
        resolution=None,
        mode="image",
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        character_ids=[],
        grok_mode=None,
        wizard_review_enabled=bool(old.get("wizard_review_enabled", True)),
        wizard_scenario=old.get("wizard_scenario", "video"),
    )
    await safe_edit_message(call.message, _status_text(await state.get_data()), reply_markup=_collection_kb())
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.h3_reference_upload, F.data == "h3ref:clear")
async def clear_h3_references(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
    )
    await safe_edit_message(call.message, _status_text(await state.get_data()), reply_markup=_collection_kb())
    await safe_answer_callback(call, "Очищено")


@router.message(VideoGenFSM.h3_reference_upload, F.photo)
async def add_h3_image(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("ref_file_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_IMAGES:
        await message.answer(f"Лимит фото — {MAX_REFERENCE_IMAGES}.", reply_markup=_collection_kb())
        return
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    if best.file_id not in refs:
        refs.append(best.file_id)
    await state.update_data(ref_file_ids=refs, image_file_id=refs[0])
    await message.answer(_status_text(await state.get_data()), reply_markup=_collection_kb())


@router.message(VideoGenFSM.h3_reference_upload, F.video)
async def add_h3_video(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = _as_list(data.get("reference_video_url"))
    if len(refs) >= MAX_REFERENCE_VIDEOS:
        await message.answer(f"Лимит видео — {MAX_REFERENCE_VIDEOS}.", reply_markup=_collection_kb())
        return
    duration = int(message.video.duration or 0)  # type: ignore[union-attr]
    if duration > MAX_REFERENCE_VIDEO_SECONDS:
        await message.answer(
            f"Референсное видео должно быть не длиннее {MAX_REFERENCE_VIDEO_SECONDS} сек.",
            reply_markup=_collection_kb(),
        )
        return
    url = await mirror_telegram_file(bot, message.video.file_id, is_video=True)  # type: ignore[union-attr]
    if url not in refs:
        refs.append(url)
    await state.update_data(reference_video_url=refs)
    await message.answer(_status_text(await state.get_data()), reply_markup=_collection_kb())


async def _save_audio(message: Message, bot: Bot) -> str | None:
    media = message.audio or message.voice or message.document
    if media is None:
        return None
    mime_type = str(getattr(media, "mime_type", "") or "").lower()
    if message.document and not mime_type.startswith("audio/"):
        return None
    telegram_file = await bot.get_file(media.file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    return save_public_file(raw, mime_type or "audio/ogg", subdir="h3-audio")


@router.message(VideoGenFSM.h3_reference_upload, F.audio | F.voice | F.document)
async def add_h3_audio(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("audio_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_AUDIOS:
        await message.answer(f"Лимит аудио — {MAX_REFERENCE_AUDIOS}.", reply_markup=_collection_kb())
        return
    url = await _save_audio(message, bot)
    if not url:
        await message.answer("Пришли аудиофайл или voice-сообщение.", reply_markup=_collection_kb())
        return
    refs.append(url)
    await state.update_data(audio_ids=refs)
    await message.answer(_status_text(await state.get_data()), reply_markup=_collection_kb())


@router.callback_query(VideoGenFSM.h3_reference_upload, F.data == "h3ref:done")
async def finish_h3_references(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    from bot.handlers import video_gen as legacy

    data = await state.get_data()
    images, videos, audios = _counts(data)
    if images + videos + audios == 0:
        await safe_answer_callback(call, "Добавь хотя бы один референс", show_alert=True)
        return

    # Generic APIX launch code accepts multimodal H3 state unchanged. `mode`
    # only affects UI validation; the H3 adapter uses all collected lists.
    await state.update_data(mode="image" if images else ("video" if videos else "text"))
    model_cost = await repo.get_model_cost(session, REFERENCE_MODEL)
    display_name = getattr(model_cost, "display_name", None) or "MiniMax H3 Reference"
    await state.set_state(VideoGenFSM.params_select)
    updated = await state.get_data()
    await safe_edit_message(
        call.message,
        f"✅ Референсы сохранены: фото {images}, видео {videos}, аудио {audios}.\n\n"
        f"⚙️ <b>Параметры</b> · {display_name}\n"
        "Выбери длительность и формат, затем переходи к промпту.",
        reply_markup=legacy._video_params_reply_markup(REFERENCE_MODEL, updated),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.h3_reference_upload)
async def invalid_h3_reference(message: Message) -> None:
    await message.answer(
        "Здесь можно отправлять фото, видео, аудиофайл или voice-сообщение.",
        reply_markup=back_to_menu_kb(),
    )
