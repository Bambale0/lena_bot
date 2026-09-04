from __future__ import annotations

from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import mirror_telegram_file
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.gemini_omni import (
    GEMINI_OMNI_MAX_IMAGE_SLOTS,
    GEMINI_OMNI_VIDEO_MODEL,
    normalize_gemini_omni_ids,
    validate_gemini_omni_media_slots,
)
from db import repository as repo

router = Router(name="gemini_omni_references")

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024
_MAX_VIDEO_BYTES = 500 * 1024 * 1024


class GeminiOmniVideoModeFilter(BaseFilter):
    async def __call__(self, _event: Message | CallbackQuery, state: FSMContext) -> bool:
        data = await state.get_data()
        return data.get("model_key") == GEMINI_OMNI_VIDEO_MODEL and data.get("mode") == "video"


class GeminiOmniModelFilter(BaseFilter):
    async def __call__(self, _event: Message | CallbackQuery, state: FSMContext) -> bool:
        data = await state.get_data()
        return data.get("model_key") == GEMINI_OMNI_VIDEO_MODEL


def _media_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Готово", callback_data="omni_media:done"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _image_file_ids(data: dict) -> list[str]:
    values = [str(item) for item in (data.get("ref_file_ids") or []) if item]
    return list(dict.fromkeys(values))


def _image_count(data: dict) -> int:
    file_ids = _image_file_ids(data)
    if file_ids:
        return len(file_ids)
    image_url = data.get("image_url")
    if isinstance(image_url, list):
        return len([item for item in image_url if item])
    return 1 if image_url or data.get("image_file_id") else 0


def _character_count(data: dict) -> int:
    return len([item for item in (data.get("character_ids") or []) if item])


def _video_count(data: dict) -> int:
    return 1 if data.get("reference_video_url") else 0


def _used_slots(data: dict) -> int:
    return _image_count(data) + _video_count(data) * 2 + _character_count(data)


def _validate_quota(*, image_count: int, video_count: int, character_count: int) -> None:
    validate_gemini_omni_media_slots(
        image_count=image_count,
        video_count=video_count,
        character_count=character_count,
    )


def _quota_error(*, image_count: int, video_count: int, character_count: int) -> str:
    used = image_count + video_count * 2 + character_count
    return (
        "❌ Квота Gemini Omni превышена.\n\n"
        "Фото занимает 1 слот, видео — 2 слота, Character ID — 1 слот. "
        f"Всего доступно {GEMINI_OMNI_MAX_IMAGE_SLOTS}; сейчас получилось {used}."
    )


def _status_text(data: dict) -> str:
    images = _image_count(data)
    videos = _video_count(data)
    characters = _character_count(data)
    used = _used_slots(data)
    return (
        f"Видео: <b>{videos}/1</b> · Фото: <b>{images}</b> · "
        f"Character ID: <b>{characters}</b>\n"
        f"Квота медиа: <b>{used}/{GEMINI_OMNI_MAX_IMAGE_SLOTS}</b> слотов."
    )


def _document_kind(message: Message) -> str | None:
    document = message.document
    if document is None:
        return None
    suffix = Path(document.file_name or "").suffix.lower()
    mime = str(document.mime_type or "").lower()
    if suffix in _VIDEO_EXTENSIONS or mime.startswith("video/") or mime == "application/quicktime":
        return "video"
    if suffix in _IMAGE_EXTENSIONS or mime.startswith("image/"):
        return "image"
    return None


async def _store_video(
    *,
    message: Message,
    state: FSMContext,
    bot: Bot,
    file_id: str,
    duration: int | None,
    file_size: int | None,
) -> None:
    data = await state.get_data()
    if data.get("reference_video_url"):
        await message.answer("❌ Для Gemini Omni можно добавить только одно видео.", reply_markup=_media_keyboard())
        return
    if file_size and file_size > _MAX_VIDEO_BYTES:
        await message.answer("❌ Видео слишком большое. Максимум 500 МБ.", reply_markup=_media_keyboard())
        return

    image_count = _image_count(data)
    character_count = _character_count(data)
    try:
        _validate_quota(image_count=image_count, video_count=1, character_count=character_count)
    except ValueError:
        await message.answer(
            _quota_error(image_count=image_count, video_count=1, character_count=character_count),
            reply_markup=_media_keyboard(),
        )
        return

    video_url = await mirror_telegram_file(bot, file_id, is_video=True)
    clip_end = min(max(int(duration or 10), 1), 10)
    await state.update_data(
        reference_video_url=video_url,
        video_clip_start=0,
        video_clip_end=clip_end,
    )
    updated = await state.get_data()
    await message.answer(
        "✅ Видео добавлено. Можно добавить фото-референсы или завершить сбор.\n\n"
        f"{_status_text(updated)}",
        reply_markup=_media_keyboard(),
    )


async def _store_image(
    *,
    message: Message,
    state: FSMContext,
    file_id: str,
    file_size: int | None,
) -> None:
    if file_size and file_size > _MAX_IMAGE_BYTES:
        await message.answer("❌ Изображение слишком большое. Максимум 10 МБ.", reply_markup=_media_keyboard())
        return

    data = await state.get_data()
    existing = _image_file_ids(data)
    candidate = existing if file_id in existing else [*existing, file_id]
    video_count = _video_count(data)
    character_count = _character_count(data)
    try:
        _validate_quota(
            image_count=len(candidate),
            video_count=video_count,
            character_count=character_count,
        )
    except ValueError:
        await message.answer(
            _quota_error(
                image_count=len(candidate),
                video_count=video_count,
                character_count=character_count,
            ),
            reply_markup=_media_keyboard(),
        )
        return

    await state.update_data(
        image_file_id=candidate[0] if candidate else None,
        ref_file_ids=candidate,
        image_url=None,
    )
    updated = await state.get_data()
    await message.answer(
        "✅ Фото добавлено. Можно отправить ещё медиа или нажать «Готово».\n\n"
        f"{_status_text(updated)}",
        reply_markup=_media_keyboard(),
    )


