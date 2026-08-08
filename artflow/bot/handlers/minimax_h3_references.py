from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.minimax_h3_adapter import (
    MAX_REFERENCE_AUDIOS,
    MAX_REFERENCE_FILES,
    MAX_REFERENCE_IMAGES,
    MAX_REFERENCE_MEDIA_SECONDS,
    MAX_REFERENCE_TOTAL_SECONDS,
    MAX_REFERENCE_VIDEOS,
    MIN_REFERENCE_MEDIA_SECONDS,
    PUBLIC_DISPLAY_NAME,
    PUBLIC_MODEL,
)
from api.public_files import mirror_telegram_file, save_public_file
from bot.keyboards.main_menu import back_to_menu_kb
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import User

router = Router(name="minimax_h3_references")


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


def _total_files(data: dict) -> int:
    return sum(_counts(data))


def _collection_kb(*, allow_empty: bool = True) -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Референсы готовы", callback_data="h3ref:done"))
    if allow_empty:
        builder.row(InlineKeyboardButton(text="➡️ Без референсов", callback_data="h3ref:none"))
    builder.row(InlineKeyboardButton(text="🗑 Очистить", callback_data="h3ref:clear"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _status_text(data: dict) -> str:
    images, videos, audios = _counts(data)
    video_seconds = int(data.get("h3_video_total_seconds") or 0)
    audio_seconds = int(data.get("h3_audio_total_seconds") or 0)
    return (
        f"🎞 <b>{PUBLIC_DISPLAY_NAME.replace('🎞 ', '')}</b> · референсы опциональны\n\n"
        "Маршрут выбирать не нужно — бот определит его по материалам:\n"
        "• без файлов → Text-to-Video\n"
        "• 1 фото → первый кадр\n"
        "• 2 фото → первый + последний кадр\n"
        "• 3+ фото или видео/аудио → Reference-to-Video\n\n"
        f"🖼 Фото: <b>{images}/{MAX_REFERENCE_IMAGES}</b>\n"
        f"🎬 Видео: <b>{videos}/{MAX_REFERENCE_VIDEOS}</b> · {video_seconds}/{MAX_REFERENCE_TOTAL_SECONDS} сек\n"
        f"🎵 Аудио: <b>{audios}/{MAX_REFERENCE_AUDIOS}</b> · {audio_seconds}/{MAX_REFERENCE_TOTAL_SECONDS} сек\n"
        f"📦 Всего файлов: <b>{images + videos + audios}/{MAX_REFERENCE_FILES}</b>\n\n"
        f"Видео/аудио: каждый файл {MIN_REFERENCE_MEDIA_SECONDS}–{MAX_REFERENCE_MEDIA_SECONDS} сек. "
        "Аудио не может быть единственным референсом."
    )


async def _go_to_params(call: CallbackQuery, state: FSMContext, *, ratio: str | None = None) -> None:
    from bot.handlers import video_gen as legacy

    if ratio is not None:
        await state.update_data(aspect_ratio=ratio)
    await state.set_state(VideoGenFSM.params_select)
    data = await state.get_data()
    await safe_edit_message(
        call.message,
        f"⚙️ <b>Параметры</b> · {PUBLIC_DISPLAY_NAME}\n\n"
        "Качество, длительность и формат задаются здесь. Маршрут H3 выберется автоматически по входам.",
        reply_markup=legacy._video_params_reply_markup(PUBLIC_MODEL, data),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.model_select, F.data == f"vid_model:{PUBLIC_MODEL}")
async def choose_h3_model(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    # Gate only by the cheapest valid H3 request; the user can pick 2K later.
    cheapest = await repo.resolve_video_model_cost(
        session,
        PUBLIC_MODEL,
        duration=4,
        resolution="768P",
    )
    if not cheapest:
        await safe_answer_callback(call, "Модель временно недоступна", show_alert=True)
        return
    minimum = float(cheapest.credits) * 4
    if float(db_user.credits) < minimum:
        await safe_answer_callback(
            call,
            f"Недостаточно 💋. Минимальная генерация H3 стоит {minimum:g} 💋.",
            show_alert=True,
        )
        return

    old = await state.get_data()
    scenario = str(old.get("wizard_scenario") or "").strip().lower()
    await state.update_data(
        model_key=PUBLIC_MODEL,
        credits=float(cheapest.credits),
        duration=6,
        aspect_ratio="16:9" if scenario == "text" else "adaptive",
        resolution="2K",
        mode="text" if scenario == "text" else "image",
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        character_ids=[],
        h3_video_total_seconds=0,
        h3_audio_total_seconds=0,
        grok_mode=None,
        wizard_review_enabled=bool(old.get("wizard_review_enabled", True)),
        wizard_scenario=scenario or old.get("wizard_scenario"),
    )

    if scenario == "text":
        await _go_to_params(call, state, ratio="16:9")
        return

    if scenario == "image":
        await state.set_state(VideoGenFSM.image_upload)
        await safe_edit_message(
            call.message,
            f"🖼 <b>{PUBLIC_DISPLAY_NAME}</b>\n\n"
            "Пришли фото. Ничего выбирать не нужно:\n"
            "• 1 фото — первый кадр\n"
            "• 2 фото — первый + последний кадр\n"
            "• 3–9 фото — H3 Reference\n\n"
            "После загрузки нажми <b>Готово</b>.",
            reply_markup=back_to_menu_kb(),
        )
        await safe_answer_callback(call)
        return

    # Video scenario and the advanced model picker both use one optional
    # multimodal collector. Presence/absence of refs determines the route.
    await state.set_state(VideoGenFSM.h3_reference_upload)
    await safe_edit_message(call.message, _status_text(await state.get_data()), reply_markup=_collection_kb())
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.h3_reference_upload, F.data == "h3ref:none")
async def h3_without_references(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        mode="text",
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        character_ids=[],
        h3_video_total_seconds=0,
        h3_audio_total_seconds=0,
    )
    await _go_to_params(call, state, ratio="16:9")


@router.callback_query(VideoGenFSM.h3_reference_upload, F.data == "h3ref:clear")
async def clear_h3_references(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        character_ids=[],
        h3_video_total_seconds=0,
        h3_audio_total_seconds=0,
    )
    await safe_edit_message(call.message, _status_text(await state.get_data()), reply_markup=_collection_kb())
    await safe_answer_callback(call, "Очищено")


@router.message(VideoGenFSM.h3_reference_upload, F.photo)
async def add_h3_image(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("ref_file_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_IMAGES or _total_files(data) >= MAX_REFERENCE_FILES:
        await message.answer("Достигнут лимит H3 по референсам.", reply_markup=_collection_kb())
        return
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    if best.file_id not in refs:
        refs.append(best.file_id)
    await state.update_data(ref_file_ids=refs, image_file_id=refs[0], mode="image")
    await message.answer(_status_text(await state.get_data()), reply_markup=_collection_kb())


@router.message(VideoGenFSM.h3_reference_upload, F.video)
async def add_h3_video(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = _as_list(data.get("reference_video_url"))
    if len(refs) >= MAX_REFERENCE_VIDEOS or _total_files(data) >= MAX_REFERENCE_FILES:
        await message.answer("Достигнут лимит видео-референсов H3.", reply_markup=_collection_kb())
        return
    duration = int(message.video.duration or 0)  # type: ignore[union-attr]
    if duration < MIN_REFERENCE_MEDIA_SECONDS or duration > MAX_REFERENCE_MEDIA_SECONDS:
        await message.answer(
            f"Видео-референс должен быть {MIN_REFERENCE_MEDIA_SECONDS}–{MAX_REFERENCE_MEDIA_SECONDS} сек.",
            reply_markup=_collection_kb(),
        )
        return
    total = int(data.get("h3_video_total_seconds") or 0)
    if total + duration > MAX_REFERENCE_TOTAL_SECONDS:
        await message.answer(
            f"Суммарная длина видео-референсов не может превышать {MAX_REFERENCE_TOTAL_SECONDS} сек.",
            reply_markup=_collection_kb(),
        )
        return
    url = await mirror_telegram_file(bot, message.video.file_id, is_video=True)  # type: ignore[union-attr]
    if url not in refs:
        refs.append(url)
        total += duration
    await state.update_data(reference_video_url=refs, h3_video_total_seconds=total, mode="video")
    await message.answer(_status_text(await state.get_data()), reply_markup=_collection_kb())


def _probe_duration(path: str) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def _convert_to_mp3(source_path: str, output_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", source_path, "-vn", "-codec:a", "libmp3lame", "-q:a", "2", output_path],
        capture_output=True,
        timeout=60,
        check=True,
    )


async def _save_h3_audio(message: Message, bot: Bot) -> tuple[str, int] | None:
    media = message.audio or message.voice or message.document
    if media is None:
        return None
    mime_type = str(getattr(media, "mime_type", "") or "").lower()
    file_name = str(getattr(media, "file_name", "") or "")
    if message.document and not (mime_type.startswith("audio/") or file_name.lower().endswith((".mp3", ".wav"))):
        return None

    telegram_file = await bot.get_file(media.file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    source_suffix = Path(file_name).suffix or (".ogg" if message.voice else ".bin")

    source_path = ""
    output_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=source_suffix) as src:
            src.write(raw)
            source_path = src.name
        measured = getattr(media, "duration", None)
        duration_f = float(measured) if measured else await asyncio.to_thread(_probe_duration, source_path)
        duration = int(round(duration_f or 0))
        if duration < MIN_REFERENCE_MEDIA_SECONDS or duration > MAX_REFERENCE_MEDIA_SECONDS:
            raise ValueError(
                f"Аудио-референс должен быть {MIN_REFERENCE_MEDIA_SECONDS}–{MAX_REFERENCE_MEDIA_SECONDS} сек."
            )

        is_native = mime_type in {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"} or file_name.lower().endswith((".mp3", ".wav"))
        if is_native:
            public_url = save_public_file(raw, "audio/mpeg" if file_name.lower().endswith(".mp3") else (mime_type or "audio/wav"), subdir="h3-audio")
        else:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as out:
                output_path = out.name
            await asyncio.to_thread(_convert_to_mp3, source_path, output_path)
            converted = Path(output_path).read_bytes()
            public_url = save_public_file(converted, "audio/mpeg", subdir="h3-audio")
        return public_url, duration
    finally:
        for path in (source_path, output_path):
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass


@router.message(VideoGenFSM.h3_reference_upload, F.audio | F.voice | F.document)
async def add_h3_audio(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("audio_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_AUDIOS or _total_files(data) >= MAX_REFERENCE_FILES:
        await message.answer("Достигнут лимит аудио-референсов H3.", reply_markup=_collection_kb())
        return
    try:
        saved = await _save_h3_audio(message, bot)
    except ValueError as exc:
        await message.answer(f"❌ {exc}", reply_markup=_collection_kb())
        return
    except Exception:
        await message.answer("❌ Не удалось подготовить аудио. Пришли MP3/WAV или voice ещё раз.", reply_markup=_collection_kb())
        return
    if not saved:
        await message.answer("Пришли аудиофайл MP3/WAV или voice-сообщение.", reply_markup=_collection_kb())
        return
    url, duration = saved
    total = int(data.get("h3_audio_total_seconds") or 0)
    if total + duration > MAX_REFERENCE_TOTAL_SECONDS:
        await message.answer(
            f"Суммарная длина аудио-референсов не может превышать {MAX_REFERENCE_TOTAL_SECONDS} сек.",
            reply_markup=_collection_kb(),
        )
        return
    refs.append(url)
    await state.update_data(audio_ids=refs, h3_audio_total_seconds=total + duration, mode="video")
    await message.answer(_status_text(await state.get_data()), reply_markup=_collection_kb())


@router.callback_query(VideoGenFSM.h3_reference_upload, F.data == "h3ref:done")
async def finish_h3_references(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    images, videos, audios = _counts(data)
    if audios and not (images or videos):
        await safe_answer_callback(
            call,
            "Аудио H3 нельзя использовать отдельно — добавь фото или видео.",
            show_alert=True,
        )
        return
    if images + videos + audios == 0:
        await _go_to_params(call, state, ratio="16:9")
        return

    # This `mode` only controls generic UI presentation. The H3 backend chooses
    # T2V/I2V/Reference again from the actual collected inputs.
    mode = "video" if videos or audios or images > 2 else "image"
    await state.update_data(mode=mode, aspect_ratio="adaptive" if mode == "video" else None)
    await _go_to_params(call, state)


@router.message(VideoGenFSM.h3_reference_upload)
async def invalid_h3_reference(message: Message) -> None:
    await message.answer(
        "Можно отправить фото, видео или аудио. Либо нажми «Без референсов» для Text-to-Video.",
        reply_markup=_collection_kb(),
    )
