from __future__ import annotations

import asyncio
import html
import json
import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api import polling
from api.higgsfield_seedance25_edit import (
    BITRATE_MODES,
    MAX_AUDIO_REFS,
    MAX_IMAGE_REFS,
    MAX_VIDEO_REFS,
    RESOLUTIONS,
    build_video_edit_payload,
    create_video_edit_task,
    is_configured,
    poll_video_edit,
)
from api.public_files import mirror_telegram_file, save_public_file
from bot.filters.admin import IsAdmin
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="higgsfield_seedance25_edit_test")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_DEFAULT_PROMPT = (
    "Use @Image1 as the identity reference for the main character. "
    "Replace only the main character in the source video with the person from @Image1. "
    "Preserve the person's facial identity, facial proportions, skin tone, hairstyle and body appearance "
    "from the reference images. Preserve the source motion, performance, camera movement, timing, "
    "composition, background and lighting. Do not replace other people."
)


class HiggsfieldSeedance25FSM(StatesGroup):
    dashboard = State()
    awaiting_prompt = State()
    awaiting_source_video = State()
    awaiting_image_ref = State()
    awaiting_video_ref = State()
    awaiting_audio_ref = State()


def _initial_data() -> dict[str, Any]:
    return {
        "hf25_mode": "video-edit",
        "hf25_prompt": _DEFAULT_PROMPT,
        "hf25_source_video_url": None,
        "hf25_image_urls": [],
        "hf25_video_urls": [],
        "hf25_audio_urls": [],
        "hf25_resolution": "720p",
        "hf25_bitrate_mode": "high",
        "hf25_generate_audio": True,
        "hf25_last_task_id": None,
    }


async def _data(state: FSMContext) -> dict[str, Any]:
    data = await state.get_data()
    if data.get("hf25_mode") != "video-edit":
        defaults = _initial_data()
        await state.clear()
        await state.update_data(**defaults)
        return defaults
    return data


def _values(data: dict[str, Any], key: str) -> list[str]:
    raw = data.get(key) or []
    return [str(value).strip() for value in raw if str(value or "").strip()]


def _clip(value: Any, limit: int = 700) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dashboard_text(data: dict[str, Any]) -> str:
    images = _values(data, "hf25_image_urls")
    videos = _values(data, "hf25_video_urls")
    audios = _values(data, "hf25_audio_urls")
    return (
        "🧬 <b>Higgsfield · Seedance 2.5 Video Edit</b>\n\n"
        "Изолированный админский тест качества замены персонажа. "
        "Боевой Seedance/KIE routing не меняется, APIX-кредиты не списываются; "
        "платный запуск расходует только баланс Higgsfield.\n\n"
        f"🔑 Higgsfield: <b>{'✅ настроен' if is_configured() else '❌ ключ не настроен'}</b>\n"
        f"🎞 Исходное видео: <b>{'✅ загружено' if data.get('hf25_source_video_url') else '❌ нужно загрузить'}</b>\n"
        f"🖼 Identity refs: <b>{len(images)}/{MAX_IMAGE_REFS}</b>\n"
        f"🎥 Доп. video refs: <b>{len(videos)}/{MAX_VIDEO_REFS}</b>\n"
        f"🎵 Audio refs: <b>{len(audios)}/{MAX_AUDIO_REFS}</b>\n"
        f"📺 Resolution: <b>{html.escape(str(data.get('hf25_resolution') or '720p'))}</b>\n"
        f"📦 Bitrate: <b>{html.escape(str(data.get('hf25_bitrate_mode') or 'high'))}</b>\n"
        f"🔊 Generate audio: <b>{'ON' if data.get('hf25_generate_audio') else 'OFF'}</b>\n\n"
        "Для проверки identity первым референсом лучше загрузить чистый фронтальный портрет, "
        "затем при необходимости 3/4 и общий план отдельными файлами.\n\n"
        f"✍️ <b>Prompt</b>\n{html.escape(_clip(data.get('hf25_prompt')))}"
        + (
            f"\n\nПоследний task: <code>{html.escape(str(data['hf25_last_task_id']))}</code>"
            if data.get("hf25_last_task_id")
            else ""
        )
    )


