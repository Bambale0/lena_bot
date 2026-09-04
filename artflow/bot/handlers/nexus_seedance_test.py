from __future__ import annotations

import html
import json
import logging
import os
import uuid
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.nexusapi_client import (
    NEXUS_SEEDANCE25_ASPECT_RATIOS,
    NEXUS_SEEDANCE25_MAX_AUDIO_REFS,
    NEXUS_SEEDANCE25_MAX_IMAGE_REFS,
    NEXUS_SEEDANCE25_MAX_VIDEO_REFS,
    NEXUS_SEEDANCE25_MODEL,
    NEXUS_SEEDANCE25_RESOLUTIONS,
    NexusApiClient,
    NexusApiError,
    NexusApiTimeout,
    build_seedance25_params,
    extract_result_urls,
    find_model_in_catalog,
    pretty_json,
)
from api.public_files import mirror_telegram_file, save_public_file
from bot.filters.admin import IsAdmin
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message

logger = logging.getLogger(__name__)
router = Router(name="nexusapi_seedance25_test")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_DEFAULT_PROMPT = "Cinematic realistic shot of a cyclist moving through a rainy neon city at night, natural motion, coherent camera movement"
_DURATION_PRESETS = (4, 5, 10, 15, 30)


class Seedance25TestFSM(StatesGroup):
    dashboard = State()
    awaiting_prompt = State()
    awaiting_duration = State()
    awaiting_seed = State()
    awaiting_image_ref = State()
    awaiting_video_ref = State()
    awaiting_audio_ref = State()
    awaiting_start_frame = State()
    awaiting_end_frame = State()
    awaiting_webhook = State()
    awaiting_overrides = State()


def _new_key() -> str:
    return str(uuid.uuid4())


def _initial_data() -> dict[str, Any]:
    return {
        "s25_model": NEXUS_SEEDANCE25_MODEL,
        "s25_prompt": _DEFAULT_PROMPT,
        "s25_duration": 4,
        "s25_aspect_ratio": "adaptive",
        "s25_resolution": "480p",
        "s25_seed": None,
        "s25_generate_audio": True,
        "s25_content_filter": False,
        "s25_image_urls": [],
        "s25_video_urls": [],
        "s25_audio_urls": [],
        "s25_start_image_url": None,
        "s25_end_image_url": None,
        "s25_webhook_url": None,
        "s25_overrides": {},
        "s25_idempotency_key": _new_key(),
        "s25_last_task_id": None,
    }


async def _data(state: FSMContext) -> dict[str, Any]:
    data = await state.get_data()
    if data.get("s25_model") != NEXUS_SEEDANCE25_MODEL:
        defaults = _initial_data()
        await state.clear()
        await state.update_data(**defaults)
        return defaults
    if not data.get("s25_idempotency_key"):
        key = _new_key()
        await state.update_data(s25_idempotency_key=key)
        data = {**data, "s25_idempotency_key": key}
    return data


async def _change_request(state: FSMContext, **changes: Any) -> None:
    await state.update_data(**changes, s25_idempotency_key=_new_key())


