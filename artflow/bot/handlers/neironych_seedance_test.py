from __future__ import annotations

import asyncio
import html
import json
import logging
import tempfile
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.neironych_seedance import NeironychSeedanceClient, NeironychSeedanceError
from bot.filters.admin import IsAdmin
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from core.neironych_seedance_contract import (
    SEEDANCE_FIXED_ASPECT_RATIOS,
    SEEDANCE_MODELS,
    SeedanceContractError,
    build_seedance_payload,
    enabled_seedance_models,
    get_seedance_spec,
    resolve_seedance_model,
)

logger = logging.getLogger(__name__)
router = Router(name="neironych_seedance_admin_test")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

_PRICE_URL = "https://api.xn--e1aikcel5c5a.online/price"
_DEFAULT_PROMPT = (
    "Cinematic realistic video, coherent natural motion, stable subject identity, "
    "consistent lighting and camera movement"
)


class NeironychSeedanceFSM(StatesGroup):
    dashboard = State()
    awaiting_prompt = State()
    awaiting_duration = State()
    awaiting_image_ref = State()
    awaiting_video_ref = State()
    awaiting_audio_ref = State()
    awaiting_start_frame = State()
    awaiting_end_frame = State()
    awaiting_overrides = State()


def _new_idempotency_key() -> str:
    return f"apix-seedance-test-{uuid.uuid4()}"


def _model_label(model: str) -> str:
    return "Seedance 2" if model == "seedance-2.0" else "Seedance 2.5"


def _initial_data(model: str) -> dict[str, Any]:
    spec = get_seedance_spec(model)
    return {
        "neur_model": spec.model,
        "neur_mode": "text",
        "neur_prompt": _DEFAULT_PROMPT,
        "neur_resolution": "720p",
        "neur_duration": 5,
        "neur_aspect_ratio": "16:9",
        "neur_image_urls": [],
        "neur_video_urls": [],
        "neur_audio_urls": [],
        "neur_start_image_url": None,
        "neur_end_image_url": None,
        "neur_overrides": {},
        "neur_idempotency_key": _new_idempotency_key(),
        "neur_last_request_id": None,
        "neur_last_delivered_request_id": None,
        "neur_available_models": [],
        "neur_prices": {},
    }


async def _data(state: FSMContext) -> dict[str, Any]:
    data = await state.get_data()
    model = str(data.get("neur_model") or "")
    if model not in SEEDANCE_MODELS:
        raise SeedanceContractError("Состояние теста устарело. Открой «🧪 Тест» заново.")
    return data


async def _change_request(state: FSMContext, **changes: Any) -> None:
    await state.update_data(
        **changes,
        neur_idempotency_key=_new_idempotency_key(),
        neur_last_request_id=None,
        neur_last_delivered_request_id=None,
    )


def _urls(data: dict[str, Any], key: str) -> list[str]:
    values = data.get(key) or []
    return [str(value).strip() for value in values if str(value or "").strip()]


