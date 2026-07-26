# bot/handlers/video_gen.py
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from html import escape
from urllib.parse import urlencode

import aiohttp
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api import polling, video_service
from api.public_files import mirror_telegram_file
from api.video_service import VideoModel
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    VIDEO_CAPS,
    VIDEO_GROUP_TITLES,
    after_generation_kb,
    multi_ref_kb,
    video_mode_kb,
    video_model_groups_kb,
    video_models_kb,
    video_params_kb,
)
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from core.gemini_omni import (
    GEMINI_OMNI_AUDIO_VOICES,
    GEMINI_OMNI_MAX_AUDIO_IDS,
    GEMINI_OMNI_MAX_CHARACTER_IDS,
    GEMINI_OMNI_VIDEO_MODEL,
    normalize_gemini_omni_ids,
    normalize_gemini_omni_resolution,
    normalize_gemini_omni_seed,
)
from db import repository as repo
from db.models import GenerationType, User
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = Router(name="video_gen")


def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}{query}"


async def _send_video_with_fallback(
    bot: Bot,
    *,
    chat_id: int,
    video_url: str,
    caption: str,
    reply_markup,
) -> None:
    try:
        await bot.send_video(
            chat_id=chat_id,
            video=video_url,
            caption=caption,
            reply_markup=reply_markup,
            supports_streaming=True,
        )
        return
    except TelegramBadRequest as exc:
        if "failed to get HTTP URL content" not in str(exc):
            raise
        logger.warning(
            "Telegram failed to fetch video URL directly, falling back to local upload url=%s error=%s",
            video_url,
            exc,
        )

    tmp_file = None
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Telegram Bot SDK/1.0)",
            "Accept": "*/*",
        }
        async with aiohttp.ClientSession() as http:
            async with http.get(
                video_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=180),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Video download failed: status={resp.status}")
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
                tmp_file = tmp.name
                tmp.close()
                with open(tmp_file, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        if chunk:
                            fh.write(chunk)

        await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(tmp_file),
            caption=caption,
            reply_markup=reply_markup,
            supports_streaming=True,
        )
    except Exception as exc:
        logger.exception(
            "Video fallback upload failed url=%s error=%s",
            video_url,
            exc,
        )
        await bot.send_message(
            chat_id=chat_id,
            text=f"{caption}\n\nСкачать видео: {video_url}",
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                logger.warning("Failed to remove temporary video file: %s", tmp_file)

_DEFAULT_DURATION: dict[str, int] = {
    VideoModel.KLING_26_T2V: 5,
    VideoModel.KLING_26_I2V: 5,
    VideoModel.KLING_30: 5,
    VideoModel.WAN_27_T2V: 5,
    VideoModel.WAN_27_I2V: 5,
    VideoModel.SEEDANCE_2: 5,
    VideoModel.SEEDANCE_2_FAST: 5,
    VideoModel.GROK_T2V: 6,
    VideoModel.HAPPYHORSE_T2V: 5,
    VideoModel.HAPPYHORSE_I2V: 5,
    GEMINI_OMNI_VIDEO_MODEL: 4,
}
_DEFAULT_RATIO: dict[str, str] = {
    VideoModel.KLING_26_T2V: "16:9",
    VideoModel.KLING_30: "16:9",
    VideoModel.WAN_27_T2V: "16:9",
    VideoModel.SEEDANCE_2: "16:9",
    VideoModel.SEEDANCE_2_FAST: "16:9",
    VideoModel.GROK_T2V: "2:3",
    VideoModel.HAPPYHORSE_T2V: "16:9",
    VideoModel.VEO_3_FAST: "16:9",
    VideoModel.VEO_3: "16:9",
    VideoModel.VEO_3_LITE: "16:9",
    GEMINI_OMNI_VIDEO_MODEL: "16:9",
}
_DEFAULT_RES: dict[str, str] = {
    VideoModel.KLING_26_T2V: "720p",
    VideoModel.KLING_26_I2V: "720p",
    VideoModel.WAN_27_T2V: "1080p",
    VideoModel.WAN_27_I2V: "1080p",
    VideoModel.SEEDANCE_2: "720p",
    VideoModel.SEEDANCE_2_FAST: "720p",
    VideoModel.GROK_T2V: "480p",
    VideoModel.GROK_I2V: "480p",
    VideoModel.HAPPYHORSE_T2V: "1080p",
    VideoModel.HAPPYHORSE_I2V: "1080p",
    VideoModel.KLING_30: "pro",
    VideoModel.KLING_26_MOTION: "720p",
    VideoModel.KLING_30_MOTION: "1080p",
    GEMINI_OMNI_VIDEO_MODEL: "720p",
}
_MOTION_MODELS = {VideoModel.KLING_26_MOTION, VideoModel.KLING_30_MOTION}


def _is_per_second_video_model(model_key: str) -> bool:
    return VIDEO_CAPS.get(model_key, {}).get("billing_mode") == "per_second"


def _video_total_credits(model_key: str, duration: int, rate_or_flat: float) -> float:
    if _is_per_second_video_model(model_key):
        return rate_or_flat * duration
    return rate_or_flat


def _video_price_text(model_key: str, duration: int, rate_or_flat: float) -> str:
    total = _video_total_credits(model_key, duration, rate_or_flat)
    if _is_per_second_video_model(model_key):
        return f"{rate_or_flat:g} 💋/сек × {duration} сек = {total:g} 💋"
    return f"{total:g} 💋"


def _has_gemini_omni_video_input(model_key: str, data: dict) -> bool:
    return model_key == GEMINI_OMNI_VIDEO_MODEL and bool(data.get("reference_video_url"))


def _is_feed_video_use(data: dict) -> bool:
    return data.get("feed_use_gen_type") == "video" and data.get("feed_use_prompt") is not None


def _is_video_reuse_prompt(data: dict) -> bool:
    return data.get("video_reuse_prompt") is not None


def _video_params_next_label(data: dict) -> str:
    return "▶️ Запустить" if _is_feed_video_use(data) or _is_video_reuse_prompt(data) else "▶️ Далее: Промпт"


def _video_params_reply_markup(model_key: str, data: dict):
    return video_params_kb(
        model_key,
        data.get("duration"),
        data.get("aspect_ratio"),
        data.get("resolution"),
        data.get("grok_mode"),
        selected_mode=data.get("mode"),
        ref_count=_video_ref_count(data),
        next_label=_video_params_next_label(data),
    )


def _normalize_resolution_for_state(model_key: str, resolution: str | None) -> str | None:
    if model_key == VideoModel.KLING_30:
        aliases = {
            "2K": "pro",
            "720p": "std",
            "1080p": "pro",
            "2160p": "4K",
        }
        return aliases.get(resolution, resolution)
    if model_key == VideoModel.KLING_30_MOTION:
        aliases = {
            "std": "720p",
            "pro": "1080p",
            "2K": "1080p",
            "4K": "1080p",
        }
        return aliases.get(resolution, resolution)
    if model_key != GEMINI_OMNI_VIDEO_MODEL:
        return resolution
    try:
        return normalize_gemini_omni_resolution(resolution)
    except ValueError:
        return "720p"


async def _resolve_video_model_cost(
    session: AsyncSession,
    model_key: str,
    *,
    duration: int | None,
    resolution: str | None,
    has_video_input: bool = False,
):
    return await repo.resolve_video_model_cost(
        session,
        model_key,
        duration=None if has_video_input else duration,
        resolution=_normalize_resolution_for_state(model_key, resolution),
    )


def _params_summary(data: dict) -> str:
    is_gemini_video_ref = data.get("reference_video_url") and data.get("model_key") == GEMINI_OMNI_VIDEO_MODEL
    ref_count = _video_ref_count(data)
    parts = [p for p in [
        data.get("aspect_ratio"),
        "длительность авто" if is_gemini_video_ref else (f"{data['duration']} сек" if data.get("duration") else None),
        data.get("resolution"),
        data.get("grok_mode"),
        f"референсы: {ref_count}" if data.get("mode") == "image" and ref_count else None,
        "видео-референс" if is_gemini_video_ref else None,
        f"Audio ID: {len(data.get('audio_ids') or [])}" if data.get("audio_ids") else None,
        f"Character IDs: {len(data.get('character_ids') or [])}" if data.get("character_ids") else None,
        f"seed {data['seed']}" if data.get("seed") is not None else None,
    ] if p]
    return " · ".join(parts) if parts else "по умолчанию"


def _video_params_hint(model_key: str, data: dict) -> str:
    parts = ["Нажимай кнопки ниже: ✅ показывает выбранные параметры."]
    if model_key == GEMINI_OMNI_VIDEO_MODEL:
        if data.get("mode") == "image":
            max_refs = int(VIDEO_CAPS.get(model_key, {}).get("max_refs", 7) or 7)
            parts.append(f"Фото-референсы: {_video_ref_count(data)}/{max_refs}. Gemini Omni может учитывать до {max_refs} фото.")
        elif data.get("mode") == "video" or data.get("reference_video_url"):
            parts.append("Для видео-референса длительность задаёт модель автоматически; можно настроить формат, качество, Audio ID, Character IDs и seed.")
        else:
            parts.append("Можно добавить 1 Audio ID для голоса и до 3 Character IDs для персонажей.")
    if data.get("mode") == "image" and not _video_ref_count(data) and model_key == VideoModel.GROK_I2V:
        parts.append("Формат кадра появится после загрузки нужного количества референсов.")
    else:
        action = "Запустить" if _is_feed_video_use(data) or _is_video_reuse_prompt(data) else "Далее"
        parts.append(f"Когда всё готово, нажми <b>{action}</b>.")
    return " ".join(parts)


def _video_ref_count(data: dict) -> int:
    if data.get("mode") != "image":
        return 0
    ref_file_ids = data.get("ref_file_ids")
    if isinstance(ref_file_ids, list):
        count = len([item for item in ref_file_ids if item])
        if count:
            return count
    image_url = data.get("image_url")
    if isinstance(image_url, list):
        return len([item for item in image_url if item])
    if image_url or data.get("image_file_id"):
        return 1
    return 0


def _video_max_refs(model_key: str) -> int:
    return int(VIDEO_CAPS.get(model_key, {}).get("max_refs", 1) or 1)


async def _video_reference_image_url(bot: Bot, data: dict) -> str | list[str] | None:
    ref_file_ids = [str(item) for item in (data.get("ref_file_ids") or []) if item]
    image_file_id = data.get("image_file_id")
    if not ref_file_ids and image_file_id:
        ref_file_ids = [str(image_file_id)]

    if ref_file_ids:
        urls = [await mirror_telegram_file(bot, file_id) for file_id in ref_file_ids]
        return urls if len(urls) > 1 else urls[0]

    image_url = data.get("image_url")
    return image_url or None


def _as_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _non_empty(value):
    if value is None or value == "" or value == []:
        return None
    return value


def _url_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _first_url_value(inp: dict, keys: tuple[str, ...]):
    for key in keys:
        urls = _url_list(inp.get(key))
        if urls:
            return urls if len(urls) > 1 else urls[0]
    return None


def _first_scalar(inp: dict, keys: tuple[str, ...]):
    for key in keys:
        value = _non_empty(inp.get(key))
        if value is not None:
            return value
    return None


def _merge_repeat_params(*items: dict) -> dict:
    merged: dict = {}
    for item in items:
        for key, value in item.items():
            if _non_empty(value) is not None:
                merged[key] = value
    return merged


async def _external_source_feed_id(
    *,
    session: AsyncSession,
    db_user: User,
    source_feed_gen_id: int | None,
) -> int | None:
    if not source_feed_gen_id:
        return None
    source = await repo.get_generation_by_id(session, source_feed_gen_id)
    if source and getattr(source, "user_id", None) == getattr(db_user, "id", None):
        return None
    return source_feed_gen_id


async def _video_repeat_params_from_task(task_id: str | None) -> dict:
    if not task_id or task_id.startswith("comet:"):
        return {}
    try:
        payload = await video_service.kieai_client.get_task_status(task_id)
    except Exception as exc:
        logger.warning("Failed to read previous KIE video params task=%s: %s", task_id, exc)
        return {}

    data = _as_dict(payload.get("data"))
    param = _as_dict(data.get("param"))
    inp = _as_dict(param.get("input"))
    if not inp:
        return {}

    video_list = inp.get("video_list")
    video_ref = None
    video_start = None
    video_end = None
    if isinstance(video_list, list) and video_list and isinstance(video_list[0], dict):
        video_ref = video_list[0].get("url")
        video_start = video_list[0].get("start")
        video_end = video_list[0].get("ends")
    if not video_ref:
        video_ref = _first_url_value(inp, ("reference_video_url", "referenceVideoUrl", "video_url", "videoUrl"))
    if not video_ref:
        video_urls = _url_list(inp.get("video_urls") or inp.get("videoUrls"))
        if video_urls:
            video_ref = video_urls[0]

    image_url = _first_url_value(
        inp,
        (
            "image_urls",
            "imageUrls",
            "reference_image_urls",
            "referenceImageUrls",
            "input_urls",
            "inputUrls",
            "image_input",
            "imageInput",
            "image_url",
            "imageUrl",
            "reference_image_url",
            "referenceImageUrl",
            "first_frame_url",
            "firstFrameUrl",
            "input_url",
            "inputUrl",
        ),
    )
    grok_mode = inp.get("mode") if inp.get("mode") in {"fun", "normal", "spicy"} else inp.get("grok_mode")

    return {
        "duration": _first_scalar(inp, ("duration", "duration_sec", "durationSec")),
        "aspect_ratio": _first_scalar(inp, ("aspect_ratio", "aspectRatio", "ratio")),
        "resolution": _first_scalar(inp, ("resolution",)),
        "image_url": image_url,
        "reference_video_url": video_ref,
        "video_start": video_start,
        "video_end": video_end,
        "audio_ids": inp.get("audio_ids"),
        "character_ids": inp.get("character_ids"),
        "seed": inp.get("seed"),
        "grok_mode": grok_mode,
    }


async def _video_repeat_params_for_generation(session: AsyncSession, prev) -> dict:
    stored = _as_dict(getattr(prev, "input_params", None))
    provider = await _video_repeat_params_from_task(getattr(prev, "task_id", None))
    repeat_params = _merge_repeat_params(provider, stored)

    if not repeat_params.get("image_url") and not repeat_params.get("reference_video_url"):
        parent_id = getattr(prev, "parent_generation_id", None)
        if parent_id:
            parent = await repo.get_generation_by_id(session, parent_id)
            parent_type = getattr(getattr(parent, "gen_type", None), "value", getattr(parent, "gen_type", None))
            parent_result_url = getattr(parent, "result_url", None)
            if parent_type == GenerationType.image.value and parent_result_url:
                repeat_params["image_url"] = parent_result_url
    return repeat_params


def _video_state_from_repeat_params(model_key: str, repeat_params: dict) -> dict:
    image_url = repeat_params.get("image_url")
    if isinstance(image_url, list):
        image_url = [str(item) for item in image_url if item]
    elif image_url:
        image_url = str(image_url)
    else:
        image_url = None

    reference_video_url = repeat_params.get("reference_video_url")
    if reference_video_url:
        reference_video_url = str(reference_video_url)

    caps = VIDEO_CAPS.get(model_key, {})
    duration = _as_int(repeat_params.get("duration"), _DEFAULT_DURATION.get(model_key, 5))
    aspect_ratio = repeat_params.get("aspect_ratio") or _DEFAULT_RATIO.get(model_key)
    resolution = _normalize_resolution_for_state(
        model_key,
        repeat_params.get("resolution") or _DEFAULT_RES.get(model_key),
    )
    grok_mode = repeat_params.get("grok_mode") or ("normal" if caps.get("mode_options") else None)
    audio_ids = repeat_params.get("audio_ids") if isinstance(repeat_params.get("audio_ids"), list) else None
    character_ids = (
        repeat_params.get("character_ids")
        if isinstance(repeat_params.get("character_ids"), list)
        else None
    )
    seed = repeat_params.get("seed")
    try:
        seed = normalize_gemini_omni_seed(seed)
    except ValueError:
        seed = None

    return {
        "model_key": model_key,
        "mode": "video" if reference_video_url else ("image" if image_url else "text"),
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "image_url": image_url,
        "reference_video_url": reference_video_url,
        "audio_ids": audio_ids,
        "character_ids": character_ids,
        "seed": seed,
        "grok_mode": grok_mode,
        "video_clip_start": repeat_params.get("video_start"),
        "video_clip_end": repeat_params.get("video_end"),
        "image_file_id": None,
        "ref_file_ids": [],
        "motion_step": None,
    }


def _video_state_has_required_input(data: dict) -> bool:
    model_key = str(data.get("model_key") or "")
    modes = VIDEO_CAPS.get(model_key, {}).get("modes", ["text"])
    mode = data.get("mode")
    if mode == "motion" or ("motion" in modes and "text" not in modes and "image" not in modes):
        return bool(data.get("image_url") and data.get("reference_video_url"))
    if mode == "video":
        return bool(data.get("reference_video_url"))
    if mode == "image" or ("image" in modes and "text" not in modes):
        return bool(data.get("image_url"))
    return bool(data.get("image_url") or data.get("reference_video_url") or "text" in modes)


def _video_input_params_from_generation_state(
    *,
    model_key: str,
    data: dict,
    image_url: str | list[str] | None,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    grok_mode: str | None,
) -> dict:
    return {
        "model_key": model_key,
        "mode": data.get("mode"),
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "image_url": image_url,
        "reference_video_url": data.get("reference_video_url"),
        "video_start": data.get("video_clip_start"),
        "video_end": data.get("video_clip_end"),
        "audio_ids": data.get("audio_ids"),
        "character_ids": data.get("character_ids"),
        "seed": data.get("seed"),
        "grok_mode": grok_mode,
    }


def _video_required_upload_mode(model_key: str, data: dict) -> str | None:
    modes = VIDEO_CAPS.get(model_key, {}).get("modes", ["text"])
    mode = data.get("mode")
    if mode in {"image", "video", "motion"} and mode in modes:
        return str(mode)
    if "motion" in modes:
        return "motion"
    if "image" in modes:
        return "image"
    if "video" in modes:
        return "video"
    return None


def _normalize_aspect_ratio_for_state(model_key: str, mode: str | None, aspect_ratio: str | None, ref_count: int) -> str | None:
    min_refs = int(VIDEO_CAPS.get(model_key, {}).get("aspect_ratio_min_refs", 0) or 0)
    if min_refs and mode == "image" and ref_count < min_refs:
        return None
    return aspect_ratio


def _has_params(model_key: str) -> bool:
    caps = VIDEO_CAPS.get(model_key, {})
    return bool(
        caps.get("duration_options") or
        caps.get("aspect_ratios") or
        (caps.get("has_resolution") and caps.get("resolutions")) or
        caps.get("mode_options")
    )


# ── Model select ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:video")
async def cb_video_menu(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.model_select)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎬 <b>Генерация видео</b>\n\n"
        "Модели разложены по типу задачи, чтобы не искать нужную среди всего списка:\n\n"
        "• <b>✨ Gemini Omni</b> — мультимодальное видео, видео-референс, Audio ID и Character IDs\n"
        "• <b>⚡ Быстрый старт</b> — текст в видео и универсальные модели\n"
        "• <b>🖼️ Из изображения в видео</b> — если хочешь оживить фото\n"
        "• <b>🕺 Управление камерой</b> — если нужно движение камеры и ракурсы\n\n"
        "⏱ Генерация обычно занимает <b>1–5 минут</b> — бот пришлёт видео, когда оно будет готово.\n\n"
        "👇 <b>Сначала выбери категорию:</b>",
        reply_markup=video_model_groups_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.model_select, F.data.startswith("vid_group:"))