def _dashboard_kb(data: dict[str, Any]):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✍️ Промпт", callback_data="hfs25:prompt"))
    b.row(
        InlineKeyboardButton(
            text="🎞 Исходное видео" + (" ✅" if data.get("hf25_source_video_url") else ""),
            callback_data="hfs25:source",
        )
    )
    b.row(
        InlineKeyboardButton(
            text=f"🖼 Identity refs · {len(_values(data, 'hf25_image_urls'))}",
            callback_data="hfs25:images",
        )
    )
    b.row(
        InlineKeyboardButton(
            text=f"🎥 Доп. видео · {len(_values(data, 'hf25_video_urls'))}",
            callback_data="hfs25:videos",
        ),
        InlineKeyboardButton(
            text=f"🎵 Аудио · {len(_values(data, 'hf25_audio_urls'))}",
            callback_data="hfs25:audios",
        ),
    )
    b.row(
        InlineKeyboardButton(
            text=f"📺 {data.get('hf25_resolution') or '720p'}",
            callback_data="hfs25:resolution",
        ),
        InlineKeyboardButton(
            text=f"📦 {data.get('hf25_bitrate_mode') or 'high'}",
            callback_data="hfs25:bitrate",
        ),
    )
    b.row(
        InlineKeyboardButton(
            text=f"🔊 Audio {'ON' if data.get('hf25_generate_audio') else 'OFF'}",
            callback_data="hfs25:audio:toggle",
        )
    )
    b.row(InlineKeyboardButton(text="📋 Итоговый payload", callback_data="hfs25:payload"))
    b.row(InlineKeyboardButton(text="🚀 Запустить платный тест", callback_data="hfs25:run"))
    b.row(
        InlineKeyboardButton(text="♻️ Сбросить", callback_data="hfs25:reset"),
        InlineKeyboardButton(text="🧪 Другие модели", callback_data="nxt:model:choose"),
    )
    b.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return b.as_markup()


def _back(clear_callback: str | None = None):
    b = InlineKeyboardBuilder()
    if clear_callback:
        b.row(InlineKeyboardButton(text="🗑 Очистить", callback_data=clear_callback))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="hfs25:dashboard"))
    return b.as_markup()


async def _show_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(HiggsfieldSeedance25FSM.dashboard)
    await safe_edit_message(message, _dashboard_text(data), reply_markup=_dashboard_kb(data))


async def _answer_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(HiggsfieldSeedance25FSM.dashboard)
    await message.answer(_dashboard_text(data), reply_markup=_dashboard_kb(data))


async def _download_document(bot: Bot, message: Message) -> tuple[bytes, str] | None:
    document = message.document
    if not document:
        return None
    telegram_file = await bot.get_file(document.file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    return raw, str(document.mime_type or "application/octet-stream")


async def _append_url(state: FSMContext, key: str, url: str, limit: int) -> None:
    data = await _data(state)
    values = _values(data, key)
    if url not in values:
        values.append(url)
    if len(values) > limit:
        raise ValueError(f"Лимит — {limit}")
    await state.update_data(**{key: values})


def _current_payload(data: dict[str, Any]) -> dict[str, Any]:
    return build_video_edit_payload(
        prompt=str(data.get("hf25_prompt") or ""),
        video_url=str(data.get("hf25_source_video_url") or ""),
        image_urls=_values(data, "hf25_image_urls"),
        video_urls=_values(data, "hf25_video_urls"),
        audio_urls=_values(data, "hf25_audio_urls"),
        resolution=str(data.get("hf25_resolution") or "720p"),
        bitrate_mode=str(data.get("hf25_bitrate_mode") or "high"),
        generate_audio=bool(data.get("hf25_generate_audio", True)),
    )


@router.callback_query(F.data == "nxt:model:hf-seedance25-edit")
async def open_lab(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**_initial_data())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:dashboard")
async def dashboard(call: CallbackQuery, state: FSMContext) -> None:
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:reset")
async def reset(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**_initial_data())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Video Edit lab сброшен")


@router.callback_query(F.data == "hfs25:prompt")
async def prompt_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(HiggsfieldSeedance25FSM.awaiting_prompt)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "✍️ <b>Prompt</b>\n\nПришли новый промпт. Для identity-теста указывай @Image1 как основной референс персонажа.",
        reply_markup=_back(),
    )
    await safe_answer_callback(call)