def _overrides(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("neur_overrides")
    return dict(value) if isinstance(value, dict) else {}


def _clip(value: Any, limit: int = 650) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _client() -> NeironychSeedanceClient:
    return NeironychSeedanceClient(
        settings.NEIRONYCH_API_KEY,
        settings.NEIRONYCH_API_BASE_URL,
        timeout_seconds=settings.NEIRONYCH_HTTP_TIMEOUT_SECONDS,
    )


async def _refresh_provider_meta(state: FSMContext) -> tuple[list[str], dict[str, dict[str, float]]]:
    client = _client()
    models: list[str] = []
    prices: dict[str, dict[str, float]] = {}
    try:
        models = await client.list_models()
        try:
            prices = await client.get_prices()
        except Exception as exc:
            logger.warning("Neironych price page read failed: %s", exc)
    finally:
        await client.aclose()
    await state.update_data(neur_available_models=models, neur_prices=prices)
    return models, prices


def _price_lines(data: dict[str, Any]) -> list[str]:
    model = str(data.get("neur_model") or "")
    spec = get_seedance_spec(model)
    all_prices = data.get("neur_prices")
    prices = all_prices.get(model, {}) if isinstance(all_prices, dict) else {}
    lines: list[str] = []
    for resolution in spec.resolutions:
        raw = prices.get(resolution) if isinstance(prices, dict) else None
        if isinstance(raw, (int, float)) and raw > 0:
            lines.append(f"{resolution}: {float(raw):.2f} ₽/с")
        else:
            lines.append(f"{resolution}: цена не опубликована")
    return lines


def _estimate_text(data: dict[str, Any]) -> str:
    if str(data.get("neur_mode") or "") == "edit":
        return "Расход edit зависит от billed_seconds провайдера; точная сумма будет в результате."
    model = str(data.get("neur_model") or "")
    resolution = str(data.get("neur_resolution") or "")
    duration = int(data.get("neur_duration") or 0)
    all_prices = data.get("neur_prices")
    prices = all_prices.get(model, {}) if isinstance(all_prices, dict) else {}
    rate = prices.get(resolution) if isinstance(prices, dict) else None
    if isinstance(rate, (int, float)) and rate > 0 and duration > 0:
        return f"Оценка теста: ≈ {float(rate) * duration:.2f} ₽ ({float(rate):.2f} ₽/с × {duration}с)."
    return "Точная цена для выбранного режима сейчас не получена с публичного прайса."


def _availability(data: dict[str, Any]) -> str:
    model = str(data.get("neur_model") or "")
    values = data.get("neur_available_models")
    if not isinstance(values, list) or not values:
        return "⚠️ не проверена"
    return "✅ доступна" if resolve_seedance_model(model, values) else "❌ выключена"


def _dashboard_text(data: dict[str, Any]) -> str:
    model = str(data.get("neur_model") or "")
    mode = str(data.get("neur_mode") or "text")
    spec = get_seedance_spec(model)
    images = _urls(data, "neur_image_urls")
    videos = _urls(data, "neur_video_urls")
    audios = _urls(data, "neur_audio_urls")
    configured = "✅ настроен" if settings.NEIRONYCH_API_KEY.strip() else "❌ ключ не настроен"
    duration = (
        "по исходному видео"
        if mode == "edit"
        else f"{int(data.get('neur_duration') or spec.min_duration)} сек"
    )
    ratio = (
        "adaptive / по исходнику"
        if mode == "edit"
        else "adaptive"
        if mode == "frame" and model == "seedance-2.5"
        else str(data.get("neur_aspect_ratio") or "—")
    )
    frame_state = (
        f"{'✅' if data.get('neur_start_image_url') else '—'} start · "
        f"{'✅' if data.get('neur_end_image_url') else '—'} end"
    )
    price_text = " · ".join(_price_lines(data))
    text = (
        f"🎬 <b>Нейроныч · {_model_label(model)} Lab</b>\n\n"
        "Изолированный админский тест. APIX-кредиты не списываются; "
        "платный запуск расходует только баланс Нейроныч API. "
        "Новый платный POST выполняется только после кнопки «Запустить».\n\n"
        f"🔑 API: <b>{configured}</b>\n"
        f"🟢 Модель: <b>{_availability(data)}</b> · <code>{html.escape(model)}</code>\n"
        f"🧭 Режим: <b>{html.escape(mode)}</b>\n"
        f"📺 Resolution: <b>{html.escape(str(data.get('neur_resolution') or '720p'))}</b>\n"
        f"⏱ Duration: <b>{duration}</b>\n"
        f"📐 Ratio: <b>{html.escape(ratio)}</b>\n"
        f"🖼 Фото: <b>{len(images)}/{spec.max_image_refs}</b> · "
        f"🎥 Видео: <b>{len(videos)}/{spec.max_video_refs}</b> · "
        f"🎵 Аудио: <b>{len(audios)}/{spec.max_audio_refs}</b> · Σ {spec.max_total_refs}\n"
        f"🎞 Кадры: <b>{frame_state}</b>\n"
        f"🧰 Raw overrides: <b>{len(_overrides(data))}</b>\n"
        f"🛡 Idempotency: <code>{html.escape(str(data.get('neur_idempotency_key') or ''))}</code>\n\n"
        f"💰 <b>Live price</b>: {html.escape(price_text)}\n"
        f"{html.escape(_estimate_text(data))}\n\n"
        f"✍️ <b>Prompt</b>\n{html.escape(_clip(data.get('neur_prompt')))}"
    )
    if data.get("neur_last_request_id"):
        text += (
            "\n\nПоследний request: "
            f"<code>{html.escape(str(data['neur_last_request_id']))}</code>"
        )
    return text


def _dashboard_kb(data: dict[str, Any]):
    model = str(data.get("neur_model") or "")
    mode = str(data.get("neur_mode") or "text")
    spec = get_seedance_spec(model)
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(
            text=("✅ " if mode == "text" else "") + "📝 Text → Video",
            callback_data="neur:mode:text",
        ),
        InlineKeyboardButton(
            text=("✅ " if mode == "reference" else "") + "🧩 Референсы",
            callback_data="neur:mode:reference",
        ),
    )
    b.row(
        InlineKeyboardButton(
            text=("✅ " if mode == "frame" else "") + "🎞 First / Last",
            callback_data="neur:mode:frame",
        ),
        *(
            [
                InlineKeyboardButton(
                    text=("✅ " if mode == "edit" else "") + "✂️ Video Edit",
                    callback_data="neur:mode:edit",
                )
            ]
            if spec.supports_edit
            else []
        ),
    )
    b.row(InlineKeyboardButton(text="✍️ Промпт", callback_data="neur:prompt"))
    if mode != "edit":
        b.row(
            InlineKeyboardButton(
                text=f"⏱ {int(data.get('neur_duration') or spec.min_duration)}с",
                callback_data="neur:duration",
            ),
            InlineKeyboardButton(
                text=f"📐 {'adaptive' if mode == 'frame' and model == 'seedance-2.5' else data.get('neur_aspect_ratio')}",
                callback_data="neur:ratio",
            ),
        )
    b.row(
        InlineKeyboardButton(
            text=f"📺 {data.get('neur_resolution') or '720p'}",
            callback_data="neur:resolution",
        ),
        InlineKeyboardButton(text="💰 Обновить прайс", callback_data="neur:price"),
    )
    if mode in {"reference", "edit", "raw"}:
        b.row(
            InlineKeyboardButton(
                text=f"🖼 Фото {len(_urls(data, 'neur_image_urls'))}",
                callback_data="neur:images",
            ),
            InlineKeyboardButton(
                text=f"🎥 Видео {len(_urls(data, 'neur_video_urls'))}",
                callback_data="neur:videos",
            ),
            InlineKeyboardButton(
                text=f"🎵 Аудио {len(_urls(data, 'neur_audio_urls'))}",
                callback_data="neur:audios",
            ),
        )
    if mode == "frame":
        b.row(
            InlineKeyboardButton(text="🎞 Start frame", callback_data="neur:start"),
            InlineKeyboardButton(text="🎞 End frame", callback_data="neur:end"),
        )
    b.row(
        InlineKeyboardButton(text="🧰 Raw JSON", callback_data="neur:overrides"),
        InlineKeyboardButton(text="📋 Payload", callback_data="neur:payload"),
    )
    if data.get("neur_last_request_id"):
        b.row(InlineKeyboardButton(text="🔎 Проверить request", callback_data="neur:status"))
    b.row(InlineKeyboardButton(text="🚀 Запустить платный тест", callback_data="neur:run"))
    b.row(
        InlineKeyboardButton(text="🆕 Новый Request ID", callback_data="neur:newkey"),
        InlineKeyboardButton(text="♻️ Сбросить", callback_data="neur:reset"),
    )
    b.row(InlineKeyboardButton(text="💰 Публичный прайс ↗", url=_PRICE_URL))
    b.row(
        InlineKeyboardButton(text="🧪 Другие модели", callback_data="nxt:model:choose"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    )
    return b.as_markup()


def _back(clear_callback: str | None = None):
    b = InlineKeyboardBuilder()
    if clear_callback:
        b.row(InlineKeyboardButton(text="🗑 Очистить", callback_data=clear_callback))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="neur:dashboard"))
    return b.as_markup()