async def cb_video_group(call: CallbackQuery, session: AsyncSession) -> None:
    group_key = call.data.split(":")[1]  # type: ignore[union-attr]
    model_costs = await repo.get_all_model_costs(session)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🎬 <b>{VIDEO_GROUP_TITLES.get(group_key, 'Модели')}</b>\n\n"
        "Выбери модель внутри этой категории:",
        reply_markup=video_models_kb(model_costs, group_key),
    )
    await safe_answer_callback(call)


def _split_pipe_fields(text: str, max_parts: int) -> list[str]:
    parts = [part.strip() for part in text.split("|")]
    if len(parts) < max_parts:
        parts.extend([""] * (max_parts - len(parts)))
    return parts[:max_parts]


@router.callback_query(VideoGenFSM.model_select, F.data == "vid_omni_audio")
async def cb_gemini_omni_audio(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.omni_audio_input)
    voices_preview = ", ".join(f"<code>{voice}</code>" for voice in list(GEMINI_OMNI_AUDIO_VOICES)[:12])
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎙️ <b>Gemini Omni Audio ID</b>\n\n"
        "Отправь строку в формате:\n"
        "<code>voice_id | название | описание голоса | пример фразы</code>\n\n"
        "Этот шаг создаёт один ID, который потом можно вставить в параметры видео.\n"
        f"Голоса, с которых удобно начать: {voices_preview}\n"
        "Полный список лежит в документации KIE, сохранённой в <code>docs/kie/gemini-omni-audio.md</code>.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.omni_audio_input, F.text)