def _list(data: dict[str, Any], key: str) -> list[str]:
    values = data.get(key) or []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _overrides(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("s25_overrides")
    return dict(value) if isinstance(value, dict) else {}


def _clip(value: Any, limit: int = 420) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _dashboard_text(data: dict[str, Any]) -> str:
    client = NexusApiClient()
    images = _list(data, "s25_image_urls")
    videos = _list(data, "s25_video_urls")
    audios = _list(data, "s25_audio_urls")
    key_state = "✅ настроен" if client.configured else "❌ NEXUS_API_KEY не задан"
    frames = "—"
    if data.get("s25_start_image_url") and data.get("s25_end_image_url"):
        frames = "✅ start + end"
    elif data.get("s25_start_image_url") or data.get("s25_end_image_url"):
        frames = "⚠️ нужен второй кадр"
    text = (
        "🎬 <b>NexusAPI · Seedance 2.5 Lab</b>\n\n"
        "Админский тест провайдера. APIX-кредиты не списываются; платный запуск расходует только баланс NexusAPI.\n\n"
        f"🔑 Key: <b>{key_state}</b>\n"
        f"🤖 Model: <code>{NEXUS_SEEDANCE25_MODEL}</code>\n"
        f"⏱ Duration: <b>{data.get('s25_duration')} сек</b>\n"
        f"📐 Ratio: <b>{html.escape(str(data.get('s25_aspect_ratio')))}</b>\n"
        f"📺 Resolution: <b>{html.escape(str(data.get('s25_resolution')))}</b>\n"
        f"🎲 Seed: <b>{html.escape(str(data.get('s25_seed') if data.get('s25_seed') is not None else 'Auto'))}</b>\n"
        f"🔊 Generate audio: <b>{'ON' if data.get('s25_generate_audio') else 'OFF'}</b>\n"
        f"🛡 Content filter: <b>{'ON' if data.get('s25_content_filter') else 'OFF'}</b>\n"
        f"🖼 Image refs: <b>{len(images)}/{NEXUS_SEEDANCE25_MAX_IMAGE_REFS}</b>\n"
        f"🎥 Video refs: <b>{len(videos)}/{NEXUS_SEEDANCE25_MAX_VIDEO_REFS}</b>\n"
        f"🎵 Audio refs: <b>{len(audios)}/{NEXUS_SEEDANCE25_MAX_AUDIO_REFS}</b>\n"
        f"🎞 First/last: <b>{frames}</b>\n"
        f"🧰 Overrides: <b>{len(_overrides(data))} полей</b>\n"
        f"🛡 Request ID: <code>{html.escape(str(data.get('s25_idempotency_key') or ''))}</code>\n\n"
        f"✍️ <b>Prompt</b>\n{html.escape(_clip(data.get('s25_prompt'), 700))}"
    )
    if data.get("s25_last_task_id"):
        text += f"\n\nПоследний task: <code>{html.escape(str(data['s25_last_task_id']))}</code>"
    return text


def _dashboard_kb(data: dict[str, Any]):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✍️ Промпт", callback_data="ns25:prompt"))
    b.row(
        InlineKeyboardButton(text=f"⏱ {data.get('s25_duration')} сек", callback_data="ns25:duration"),
        InlineKeyboardButton(text=f"📺 {data.get('s25_resolution')}", callback_data="ns25:resolution"),
    )
    b.row(
        InlineKeyboardButton(text=f"📐 {data.get('s25_aspect_ratio')}", callback_data="ns25:ratio"),
        InlineKeyboardButton(text=f"🎲 {data.get('s25_seed') if data.get('s25_seed') is not None else 'Auto'}", callback_data="ns25:seed"),
    )
    b.row(
        InlineKeyboardButton(text=f"🔊 Audio {'ON' if data.get('s25_generate_audio') else 'OFF'}", callback_data="ns25:audio:toggle"),
        InlineKeyboardButton(text=f"🛡 Filter {'ON' if data.get('s25_content_filter') else 'OFF'}", callback_data="ns25:filter:toggle"),
    )
    b.row(
        InlineKeyboardButton(text=f"🖼 Фото {len(_list(data, 's25_image_urls'))}", callback_data="ns25:images"),
        InlineKeyboardButton(text=f"🎥 Видео {len(_list(data, 's25_video_urls'))}", callback_data="ns25:videos"),
        InlineKeyboardButton(text=f"🎵 Аудио {len(_list(data, 's25_audio_urls'))}", callback_data="ns25:audios"),
    )
    b.row(
        InlineKeyboardButton(text="🎞 Start frame", callback_data="ns25:start"),
        InlineKeyboardButton(text="🎞 End frame", callback_data="ns25:end"),
    )
    b.row(
        InlineKeyboardButton(text="🧬 Live OpenAPI", callback_data="ns25:schema"),
        InlineKeyboardButton(text="💰 Live каталог", callback_data="ns25:catalog"),
    )
    b.row(
        InlineKeyboardButton(text="🧰 Raw overrides", callback_data="ns25:overrides"),
        InlineKeyboardButton(text="📋 Итоговый payload", callback_data="ns25:payload"),
    )
    if data.get("s25_last_task_id"):
        b.row(InlineKeyboardButton(text="🔎 Статус task", callback_data="ns25:status"))
    b.row(InlineKeyboardButton(text="🚀 Запустить платный тест", callback_data="ns25:run"))
    b.row(
        InlineKeyboardButton(text="🆕 Новый Request ID", callback_data="ns25:newkey"),
        InlineKeyboardButton(text="♻️ Сбросить", callback_data="ns25:reset"),
    )
    b.row(
        InlineKeyboardButton(text="🧪 Другие модели", callback_data="nxt:model:choose"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    )
    return b.as_markup()


def _back():
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ns25:dashboard"))
    return b.as_markup()


def _clear_back(clear_callback: str):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 Очистить", callback_data=clear_callback))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ns25:dashboard"))
    return b.as_markup()