async def _show_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(NeironychSeedanceFSM.dashboard)
    await safe_edit_message(message, _dashboard_text(data), reply_markup=_dashboard_kb(data))


async def _answer_dashboard(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    await state.set_state(NeironychSeedanceFSM.dashboard)
    await message.answer(_dashboard_text(data), reply_markup=_dashboard_kb(data))


def _current_payload(data: dict[str, Any]) -> dict[str, Any]:
    return build_seedance_payload(
        model=str(data.get("neur_model") or ""),
        mode=str(data.get("neur_mode") or ""),
        prompt=str(data.get("neur_prompt") or ""),
        resolution=str(data.get("neur_resolution") or ""),
        duration=int(data.get("neur_duration") or 0),
        aspect_ratio=str(data.get("neur_aspect_ratio") or ""),
        image_urls=_urls(data, "neur_image_urls"),
        video_urls=_urls(data, "neur_video_urls"),
        audio_urls=_urls(data, "neur_audio_urls"),
        start_image_url=data.get("neur_start_image_url"),
        end_image_url=data.get("neur_end_image_url"),
        extra=_overrides(data),
    )


async def _open_model(call: CallbackQuery, state: FSMContext, model: str) -> None:
    await state.clear()
    await state.update_data(**_initial_data(model))
    try:
        await _refresh_provider_meta(state)
    except Exception as exc:
        logger.warning("Neironych provider metadata unavailable: %s", exc)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "nxt:model:neur-s20")
async def open_seedance20(call: CallbackQuery, state: FSMContext) -> None:
    await _open_model(call, state, "seedance-2.0")


@router.callback_query(F.data == "nxt:model:neur-s25")
async def open_seedance25(call: CallbackQuery, state: FSMContext) -> None:
    await _open_model(call, state, "seedance-2.5")


@router.callback_query(F.data == "neur:dashboard")
async def dashboard(call: CallbackQuery, state: FSMContext) -> None:
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:price")
async def refresh_price(call: CallbackQuery, state: FSMContext) -> None:
    try:
        await _refresh_provider_meta(state)
    except Exception as exc:
        await safe_answer_callback(call, f"Не удалось обновить: {str(exc)[:120]}", show_alert=True)
        return
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Прайс и доступность обновлены")


@router.callback_query(F.data.startswith("neur:mode:"))
async def mode_set(call: CallbackQuery, state: FSMContext) -> None:
    mode = str(call.data or "").rsplit(":", 1)[-1]
    data = await _data(state)
    model = str(data.get("neur_model") or "")
    spec = get_seedance_spec(model)
    if mode not in {"text", "reference", "frame", "edit", "raw"}:
        await safe_answer_callback(call, "Неизвестный режим", show_alert=True)
        return
    if mode == "edit" and not spec.supports_edit:
        await safe_answer_callback(call, "Edit доступен только в Seedance 2.5", show_alert=True)
        return

    changes: dict[str, Any] = {"neur_mode": mode}
    if mode == "text":
        changes.update(
            neur_image_urls=[],
            neur_video_urls=[],
            neur_audio_urls=[],
            neur_start_image_url=None,
            neur_end_image_url=None,
        )
    elif mode in {"reference", "edit"}:
        changes.update(neur_start_image_url=None, neur_end_image_url=None)
        if mode == "edit":
            changes["neur_aspect_ratio"] = "adaptive"
    elif mode == "frame":
        changes.update(neur_image_urls=[], neur_video_urls=[], neur_audio_urls=[])
        if model == "seedance-2.5":
            changes["neur_aspect_ratio"] = "adaptive"
    await _change_request(state, **changes)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:prompt")