@router.message(HiggsfieldSeedance25FSM.awaiting_prompt, F.text)
async def prompt_save(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    if not value:
        await message.answer("Промпт не может быть пустым.")
        return
    await state.update_data(hf25_prompt=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "hfs25:source")
async def source_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(HiggsfieldSeedance25FSM.awaiting_source_video)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎞 <b>Исходное видео</b>\n\nПришли короткий MP4/MOV ролик или публичный HTTP(S) URL. "
        "Для первого identity-теста лучше 4–6 секунд.",
        reply_markup=_back("hfs25:source:clear"),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:source:clear")
async def source_clear(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(hf25_source_video_url=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Исходное видео очищено")


@router.message(HiggsfieldSeedance25FSM.awaiting_source_video, F.video)
async def source_video(message: Message, state: FSMContext, bot: Bot) -> None:
    media = message.video
    assert media is not None
    duration = float(media.duration or 0)
    if duration and not 4 <= duration <= 30:
        await message.answer("Для теста используй исходное видео от 4 до 30 секунд.")
        return
    url = await mirror_telegram_file(bot, media.file_id, is_video=True)
    await state.update_data(hf25_source_video_url=url)
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_source_video, F.document)
async def source_document(message: Message, state: FSMContext, bot: Bot) -> None:
    mime = str(message.document.mime_type or "").lower() if message.document else ""
    if not mime.startswith("video/"):
        await message.answer("Нужен video-документ.")
        return
    item = await _download_document(bot, message)
    assert item is not None
    raw, mime = item
    url = save_public_file(raw, mime, subdir="higgsfield-seedance25/source")
    await state.update_data(hf25_source_video_url=url)
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_source_video, F.text)
async def source_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_video_edit_payload(prompt="validate", video_url=value)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await state.update_data(hf25_source_video_url=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "hfs25:images")
async def images_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(HiggsfieldSeedance25FSM.awaiting_image_ref)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🖼 <b>Identity refs</b> · {len(_values(data, 'hf25_image_urls'))}/{MAX_IMAGE_REFS}\n\n"
        "Пришли фото, image-документ или публичный URL. Загружай отдельными файлами: "
        "сначала чистый фронтальный портрет, затем дополнительные ракурсы.",
        reply_markup=_back("hfs25:images:clear"),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:images:clear")
async def images_clear(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(hf25_image_urls=[])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Identity refs очищены")


@router.message(HiggsfieldSeedance25FSM.awaiting_image_ref, F.photo)
async def image_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    url = await mirror_telegram_file(bot, best.file_id)
    try:
        await _append_url(state, "hf25_image_urls", url, MAX_IMAGE_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_image_ref, F.document)
async def image_document(message: Message, state: FSMContext, bot: Bot) -> None:
    mime = str(message.document.mime_type or "").lower() if message.document else ""
    if not mime.startswith("image/"):
        await message.answer("Нужен image-документ.")
        return
    item = await _download_document(bot, message)
    assert item is not None
    raw, mime = item
    url = save_public_file(raw, mime, subdir="higgsfield-seedance25/images")
    try:
        await _append_url(state, "hf25_image_urls", url, MAX_IMAGE_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_image_ref, F.text)
async def image_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_video_edit_payload(
            prompt="validate",
            video_url="https://example.test/source.mp4",
            image_urls=[value],
        )
        await _append_url(state, "hf25_image_urls", value, MAX_IMAGE_REFS)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "hfs25:videos")
async def videos_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(HiggsfieldSeedance25FSM.awaiting_video_ref)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🎥 <b>Дополнительные video refs</b> · {len(_values(data, 'hf25_video_urls'))}/{MAX_VIDEO_REFS}\n\n"
        "Опционально: пришли видео, video-документ или публичный URL.",
        reply_markup=_back("hfs25:videos:clear"),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:videos:clear")
async def videos_clear(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(hf25_video_urls=[])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Дополнительные видео очищены")


@router.message(HiggsfieldSeedance25FSM.awaiting_video_ref, F.video)
async def video_ref(message: Message, state: FSMContext, bot: Bot) -> None:
    media = message.video
    assert media is not None
    url = await mirror_telegram_file(bot, media.file_id, is_video=True)
    try:
        await _append_url(state, "hf25_video_urls", url, MAX_VIDEO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_video_ref, F.document)
async def video_ref_document(message: Message, state: FSMContext, bot: Bot) -> None:
    mime = str(message.document.mime_type or "").lower() if message.document else ""
    if not mime.startswith("video/"):
        await message.answer("Нужен video-документ.")
        return
    item = await _download_document(bot, message)
    assert item is not None
    raw, mime = item
    url = save_public_file(raw, mime, subdir="higgsfield-seedance25/videos")
    try:
        await _append_url(state, "hf25_video_urls", url, MAX_VIDEO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_video_ref, F.text)
async def video_ref_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_video_edit_payload(
            prompt="validate",
            video_url="https://example.test/source.mp4",
            video_urls=[value],
        )
        await _append_url(state, "hf25_video_urls", value, MAX_VIDEO_REFS)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "hfs25:audios")
async def audios_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(HiggsfieldSeedance25FSM.awaiting_audio_ref)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🎵 <b>Audio refs</b> · {len(_values(data, 'hf25_audio_urls'))}/{MAX_AUDIO_REFS}\n\n"
        "Опционально: пришли audio/voice, audio-документ или публичный URL.",
        reply_markup=_back("hfs25:audios:clear"),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:audios:clear")
async def audios_clear(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(hf25_audio_urls=[])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Audio refs очищены")


@router.message(HiggsfieldSeedance25FSM.awaiting_audio_ref, F.audio | F.voice)
async def audio_ref(message: Message, state: FSMContext, bot: Bot) -> None:
    media = message.audio or message.voice
    assert media is not None
    telegram_file = await bot.get_file(media.file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    mime = str(getattr(media, "mime_type", "") or "audio/ogg")
    url = save_public_file(raw, mime, subdir="higgsfield-seedance25/audio")
    try:
        await _append_url(state, "hf25_audio_urls", url, MAX_AUDIO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_audio_ref, F.document)
async def audio_ref_document(message: Message, state: FSMContext, bot: Bot) -> None:
    mime = str(message.document.mime_type or "").lower() if message.document else ""
    if not mime.startswith("audio/"):
        await message.answer("Нужен audio-документ.")
        return
    item = await _download_document(bot, message)
    assert item is not None
    raw, mime = item
    url = save_public_file(raw, mime, subdir="higgsfield-seedance25/audio")
    try:
        await _append_url(state, "hf25_audio_urls", url, MAX_AUDIO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(HiggsfieldSeedance25FSM.awaiting_audio_ref, F.text)
async def audio_ref_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_video_edit_payload(
            prompt="validate",
            video_url="https://example.test/source.mp4",
            audio_urls=[value],
        )
        await _append_url(state, "hf25_audio_urls", value, MAX_AUDIO_REFS)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "hfs25:resolution")
async def resolution_menu(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    for value in RESOLUTIONS:
        b.button(text=value, callback_data=f"hfs25:resolution:{value}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="hfs25:dashboard"))
    await safe_edit_message(call.message, "📺 <b>Resolution</b>", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("hfs25:resolution:"))
async def resolution_set(call: CallbackQuery, state: FSMContext) -> None:
    value = str(call.data or "").rsplit(":", 1)[-1]
    if value not in RESOLUTIONS:
        await safe_answer_callback(call, "Неизвестное resolution", show_alert=True)
        return
    await state.update_data(hf25_resolution=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:bitrate")
async def bitrate_menu(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    for value in BITRATE_MODES:
        b.button(text=value, callback_data=f"hfs25:bitrate:{value}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="hfs25:dashboard"))
    await safe_edit_message(call.message, "📦 <b>Bitrate mode</b>", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("hfs25:bitrate:"))
async def bitrate_set(call: CallbackQuery, state: FSMContext) -> None:
    value = str(call.data or "").rsplit(":", 1)[-1]
    if value not in BITRATE_MODES:
        await safe_answer_callback(call, "Неизвестный bitrate", show_alert=True)
        return
    await state.update_data(hf25_bitrate_mode=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:audio:toggle")
async def audio_toggle(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.update_data(
        hf25_generate_audio=not bool(data.get("hf25_generate_audio", True))
    )
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:payload")
async def payload_preview(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    try:
        payload = _current_payload(data)
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📋 <b>Higgsfield payload</b>\n\n"
        f"<pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2)[:3500])}</pre>",
        reply_markup=_back(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "hfs25:run")
async def run(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    if not is_configured():
        await safe_answer_callback(call, "На сервере нет HIGGSFIELD_CREDENTIALS", show_alert=True)
        return
    if not _values(data, "hf25_image_urls"):
        await safe_answer_callback(
            call,
            "Для identity-теста добавь хотя бы один фото-референс.",
            show_alert=True,
        )
        return
    try:
        payload = _current_payload(data)
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return

    await safe_answer_callback(call, "Платный Higgsfield Video Edit test запущен")
    status_message = await call.message.answer(  # type: ignore[union-attr]
        "🧬 <b>Seedance 2.5 Video Edit</b>\n\nОтправляю задачу в Higgsfield…"
    )
    try:
        task_id = await create_video_edit_task(**payload)
    except Exception as exc:
        logger.exception("Higgsfield Seedance 2.5 Video Edit submit failed")
        await status_message.edit_text(
            "❌ Не удалось запустить Video Edit.\n\n" + html.escape(str(exc)),
            reply_markup=_dashboard_kb(data),
        )
        return

    await state.update_data(hf25_last_task_id=task_id)
    result_markup = _dashboard_kb({**data, "hf25_last_task_id": task_id})
    await status_message.edit_text(
        "🧬 <b>Seedance 2.5 Video Edit</b>\n\n"
        f"✅ Task: <code>{html.escape(task_id)}</code>\n"
        "⏳ Жду результат…"
    )
    logger.info(
        "Higgsfield Seedance 2.5 admin lab started task=%s images=%d videos=%d audios=%d resolution=%s bitrate=%s",
        task_id,
        len(payload.get("image_urls") or []),
        len(payload.get("video_urls") or []),
        len(payload.get("audio_urls") or []),
        payload["resolution"],
        payload["bitrate_mode"],
    )

    async def on_success(url: str) -> None:
        try:
            await call.message.answer_video(  # type: ignore[union-attr]
                URLInputFile(url, filename="seedance-2.5-video-edit.mp4"),
                caption="✅ <b>Seedance 2.5 Video Edit</b> · Higgsfield test",
                supports_streaming=True,
            )
        except Exception as exc:
            logger.warning("Higgsfield Seedance edit result delivery failed: %s", exc)
            await call.message.answer(  # type: ignore[union-attr]
                "✅ Результат готов:\n" + html.escape(url)
            )
        await status_message.edit_text(
            "✅ <b>Seedance 2.5 Video Edit completed</b>\n\n"
            f"Task: <code>{html.escape(task_id)}</code>",
            reply_markup=result_markup,
        )

    async def on_failure(error: str) -> None:
        await status_message.edit_text(
            "❌ <b>Seedance 2.5 Video Edit failed</b>\n\n"
            f"Task: <code>{html.escape(task_id)}</code>\n"
            f"{html.escape(error)}",
            reply_markup=result_markup,
        )

    asyncio.create_task(
        polling.poll_until_done(
            task_id,
            poll_video_edit,
            on_success,
            on_failure,
            provider="higgsfield",
        )
    )