async def handle_gemini_omni_audio(message: Message, state: FSMContext) -> None:
    audio_id, name, description, example = _split_pipe_fields(message.text or "", 4)  # type: ignore[union-attr]
    try:
        result = await video_service.create_gemini_omni_audio(
            audio_id=audio_id,
            name=name,
            voice_description=description or None,
            example_dialogue=example or None,
        )
    except Exception as exc:
        await message.answer(f"❌ Не удалось создать Audio ID: {escape(str(exc))}", reply_markup=back_to_menu_kb())
        return

    await state.set_state(VideoGenFSM.model_select)
    await message.answer(
        "✅ <b>Audio ID создан</b>\n\n"
        f"Название: <b>{escape(result.name)}</b>\n"
        f"ID: <code>{escape(result.audio_id)}</code>\n\n"
        "Теперь его можно добавить в параметрах Gemini Omni Video.",
        reply_markup=video_model_groups_kb(),
    )


@router.callback_query(VideoGenFSM.model_select, F.data == "vid_omni_character")
async def cb_gemini_omni_character(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.omni_character_image)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🧍 <b>Gemini Omni Character ID</b>\n\n"
        "Загрузи одно фото персонажа. После фото я попрошу описание, имя и optional Audio ID.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.omni_character_image, F.photo)
async def handle_gemini_omni_character_image(message: Message, state: FSMContext, bot: Bot) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    image_url = await mirror_telegram_file(bot, best[0].file_id)
    await state.update_data(omni_character_image_url=image_url)
    await state.set_state(VideoGenFSM.omni_character_input)
    await message.answer(
        "✅ Фото загружено.\n\n"
        "Отправь строку в формате:\n"
        "<code>описание персонажа | имя | audio_id</code>\n\n"
        "Имя и Audio ID можно оставить пустыми.",
        reply_markup=back_to_menu_kb(),
    )