async def prompt_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NeironychSeedanceFSM.awaiting_prompt)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "✍️ <b>Prompt</b>\n\nДо 40 000 байт UTF-8. Референсы можно указывать как @Image 1, @Video 1, @Audio 1.",
        reply_markup=_back(),
    )
    await safe_answer_callback(call)


@router.message(NeironychSeedanceFSM.awaiting_prompt, F.text)
async def prompt_save(message: Message, state: FSMContext) -> None:
    value = str(message.text or "").strip()
    if not value:
        await message.answer("Промпт не может быть пустым.")
        return
    if len(value.encode("utf-8")) > 40_000:
        await message.answer("Промпт превышает 40 000 байт UTF-8.")
        return
    await _change_request(state, neur_prompt=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "neur:duration")
async def duration_menu(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    spec = get_seedance_spec(str(data.get("neur_model") or ""))
    b = InlineKeyboardBuilder()
    for value in range(spec.min_duration, spec.max_duration + 1):
        b.button(text=f"{value}с", callback_data=f"neur:duration:{value}")
    b.adjust(6)
    b.row(InlineKeyboardButton(text="✍️ Ввести", callback_data="neur:duration:custom"))
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="neur:dashboard"))
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"⏱ <b>Duration</b> · {spec.min_duration}–{spec.max_duration} секунд",
        reply_markup=b.as_markup(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("neur:duration:"))
async def duration_set(call: CallbackQuery, state: FSMContext) -> None:
    raw = str(call.data or "").rsplit(":", 1)[-1]
    if raw == "custom":
        await state.set_state(NeironychSeedanceFSM.awaiting_duration)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            "Пришли целое число секунд.",
            reply_markup=_back(),
        )
        await safe_answer_callback(call)
        return
    await _set_duration(call, state, raw)