@router.callback_query(
    VideoGenFSM.mode_select,
    F.data == f"vid_mode:video:{GEMINI_OMNI_VIDEO_MODEL}",
)
async def choose_gemini_omni_video_mode(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(
        model_key=GEMINI_OMNI_VIDEO_MODEL,
        mode="video",
        reference_video_url=None,
        video_clip_start=0,
        video_clip_end=None,
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        audio_ids=[],
        character_ids=[],
        seed=None,
    )
    await state.set_state(VideoGenFSM.image_upload)
    model_cost = await repo.get_model_cost(session, GEMINI_OMNI_VIDEO_MODEL)
    display_name = getattr(model_cost, "display_name", None) or "Gemini Omni Video"
    await safe_edit_message(
        call.message,
        f"🎞 <b>{display_name}</b> · видео + фото референсы\n\n"
        "Отправь <b>1 видео</b> (MP4/MOV) и, если нужно, добавь фото "
        "JPG/JPEG/PNG/WEBP. Видео занимает 2 слота, каждое фото — 1. "
        f"Общая квота вместе с Character ID: <b>{GEMINI_OMNI_MAX_IMAGE_SLOTS} слотов</b>.\n\n"
        "Можно присылать файлы по одному. Когда референсы собраны, нажми <b>✅ Готово</b>.",
        reply_markup=_media_keyboard(),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.image_upload, GeminiOmniVideoModeFilter(), F.video)
async def upload_gemini_omni_video(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    video = message.video
    if video is None:
        return
    await _store_video(
        message=message,
        state=state,
        bot=bot,
        file_id=video.file_id,
        duration=video.duration,
        file_size=video.file_size,
    )


@router.message(VideoGenFSM.image_upload, GeminiOmniVideoModeFilter(), F.photo)
async def upload_gemini_omni_photo(message: Message, state: FSMContext) -> None:
    photos = message.photo or []
    if not photos:
        return
    best = max(photos, key=lambda item: item.file_size or 0)
    await _store_image(
        message=message,
        state=state,
        file_id=best.file_id,
        file_size=best.file_size,
    )


@router.message(VideoGenFSM.image_upload, GeminiOmniVideoModeFilter(), F.document)
async def upload_gemini_omni_document(
    message: Message,
    state: FSMContext,
    bot: Bot,
) -> None:
    document = message.document
    if document is None:
        return
    kind = _document_kind(message)
    if kind == "video":
        await _store_video(
            message=message,
            state=state,
            bot=bot,
            file_id=document.file_id,
            duration=None,
            file_size=document.file_size,
        )
        return
    if kind == "image":
        await _store_image(
            message=message,
            state=state,
            file_id=document.file_id,
            file_size=document.file_size,
        )
        return
    await message.answer(
        "❌ Нужен MP4/MOV или изображение JPG/JPEG/PNG/WEBP.",
        reply_markup=_media_keyboard(),
    )


@router.callback_query(
    VideoGenFSM.image_upload,
    GeminiOmniVideoModeFilter(),
    F.data == "omni_media:done",
)
async def finish_gemini_omni_media(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    if not data.get("reference_video_url"):
        await safe_answer_callback(call, "Сначала загрузи видео", show_alert=True)
        return
    try:
        _validate_quota(
            image_count=_image_count(data),
            video_count=1,
            character_count=_character_count(data),
        )
    except ValueError:
        await safe_answer_callback(call, "Превышена квота медиа Gemini Omni", show_alert=True)
        return

    from bot.handlers import video_gen as legacy

    model_cost = await repo.get_model_cost(session, GEMINI_OMNI_VIDEO_MODEL)
    display_name = getattr(model_cost, "display_name", None) or "Gemini Omni Video"
    await state.set_state(VideoGenFSM.params_select)
    updated = await state.get_data()
    await safe_edit_message(
        call.message,
        f"✅ Референсы сохранены.\n{_status_text(updated)}\n\n"
        f"⚙️ <b>Параметры</b> · {display_name}\n"
        f"{legacy._video_params_hint(GEMINI_OMNI_VIDEO_MODEL, updated)}",
        reply_markup=legacy._video_params_reply_markup(GEMINI_OMNI_VIDEO_MODEL, updated),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.omni_ids_input, GeminiOmniModelFilter(), F.text)
async def handle_gemini_omni_ids_with_quota(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    if data.get("omni_input_target") == "character":
        raw = (message.text or "").strip()
        try:
            character_ids = [] if raw == "-" else normalize_gemini_omni_ids(
                raw,
                max_items=3,
                field_name="character_ids",
            )
            _validate_quota(
                image_count=_image_count(data),
                video_count=_video_count(data),
                character_count=len(character_ids),
            )
        except ValueError:
            await message.answer(
                _quota_error(
                    image_count=_image_count(data),
                    video_count=_video_count(data),
                    character_count=len(character_ids) if "character_ids" in locals() else 4,
                ),
                reply_markup=_media_keyboard(),
            )
            return

    from bot.handlers import video_gen as legacy

    await legacy.handle_omni_ids_input(message, state, session)