@router.message(VideoGenFSM.omni_character_input, F.text)
async def handle_gemini_omni_character(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    description, name, audio_raw = _split_pipe_fields(message.text or "", 3)  # type: ignore[union-attr]
    try:
        audio_ids = normalize_gemini_omni_ids(
            audio_raw,
            max_items=GEMINI_OMNI_MAX_AUDIO_IDS,
            field_name="audio_ids",
        )
        result = await video_service.create_gemini_omni_character(
            descriptions=description,
            image_urls=data.get("omni_character_image_url"),
            audio_ids=audio_ids,
            character_name=name or None,
        )
    except Exception as exc:
        await message.answer(f"❌ Не удалось создать Character ID: {escape(str(exc))}", reply_markup=back_to_menu_kb())
        return

    await state.set_state(VideoGenFSM.model_select)
    await message.answer(
        "✅ <b>Character ID создан</b>\n\n"
        + (f"Имя: <b>{escape(result.character_name)}</b>\n" if result.character_name else "")
        + f"ID: <code>{escape(result.character_id)}</code>\n\n"
        "Теперь его можно добавить в параметрах Gemini Omni Video.",
        reply_markup=video_model_groups_kb(),
    )


@router.callback_query(VideoGenFSM.model_select, F.data.startswith("vid_model:"))
async def cb_video_model(
    call: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    model_key = call.data.split(":")[1]  # type: ignore[union-attr]
    default_duration = _DEFAULT_DURATION.get(model_key, 5)
    default_resolution = _DEFAULT_RES.get(model_key)
    model_cost = await _resolve_video_model_cost(
        session,
        model_key,
        duration=default_duration,
        resolution=default_resolution,
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return
    min_credits = _video_total_credits(model_key, default_duration, model_cost.credits)
    if db_user.credits < min_credits:
        await call.answer(
            f"Недостаточно 💋! Нужно минимум {_video_price_text(model_key, default_duration, model_cost.credits)}, у тебя {db_user.credits:g} 💋.",
            show_alert=True,
        )
        return

    await state.update_data(
        model_key=model_key,
        credits=model_cost.credits,
        duration=default_duration,
        aspect_ratio=_DEFAULT_RATIO.get(model_key),
        resolution=default_resolution,
        grok_mode="normal" if VIDEO_CAPS.get(model_key, {}).get("mode_options") else None,
    )

    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    state_data = await state.get_data()
    force_feed_reference = bool(state_data.get("feed_force_reference") and "image" in modes)

    if force_feed_reference:
        await state.update_data(mode="image")
        await _handle_mode(call, state, session, model_key, model_cost.display_name, "image")
    elif len(modes) == 1:
        await state.update_data(mode=modes[0])
        await _handle_mode(call, state, session, model_key, model_cost.display_name, modes[0])
    else:
        await state.set_state(VideoGenFSM.mode_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{model_cost.display_name}</b> ({_video_price_text(model_key, default_duration, model_cost.credits)})\n\nВыбери режим:",
            reply_markup=video_mode_kb(model_key),
        )
    await safe_answer_callback(call)


async def _handle_mode(
    call: CallbackQuery, state: FSMContext,
    session: AsyncSession, model_key: str, display_name: str, mode: str,
) -> None:
    if mode == "image":
        await state.set_state(VideoGenFSM.image_upload)
        max_refs = _video_max_refs(model_key)
        data = await state.get_data()
        if _is_feed_video_use(data):
            upload_text = (
                f"✅ <b>{display_name}</b> · повтор по фото\n\n"
                "🖼️ Загрузи своё фото/референс. Промпт из ленты применю скрыто, "
                "а новый ролик соберу по твоему изображению."
            )
            if max_refs > 1:
                upload_text += f"\n\nМожно отправить до {max_refs} фото; после загрузки нажми <b>Готово</b>."
        elif model_key == GEMINI_OMNI_VIDEO_MODEL:
            upload_text = (
                f"✅ <b>{display_name}</b> · фото-референсы\n\n"
                f"🖼️ Загрузи до {max_refs} фото. Можно отправить несколько фото подряд или альбомом, "
                "после загрузки нажми <b>Готово</b>."
            )
        elif max_refs > 1:
            upload_text = (
                f"✅ <b>{display_name}</b> · фото-референсы\n\n"
                f"🖼️ Загрузи до {max_refs} фото. После загрузки нажми <b>Готово</b>."
            )
        else:
            upload_text = f"✅ <b>{display_name}</b> · анимация по фото\n\n🖼️ Загрузи первый кадр:"
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            upload_text,
            reply_markup=back_to_menu_kb(),
        )
    elif mode == "video":
        await state.set_state(VideoGenFSM.image_upload)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · видео-референс\n\n"
            "🎞️ Загрузи исходное видео до 30 сек. Gemini Omni возьмёт фрагмент до 10 сек.",
            reply_markup=back_to_menu_kb(),
        )
    elif mode == "motion":
        await state.set_state(VideoGenFSM.image_upload)
        await state.update_data(motion_step="person")
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · управление камерой\n\n"
            "👤 <b>Шаг 1/2:</b> Загрузи фото персонажа\n"
            "<i>(голова, плечи, торс; JPEG/PNG; ≤10 МБ)</i>",
            reply_markup=back_to_menu_kb(),
        )
    else:
        await _go_to_params_or_prompt(call, state, model_key, display_name)


# ── Mode select ───────────────────────────────────────────────────────────────