async def _set_duration(call: CallbackQuery, state: FSMContext, raw: str) -> None:
    data = await _data(state)
    spec = get_seedance_spec(str(data.get("neur_model") or ""))
    try:
        value = int(raw)
    except ValueError:
        await safe_answer_callback(call, "Нужны целые секунды", show_alert=True)
        return
    if not spec.min_duration <= value <= spec.max_duration:
        await safe_answer_callback(
            call,
            f"Допустимо {spec.min_duration}–{spec.max_duration} сек",
            show_alert=True,
        )
        return
    await _change_request(state, neur_duration=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.message(NeironychSeedanceFSM.awaiting_duration, F.text)
async def duration_custom(message: Message, state: FSMContext) -> None:
    data = await _data(state)
    spec = get_seedance_spec(str(data.get("neur_model") or ""))
    try:
        value = int(str(message.text or "").strip())
    except ValueError:
        await message.answer("Нужно целое число секунд.")
        return
    if not spec.min_duration <= value <= spec.max_duration:
        await message.answer(f"Допустимо {spec.min_duration}–{spec.max_duration} секунд.")
        return
    await _change_request(state, neur_duration=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "neur:resolution")
async def resolution_menu(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    spec = get_seedance_spec(str(data.get("neur_model") or ""))
    b = InlineKeyboardBuilder()
    for value in spec.resolutions:
        b.button(text=value, callback_data=f"neur:resolution:{value}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="neur:dashboard"))
    await safe_edit_message(call.message, "📺 <b>Resolution</b>", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("neur:resolution:"))
async def resolution_set(call: CallbackQuery, state: FSMContext) -> None:
    value = str(call.data or "").rsplit(":", 1)[-1]
    data = await _data(state)
    spec = get_seedance_spec(str(data.get("neur_model") or ""))
    if value not in spec.resolutions:
        await safe_answer_callback(call, "Неподдерживаемое resolution", show_alert=True)
        return
    await _change_request(state, neur_resolution=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:ratio")
async def ratio_menu(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    model = str(data.get("neur_model") or "")
    mode = str(data.get("neur_mode") or "")
    if mode == "frame" and model == "seedance-2.5":
        await safe_answer_callback(
            call,
            "Seedance 2.5 с first/last frame использует adaptive.",
            show_alert=True,
        )
        return
    b = InlineKeyboardBuilder()
    for value in SEEDANCE_FIXED_ASPECT_RATIOS:
        b.button(text=value, callback_data=f"neur:ratio:{value.replace(':', 'x')}")
    b.adjust(3, 3)
    b.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="neur:dashboard"))
    await safe_edit_message(call.message, "📐 <b>Aspect ratio</b>", reply_markup=b.as_markup())  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("neur:ratio:"))
async def ratio_set(call: CallbackQuery, state: FSMContext) -> None:
    value = str(call.data or "").rsplit(":", 1)[-1].replace("x", ":")
    if value not in SEEDANCE_FIXED_ASPECT_RATIOS:
        await safe_answer_callback(call, "Неподдерживаемый ratio", show_alert=True)
        return
    await _change_request(state, neur_aspect_ratio=value)
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


def _media_limits(model: str, kind: str) -> int:
    if kind == "image":
        return 20 * 1024 * 1024
    if kind == "audio":
        return 15 * 1024 * 1024
    if kind == "video":
        return (100 if model == "seedance-2.5" else 50) * 1024 * 1024
    return 0


def _supported_mime(kind: str, mime: str) -> bool:
    value = str(mime or "").lower().split(";", 1)[0]
    if kind == "image":
        return value in {"image/jpeg", "image/png"}
    if kind == "video":
        return value in {"video/mp4", "video/quicktime"}
    if kind == "audio":
        return value in {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"}
    return False


async def _message_bytes(message: Message, expected_kind: str) -> tuple[bytes, str] | None:
    model_data = None
    media = None
    mime = ""
    file_size = 0
    if expected_kind == "image" and message.photo:
        media = max(message.photo, key=lambda item: item.file_size or 0)
        mime = "image/jpeg"
        file_size = int(media.file_size or 0)
    elif expected_kind == "video" and message.video:
        media = message.video
        mime = str(media.mime_type or "video/mp4")
        file_size = int(media.file_size or 0)
    elif expected_kind == "audio" and message.audio:
        media = message.audio
        mime = str(media.mime_type or "")
        file_size = int(media.file_size or 0)
    elif message.document:
        media = message.document
        mime = str(media.mime_type or "")
        file_size = int(media.file_size or 0)

    if media is None:
        await message.answer(
            "Пришли поддерживаемый файл: JPEG/PNG, MP4/MOV или WAV/MP3 — по выбранному типу."
        )
        return None
    if not _supported_mime(expected_kind, mime):
        await message.answer(
            f"Для {expected_kind} этот формат не подходит Seedance. "
            "Используй JPEG/PNG, MP4/MOV или WAV/MP3."
        )
        return None

    state = message.bot
    del state, model_data
    tg_file = await message.bot.get_file(media.file_id)
    downloaded = await message.bot.download_file(tg_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    if file_size and len(raw) != file_size:
        logger.info(
            "Neironych admin media size differs telegram=%s downloaded=%s",
            file_size,
            len(raw),
        )
    return raw, mime


async def _upload_message_media(
    message: Message,
    state: FSMContext,
    *,
    kind: str,
) -> str | None:
    data = await _data(state)
    model = str(data.get("neur_model") or "")
    spec = get_seedance_spec(model)
    item = await _message_bytes(message, kind)
    if item is None:
        return None
    raw, mime = item
    limit = _media_limits(model, kind)
    if len(raw) > limit:
        await message.answer(f"Файл превышает лимит Seedance для {kind}: {limit // (1024 * 1024)} MB.")
        return None

    client = _client()
    try:
        return await client.upload_media(
            model=model,
            media_type=kind,
            content=raw,
            content_type=mime,
        )
    except NeironychSeedanceError as exc:
        await message.answer("Не удалось загрузить референс: " + html.escape(str(exc))[:900])
        return None
    finally:
        await client.aclose()


async def _append_ref(state: FSMContext, kind: str, url: str) -> None:
    data = await _data(state)
    model = str(data.get("neur_model") or "")
    spec = get_seedance_spec(model)
    mapping = {
        "image": ("neur_image_urls", spec.max_image_refs),
        "video": ("neur_video_urls", spec.max_video_refs),
        "audio": ("neur_audio_urls", spec.max_audio_refs),
    }
    key, limit = mapping[kind]
    values = _urls(data, key)
    if url not in values:
        values.append(url)
    if len(values) > limit:
        raise SeedanceContractError(f"Лимит {kind}: {limit}")
    total = (
        len(values)
        + sum(
            len(_urls(data, other))
            for other in {"neur_image_urls", "neur_video_urls", "neur_audio_urls"}
            if other != key
        )
    )
    if total > spec.max_total_refs:
        raise SeedanceContractError(f"Суммарный лимит референсов: {spec.max_total_refs}")
    await _change_request(state, **{key: values})


def _ref_prompt(kind: str, data: dict[str, Any]) -> str:
    model = str(data.get("neur_model") or "")
    spec = get_seedance_spec(model)
    counts = {
        "image": len(_urls(data, "neur_image_urls")),
        "video": len(_urls(data, "neur_video_urls")),
        "audio": len(_urls(data, "neur_audio_urls")),
    }
    maximum = {
        "image": spec.max_image_refs,
        "video": spec.max_video_refs,
        "audio": spec.max_audio_refs,
    }[kind]
    formats = {
        "image": "JPEG/PNG",
        "video": "MP4/MOV",
        "audio": "WAV/MP3",
    }[kind]
    return (
        f"📎 <b>{kind.title()} reference</b> · {counts[kind]}/{maximum}\n\n"
        f"Пришли {formats} файлом/медиа или публичный HTTPS URL. "
        "Локальный файл сначала загружается через Нейроныч /v1/media/uploads."
    )


async def _ref_begin(call: CallbackQuery, state: FSMContext, kind: str) -> None:
    data = await _data(state)
    states = {
        "image": NeironychSeedanceFSM.awaiting_image_ref,
        "video": NeironychSeedanceFSM.awaiting_video_ref,
        "audio": NeironychSeedanceFSM.awaiting_audio_ref,
    }
    await state.set_state(states[kind])
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _ref_prompt(kind, data),
        reply_markup=_back(f"neur:{kind}s:clear"),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:images")
async def images_begin(call: CallbackQuery, state: FSMContext) -> None:
    await _ref_begin(call, state, "image")


@router.callback_query(F.data == "neur:videos")
async def videos_begin(call: CallbackQuery, state: FSMContext) -> None:
    await _ref_begin(call, state, "video")


@router.callback_query(F.data == "neur:audios")
async def audios_begin(call: CallbackQuery, state: FSMContext) -> None:
    await _ref_begin(call, state, "audio")


async def _clear_refs(call: CallbackQuery, state: FSMContext, key: str, label: str) -> None:
    await _change_request(state, **{key: []})
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, f"{label} очищены")


@router.callback_query(F.data == "neur:images:clear")
async def images_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _clear_refs(call, state, "neur_image_urls", "Фото")


@router.callback_query(F.data == "neur:videos:clear")
async def videos_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _clear_refs(call, state, "neur_video_urls", "Видео")


@router.callback_query(F.data == "neur:audios:clear")
async def audios_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _clear_refs(call, state, "neur_audio_urls", "Аудио")


async def _save_ref_message(message: Message, state: FSMContext, kind: str) -> None:
    value = str(message.text or "").strip() if message.text else ""
    if value:
        if not value.startswith("https://"):
            await message.answer("Нужен публичный HTTPS URL.")
            return
        url = value
    else:
        url = await _upload_message_media(message, state, kind=kind) or ""
        if not url:
            return
    try:
        await _append_ref(state, kind, url)
        _current_payload(await _data(state))
    except SeedanceContractError as exc:
        await message.answer(html.escape(str(exc)))
        return
    await _answer_dashboard(message, state)


@router.message(NeironychSeedanceFSM.awaiting_image_ref, F.photo | F.document | F.text)
async def image_ref_save(message: Message, state: FSMContext) -> None:
    await _save_ref_message(message, state, "image")


@router.message(NeironychSeedanceFSM.awaiting_video_ref, F.video | F.document | F.text)
async def video_ref_save(message: Message, state: FSMContext) -> None:
    await _save_ref_message(message, state, "video")


@router.message(NeironychSeedanceFSM.awaiting_audio_ref, F.audio | F.document | F.text)
async def audio_ref_save(message: Message, state: FSMContext) -> None:
    await _save_ref_message(message, state, "audio")


async def _frame_begin(call: CallbackQuery, state: FSMContext, *, start: bool) -> None:
    await state.set_state(
        NeironychSeedanceFSM.awaiting_start_frame
        if start
        else NeironychSeedanceFSM.awaiting_end_frame
    )
    label = "START" if start else "END"
    clear = "neur:start:clear" if start else "neur:end:clear"
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🎞 <b>{label} frame</b>\n\nПришли JPEG/PNG или публичный HTTPS URL.",
        reply_markup=_back(clear),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:start")
async def start_begin(call: CallbackQuery, state: FSMContext) -> None:
    await _frame_begin(call, state, start=True)


@router.callback_query(F.data == "neur:end")
async def end_begin(call: CallbackQuery, state: FSMContext) -> None:
    await _frame_begin(call, state, start=False)


async def _frame_clear(call: CallbackQuery, state: FSMContext, key: str) -> None:
    await _change_request(state, **{key: None})
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:start:clear")
async def start_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _frame_clear(call, state, "neur_start_image_url")


@router.callback_query(F.data == "neur:end:clear")
async def end_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _frame_clear(call, state, "neur_end_image_url")


async def _save_frame(message: Message, state: FSMContext, key: str) -> None:
    value = str(message.text or "").strip() if message.text else ""
    if value:
        if not value.startswith("https://"):
            await message.answer("Нужен публичный HTTPS URL.")
            return
        url = value
    else:
        url = await _upload_message_media(message, state, kind="image") or ""
        if not url:
            return
    await _change_request(state, **{key: url})
    try:
        _current_payload(await _data(state))
    except SeedanceContractError as exc:
        # It is valid to upload START before END; only reject hard contract errors.
        if "стартовое" not in str(exc).lower():
            await message.answer(html.escape(str(exc)))
    await _answer_dashboard(message, state)


@router.message(
    NeironychSeedanceFSM.awaiting_start_frame,
    F.photo | F.document | F.text,
)
async def start_save(message: Message, state: FSMContext) -> None:
    await _save_frame(message, state, "neur_start_image_url")


@router.message(
    NeironychSeedanceFSM.awaiting_end_frame,
    F.photo | F.document | F.text,
)
async def end_save(message: Message, state: FSMContext) -> None:
    await _save_frame(message, state, "neur_end_image_url")


@router.callback_query(F.data == "neur:overrides")
async def overrides_begin(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(NeironychSeedanceFSM.awaiting_overrides)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🧰 <b>Raw JSON overrides</b>\n\n"
        "Экспертный escape hatch для новых полей провайдера. model, prompt, duration, "
        "resolution, aspect_ratio и референсы остаются под контролем формы. "
        "Известные запрещённые legacy-поля будут отфильтрованы до платного POST.",
        reply_markup=_back("neur:overrides:clear"),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:overrides:clear")
async def overrides_clear(call: CallbackQuery, state: FSMContext) -> None:
    await _change_request(state, neur_overrides={})
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Overrides очищены")


@router.message(NeironychSeedanceFSM.awaiting_overrides, F.text)
async def overrides_save(message: Message, state: FSMContext) -> None:
    try:
        value = json.loads(str(message.text or ""))
    except json.JSONDecodeError as exc:
        await message.answer("Некорректный JSON: " + html.escape(str(exc)))
        return
    if not isinstance(value, dict):
        await message.answer("Нужен JSON object: <code>{...}</code>")
        return
    for protected in {
        "model",
        "prompt",
        "duration",
        "resolution",
        "aspect_ratio",
        "reference_images",
        "reference_videos",
        "reference_audios",
        "start_image",
        "end_image",
    }:
        value.pop(protected, None)
    await _change_request(state, neur_overrides=value)
    await _answer_dashboard(message, state)


@router.callback_query(F.data == "neur:payload")
async def payload_preview(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    try:
        body = {"model": data["neur_model"], **_current_payload(data)}
    except SeedanceContractError as exc:
        await safe_answer_callback(call, str(exc)[:180], show_alert=True)
        return
    text = json.dumps(body, ensure_ascii=False, indent=2)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📋 <b>Точный POST /v1/videos/generations</b>\n\n"
        f"<pre>{html.escape(text[:3500])}</pre>",
        reply_markup=_back(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "neur:newkey")
async def new_key(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        neur_idempotency_key=_new_idempotency_key(),
        neur_last_request_id=None,
        neur_last_delivered_request_id=None,
    )
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Новый Idempotency-Key")


@router.callback_query(F.data == "neur:reset")
async def reset(call: CallbackQuery, state: FSMContext) -> None:
    data = await _data(state)
    model = str(data.get("neur_model") or "")
    await state.clear()
    await state.update_data(**_initial_data(model))
    try:
        await _refresh_provider_meta(state)
    except Exception:
        pass
    await _show_dashboard(call.message, state)  # type: ignore[arg-type]
    await safe_answer_callback(call, "Seedance lab сброшен")


def _error_text(exc: Exception) -> str:
    if isinstance(exc, NeironychSeedanceError):
        prefix = {
            401: "🔑 API key отклонён.",
            402: "💳 Недостаточный тестовый баланс.",
            403: "⛔ Доступ к модели запрещён.",
            413: "📦 Файл/запрос слишком большой.",
            415: "🎞 Неподдерживаемый формат media.",
            422: "🧩 Провайдер отклонил параметры.",
            429: "🚦 Rate limit.",
        }.get(exc.status_code, "❌ Нейроныч API error.")
        return prefix + "\n\n" + html.escape(str(exc))
    if isinstance(exc, SeedanceContractError):
        return "🧩 " + html.escape(str(exc))
    return "❌ Seedance test error: " + html.escape(str(exc))


async def _download_and_send(
    bot: Bot,
    *,
    chat_id: int,
    request_id: str,
    model: str,
    billed_seconds: float | None,
) -> None:
    handle = tempfile.NamedTemporaryFile(
        prefix="apix-neironych-seedance-",
        suffix=".mp4",
        delete=False,
    )
    path = Path(handle.name)
    handle.close()
    client = _client()
    try:
        await client.download_content_to(
            request_id,
            path,
            max_bytes=settings.NEIRONYCH_TEST_MAX_VIDEO_BYTES,
        )
        billed = (
            f"\nBilled: <b>{billed_seconds:g} sec</b>"
            if billed_seconds is not None
            else ""
        )
        await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(path),
            caption=(
                f"✅ <b>Нейроныч · {_model_label(model)}</b>\n"
                f"Request: <code>{html.escape(request_id)}</code>{billed}"
            ),
            supports_streaming=True,
        )
    finally:
        path.unlink(missing_ok=True)
        await client.aclose()


async def _poll_and_deliver(
    bot: Bot,
    *,
    chat_id: int,
    request_id: str,
    model: str,
    status_message: Message,
) -> None:
    client = _client()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + float(settings.NEIRONYCH_TEST_POLL_TIMEOUT_SECONDS)
    try:
        while loop.time() < deadline:
            result = await client.get_video(request_id)
            if result.done:
                await status_message.edit_text(
                    f"✅ <b>{_model_label(model)} готов</b>\n"
                    f"Request: <code>{html.escape(request_id)}</code>\n"
                    "Скачиваю MP4 с авторизацией…"
                )
                await client.aclose()
                await _download_and_send(
                    bot,
                    chat_id=chat_id,
                    request_id=request_id,
                    model=model,
                    billed_seconds=result.billed_seconds,
                )
                return
            if result.failed:
                await status_message.edit_text(
                    f"❌ <b>{_model_label(model)} failed</b>\n"
                    f"Request: <code>{html.escape(request_id)}</code>\n"
                    f"{html.escape(result.error or result.status)}"
                )
                return
            await asyncio.sleep(float(settings.NEIRONYCH_TEST_POLL_INTERVAL_SECONDS))
        await status_message.edit_text(
            f"⏱ <b>Seedance всё ещё выполняется</b>\n"
            f"Request: <code>{html.escape(request_id)}</code>\n"
            "Автопроверка остановлена по timeout. Request сохранён — нажми «Проверить request»."
        )
    except Exception as exc:
        logger.exception(
            "Neironych Seedance admin poll failed request_id=%s model=%s",
            request_id,
            model,
        )
        try:
            await status_message.edit_text(
                f"⚠️ Автопроверка остановилась. Request сохранён: "
                f"<code>{html.escape(request_id)}</code>\n\n{_error_text(exc)}"
            )
        except Exception:
            pass
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


@router.callback_query(F.data == "neur:status")
async def status(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await _data(state)
    request_id = str(data.get("neur_last_request_id") or "").strip()
    model = str(data.get("neur_model") or "")
    if not request_id:
        await safe_answer_callback(call, "Request ещё нет", show_alert=True)
        return
    client = _client()
    try:
        result = await client.get_video(request_id)
    except Exception as exc:
        await safe_answer_callback(call, _error_text(exc)[:180], show_alert=True)
        return
    finally:
        await client.aclose()

    if result.done:
        await safe_answer_callback(call, "Готово — скачиваю")
        if data.get("neur_last_delivered_request_id") != request_id:
            await _download_and_send(
                bot,
                chat_id=call.message.chat.id,  # type: ignore[union-attr]
                request_id=request_id,
                model=model,
                billed_seconds=result.billed_seconds,
            )
            await state.update_data(neur_last_delivered_request_id=request_id)
        await _show_dashboard(call.message, state)  # type: ignore[arg-type]
        return
    if result.failed:
        await safe_answer_callback(call, "Задача завершилась ошибкой", show_alert=True)
        await call.message.answer(  # type: ignore[union-attr]
            f"❌ <code>{html.escape(request_id)}</code> · "
            f"{html.escape(result.error or result.status)}"
        )
        return
    await safe_answer_callback(call, f"Статус: {result.status or 'pending'}", show_alert=True)


@router.callback_query(F.data == "neur:run")
async def run(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await _data(state)
    model = str(data.get("neur_model") or "")
    if not settings.NEIRONYCH_API_KEY.strip():
        await safe_answer_callback(
            call,
            "На production не настроен NEIRONYCH_API_KEY",
            show_alert=True,
        )
        return
    try:
        payload = _current_payload(data)
    except SeedanceContractError as exc:
        await safe_answer_callback(call, str(exc)[:180], show_alert=True)
        return

    client = _client()
    try:
        available = await client.list_models()
        provider_model = resolve_seedance_model(model, available)
        if provider_model is None:
            allowed = ", ".join(enabled_seedance_models(available)) or "нет"
            await safe_answer_callback(
                call,
                f"Модель сейчас выключена. Доступно Seedance: {allowed}",
                show_alert=True,
            )
            return

        await safe_answer_callback(call, "Отправляю платный тест")
        request_id = await client.create_video(
            model=provider_model,
            payload=payload,
            idempotency_key=str(data.get("neur_idempotency_key") or ""),
        )
    except Exception as exc:
        logger.exception("Neironych Seedance admin submit failed model=%s", model)
        await safe_answer_callback(call, _error_text(exc)[:180], show_alert=True)
        return
    finally:
        await client.aclose()

    await state.update_data(
        neur_last_request_id=request_id,
        neur_available_models=available,
    )
    status_message = await call.message.answer(  # type: ignore[union-attr]
        f"🎬 <b>Нейроныч · {_model_label(model)}</b>\n\n"
        f"✅ Request: <code>{html.escape(request_id)}</code>\n"
        "⏳ Генерация запущена. Жду результат…"
    )
    logger.info(
        "neironych_seedance_admin_test_started request_id=%s model=%s mode=%s refs_images=%s refs_videos=%s refs_audio=%s resolution=%s",
        request_id,
        model,
        data.get("neur_mode"),
        len(_urls(data, "neur_image_urls")),
        len(_urls(data, "neur_video_urls")),
        len(_urls(data, "neur_audio_urls")),
        data.get("neur_resolution"),
    )
    asyncio.create_task(
        _poll_and_deliver(
            bot,
            chat_id=call.message.chat.id,  # type: ignore[union-attr]
            request_id=request_id,
            model=model,
            status_message=status_message,
        )
    )
