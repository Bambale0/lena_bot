from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import mirror_telegram_file, save_public_file
from api.seedance25_adapter import (
    DISPLAY_NAME,
    MAX_REFERENCE_AUDIOS,
    MAX_REFERENCE_IMAGES,
    MAX_REFERENCE_VIDEOS,
    MODEL_KEY,
    route_for_inputs,
)
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import User

router = Router(name="seedance25_references")


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]


def _counts(data: dict) -> tuple[int, int, int]:
    return (
        len([item for item in (data.get("ref_file_ids") or []) if item]),
        len(_as_list(data.get("reference_video_url"))),
        len([item for item in (data.get("audio_ids") or []) if item]),
    )


def _kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Референсы готовы", callback_data="s25ref:done"))
    builder.row(InlineKeyboardButton(text="➡️ Без референсов", callback_data="s25ref:none"))
    builder.row(InlineKeyboardButton(text="🗑 Очистить", callback_data="s25ref:clear"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _text(data: dict) -> str:
    images, videos, audios = _counts(data)
    return (
        "🌱 <b>Seedance 2.5</b>\n\n"
        "Просто пришли нужные референсы — режим выбирать не надо:\n"
        "• без референсов → текст в видео\n"
        "• ровно 1 фото → первый кадр\n"
        "• 2+ фото → мультимодальные референсы\n"
        "• любое видео или аудио → мультимодальные референсы\n\n"
        f"🖼 Фото: <b>{images}/{MAX_REFERENCE_IMAGES}</b>\n"
        f"🎬 Видео: <b>{videos}/{MAX_REFERENCE_VIDEOS}</b>\n"
        f"🎵 Аудио: <b>{audios}/{MAX_REFERENCE_AUDIOS}</b>\n\n"
        "Можно смешивать фото, видео и аудио в одной генерации."
    )


async def _go_params(call: CallbackQuery, state: FSMContext) -> None:
    from bot.handlers import video_gen as legacy

    data = await state.get_data()
    images, videos, audios = _counts(data)
    route = route_for_inputs(
        images=[str(item) for item in (data.get("ref_file_ids") or []) if item],
        videos=_as_list(data.get("reference_video_url")),
        audios=[str(item) for item in (data.get("audio_ids") or []) if item],
    )
    await state.update_data(
        mode=route,
        aspect_ratio="adaptive" if route == "image" else data.get("aspect_ratio"),
    )
    updated = await state.get_data()
    await state.set_state(VideoGenFSM.params_select)
    await safe_edit_message(
        call.message,
        f"⚙️ <b>Параметры</b> · {DISPLAY_NAME}\n\n"
        f"Референсы: фото {images}, видео {videos}, аудио {audios}.\n"
        "Seedance сам выберет внутренний сценарий по этим материалам.",
        reply_markup=legacy._video_params_reply_markup(MODEL_KEY, updated),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.model_select, F.data == f"vid_model:{MODEL_KEY}")
async def choose_seedance25(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    model_cost = await repo.resolve_video_model_cost(
        session,
        MODEL_KEY,
        duration=5,
        resolution="720p",
    )
    if not model_cost:
        await safe_answer_callback(call, "Модель временно недоступна", show_alert=True)
        return
    minimum = float(model_cost.credits) * 5
    if float(db_user.credits) < minimum:
        await safe_answer_callback(
            call,
            f"Недостаточно 💋. Для 5 сек нужно минимум {minimum:g} 💋.",
            show_alert=True,
        )
        return

    old = await state.get_data()
    await state.set_state(VideoGenFSM.seedance25_reference_upload)
    await state.update_data(
        model_key=MODEL_KEY,
        credits=float(model_cost.credits),
        duration=5,
        aspect_ratio="adaptive",
        resolution="720p",
        mode="text",
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        character_ids=[],
        grok_mode=None,
        wizard_review_enabled=bool(old.get("wizard_review_enabled", True)),
        wizard_scenario=old.get("wizard_scenario", "advanced"),
    )
    await safe_edit_message(call.message, _text(await state.get_data()), reply_markup=_kb())
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.seedance25_reference_upload, F.data == "s25ref:none")
async def no_seedance25_refs(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        mode="text",
    )
    await _go_params(call, state)


@router.callback_query(VideoGenFSM.seedance25_reference_upload, F.data == "s25ref:clear")
async def clear_seedance25_refs(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
    )
    await safe_edit_message(call.message, _text(await state.get_data()), reply_markup=_kb())
    await safe_answer_callback(call, "Очищено")


@router.message(VideoGenFSM.seedance25_reference_upload, F.photo)
async def add_seedance25_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("ref_file_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_IMAGES:
        await message.answer(f"Лимит фото — {MAX_REFERENCE_IMAGES}.", reply_markup=_kb())
        return
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    if best.file_id not in refs:
        refs.append(best.file_id)
    await state.update_data(ref_file_ids=refs, image_file_id=refs[0], image_url=None)
    await message.answer(_text(await state.get_data()), reply_markup=_kb())


@router.message(VideoGenFSM.seedance25_reference_upload, F.video)
async def add_seedance25_video(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = _as_list(data.get("reference_video_url"))
    if len(refs) >= MAX_REFERENCE_VIDEOS:
        await message.answer(f"Лимит видео — {MAX_REFERENCE_VIDEOS}.", reply_markup=_kb())
        return
    url = await mirror_telegram_file(bot, message.video.file_id, is_video=True)  # type: ignore[union-attr]
    if url not in refs:
        refs.append(url)
    await state.update_data(reference_video_url=refs)
    await message.answer(_text(await state.get_data()), reply_markup=_kb())


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
    return save_public_file(raw, mime_type or "audio/ogg", subdir="seedance25/audio")


@router.message(VideoGenFSM.seedance25_reference_upload, F.audio | F.voice | F.document)
async def add_seedance25_audio(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("audio_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_AUDIOS:
        await message.answer(f"Лимит аудио — {MAX_REFERENCE_AUDIOS}.", reply_markup=_kb())
        return
    url = await _save_audio(message, bot)
    if not url:
        await message.answer("Пришли аудиофайл или voice-сообщение.", reply_markup=_kb())
        return
    if url not in refs:
        refs.append(url)
    await state.update_data(audio_ids=refs)
    await message.answer(_text(await state.get_data()), reply_markup=_kb())


@router.callback_query(VideoGenFSM.seedance25_reference_upload, F.data == "s25ref:done")
async def finish_seedance25_refs(call: CallbackQuery, state: FSMContext) -> None:
    await _go_params(call, state)


@router.message(VideoGenFSM.seedance25_reference_upload)
async def invalid_seedance25_ref(message: Message) -> None:
    await message.answer(
        "Здесь можно отправить фото, видео, аудио/voice или нажать «Без референсов».",
        reply_markup=_kb(),
    )