@router.callback_query(VideoGenFSM.mode_select, F.data.startswith("vid_mode:"))
async def cb_video_mode(
    call: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    mode, model_key = parts[1], parts[2]
    data = await state.get_data()
    if data.get("feed_force_reference") and "image" in VIDEO_CAPS.get(model_key, {}).get("modes", []):
        if mode != "image":
            await call.answer("Для повтора из ленты сначала загрузи своё фото.", show_alert=True)
            return
    await state.update_data(mode=mode)
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await _handle_mode(call, state, session, model_key, display_name, mode)
    await safe_answer_callback(call)


# ── Image / person upload ─────────────────────────────────────────────────────

@router.message(VideoGenFSM.image_upload, F.video)
async def handle_video_upload(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    """Motion Control step 2 or Gemini Omni video-to-video upload."""
    data = await state.get_data()
    motion_step: str | None = data.get("motion_step")
    model_key: str = data["model_key"]
    is_gemini_omni_video_mode = model_key == GEMINI_OMNI_VIDEO_MODEL and data.get("mode") == "video"

    if motion_step != "video_url" and not is_gemini_omni_video_mode:
        await message.answer("Пожалуйста, загрузи видео только на шаге 2 управления камерой.", reply_markup=back_to_menu_kb())
        return

    video = message.video  # type: ignore[union-attr]
    video_duration: int = video.duration or 5
    file_id = video.file_id
    stored_resolution: str | None = data.get("resolution")
    resolution = _normalize_resolution_for_state(model_key, stored_resolution)
    if resolution != stored_resolution:
        await state.update_data(resolution=resolution)

    if is_gemini_omni_video_mode and video_duration > 30:
        await message.answer(
            "❌ Gemini Omni принимает видео-референс до 30 секунд. Загрузи более короткий фрагмент.",
            reply_markup=back_to_menu_kb(),
        )
        return

    # Motion Control currently uses Kling, but keep the pricing logic generic.
    model_cost = await _resolve_video_model_cost(
        session,
        model_key,
        duration=data.get("duration"),
        resolution=resolution,
        has_video_input=is_gemini_omni_video_mode,
    )
    rate_or_flat = model_cost.credits if model_cost else int(data.get("credits", 8))
    billable_duration = video_duration if motion_step == "video_url" else int(data.get("duration", 4))
    total_credits = _video_total_credits(model_key, billable_duration, rate_or_flat)

    if db_user.credits < total_credits:
        await message.answer(
            f"❌ Недостаточно 💋!\n"
            f"Видео: {_video_price_text(model_key, billable_duration, rate_or_flat)}\n"
            f"Баланс: {db_user.credits:g} 💋.",
            reply_markup=back_to_menu_kb(),
        )
        return

    # Mirror video to public storage for KIE API
    try:
        video_url = await mirror_telegram_file(bot, file_id, is_video=True)
    except TelegramBadRequest as exc:
        if "file is too big" in str(exc).lower():
            await message.answer(
                "❌ Это видео слишком большое для загрузки через Telegram Bot API, поэтому я не могу автоматически забрать его в обработку.\n\n"
                "Что можно сделать: сожми ролик, укороти его или отправь файл меньшего размера.",
                reply_markup=back_to_menu_kb(),
            )
            return
        raise

    model_cost_obj = await repo.get_model_cost(session, model_key)
    display_name = model_cost_obj.display_name if model_cost_obj else model_key

    if is_gemini_omni_video_mode:
        clip_end = min(video_duration, 10)
        await state.update_data(
            reference_video_url=video_url,
            video_clip_start=0,
            video_clip_end=clip_end,
            credits=rate_or_flat,
        )
        updated = await state.get_data()
        await state.set_state(VideoGenFSM.params_select)
        await message.answer(
            f"✅ Видео загружено! (<b>{_video_price_text(model_key, billable_duration, rate_or_flat)}</b>)\n\n"
            f"⚙️ <b>Параметры</b> · {display_name}\n"
            f"{_video_params_hint(model_key, updated)}",
            reply_markup=_video_params_reply_markup(model_key, updated),
        )
        return

    await state.update_data(
        reference_video_url=video_url,
        motion_duration=video_duration,
        motion_credits=total_credits,
        credits=rate_or_flat,
        motion_step="prompt",
    )
    updated = await state.get_data()
    if _is_video_reuse_prompt(updated):
        await message.answer("✅ Видео загружено! Запускаю с сохранённым промптом.")
        await _launch_video_generation_from_state(
            source_message=message,
            state=state,
            session=session,
            db_user=db_user,
            bot=bot,
            prompt=str(updated["video_reuse_prompt"]),
            source_feed_gen_id=updated.get("source_feed_gen_id"),
            parent_generation_id=updated.get("parent_generation_id"),
            hidden_feed_prompt=bool(updated.get("source_feed_gen_id")),
        )
        return
    await state.set_state(VideoGenFSM.prompt_input)
    await message.answer(
        f"✅ Видео загружено! (<b>{_video_price_text(model_key, video_duration, rate_or_flat)}</b>)\n\n"
        f"✅ <b>{display_name}</b>\n\n"
        "✍️ Введи промпт (или отправь <code>-</code> для пропуска):",
        reply_markup=back_to_menu_kb(),
    )


@router.message(VideoGenFSM.image_upload, F.photo)
async def handle_image_upload(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id

    data = await state.get_data()
    model_key: str = data["model_key"]
    motion_step: str | None = data.get("motion_step")

    if motion_step == "person":
        await state.update_data(image_file_id=file_id, motion_step="video_url")
        await message.answer(
            "✅ Фото загружено!\n\n"
            "🎬 <b>Шаг 2/2:</b> Загрузи референсное видео\n"
            "<i>(видеофайл MP4, макс. 30 сек — бот автоматически определит длину)</i>",
            reply_markup=back_to_menu_kb(),
        )
        await state.set_state(VideoGenFSM.image_upload)
        return

    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    max_refs = _video_max_refs(model_key)

    if max_refs > 1 and data.get("mode") == "image":
        existing = [str(item) for item in (data.get("ref_file_ids") or []) if item]
        if file_id not in existing and len(existing) < max_refs:
            existing.append(file_id)
        await state.update_data(
            image_file_id=existing[0] if existing else file_id,
            ref_file_ids=existing,
            image_url=None,
        )
        can_add_more = len(existing) < max_refs
        await message.answer(
            f"✅ Фото {len(existing)}/{max_refs} загружено!"
            + (f"\nМожно добавить ещё (до {max_refs} фото)." if can_add_more else "\nДостигнут максимум.")
            + "\nКогда все референсы добавлены, нажми <b>Готово</b>.",
            reply_markup=multi_ref_kb(len(existing), max_refs),
        )
        return

    await state.update_data(image_file_id=file_id, ref_file_ids=[file_id], image_url=None)
    await _after_video_ref_upload(message, state, session, model_key, display_name)


async def _after_video_ref_upload(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    model_key: str,
    display_name: str,
) -> None:
    updated = await state.get_data()

    if _has_params(model_key):
        await state.set_state(VideoGenFSM.params_select)
        await message.answer(
            f"✅ Фото загружено!\n\n⚙️ <b>Параметры</b> · {display_name}\n"
            f"{_video_params_hint(model_key, updated)}",
            reply_markup=_video_params_reply_markup(model_key, updated),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await message.answer("✅ Фото загружено!\n\n✍️ Введи промпт:", reply_markup=back_to_menu_kb())


@router.callback_query(VideoGenFSM.image_upload, F.data == "ref:add_more")
async def cb_video_ref_add_more(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    max_refs = _video_max_refs(str(data.get("model_key") or ""))
    await call.answer(f"Отправь следующее фото ({_video_ref_count(data)}/{max_refs})")


@router.callback_query(VideoGenFSM.image_upload, F.data == "ref:done_multi")
async def cb_video_ref_done_multi(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    if _video_ref_count(data) <= 0:
        await call.answer("Сначала загрузи хотя бы одно фото", show_alert=True)
        return
    model_key = str(data["model_key"])
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await _after_video_ref_upload(call.message, state, session, model_key, display_name)  # type: ignore[arg-type]
    await call.answer()


# ── Params select ─────────────────────────────────────────────────────────────

async def _go_to_params_or_prompt(
    call: CallbackQuery, state: FSMContext, model_key: str, display_name: str,
) -> None:
    data = await state.get_data()
    if _has_params(model_key):
        await state.set_state(VideoGenFSM.params_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"⚙️ <b>Параметры</b> · {display_name}\n"
            f"{_video_params_hint(model_key, data)}",
            reply_markup=_video_params_reply_markup(model_key, data),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\n✍️ Введи промпт:",
            reply_markup=back_to_menu_kb(),
        )


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_dur:"))
async def cb_vpar_dur(call: CallbackQuery, state: FSMContext) -> None:
    dur = int(call.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(duration=dur)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_video_params_reply_markup(data["model_key"], data)
    )
    await call.answer(f"{dur} сек")


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_ratio:"))
async def cb_vpar_ratio(call: CallbackQuery, state: FSMContext) -> None:
    ratio = call.data.removeprefix("vpar_ratio:")  # type: ignore[union-attr]
    await state.update_data(aspect_ratio=ratio)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_video_params_reply_markup(data["model_key"], data)
    )
    await call.answer(ratio)


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_res:"))
async def cb_vpar_res(call: CallbackQuery, state: FSMContext) -> None:
    res = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(resolution=res)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_video_params_reply_markup(data["model_key"], data)
    )
    await call.answer(res)


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_mode:"))
async def cb_vpar_mode(call: CallbackQuery, state: FSMContext) -> None:
    mode = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(grok_mode=mode)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_video_params_reply_markup(data["model_key"], data)
    )
    await call.answer(mode)


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_omni:"))
async def cb_vpar_omni_extra(call: CallbackQuery, state: FSMContext) -> None:
    target = call.data.split(":")[1]  # type: ignore[union-attr]
    data = await state.get_data()
    if data.get("model_key") != GEMINI_OMNI_VIDEO_MODEL:
        await call.answer("Этот параметр доступен только для Gemini Omni", show_alert=True)
        return

    await state.update_data(omni_input_target=target)
    await state.set_state(VideoGenFSM.omni_ids_input)
    if target == "audio":
        text = (
            "🎙️ <b>Audio ID</b>\n\n"
            "Отправь один ID. Этот ID создаётся кнопкой "
            "<b>Создать Audio ID</b> в меню Gemini Omni.\n\n"
            "Чтобы очистить поле, отправь <code>-</code>."
        )
    elif target == "character":
        text = (
            "🧍 <b>Character IDs</b>\n\n"
            "Отправь до 3 ID через запятую. Эти ID создаются кнопкой "
            "<b>Создать Character ID</b> в меню Gemini Omni.\n\n"
            "Чтобы очистить поле, отправь <code>-</code>."
        )
    else:
        text = (
            "🌱 <b>Seed</b>\n\n"
            "Отправь целое число от 0 до 2147483647. "
            "Чтобы сбросить seed, отправь <code>-</code>."
        )
    await safe_edit_message(call.message, text, reply_markup=back_to_menu_kb())  # type: ignore[arg-type]
    await call.answer()


@router.message(VideoGenFSM.omni_ids_input, F.text)
async def handle_omni_ids_input(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    target = data.get("omni_input_target")
    raw = (message.text or "").strip()  # type: ignore[union-attr]
    try:
        if target == "audio":
            value = [] if raw == "-" else normalize_gemini_omni_ids(
                raw,
                max_items=GEMINI_OMNI_MAX_AUDIO_IDS,
                field_name="audio_ids",
            )
            await state.update_data(audio_ids=value, omni_input_target=None)
            saved_text = "Audio ID очищен" if not value else "Audio ID добавлен"
        elif target == "character":
            value = [] if raw == "-" else normalize_gemini_omni_ids(
                raw,
                max_items=GEMINI_OMNI_MAX_CHARACTER_IDS,
                field_name="character_ids",
            )
            await state.update_data(character_ids=value, omni_input_target=None)
            saved_text = f"character IDs: {len(value)}"
        else:
            value = None if raw == "-" else normalize_gemini_omni_seed(raw)
            await state.update_data(seed=value, omni_input_target=None)
            saved_text = "seed сброшен" if value is None else f"seed: {value}"
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=back_to_menu_kb())
        return

    updated = await state.get_data()
    model_key = updated["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await state.set_state(VideoGenFSM.params_select)
    await message.answer(
        f"✅ Сохранено: <b>{escape(saved_text)}</b>\n\n"
        f"⚙️ <b>Параметры</b> · {display_name}\n"
        f"{_video_params_hint(model_key, updated)}",
        reply_markup=_video_params_reply_markup(model_key, updated),
    )


@router.callback_query(VideoGenFSM.params_select, F.data == "vpar_next")
async def cb_vpar_next(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    model_cost = await _resolve_video_model_cost(
        session,
        data["model_key"],
        duration=data.get("duration"),
        resolution=data.get("resolution"),
        has_video_input=_has_gemini_omni_video_input(data["model_key"], data),
    )
    display_name = model_cost.display_name if model_cost else data["model_key"]
    if model_cost:
        await state.update_data(credits=model_cost.credits)
    summary = _params_summary(data)
    duration_val = data.get("duration", 5)
    rate_or_flat = float(model_cost.credits if model_cost else data.get("credits", 0))
    await state.update_data(credits=rate_or_flat)
    if _is_feed_video_use(data):
        await safe_answer_callback(call, "Запускаю повтор")
        await _launch_video_generation_from_state(
            source_message=call.message,  # type: ignore[arg-type]
            state=state,
            session=session,
            db_user=db_user,
            bot=bot,
            prompt=str(data["feed_use_prompt"]),
            source_feed_gen_id=data.get("source_feed_gen_id") or data.get("feed_use_gen_id"),
            hidden_feed_prompt=True,
        )
        return

    if _is_video_reuse_prompt(data):
        await safe_answer_callback(call, "Запускаю с новыми параметрами")
        await _launch_video_generation_from_state(
            source_message=call.message,  # type: ignore[arg-type]
            state=state,
            session=session,
            db_user=db_user,
            bot=bot,
            prompt=str(data["video_reuse_prompt"]),
            source_feed_gen_id=data.get("source_feed_gen_id"),
            parent_generation_id=data.get("parent_generation_id"),
            hidden_feed_prompt=bool(data.get("source_feed_gen_id")),
        )
        return

    await state.set_state(VideoGenFSM.prompt_input)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ <b>{display_name}</b> ({_video_price_text(data['model_key'], duration_val, rate_or_flat)})"
        f" · <code>{summary}</code>\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.callback_query(VideoGenFSM.params_select, F.data == "vpar_back")
async def cb_vpar_back(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    if data.get("feed_force_reference"):
        model_costs = await repo.get_all_model_costs(session)
        await state.set_state(VideoGenFSM.model_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🎬 <b>Повторить видео</b>\n\n"
            "Выбери модель для повтора по твоему фото/референсу:",
            reply_markup=video_models_kb(model_costs, "i2v"),
        )
        await call.answer()
        return

    if len(modes) > 1:
        await state.set_state(VideoGenFSM.mode_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\nВыбери режим:",
            reply_markup=video_mode_kb(model_key),
        )
    else:
        model_costs = await repo.get_all_model_costs(session)
        await state.set_state(VideoGenFSM.model_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🎬 <b>Генерация видео</b>\n\nВыбери модель:",
            reply_markup=video_models_kb(model_costs),
        )
    await call.answer()




async def _launch_video_generation_from_state(
    *,
    source_message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    prompt: str,
    source_feed_gen_id: int | None = None,
    parent_generation_id: int | None = None,
    hidden_feed_prompt: bool = False,
) -> bool:
    user_id = db_user.id
    data = await state.get_data()
    model_key: str = data["model_key"]
    duration: int = data.get("duration", 5)
    stored_aspect_ratio: str | None = data.get("aspect_ratio")
    aspect_ratio = _normalize_aspect_ratio_for_state(
        model_key,
        data.get("mode"),
        stored_aspect_ratio,
        _video_ref_count(data),
    )
    if aspect_ratio != stored_aspect_ratio:
        await state.update_data(aspect_ratio=aspect_ratio)
        data = {**data, "aspect_ratio": aspect_ratio}

    stored_resolution: str | None = data.get("resolution")
    resolution = _normalize_resolution_for_state(model_key, stored_resolution)
    if resolution != stored_resolution:
        await state.update_data(resolution=resolution)
        data = {**data, "resolution": resolution}

    grok_mode: str = data.get("grok_mode", "normal")
    image_url = await _video_reference_image_url(bot, data)

    has_gemini_omni_video_input = _has_gemini_omni_video_input(model_key, data)
    model_cost = await _resolve_video_model_cost(
        session,
        model_key,
        duration=duration,
        resolution=resolution,
        has_video_input=has_gemini_omni_video_input,
    )
    motion_credits = data.get("motion_credits")
    if motion_credits is not None:
        credits = int(motion_credits)
    else:
        rate_or_flat = model_cost.credits if model_cost else int(data.get("credits", 0))
        credits = int(_video_total_credits(model_key, duration, rate_or_flat))

    input_params = _video_input_params_from_generation_state(
        model_key=model_key,
        data=data,
        image_url=image_url,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        grok_mode=grok_mode,
    )
    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await source_message.answer("❌ Недостаточно 💋.", reply_markup=main_menu_kb())
        await state.clear()
        return False

    source_feed_gen_id = await _external_source_feed_id(
        session=session,
        db_user=db_user,
        source_feed_gen_id=source_feed_gen_id,
    )
    gen = await repo.create_generation(
        session,
        db_user.id,
        model_key,
        GenerationType.video,
        prompt,
        credits,
        parent_generation_id=parent_generation_id,
        source_feed_gen_id=source_feed_gen_id,
        input_params=input_params,
    )
    gen_id = gen.id

    await state.set_state(VideoGenFSM.generating)
    summary = _params_summary(data)
    status_title = (
        "⏳ <b>Запускаю повтор видео...</b>"
        if hidden_feed_prompt
        else "⏳ <b>Генерирую видео...</b>"
    )
    status_msg = await source_message.answer(
        f"{status_title}\n"
        f"<b>{model_cost.display_name if model_cost else model_key}</b>"
        + (f" · <i>{summary}</i>" if summary != "по умолчанию" else "") +
        "\n\nЭто займёт 2–10 минут."
    )

    try:
        result = await video_service.generate_video(
            VideoModel(model_key),
            prompt,
            image_url=image_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            reference_video_url=data.get("reference_video_url"),
            grok_mode=grok_mode,
            audio_ids=data.get("audio_ids"),
            character_ids=data.get("character_ids"),
            video_start=data.get("video_clip_start"),
            video_end=data.get("video_clip_end"),
            seed=data.get("seed"),
            callback_url=_kie_callback_url(),
        )
    except Exception as e:
        logger.error("Video generation error: %s", e)
        await session.rollback()
        if await repo.fail_generation(session, gen_id, str(e)):
            await repo.add_credits(session, user_id, credits)
        await status_msg.edit_text(
            "❌ Ошибка запуска генерации. 💋 возвращены.\n\n"
            "Попробуй другую модель или повтори через минуту.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return False

    await repo.update_generation_task(session, gen_id, result.task_id)
    poll_fn = video_service.get_poll_fn(result.provider)

    async def on_success(url: str) -> None:
        async with AsyncSessionLocal() as bg_session:
            current = await repo.get_generation_by_id(bg_session, gen_id)
            current_status = getattr(getattr(current, "status", None), "value", getattr(current, "status", None))
            if current_status in {"done", "failed"}:
                return
            await repo.finish_generation(bg_session, gen_id, url)
        try:
            await status_msg.delete()
        except Exception:
            pass
        caption = "✅ <b>Видео готово!</b>"
        if hidden_feed_prompt:
            caption += "\n\nПромпт из ленты применён скрыто."
        else:
            caption += f"\n\n<i>{prompt[:200]}</i>"
        if summary != "по умолчанию":
            caption += f"\n<code>{summary}</code>"
        await _send_video_with_fallback(
            bot,
            chat_id=source_message.chat.id,
            video_url=url,
            caption=caption,
            reply_markup=after_generation_kb(
                gen_id,
                "video",
                allow_publish=not bool(source_feed_gen_id),
                allow_copy_prompt=not bool(source_feed_gen_id),
            ),
        )

    async def on_failure(err: str) -> None:
        async with AsyncSessionLocal() as bg_session:
            current = await repo.get_generation_by_id(bg_session, gen_id)
            current_status = getattr(getattr(current, "status", None), "value", getattr(current, "status", None))
            if current_status in {"done", "failed"}:
                return
            if await repo.fail_generation(bg_session, gen_id, err):
                await repo.add_credits(bg_session, user_id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {err}\n💋 возвращены.", reply_markup=main_menu_kb())

    if getattr(result, "uses_webhook", False) or result.provider == "kieai":
        await status_msg.edit_text(
            "⏳ <b>Видео-задача запущена.</b>\n"
            "Пришлю результат автоматически, как только видео будет готово."
        )
        if result.provider == "comet":
            asyncio.create_task(polling.poll_until_done(result.task_id, poll_fn, on_success, on_failure))
        await state.clear()
        return True

    asyncio.create_task(polling.poll_until_done(result.task_id, poll_fn, on_success, on_failure))
    await state.clear()
    return True


# ── Prompt / motion video URL ─────────────────────────────────────────────────

@router.message(VideoGenFSM.prompt_input, F.text)
async def handle_video_prompt(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    data = await state.get_data()
    model_key: str = data["model_key"]
    motion_step: str | None = data.get("motion_step")
    prompt = message.text.strip()  # type: ignore[union-attr]

    # Motion Control: step 2 — user sent reference video URL
    if motion_step == "video_url":
        await state.update_data(reference_video_url=prompt, motion_step="done")
        await state.set_state(VideoGenFSM.params_select if _has_params(model_key) else VideoGenFSM.generating)
        model_cost = await repo.get_model_cost(session, model_key)
        display_name = model_cost.display_name if model_cost else model_key
        if _has_params(model_key):
            updated = await state.get_data()
            await state.set_state(VideoGenFSM.params_select)
            await message.answer(
                f"✅ Ссылка сохранена!\n\n⚙️ <b>Параметры</b> · {display_name}\n"
                f"{_video_params_hint(model_key, updated)}",
                reply_markup=_video_params_reply_markup(model_key, updated),
            )
        else:
            await state.set_state(VideoGenFSM.prompt_input)
            await state.update_data(motion_step="prompt")
            await message.answer(
                "✅ Ссылка сохранена!\n\n✍️ Введи промпт (или отправь прочерк \"-\" для пропуска):",
                reply_markup=back_to_menu_kb(),
            )
        return

    # Motion Control: optional prompt step
    if motion_step == "prompt":
        prompt = prompt if prompt != "-" else ""
        await state.update_data(motion_prompt=prompt, motion_step="done")

    updated = await state.get_data()
    await _launch_video_generation_from_state(
        source_message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        prompt=prompt,
        source_feed_gen_id=updated.get("source_feed_gen_id"),
        parent_generation_id=updated.get("parent_generation_id"),
    )


async def _video_generation_for_result_action(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
) -> object | None:
    parts = (call.data or "").split(":")
    gen_id_raw = parts[2] if len(parts) >= 3 else ""
    if not gen_id_raw.isdigit():
        await call.answer("Генерация не найдена", show_alert=True)
        return None

    prev = await repo.get_generation_by_id(session, int(gen_id_raw))
    gen_type = getattr(getattr(prev, "gen_type", None), "value", getattr(prev, "gen_type", None))
    if (
        not prev
        or getattr(prev, "user_id", None) != db_user.id
        or not getattr(prev, "prompt", None)
        or (gen_type is not None and gen_type != GenerationType.video.value)
    ):
        await call.answer("Генерация не найдена", show_alert=True)
        return None

    model_key = str(getattr(prev, "model", ""))
    if model_key not in VIDEO_CAPS:
        await call.answer("Эту видео-модель нельзя повторить", show_alert=True)
        return None
    try:
        VideoModel(model_key)
    except ValueError:
        await call.answer("Эту видео-модель нельзя повторить", show_alert=True)
        return None
    return prev


async def _restore_video_result_state(
    *,
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    prev,
    reuse_prompt: str | None,
    source_feed_gen_id: int | None,
) -> tuple[str, str, dict] | None:
    model_key = str(prev.model)
    repeat_data = _video_state_from_repeat_params(
        model_key,
        await _video_repeat_params_for_generation(session, prev),
    )
    model_cost = await _resolve_video_model_cost(
        session,
        model_key,
        duration=repeat_data.get("duration"),
        resolution=repeat_data.get("resolution"),
        has_video_input=_has_gemini_omni_video_input(model_key, repeat_data),
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return None

    await state.update_data(
        **repeat_data,
        credits=model_cost.credits,
        parent_generation_id=prev.id,
        source_feed_gen_id=source_feed_gen_id,
        video_reuse_prompt=reuse_prompt,
        feed_use_gen_type=None,
        feed_use_prompt=None,
        feed_use_gen_id=None,
        feed_force_reference=None,
    )
    restored = await state.get_data()
    return model_key, model_cost.display_name, restored


@router.callback_query(F.data.startswith("reprompt:video:"))
async def cb_reprompt_video(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    prev = await _video_generation_for_result_action(call, session, db_user)
    if not prev:
        return

    restored = await _restore_video_result_state(
        call=call,
        session=session,
        state=state,
        prev=prev,
        reuse_prompt=None,
        source_feed_gen_id=None,
    )
    if not restored:
        return
    model_key, display_name, data = restored

    if not _video_state_has_required_input(data):
        upload_mode = _video_required_upload_mode(model_key, data)
        if not upload_mode:
            await call.answer("Не удалось восстановить входные данные", show_alert=True)
            return
        await state.update_data(mode=upload_mode)
        await _handle_mode(call, state, session, model_key, display_name, upload_mode)
        await safe_answer_callback(call)
        return

    await state.set_state(VideoGenFSM.prompt_input)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "✏️ <b>Новый промпт для видео</b>\n\n"
        f"Модель: <b>{escape(display_name)}</b>\n"
        f"Параметры: <code>{escape(_params_summary(data))}</code>\n\n"
        "Введи новый промпт:",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("reparams:video:"))
async def cb_reparams_video(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    prev = await _video_generation_for_result_action(call, session, db_user)
    if not prev:
        return

    source_feed_gen_id = getattr(prev, "source_feed_gen_id", None)
    restored = await _restore_video_result_state(
        call=call,
        session=session,
        state=state,
        prev=prev,
        reuse_prompt=str(prev.prompt),
        source_feed_gen_id=source_feed_gen_id,
    )
    if not restored:
        return
    model_key, display_name, data = restored

    if not _video_state_has_required_input(data):
        upload_mode = _video_required_upload_mode(model_key, data)
        if not upload_mode:
            await call.answer("Не удалось восстановить входные данные", show_alert=True)
            return
        await state.update_data(mode=upload_mode)
        await _handle_mode(call, state, session, model_key, display_name, upload_mode)
        await safe_answer_callback(call)
        return

    if _has_params(model_key):
        await state.set_state(VideoGenFSM.params_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"⚙️ <b>Изменить параметры</b> · {escape(display_name)}\n"
            f"{_video_params_hint(model_key, data)}",
            reply_markup=_video_params_reply_markup(model_key, data),
        )
        await safe_answer_callback(call)
        return

    await safe_answer_callback(call, "Запускаю с прежним промптом")
    await _launch_video_generation_from_state(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        prompt=str(prev.prompt),
        source_feed_gen_id=source_feed_gen_id,
        parent_generation_id=prev.id,
        hidden_feed_prompt=bool(source_feed_gen_id),
    )


@router.callback_query(F.data.startswith("regen:video:"))
async def cb_regen_video(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    user_id = db_user.id
    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    prev = await repo.get_generation_by_id(session, gen_id)
    if not prev or prev.user_id != db_user.id or not prev.prompt:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    model_key = str(prev.model)
    if model_key not in VIDEO_CAPS:
        await call.answer("Эту видео-модель нельзя повторить", show_alert=True)
        return

    try:
        video_model = VideoModel(model_key)
    except ValueError:
        await call.answer("Эту видео-модель нельзя повторить", show_alert=True)
        return

    repeat_params = await _video_repeat_params_for_generation(session, prev)
    image_url = repeat_params.get("image_url")
    if isinstance(image_url, list):
        image_url = [str(item) for item in image_url if item]
    elif image_url:
        image_url = str(image_url)
    else:
        image_url = None

    reference_video_url = repeat_params.get("reference_video_url")
    if reference_video_url:
        reference_video_url = str(reference_video_url)

    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    if not image_url and not reference_video_url and "text" not in modes:
        await call.answer(
            "Для повтора этой модели нужен исходный референс. Загрузи его заново.",
            show_alert=True,
        )
        return

    duration = _as_int(repeat_params.get("duration"), _DEFAULT_DURATION.get(model_key, 5))
    aspect_ratio = repeat_params.get("aspect_ratio") or _DEFAULT_RATIO.get(model_key)
    resolution = _normalize_resolution_for_state(
        model_key,
        repeat_params.get("resolution") or _DEFAULT_RES.get(model_key),
    )
    grok_mode = repeat_params.get("grok_mode") or ("normal" if caps.get("mode_options") else None)
    audio_ids = repeat_params.get("audio_ids") if isinstance(repeat_params.get("audio_ids"), list) else None
    character_ids = repeat_params.get("character_ids") if isinstance(repeat_params.get("character_ids"), list) else None
    seed = repeat_params.get("seed")
    try:
        seed = normalize_gemini_omni_seed(seed)
    except ValueError:
        seed = None

    mode = "video" if reference_video_url else ("image" if image_url else "text")
    repeat_data = {
        "model_key": model_key,
        "mode": mode,
        "duration": duration,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "image_url": image_url,
        "reference_video_url": reference_video_url,
        "audio_ids": audio_ids,
        "character_ids": character_ids,
        "seed": seed,
        "grok_mode": grok_mode,
    }
    input_params = {
        **repeat_data,
        "video_start": repeat_params.get("video_start"),
        "video_end": repeat_params.get("video_end"),
    }
    has_gemini_omni_video_input = _has_gemini_omni_video_input(model_key, repeat_data)
    model_cost = await _resolve_video_model_cost(
        session,
        model_key,
        duration=duration,
        resolution=resolution,
        has_video_input=has_gemini_omni_video_input,
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return

    credits = int(_video_total_credits(model_key, duration, model_cost.credits))
    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await call.answer("Недостаточно 💋", show_alert=True)
        return

    source_feed_gen_id = await _external_source_feed_id(
        session=session,
        db_user=db_user,
        source_feed_gen_id=getattr(prev, "source_feed_gen_id", None),
    )
    await safe_answer_callback(call, "🔁 Запускаю ещё вариант")
    gen = await repo.create_generation(
        session,
        db_user.id,
        model_key,
        GenerationType.video,
        prev.prompt,
        credits,
        parent_generation_id=prev.id,
        source_feed_gen_id=source_feed_gen_id,
        input_params=input_params,
    )
    gen_id = gen.id

    summary = _params_summary(repeat_data)
    status_msg = await call.message.answer(  # type: ignore[union-attr]
        f"🔁 <b>Готовлю ещё вариант...</b>\n"
        f"<b>{model_cost.display_name}</b>"
        + (f" · <i>{summary}</i>" if summary != "по умолчанию" else "") +
        "\n\nЭто займёт 2–10 минут."
    )

    try:
        result = await video_service.generate_video(
            video_model,
            prev.prompt,
            image_url=image_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            reference_video_url=reference_video_url,
            grok_mode=str(grok_mode or "normal"),
            audio_ids=audio_ids,
            character_ids=character_ids,
            video_start=repeat_params.get("video_start"),
            video_end=repeat_params.get("video_end"),
            seed=seed,
            callback_url=_kie_callback_url(),
        )
    except Exception as exc:
        logger.error("Video regeneration error: %s", exc)
        await session.rollback()
        if await repo.fail_generation(session, gen_id, str(exc)):
            await repo.add_credits(session, user_id, credits)
        await status_msg.edit_text(
            "❌ Ошибка запуска повтора. 💋 возвращены.\n\nПопробуй другую модель или повтори через минуту.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    await repo.update_generation_task(session, gen_id, result.task_id)
    poll_fn = video_service.get_poll_fn(result.provider)

    async def on_success(url: str) -> None:
        async with AsyncSessionLocal() as bg_session:
            current = await repo.get_generation_by_id(bg_session, gen_id)
            current_status = getattr(getattr(current, "status", None), "value", getattr(current, "status", None))
            if current_status in {"done", "failed"}:
                return
            await repo.finish_generation(bg_session, gen_id, url)
        try:
            await status_msg.delete()
        except Exception:
            pass
        caption = "✅ <b>Видео готово!</b>"
        if source_feed_gen_id:
            caption += "\n\nПромпт из ленты применён скрыто."
        else:
            caption += f"\n\n<i>{prev.prompt[:200]}</i>"
        if summary != "по умолчанию":
            caption += f"\n<code>{summary}</code>"
        await _send_video_with_fallback(
            bot,
            chat_id=call.message.chat.id,  # type: ignore[union-attr]
            video_url=url,
            caption=caption,
            reply_markup=after_generation_kb(
                gen_id,
                "video",
                allow_publish=not bool(source_feed_gen_id),
                allow_copy_prompt=not bool(source_feed_gen_id),
            ),
        )

    async def on_failure(err: str) -> None:
        async with AsyncSessionLocal() as bg_session:
            current = await repo.get_generation_by_id(bg_session, gen_id)
            current_status = getattr(getattr(current, "status", None), "value", getattr(current, "status", None))
            if current_status in {"done", "failed"}:
                return
            if await repo.fail_generation(bg_session, gen_id, err):
                await repo.add_credits(bg_session, user_id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {err}\n💋 возвращены.", reply_markup=main_menu_kb())

    if getattr(result, "uses_webhook", False) or result.provider == "kieai":
        await status_msg.edit_text(
            "⏳ <b>Видео-задача запущена.</b>\n"
            "Пришлю результат автоматически, как только видео будет готово."
        )
        if result.provider == "comet":
            asyncio.create_task(polling.poll_until_done(result.task_id, poll_fn, on_success, on_failure))
        await state.clear()
        return

    asyncio.create_task(polling.poll_until_done(result.task_id, poll_fn, on_success, on_failure))
    await state.clear()