async def _show_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(Seedance25TestFSM.dashboard)
    await safe_edit_message(message, _dashboard_text(data), reply_markup=_dashboard_kb(data))


async def _answer_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(Seedance25TestFSM.dashboard)
    await message.answer(_dashboard_text(data), reply_markup=_dashboard_kb(data))


def _current_params(data: dict[str, Any]) -> dict[str, Any]:
    return build_seedance25_params(
        prompt=str(data.get("s25_prompt") or ""),
        duration=int(data.get("s25_duration") or 4),
        aspect_ratio=str(data.get("s25_aspect_ratio") or "adaptive"),
        resolution=str(data.get("s25_resolution") or "480p"),
        seed=data.get("s25_seed"),
        generate_audio=bool(data.get("s25_generate_audio", True)),
        content_filter=bool(data.get("s25_content_filter", False)),
        image_urls=_list(data, "s25_image_urls"),
        video_urls=_list(data, "s25_video_urls"),
        audio_urls=_list(data, "s25_audio_urls"),
        start_image_url=data.get("s25_start_image_url"),
        end_image_url=data.get("s25_end_image_url"),
        webhook_url=data.get("s25_webhook_url"),
        extra_params=_overrides(data),
    )


@router.callback_query(F.data == "nxt:model:seedance25")
async def open_seedance25(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**_initial_data())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:dashboard")
async def dashboard(call: CallbackQuery, state: FSMContext) -> None:
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:newkey")
async def new_key(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(s25_idempotency_key=_new_key())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Новый Request ID")


@router.callback_query(F.data == "ns25:reset")
async def reset(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.update_data(**_initial_data())
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Seedance lab сброшен")


@router.callback_query(F.data == "ns25:prompt")
async def prompt_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Seedance25TestFSM.awaiting_prompt)
    await safe_edit_message(call.message, "✍️ <b>Prompt</b>\n\nПришли промпт до 5000 символов.", reply_markup=_back())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(Seedance25TestFSM.awaiting_prompt, F.text)
async def prompt_save(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    if not value or len(value) > 5000:
        await message.answer("Промпт должен содержать 1–5000 символов.")
        return
    await _change_request(state, s25_prompt=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "ns25:duration")
async def duration_menu(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    for value in _DURATION_PRESETS:
        b.button(text=f"{value} сек", callback_data=f"ns25:duration:{value}")
    b.adjust(3, 2)
    b.row(InlineKeyboardButton(text="✍️ Любые 4–30 сек", callback_data="ns25:duration:custom"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ns25:dashboard"))
    await safe_edit_message(call.message, "⏱ <b>Duration</b> · live schema: 4–30 секунд.", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("ns25:duration:"))
async def duration_set(call: CallbackQuery, state: FSMContext) -> None:
    raw = str(call.data or "").rsplit(":", 1)[-1]
    if raw == "custom":
        await state.set_state(Seedance25TestFSM.awaiting_duration)
        await safe_edit_message(call.message, "Пришли целое число секунд от 4 до 30.", reply_markup=_back())  # type: ignore[arg-type]
        await safe_answer_callback(call)
        return
    value = int(raw)
    await _change_request(state, s25_duration=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(Seedance25TestFSM.awaiting_duration, F.text)
async def duration_custom(message: Message, state: FSMContext) -> None:
    try:
        value = int(str(message.text or "").strip())
    except ValueError:
        await message.answer("Нужно целое число от 4 до 30.")
        return
    if value < 4 or value > 30:
        await message.answer("Seedance 2.5 принимает 4–30 секунд.")
        return
    await _change_request(state, s25_duration=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "ns25:resolution")
async def resolution_menu(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    for value in NEXUS_SEEDANCE25_RESOLUTIONS:
        b.button(text=value, callback_data=f"ns25:resolution:{value}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ns25:dashboard"))
    await safe_edit_message(call.message, "📺 <b>Resolution</b>", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("ns25:resolution:"))
async def resolution_set(call: CallbackQuery, state: FSMContext) -> None:
    value = str(call.data or "").rsplit(":", 1)[-1]
    if value not in NEXUS_SEEDANCE25_RESOLUTIONS:
        await safe_answer_callback(call, "Неизвестное resolution", show_alert=True)
        return
    await _change_request(state, s25_resolution=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:ratio")
async def ratio_menu(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    for value in NEXUS_SEEDANCE25_ASPECT_RATIOS:
        key = value.replace(":", "x")
        b.button(text=value, callback_data=f"ns25:ratio:{key}")
    b.adjust(2, 2, 2, 1)
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ns25:dashboard"))
    await safe_edit_message(call.message, "📐 <b>Aspect ratio</b>", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("ns25:ratio:"))
async def ratio_set(call: CallbackQuery, state: FSMContext) -> None:
    raw = str(call.data or "").rsplit(":", 1)[-1]
    value = raw.replace("x", ":") if raw != "adaptive" else raw
    if value not in NEXUS_SEEDANCE25_ASPECT_RATIOS:
        await safe_answer_callback(call, "Неизвестный ratio", show_alert=True)
        return
    await _change_request(state, s25_aspect_ratio=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:seed")
async def seed_menu(call: CallbackQuery) -> None:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎲 Auto / omit", callback_data="ns25:seed:auto"))
    b.row(InlineKeyboardButton(text="✍️ Ввести seed", callback_data="ns25:seed:custom"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="ns25:dashboard"))
    await safe_edit_message(call.message, "🎲 <b>Seed</b> · live schema: -1…2147483647.", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:seed:auto")
async def seed_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, s25_seed=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:seed:custom")
async def seed_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Seedance25TestFSM.awaiting_seed)
    await safe_edit_message(call.message, "Пришли seed от -1 до 2147483647.", reply_markup=_back())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(Seedance25TestFSM.awaiting_seed, F.text)
async def seed_save(message: Message, state: FSMContext) -> None:
    try:
        value = int(str(message.text or "").strip())
    except ValueError:
        await message.answer("Нужен целый seed.")
        return
    if value < -1 or value > 2147483647:
        await message.answer("Seed вне диапазона -1…2147483647.")
        return
    await _change_request(state, s25_seed=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "ns25:audio:toggle")
async def audio_toggle(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await _change_request(state, s25_generate_audio=not bool(data.get("s25_generate_audio", True)))
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:filter:toggle")
async def filter_toggle(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await _change_request(state, s25_content_filter=not bool(data.get("s25_content_filter", False)))
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


async def _download_document(bot: Bot, message: Message) -> tuple[bytes, str] | None:
    doc = message.document
    if not doc:
        return None
    tg_file = await bot.get_file(doc.file_id)
    downloaded = await bot.download_file(tg_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    return raw, str(doc.mime_type or "application/octet-stream")


async def _add_url(state: FSMContext, key: str, url: str, limit: int) -> None:
    data = await _data(state)
    values = _list(data, key)
    if url not in values:
        values.append(url)
    if len(values) > limit:
        raise ValueError(f"Лимит — {limit}")
    await _change_request(state, **{key: values})


@router.callback_query(F.data == "ns25:images")
async def images_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(Seedance25TestFSM.awaiting_image_ref)
    await safe_edit_message(call.message, f"🖼 Пришли фото, image-документ или публичный URL. Сейчас {len(_list(data, 's25_image_urls'))}/{NEXUS_SEEDANCE25_MAX_IMAGE_REFS}.", reply_markup=_clear_back("ns25:images:clear"))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:images:clear")
async def images_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, s25_image_urls=[])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Фото очищены")


@router.message(Seedance25TestFSM.awaiting_image_ref, F.photo)
async def image_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    url = await mirror_telegram_file(bot, best.file_id)
    try:
        await _add_url(state, "s25_image_urls", url, NEXUS_SEEDANCE25_MAX_IMAGE_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(Seedance25TestFSM.awaiting_image_ref, F.document)
async def image_document(message: Message, state: FSMContext, bot: Bot) -> None:
    mime = str(message.document.mime_type or "").lower() if message.document else ""
    if not mime.startswith("image/"):
        await message.answer("Нужен image-документ.")
        return
    item = await _download_document(bot, message)
    assert item is not None
    raw, mime = item
    url = save_public_file(raw, mime, subdir="nexusapi-seedance25/images")
    try:
        await _add_url(state, "s25_image_urls", url, NEXUS_SEEDANCE25_MAX_IMAGE_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(Seedance25TestFSM.awaiting_image_ref, F.text)
async def image_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_seedance25_params(prompt="validate", image_urls=[value])
        await _add_url(state, "s25_image_urls", value, NEXUS_SEEDANCE25_MAX_IMAGE_REFS)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "ns25:videos")
async def videos_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(Seedance25TestFSM.awaiting_video_ref)
    await safe_edit_message(call.message, f"🎥 Пришли видео, video-документ или публичный URL. Сейчас {len(_list(data, 's25_video_urls'))}/{NEXUS_SEEDANCE25_MAX_VIDEO_REFS}.", reply_markup=_clear_back("ns25:videos:clear"))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:videos:clear")
async def videos_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, s25_video_urls=[])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Видео очищены")


@router.message(Seedance25TestFSM.awaiting_video_ref, F.video)
async def video_media(message: Message, state: FSMContext, bot: Bot) -> None:
    url = await mirror_telegram_file(bot, message.video.file_id, is_video=True)  # type: ignore[union-attr]
    try:
        await _add_url(state, "s25_video_urls", url, NEXUS_SEEDANCE25_MAX_VIDEO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(Seedance25TestFSM.awaiting_video_ref, F.document)
async def video_document(message: Message, state: FSMContext, bot: Bot) -> None:
    mime = str(message.document.mime_type or "").lower() if message.document else ""
    if not mime.startswith("video/"):
        await message.answer("Нужен video-документ.")
        return
    item = await _download_document(bot, message)
    assert item is not None
    raw, mime = item
    url = save_public_file(raw, mime, subdir="nexusapi-seedance25/videos")
    try:
        await _add_url(state, "s25_video_urls", url, NEXUS_SEEDANCE25_MAX_VIDEO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(Seedance25TestFSM.awaiting_video_ref, F.text)
async def video_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_seedance25_params(prompt="validate", video_urls=[value])
        await _add_url(state, "s25_video_urls", value, NEXUS_SEEDANCE25_MAX_VIDEO_REFS)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "ns25:audios")
async def audios_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(Seedance25TestFSM.awaiting_audio_ref)
    await safe_edit_message(call.message, f"🎵 Пришли audio/voice, audio-документ или публичный URL. Сейчас {len(_list(data, 's25_audio_urls'))}/{NEXUS_SEEDANCE25_MAX_AUDIO_REFS}.", reply_markup=_clear_back("ns25:audios:clear"))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:audios:clear")
async def audios_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, s25_audio_urls=[])
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Аудио очищены")


@router.message(Seedance25TestFSM.awaiting_audio_ref, F.audio | F.voice)
async def audio_media(message: Message, state: FSMContext, bot: Bot) -> None:
    media = message.audio or message.voice
    assert media is not None
    tg_file = await bot.get_file(media.file_id)
    downloaded = await bot.download_file(tg_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    mime = str(getattr(media, "mime_type", "") or "audio/ogg")
    url = save_public_file(raw, mime, subdir="nexusapi-seedance25/audio")
    try:
        await _add_url(state, "s25_audio_urls", url, NEXUS_SEEDANCE25_MAX_AUDIO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(Seedance25TestFSM.awaiting_audio_ref, F.document)
async def audio_document(message: Message, state: FSMContext, bot: Bot) -> None:
    mime = str(message.document.mime_type or "").lower() if message.document else ""
    if not mime.startswith("audio/"):
        await message.answer("Нужен audio-документ.")
        return
    item = await _download_document(bot, message)
    assert item is not None
    raw, mime = item
    url = save_public_file(raw, mime, subdir="nexusapi-seedance25/audio")
    try:
        await _add_url(state, "s25_audio_urls", url, NEXUS_SEEDANCE25_MAX_AUDIO_REFS)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await _answer_dashboard(message, state)


@router.message(Seedance25TestFSM.awaiting_audio_ref, F.text)
async def audio_url(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    try:
        build_seedance25_params(prompt="validate", audio_urls=[value])
        await _add_url(state, "s25_audio_urls", value, NEXUS_SEEDANCE25_MAX_AUDIO_REFS)
    except ValueError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _answer_dashboard(message, state)


async def _save_frame(message: Message, state: FSMContext, bot: Bot, key: str) -> None:
    if message.photo:
        best = max(message.photo, key=lambda item: item.file_size or 0)
        url = await mirror_telegram_file(bot, best.file_id)
    elif message.document:
        mime = str(message.document.mime_type or "").lower()
        if not mime.startswith("image/"):
            await message.answer("Нужен image-документ.")
            return
        item = await _download_document(bot, message)
        assert item is not None
        raw, mime = item
        url = save_public_file(raw, mime, subdir="nexusapi-seedance25/frames")
    else:
        url = str(message.text or "").strip()
        try:
            if key == "s25_start_image_url":
                build_seedance25_params(prompt="validate", start_image_url=url, end_image_url="https://example.test/end.jpg")
            else:
                build_seedance25_params(prompt="validate", start_image_url="https://example.test/start.jpg", end_image_url=url)
        except ValueError as exc:
            await message.answer(html.escape(str(exc)))
            return
    await _change_request(state, **{key: url})
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "ns25:start")
async def start_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Seedance25TestFSM.awaiting_start_frame)
    await safe_edit_message(call.message, "🎞 Пришли START frame: фото, image-документ или URL. Для запуска нужен и END frame.", reply_markup=_clear_back("ns25:start:clear"))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:start:clear")
async def start_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, s25_start_image_url=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(Seedance25TestFSM.awaiting_start_frame, F.photo | F.document | F.text)
async def start_save(message: Message, state: FSMContext, bot: Bot) -> None:
    await _save_frame(message, state, bot, "s25_start_image_url")


@router.callback_query(F.data == "ns25:end")
async def end_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(Seedance25TestFSM.awaiting_end_frame)
    await safe_edit_message(call.message, "🎞 Пришли END frame: фото, image-документ или URL. Для запуска нужен и START frame.", reply_markup=_clear_back("ns25:end:clear"))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:end:clear")
async def end_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, s25_end_image_url=None)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(Seedance25TestFSM.awaiting_end_frame, F.photo | F.document | F.text)
async def end_save(message: Message, state: FSMContext, bot: Bot) -> None:
    await _save_frame(message, state, bot, "s25_end_image_url")


@router.callback_query(F.data == "ns25:overrides")
async def overrides_begin(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(Seedance25TestFSM.awaiting_overrides)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🧰 <b>Raw Seedance 2.5 overrides</b>\n\nСначала посмотри Live OpenAPI, затем пришли JSON-object. Поля model_name и prompt защищены. Остальные поля намеренно уйдут в Nexus как есть для проверки live-схемы.",
        reply_markup=_clear_back("ns25:overrides:clear") if _overrides(data) else _back(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:overrides:clear")
async def overrides_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, s25_overrides={})
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Overrides очищены")


@router.message(Seedance25TestFSM.awaiting_overrides, F.text)
async def overrides_save(message: Message, state: FSMContext) -> None:
    try:
        value = json.loads(str(message.text or ""))
    except json.JSONDecodeError as exc:
        await message.answer(f"Некорректный JSON: {html.escape(str(exc))}")
        return
    if not isinstance(value, dict):
        await message.answer("Нужен JSON object: <code>{...}</code>")
        return
    value.pop("model_name", None)
    value.pop("prompt", None)
    await _change_request(state, s25_overrides=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "ns25:schema")
async def schema(call: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(call, "Читаю live Seedance25Params…")
    data = await _data(state)
    try:
        result = await NexusApiClient().get_model_schema(NEXUS_SEEDANCE25_MODEL)
        text = (
            "🧬 <b>Live Nexus OpenAPI</b>\n\n"
            f"Model: <code>{result.model_name}</code>\n"
            f"Schema: <code>{html.escape(result.schema_name)}</code> · {result.elapsed_ms} ms\n\n"
            f"<pre>{html.escape(pretty_json(result.schema, max_chars=3000))}</pre>"
        )
    except NexusApiError as exc:
        text = "❌ <b>OpenAPI error</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


@router.callback_query(F.data == "ns25:catalog")
async def catalog(call: CallbackQuery, state: FSMContext) -> None:
    await safe_answer_callback(call, "Читаю live каталог…")
    data = await _data(state)
    try:
        result = await NexusApiClient().get_public_models()
        entry = find_model_in_catalog(result.payload, NEXUS_SEEDANCE25_MODEL)
        text = (
            "💰 <b>Live Nexus catalog</b>\n\n"
            f"HTTP {result.status_code} · {result.elapsed_ms} ms\n\n"
            f"<pre>{html.escape(pretty_json(entry if entry is not None else result.payload, max_chars=3000))}</pre>"
        )
    except NexusApiError as exc:
        text = "❌ <b>Catalog error</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


@router.callback_query(F.data == "ns25:payload")
async def payload(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    try:
        body = {"params": _current_params(data)}
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return
    await safe_edit_message(call.message, "📋 <b>Точный POST /generate payload</b>\n\n" f"<pre>{html.escape(pretty_json(body, max_chars=3400))}</pre>", reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "ns25:status")
async def status(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    task_id = str(data.get("s25_last_task_id") or "").strip()
    if not task_id:
        await safe_answer_callback(call, "Task ещё нет", show_alert=True)
        return
    await safe_answer_callback(call, "Проверяю task…")
    try:
        task = await NexusApiClient().get_task(task_id)
        text = "🔎 <b>Nexus Seedance task</b>\n\n<pre>" + html.escape(pretty_json(task, max_chars=3200)) + "</pre>"
    except NexusApiError as exc:
        text = "❌ <b>Task error</b>\n\n" + html.escape(str(exc))
    await safe_edit_message(call.message, text, reply_markup=_dashboard_kb(data))  # type: ignore[arg-type]


async def _send_results(message: Message, task_payload: dict[str, Any]) -> int:
    count = 0
    for index, url in enumerate(extract_result_urls(task_payload)[:4], start=1):
        try:
            await message.answer_video(
                URLInputFile(url, filename=f"nexus-seedance25-{index}.mp4"),
                caption=f"✅ Seedance 2.5 result #{index}",
                supports_streaming=True,
            )
        except Exception as exc:
            logger.warning("Nexus Seedance result delivery failed: %s", exc)
            await message.answer(f"✅ Result #{index}:\n{html.escape(url)}")
        count += 1
    return count


def _error_text(exc: Exception) -> str:
    if isinstance(exc, NexusApiTimeout):
        return "⏱ Seedance task не завершился за тестовый timeout. Task ID сохранён для ручной проверки."
    if isinstance(exc, NexusApiError):
        prefix = {
            401: "🔑 API key отклонён.",
            402: "💳 Недостаточный Nexus balance.",
            422: "🧩 Nexus отклонил Seedance params.",
            429: "🚦 Nexus rate limit.",
        }.get(exc.status_code, "❌ NexusAPI error.")
        return prefix + "\n\n" + html.escape(str(exc))
    return "❌ Seedance test error: " + html.escape(str(exc))


@router.callback_query(F.data == "ns25:run")
async def run(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    client = NexusApiClient()
    if not client.configured:
        await safe_answer_callback(call, "На сервере нет NEXUS_API_KEY", show_alert=True)
        return
    try:
        params = _current_params(data)
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        return

    await safe_answer_callback(call, "Платный Seedance 2.5 test запущен")
    status_message = await call.message.answer("🎬 <b>Nexus Seedance 2.5</b>\n\nPOST /generate…")  # type: ignore[union-attr]
    try:
        created = await client.create_params(params, idempotency_key=str(data["s25_idempotency_key"]))
        await state.update_data(s25_last_task_id=created.task_id)
        await status_message.edit_text(
            "🎬 <b>Nexus Seedance 2.5</b>\n\n"
            f"✅ POST: HTTP {created.status_code} · {created.elapsed_ms} ms\n"
            f"Task: <code>{html.escape(created.task_id)}</code>\n"
            "⏳ polling…"
        )
        timeout = float(os.getenv("NEXUS_VIDEO_POLL_TIMEOUT", "600"))
        finished = await client.wait_for_task(created.task_id, timeout_seconds=timeout)
        final_data = await _data(state)
        history = " → ".join(finished.status_history) or finished.status
        if finished.failed:
            await status_message.edit_text(
                "❌ <b>Nexus Seedance task failed</b>\n\n"
                f"Task: <code>{html.escape(created.task_id)}</code>\n"
                f"States: <code>{html.escape(history)}</code>\n"
                f"Error: {html.escape(str(finished.payload.get('error') or 'unknown'))}\n\n"
                f"<pre>{html.escape(pretty_json(finished.payload, max_chars=1800))}</pre>",
                reply_markup=_dashboard_kb(final_data),
            )
            return
        media_count = await _send_results(call.message, finished.payload)  # type: ignore[arg-type]
        total_ms = created.elapsed_ms + finished.elapsed_ms
        await status_message.edit_text(
            "✅ <b>Seedance 2.5 test completed</b>\n\n"
            f"Task: <code>{html.escape(created.task_id)}</code>\n"
            f"POST: <b>{created.elapsed_ms} ms</b>\n"
            f"Total: <b>{total_ms / 1000:.2f} s</b>\n"
            f"States: <code>{html.escape(history)}</code>\n"
            f"Media: <b>{media_count}</b>\n"
            f"Request ID: <code>{html.escape(created.idempotency_key)}</code>\n\n"
            "<b>Request</b>\n"
            f"<pre>{html.escape(pretty_json(created.request_payload, max_chars=1500))}</pre>\n"
            "<b>Final task</b>\n"
            f"<pre>{html.escape(pretty_json(finished.payload, max_chars=1500))}</pre>",
            reply_markup=_dashboard_kb(final_data),
        )
    except Exception as exc:
        logger.exception("NexusAPI Seedance 2.5 admin evaluation failed")
        final_data = await _data(state)
        await status_message.edit_text(_error_text(exc), reply_markup=_dashboard_kb(final_data))
