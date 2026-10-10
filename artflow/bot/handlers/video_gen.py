# bot/handlers/video_gen.py
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import tempfile
from html import escape
from urllib.parse import urlencode

import aiohttp
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from api import polling, video_service
from api.genjutsu_adapter import (
    DISPLAY_NAMES as GENJUTSU_DISPLAY_NAMES,
)
from api.genjutsu_adapter import (
    MAX_DURATION_SECONDS as GENJUTSU_MAX_DURATION_SECONDS,
)
from api.genjutsu_adapter import (
    MIN_DURATION_SECONDS as GENJUTSU_MIN_DURATION_SECONDS,
)
from api.genjutsu_adapter import (
    MODEL_KEYS as GENJUTSU_MODEL_KEYS,
)
from api.genjutsu_adapter import (
    is_genjutsu_configured,
)
from api.genjutsu_adapter import (
    resolve_source_duration_seconds as resolve_genjutsu_source_duration,
)
from api.neironych_seedance import NeironychPreSubmitFailure, NeironychSubmissionUnknown
from api.public_files import mirror_telegram_file
from api.seedance25_adapter import (
    CONTROL_PREFIX as SEEDANCE25_CONTROL_PREFIX,
)
from api.seedance25_adapter import (
    MODEL_KEY as SEEDANCE25_MODEL_KEY,
)
from api.seedance25_adapter import (
    _control_payload as seedance25_control_payload,
)
from api.video_prompt_limits import (
    append_telegram_seedance_prompt_chunk,
    seedance_prompt_max_chars,
    validate_video_prompt,
    video_prompt_max_chars,
)
from api.video_runtime_fixes import seedance25_edit_billing_duration
from api.video_service import VideoModel
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    VIDEO_CAPS,
    VIDEO_GROUP_TITLES,
    after_generation_kb,
    feed_video_models_kb,
    model_cost_display_text,
    multi_ref_kb,
    video_mode_kb,
    video_model_groups_kb,
    video_models_kb,
    video_params_kb,
)
from bot.keyboards.video_navigation import video_back_kb
from bot.states import VideoGenFSM
from bot.utils.feed_media import canonical_generation_result_url
from bot.utils.generation_reference import provider_task_reference
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from core.feed_remix_prompt import (
    FEED_REMIX_CONTEXT_KEY,
    FeedRemixUnavailable,
    build_feed_remix_prompt,
    feed_remix_context,
    feed_video_edit_prompt,
    generation_prompt_is_protected,
    legacy_feed_edit_unavailable,
    original_feed_video_references,
    supports_feed_source_media,
    trusted_feed_prompt,
)
from core.gemini_omni import (
    GEMINI_OMNI_AUDIO_VOICES,
    GEMINI_OMNI_MAX_AUDIO_IDS,
    GEMINI_OMNI_MAX_CHARACTER_IDS,
    GEMINI_OMNI_VIDEO_MODEL,
    normalize_gemini_omni_ids,
    normalize_gemini_omni_resolution,
    normalize_gemini_omni_seed,
    validate_gemini_omni_media_slots,
)
from core.seedance_reconciliation import (
    handle_submission_not_sent,
    handle_submission_unknown,
    make_submission_context,
    persist_submission_result,
)
from core.seedance_repeat_overrides import (
    build_seedance_content_edit_prompt,
    build_seedance_repeat_prompt,
    build_seedance_repeat_reference_plan,
    restore_seedance_reference_plan,
)
from db import repository as repo
from db.models import GenerationType, User
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
router = Router(name="video_gen")


async def _show_video_submission_review(
    status_msg: Message, state: FSMContext, session: AsyncSession, gen_id: int,
) -> None:
    """Keep the launch acknowledgement while recovery runs without user chatter."""
    logger.info("Video submission recovery continues silently gen=%s", gen_id)
    await state.clear()


async def _show_video_task_started(status_msg: Message, task_id: str) -> None:
    try:
        await status_msg.edit_text(
            "⏳ <b>Видео-задача запущена.</b>\n"
            "Пришлю результат автоматически, как только видео будет готово."
            + provider_task_reference(task_id)
        )
    except Exception as exc:
        logger.warning("Could not update video task acknowledgment task_id=%s: %s", task_id, exc)


def _long_prompt_done_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Готово", callback_data="vid_prompt:done"),
    ]])


def _seedance_repeat_edit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔢 Число / цифры", callback_data="s25repeat:number"),
            InlineKeyboardButton(text="👕 Одежда", callback_data="s25repeat:clothing"),
        ],
        [InlineKeyboardButton(text="⚙️ Остальные параметры", callback_data="s25repeat:params")],
        [InlineKeyboardButton(text="▶️ Запустить повтор", callback_data="s25repeat:launch")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
    ])


def _seedance_repeat_edit_text(display_name: str, data: dict) -> str:
    number = str(data.get("seedance_repeat_number") or "").strip()
    clothing = str(data.get("seedance_repeat_clothing") or "").strip()
    has_clothing_ref = bool(data.get("seedance_repeat_clothing_file_id"))
    clothing_value = (
        f"{escape(clothing)} + фото-референс"
        if clothing and has_clothing_ref
        else escape(clothing)
        if clothing
        else "фото-референс"
        if has_clothing_ref
        else "не менять"
    )
    return (
        f"🎬 <b>{escape(display_name)} · повтор</b>\n\n"
        "Бот сам назначит роли референсов для Seedance:\n"
        "• готовый ролик → <code>@Video1</code>\n"
        "• фото лица → первые <code>@ImageN</code> (если были)\n"
        "• фото одежды → следующий <code>@ImageN</code>\n\n"
        f"🔢 Число / цифры: <b>{escape(number) if number else 'не менять'}</b>\n"
        f"👕 Одежда: <b>{clothing_value}</b>\n\n"
        "Индексы @ImageN вводить вручную не нужно."
    )


def _seedance_repeat_has_legacy_identity(data: dict) -> bool:
    marker = f"{SEEDANCE25_CONTROL_PREFIX}identity_transfer="
    for raw in data.get("audio_ids") or []:
        value = str(raw or "").strip().lower()
        if value.startswith(marker) and value[len(marker):] in {"1", "true", "yes", "on"}:
            return True
    return False


def _seedance_repeat_without_identity_control(values: object) -> list[str]:
    marker = f"{SEEDANCE25_CONTROL_PREFIX}identity_transfer="
    return [
        str(item)
        for item in (values or [])
        if str(item or "").strip() and not str(item).strip().lower().startswith(marker)
    ]


async def _launch_collected_seedance_prompt(
    *,
    source_message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    prompt: str,
) -> None:
    data = await state.get_data()
    await state.update_data(seedance_prompt_buffer="")
    await _launch_video_generation_from_state(
        source_message=source_message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        prompt=prompt,
        source_feed_gen_id=data.get("source_feed_gen_id"),
        parent_generation_id=data.get("parent_generation_id"),
    )


def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}{query}"


def _start_video_polling(result, poll_fn, on_success, on_failure) -> None:
    """Launch provider-specific foreground polling, except durable Seedance jobs.

    Neironych Seedance runs exclusively through the recovery scheduler and
    transactional notice outbox. The generic foreground poller refunds on
    timeout/HTTP errors and can race the outbox, duplicating media downloads.
    """
    if getattr(result, "provider", None) == "neironych":
        logger.info("Neironych video entrusted to durable reconciler task=%s", result.task_id)
        return
    asyncio.create_task(
        polling.poll_until_done(
            result.task_id,
            poll_fn,
            on_success,
            on_failure,
            provider=result.provider,
        )
    )


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
    **{model_key: 1 for model_key in GENJUTSU_MODEL_KEYS},
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
    **{model_key: "480p" for model_key in GENJUTSU_MODEL_KEYS},
}
_MOTION_MODELS = {VideoModel.KLING_26_MOTION, VideoModel.KLING_30_MOTION}


def _is_per_second_video_model(model_key: str) -> bool:
    return VIDEO_CAPS.get(model_key, {}).get("billing_mode") == "per_second"


def _video_total_credits(model_key: str, duration: int, rate_or_flat: float) -> float:
    if _is_per_second_video_model(model_key):
        return round(rate_or_flat * duration, 6)
    return round(rate_or_flat, 6)


def _video_price_text(model_key: str, duration: int, rate_or_flat: float) -> str:
    total = _video_total_credits(model_key, duration, rate_or_flat)
    if _is_per_second_video_model(model_key):
        return f"{rate_or_flat:g} 💋/сек × {duration} сек = {total:g} 💋"
    return f"{total:g} 💋"


def _has_gemini_omni_video_input(model_key: str, data: dict) -> bool:
    return model_key == GEMINI_OMNI_VIDEO_MODEL and bool(data.get("reference_video_url"))


def _video_upload_billable_duration(
    data: dict,
    *,
    video_duration: int,
    motion_step: str | None,
    is_genjutsu_video_mode: bool,
) -> int:
    if (
        motion_step == "video_url"
        or is_genjutsu_video_mode
        or (
            data.get("model_key") == SEEDANCE25_MODEL_KEY
            and data.get("seedance_identity_transfer")
        )
    ):
        return video_duration
    return int(data.get("duration", 4))


def _is_feed_video_use(data: dict) -> bool:
    return data.get("feed_use_gen_type") == "video" and data.get("feed_use_prompt") is not None


def _is_video_reuse_prompt(data: dict) -> bool:
    return data.get("video_reuse_prompt") is not None


def _video_params_next_label(data: dict) -> str:
    if data.get("video_review_edit"):
        return "✅ К проверке задачи"
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
        identity_transfer=bool(data.get("seedance_identity_transfer")),
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
        "исходное видео" if data.get("model_key") in GENJUTSU_MODEL_KEYS and data.get("reference_video_url") else None,
        f"Audio ID: {len(data.get('audio_ids') or [])}" if data.get("audio_ids") else None,
        f"Character IDs: {len(data.get('character_ids') or [])}" if data.get("character_ids") else None,
        f"seed {data['seed']}" if data.get("seed") is not None else None,
    ] if p]
    return " · ".join(parts) if parts else "по умолчанию"


def _video_params_hint(model_key: str, data: dict) -> str:
    if model_key == SEEDANCE25_MODEL_KEY and data.get("seedance_identity_transfer"):
        return (
            "🎭 Фото задают внешность персонажа, исходное видео — только движение и сцену. "
            "Выбери качество <b>480p</b>, <b>720p</b> или <b>1080p</b>, затем нажми <b>Далее</b>."
        )
    parts = ["Нажимай кнопки ниже: ✅ показывает выбранные параметры."]
    if model_key == GEMINI_OMNI_VIDEO_MODEL:
        if data.get("mode") == "image":
            max_refs = int(VIDEO_CAPS.get(model_key, {}).get("max_refs", 7) or 7)
            parts.append(f"Фото-референсы: {_video_ref_count(data)}/{max_refs}. Gemini Omni может учитывать до {max_refs} фото.")
        elif data.get("mode") == "video" or data.get("reference_video_url"):
            parts.append("Для видео-референса длительность задаёт модель автоматически; можно настроить формат, качество, Audio ID, Character IDs и seed.")
        else:
            parts.append("Можно добавить 1 Audio ID для голоса и до 3 Character IDs для персонажей.")
    if model_key in GENJUTSU_MODEL_KEYS:
        parts.append(
            f"Genjutsu использует все загруженные референсы и полный исходный ролик "
            f"от {GENJUTSU_MIN_DURATION_SECONDS} до {GENJUTSU_MAX_DURATION_SECONDS} секунд."
        )
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


def _video_max_refs_for_state(data: dict) -> int:
    if data.get("model_key") == SEEDANCE25_MODEL_KEY and data.get("seedance_identity_transfer"):
        return 3
    return _video_max_refs(str(data.get("model_key") or ""))


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


def _seedance_effective_video_refs(data: dict) -> list[str]:
    _, extra_video_refs, _ = seedance25_control_payload(_url_list(data.get("audio_ids")))
    return list(dict.fromkeys([*_url_list(data.get("reference_video_url")), *extra_video_refs]))


async def _seedance_edit_duration_from_state(prompt: str, data: dict, *, force_edit: bool = False) -> int | None:
    _, _, controls = seedance25_control_payload(_url_list(data.get("audio_ids")))
    try:
        return await seedance25_edit_billing_duration(
            prompt, _seedance_effective_video_refs(data),
            force_edit=force_edit or bool(controls.get("identity_transfer")),
        )
    except ValueError:
        raise
    except Exception as exc:
        logger.warning("Seedance source preflight failed error_type=%s", type(exc).__name__)
        raise ValueError(
            "Не удалось проверить исходное видео. Поцелуи не списаны. Попробуй позже или загрузи ролик заново."
        ) from exc


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
    if (source and getattr(source, "user_id", None) == getattr(db_user, "id", None)
            and not generation_prompt_is_protected(source)):
        return None
    return source_feed_gen_id


async def _prepare_feed_video_inputs(
    *, session: AsyncSession, db_user: User, source_feed_gen_id: int | None,
    model_key: str, prompt: str, image_url: str | list[str] | None, data: dict,
    parent_generation_id: int | None = None,
) -> tuple[str, str | list[str] | None, dict, int | None]:
    source_feed_gen_id = await _external_source_feed_id(
        session=session, db_user=db_user, source_feed_gen_id=source_feed_gen_id,
    )
    if not source_feed_gen_id:
        return prompt, image_url, data, None
    source = await repo.get_public_feed_generation(session, source_feed_gen_id)
    source_type = getattr(getattr(source, "gen_type", None), "value", getattr(source, "gen_type", None))
    source_url = canonical_generation_result_url(source) if source else None
    refs = list(dict.fromkeys(_url_list(image_url)))
    if source_type == "video":
        original_videos = original_feed_video_references(source)
        if original_videos is not None:
            if prompt.strip() != str(source.prompt or "").strip():
                raise legacy_feed_edit_unavailable()
            if not refs:
                raise FeedRemixUnavailable("Для повтора загрузи своё фото-референс.")
            caps = VIDEO_CAPS.get(model_key, {})
            if not supports_feed_source_media(caps, "image"):
                raise FeedRemixUnavailable("Эта модель не поддерживает фото-референсы.")
            if original_videos and not supports_feed_source_media(caps, "video"):
                raise FeedRemixUnavailable("Эта модель не поддерживает исходные видео-референсы.")
            if len(original_videos) > 1 and model_key != SEEDANCE25_MODEL_KEY:
                raise FeedRemixUnavailable("Эта модель не поддерживает несколько исходных видео.")
            limit = int(caps.get("max_refs", 1) or 1)
            if original_videos and caps.get("max_refs_with_video") is not None:
                limit = min(limit, int(caps["max_refs_with_video"]))
            if len(refs) > limit:
                raise FeedRemixUnavailable(f"Модель поддерживает до {limit} фото.")
            submitted_videos = _seedance_effective_video_refs(data) if model_key == SEEDANCE25_MODEL_KEY else _url_list(data.get("reference_video_url"))
            # The old bot could prefill the rendered MP4. Discard only that
            # outdated value; never permit a new unsolicited video in a replay.
            if any(url not in original_videos and url != source_url for url in submitted_videos):
                raise FeedRemixUnavailable("В повторе нельзя добавлять новый видео-референс.")
            audio_ids = [
                token for token in _url_list(data.get("audio_ids"))
                if not token.startswith(f"{SEEDANCE25_CONTROL_PREFIX}video_ref=")
            ]
            if len(original_videos) > 1:
                audio_ids.extend(f"{SEEDANCE25_CONTROL_PREFIX}video_ref={url}" for url in original_videos[1:])
            data = {
                **data,
                "reference_video_url": original_videos[0] if original_videos else None,
                "feed_use_source_video_url": original_videos[0] if original_videos else None,
                "audio_ids": audio_ids,
                "mode": "multimodal" if caps.get("auto_route_by_inputs") else "image",
                FEED_REMIX_CONTEXT_KEY: feed_remix_context(source_feed_gen_id, source.prompt),
            }
            logger.info(
                "feed_creator_replay source_gen=%s model=%s photo_refs=%s original_video_refs=%s",
                source_feed_gen_id, model_key, len(refs), len(original_videos),
            )
            return source.prompt, refs if model_key == SEEDANCE25_MODEL_KEY or len(refs) > 1 else refs[0], data, source_feed_gen_id
    user_refs = any(url != source_url or source_type != "image" for url in refs)
    source_videos = (
        _seedance_effective_video_refs(data) if model_key == SEEDANCE25_MODEL_KEY
        else list(dict.fromkeys(_url_list(data.get("reference_video_url"))))
    )
    personalized = bool(
        prompt.strip() != str(getattr(source, "prompt", "") or "").strip()
        or user_refs or data.get("audio_ids") or data.get("character_ids")
        or (source_videos and (source_type != "video" or source_videos != [source_url]))
        or data.get("seedance_repeat_editor") or data.get("flow_id") == "genjutsu_face_clothing"
    )
    if not personalized:
        return prompt, image_url, data, source_feed_gen_id

    caps = VIDEO_CAPS.get(model_key, {})
    applicable = bool(source_url) and (
        bool(caps.get("supports_video_input")) if source_type == "video"
        else supports_feed_source_media(caps, source_type)
    )
    # Stored/reused prompts may include private author text. Only later
    # user-authored edit controls may extend this public base.
    previous = (
        await repo.get_generation_by_id(session, parent_generation_id)
        if parent_generation_id and parent_generation_id != source_feed_gen_id else None
    )
    safe_previous = trusted_feed_prompt(previous, user_id=db_user.id, source_generation_id=source_feed_gen_id)
    if prompt.strip() != str(getattr(source, "prompt", "") or "").strip() and safe_previous is None:
        raise legacy_feed_edit_unavailable()
    public_base = build_feed_remix_prompt("", has_user_references=True, has_source_media=applicable)
    prompt = safe_previous or public_base
    if model_key == SEEDANCE25_MODEL_KEY and source_type == "video":
        prompt = feed_video_edit_prompt(prompt)
    data = {**data, FEED_REMIX_CONTEXT_KEY: feed_remix_context(source_feed_gen_id, prompt)}
    if source_type == "image":
        refs = list(dict.fromkeys([source_url, *refs]))
        max_refs = int(caps.get("max_refs", 1) or 1)
        if len(refs) > max_refs:
            raise FeedRemixUnavailable("Слишком много фото с учётом исходного поста. Выбери другую модель или убери лишние референсы.")
        image_url = refs[0] if len(refs) == 1 else refs
    else:
        if source_videos and source_videos != [source_url]:
            raise FeedRemixUnavailable("Для повтора нужен исходный ролик из ленты. Убери дополнительное видео.")
        data = {**data, "reference_video_url": source_url}
    max_refs = int(caps.get("max_refs", 1) or 1)
    if len(refs) > max_refs:
        raise FeedRemixUnavailable(f"Модель поддерживает до {max_refs} фото с учётом исходного поста.")
    if model_key == GEMINI_OMNI_VIDEO_MODEL:
        try:
            characters = normalize_gemini_omni_ids(data.get("character_ids"), field_name="character_ids", max_items=GEMINI_OMNI_MAX_CHARACTER_IDS)
            normalize_gemini_omni_ids(data.get("audio_ids"), field_name="audio_ids", max_items=GEMINI_OMNI_MAX_AUDIO_IDS)
            validate_gemini_omni_media_slots(
                image_count=len(refs), video_count=int(bool(data.get("reference_video_url"))),
                character_count=len(characters),
            )
        except ValueError as exc:
            raise FeedRemixUnavailable(str(exc)) from exc
    return prompt, image_url, data, source_feed_gen_id


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
    if isinstance(reference_video_url, list):
        reference_video_url = _url_list(reference_video_url)
    elif reference_video_url:
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
    seedance_reference_roles = (
        [str(item) for item in repeat_params.get("seedance_reference_roles") if str(item or "").strip()]
        if isinstance(repeat_params.get("seedance_reference_roles"), list)
        else None
    )
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
        "seedance_reference_roles": seedance_reference_roles,
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
    params = {
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
    if model_key == SEEDANCE25_MODEL_KEY:
        params["seedance_reference_roles"] = data.get("seedance_reference_roles")
        if data.get("flow_id") == "genjutsu_face_clothing":
            params.update(flow_id=data["flow_id"], flow_version=1,
                          seedance_content_edit=dict(data["seedance_content_edit"]))
    return params


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


def _genjutsu_entry_markup(model_costs: list, *, configured: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    by_key = {str(item.model_key): item for item in model_costs}
    for model_key in GENJUTSU_MODEL_KEYS:
        model_cost = by_key.get(model_key)
        label = (
            str(getattr(model_cost, "display_name", "") or GENJUTSU_DISPLAY_NAMES[model_key])
        )
        if model_cost is not None:
            label += f" · {model_cost_display_text(model_cost, model_costs=model_costs)}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=(
                    f"vid_model:{model_key}"
                    if configured and model_cost is not None
                    else "genjutsu:unavailable"
                ),
            )
        ])
    rows.append([InlineKeyboardButton(text="🎭 Замена лица / одежды", callback_data="gjreplace:start")])
    rows.append([InlineKeyboardButton(text="← Назад", callback_data="menu:create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:genjutsu")
async def cb_genjutsu_menu(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    await state.clear()
    await state.set_state(VideoGenFSM.model_select)
    await state.update_data(video_model_menu="menu:genjutsu")
    model_costs = await repo.get_all_model_costs(session)
    configured = is_genjutsu_configured()
    text = (
        "🥷 <b>Genjutsu</b>\n\n"
        "Выбери, что сделать с исходным роликом:\n\n"
        "🎭 <b>Перенос движения</b> — сохраняет движение, камеру и тайминг видео, "
        "но переносит их на персонажей или сцену из твоих референсов.\n\n"
        "🔄 <b>Замена объекта</b> — меняет персонажа, одежду, товар или другой объект, "
        "стараясь сохранить остальной ролик.\n\n"
        "🎭 <b>Замена лица / одежды</b> — измени лицо, наряд или цифры через Seedance 2.5. "
        "Дальше: видео → лицо → одежда → цифры → качество → подтверждение."
    )
    if not configured:
        text += (
            "\n\n⚠️ <b>Часть инструментов недоступна.</b> "
            "Перенос движения и замена объекта через Higgsfield пока недоступны. "
            "Замена лица / одежды использует отдельное подключение Seedance 2.5."
        )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        text,
        reply_markup=_genjutsu_entry_markup(model_costs, configured=configured),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "genjutsu:unavailable")
async def cb_genjutsu_unavailable(call: CallbackQuery) -> None:
    await call.answer(
        "Genjutsu пока не подключён к Higgsfield API. Добавь серверный ключ — и запуск станет доступен.",
        show_alert=True,
    )


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
async def cb_video_group(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    group_key = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.clear()
    await state.set_state(VideoGenFSM.model_select)
    await state.update_data(video_model_menu=call.data, wizard_review_enabled=True, wizard_scenario="advanced")
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
        reply_markup=video_back_kb(),
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
        await message.answer(f"❌ Не удалось создать Audio ID: {escape(str(exc))}", reply_markup=video_back_kb())
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
        reply_markup=video_back_kb(),
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
        reply_markup=video_back_kb(),
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
        await message.answer(f"❌ Не удалось создать Character ID: {escape(str(exc))}", reply_markup=video_back_kb())
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
    state_data = await state.get_data()
    caps = VIDEO_CAPS.get(model_key, {})
    if state_data.get("feed_force_reference"):
        required_kind = "video" if state_data.get("feed_use_needs_video_reference", True) else "image"
        if state_data.get("feed_use_has_original_recipe") and model_key != state_data.get("feed_use_model"):
            await call.answer("Точный повтор доступен только на модели автора.", show_alert=True)
            return
        if not supports_feed_source_media(caps, required_kind):
            hint = (
                "Для этого повтора нужна модель с поддержкой исходного видео."
                if required_kind == "video"
                else "Для этого повтора нужна модель с поддержкой фото-референсов."
            )
            await call.answer(hint, show_alert=True)
            return
    default_duration = _DEFAULT_DURATION.get(model_key, 5)
    default_resolution = _DEFAULT_RES.get(model_key)
    default_ratio = _DEFAULT_RATIO.get(model_key)
    if state_data.get("feed_use_has_original_recipe") and model_key == state_data.get("feed_use_model"):
        input_duration = state_data.get("feed_use_original_duration")
        if isinstance(input_duration, int) and not isinstance(input_duration, bool) and input_duration in caps.get("duration_options", []):
            default_duration = input_duration
        input_resolution = state_data.get("feed_use_original_resolution")
        if input_resolution in caps.get("resolutions", []):
            default_resolution = input_resolution
        input_ratio = state_data.get("feed_use_original_aspect_ratio")
        if input_ratio in caps.get("aspect_ratios", []):
            default_ratio = input_ratio
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
        aspect_ratio=default_ratio,
        resolution=default_resolution,
        grok_mode="normal" if VIDEO_CAPS.get(model_key, {}).get("mode_options") else None,
    )

    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    state_data = await state.get_data()
    force_feed_reference = bool(state_data.get("feed_force_reference"))

    if force_feed_reference:
        mode = (
            "multimodal" if caps.get("auto_route_by_inputs") and "multimodal" in modes
            else "video" if state_data.get("feed_use_needs_video_reference", True)
            else "image"
        )
        await state.update_data(
            mode=mode,
            reference_video_url=state_data.get("feed_use_source_video_url"),
        )
        await _handle_mode(call, state, session, model_key, model_cost.display_name, mode)
    elif state_data.get("wizard_mode") in modes:
        mode = state_data["wizard_mode"]
        await state.update_data(mode=mode)
        if mode == "video" and model_key == GEMINI_OMNI_VIDEO_MODEL:
            from bot.handlers.gemini_omni_references import choose_gemini_omni_video_mode
            await choose_gemini_omni_video_mode(call, state, session)
            return
        if mode == "video":
            from bot.handlers.video_references import (
                SEEDANCE_VIDEO_REFERENCE_MODELS,
                choose_video_reference_mode,
            )
            if model_key in SEEDANCE_VIDEO_REFERENCE_MODELS:
                mode_call = call.model_copy(update={"data": f"vid_mode:video:{model_key}"})
                await choose_video_reference_mode(mode_call, state, session)
                return
        await _handle_mode(call, state, session, model_key, model_cost.display_name, mode)
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
    data = await state.get_data()
    if data.get("feed_force_reference") and mode in {"video", "multimodal"}:
        from bot.handlers.gemini_omni_references import _media_keyboard, _status_text

        await state.set_state(VideoGenFSM.image_upload)
        source_video_needed = data.get("feed_use_needs_video_reference", True)
        text = (
            f"✅ <b>{display_name}</b> · повтор по референсам автора\n\n"
            "Исходный видео-референс автора сохранён. Загрузи своё фото."
            if source_video_needed
            else f"✅ <b>{display_name}</b> · повтор по фото\n\n"
                 "Загрузи своё фото. Промпт и параметры автора сохраняются, его готовое видео не отправляется."
        )
        markup = video_back_kb()
        if model_key == GEMINI_OMNI_VIDEO_MODEL:
            text += "\n\n" + _status_text(data) + "\nПосле загрузки фото нажми «Готово»."
            markup = _media_keyboard()
        await safe_edit_message(call.message, text, reply_markup=markup)
    elif mode == "image":
        await state.set_state(VideoGenFSM.image_upload)
        max_refs = _video_max_refs(model_key)
        data = await state.get_data()
        if _is_feed_video_use(data):
            upload_text = (
                f"✅ <b>{display_name}</b> · повтор по фото\n\n"
                "🖼️ Загрузи своё фото/референс. Повтор выполним по оригинальному промпту автора, "
                "а готовое видео не будем использовать как референс."
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
            reply_markup=video_back_kb(),
        )
    elif mode == "video":
        await state.set_state(VideoGenFSM.image_upload)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · видео-референс\n\n"
            "🎞️ Загрузи исходное видео до 30 сек. Gemini Omni возьмёт фрагмент до 10 сек.",
            reply_markup=video_back_kb(),
        )
    elif mode == "motion":
        await state.set_state(VideoGenFSM.image_upload)
        await state.update_data(motion_step="person")
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · управление камерой\n\n"
            "👤 <b>Шаг 1/2:</b> Загрузи фото персонажа\n"
            "<i>(голова, плечи, торс; JPEG/PNG; ≤10 МБ)</i>",
            reply_markup=video_back_kb(),
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
    if data.get("feed_force_reference"):
        caps = VIDEO_CAPS.get(model_key, {})
        requires_video = data.get("feed_use_needs_video_reference", True)
        source_kind = "video" if requires_video else "image"
        allowed_modes = {"video", "multimodal"} if requires_video else {"image", "multimodal"}
        if not supports_feed_source_media(caps, source_kind) or mode not in allowed_modes:
            await call.answer("Для повтора выбери режим с исходными референсами автора.", show_alert=True)
            return
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    if model_key == SEEDANCE25_MODEL_KEY and mode == "identity":
        await state.update_data(
            mode="image",
            seedance_identity_transfer=True,
            seedance_identity_step="photos",
            image_file_id=None,
            ref_file_ids=[],
            image_url=None,
            reference_video_url=None,
            audio_ids=[],
            aspect_ratio="adaptive",
        )
        await state.set_state(VideoGenFSM.image_upload)
        await safe_edit_message(
            call.message,
            f"🎭 <b>{display_name} · Замена персонажа</b>\n\n"
            "Загрузи <b>1–3 фото одного человека</b>.\n"
            "Лучше всего: анфас → 3/4 → дополнительный ракурс.\n\n"
            "Первое фото будет главным якорем внешности, остальные помогут удержать лицо при поворотах.",
            reply_markup=video_back_kb(),
        )
        await safe_answer_callback(call)
        return

    await state.update_data(mode=mode, seedance_identity_transfer=False, seedance_identity_step=None)
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
    is_genjutsu_video_mode = model_key in GENJUTSU_MODEL_KEYS and data.get("genjutsu_step") == "video"
    is_seedance_identity_video_mode = (
        model_key == SEEDANCE25_MODEL_KEY
        and data.get("seedance_identity_transfer")
        and data.get("seedance_identity_step") == "video"
    )

    if (
        motion_step != "video_url"
        and not is_gemini_omni_video_mode
        and not is_genjutsu_video_mode
        and not is_seedance_identity_video_mode
    ):
        await message.answer("Пожалуйста, загрузи видео только на шаге 2 управления камерой.", reply_markup=video_back_kb())
        return

    video = message.video  # type: ignore[union-attr]
    video_duration: int = video.duration or 5
    file_id = video.file_id
    stored_resolution: str | None = data.get("resolution")
    resolution = _normalize_resolution_for_state(model_key, stored_resolution)
    if resolution != stored_resolution:
        await state.update_data(resolution=resolution)

    if is_genjutsu_video_mode and not (
        GENJUTSU_MIN_DURATION_SECONDS <= video_duration <= GENJUTSU_MAX_DURATION_SECONDS
    ):
        await message.answer(
            f"❌ Genjutsu принимает исходное видео длительностью от {GENJUTSU_MIN_DURATION_SECONDS} "
            f"до {GENJUTSU_MAX_DURATION_SECONDS} секунд. Загрузи подходящий ролик.",
            reply_markup=video_back_kb(),
        )
        return

    if is_gemini_omni_video_mode and video_duration > 30:
        await message.answer(
            "❌ Gemini Omni принимает видео-референс до 30 секунд. Загрузи более короткий фрагмент.",
            reply_markup=video_back_kb(),
        )
        return

    if is_seedance_identity_video_mode and not (4 <= video_duration <= 30):
        await message.answer(
            "❌ Для замены персонажа Seedance 2.5 нужен исходный ролик от 4 до 30 секунд.",
            reply_markup=video_back_kb(),
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
    billable_duration = _video_upload_billable_duration(
        data,
        video_duration=video_duration,
        motion_step=motion_step,
        is_genjutsu_video_mode=is_genjutsu_video_mode,
    )
    total_credits = _video_total_credits(model_key, billable_duration, rate_or_flat)

    if db_user.credits < total_credits:
        await message.answer(
            f"❌ Недостаточно 💋!\n"
            f"Видео: {_video_price_text(model_key, billable_duration, rate_or_flat)}\n"
            f"Баланс: {db_user.credits:g} 💋.",
            reply_markup=video_back_kb(),
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
                reply_markup=video_back_kb(),
            )
            return
        raise

    model_cost_obj = await repo.get_model_cost(session, model_key)
    display_name = model_cost_obj.display_name if model_cost_obj else model_key

    if is_seedance_identity_video_mode:
        await state.update_data(
            reference_video_url=video_url,
            duration=video_duration,
            aspect_ratio="adaptive",
            seedance_identity_step=None,
        )
        updated = await state.get_data()
        await state.set_state(VideoGenFSM.params_select)
        await message.answer(
            f"✅ Исходное видео загружено: <b>{video_duration} сек</b>\n\n"
            f"⚙️ <b>Качество</b> · {display_name}\n"
            f"{_video_params_hint(model_key, updated)}",
            reply_markup=_video_params_reply_markup(model_key, updated),
        )
        return

    if is_genjutsu_video_mode:
        try:
            video_duration = await resolve_genjutsu_source_duration(video_url)
        except ValueError as exc:
            await message.answer(f"❌ {escape(str(exc))}", reply_markup=video_back_kb())
            return
        model_cost = await _resolve_video_model_cost(
            session,
            model_key,
            duration=video_duration,
            resolution=resolution,
            has_video_input=False,
        )
        rate_or_flat = model_cost.credits if model_cost else float(data.get("credits", 0))
        total_credits = _video_total_credits(model_key, video_duration, rate_or_flat)
        if db_user.credits < total_credits:
            await message.answer(
                f"❌ Недостаточно 💋! Нужно {_video_price_text(model_key, video_duration, rate_or_flat)}, "
                f"на балансе {db_user.credits:g} 💋.",
                reply_markup=video_back_kb(),
            )
            return
        await state.update_data(
            reference_video_url=video_url,
            duration=video_duration,
            credits=rate_or_flat,
            genjutsu_step=None,
        )
        updated = await state.get_data()
        await state.set_state(VideoGenFSM.params_select)
        await message.answer(
            f"✅ Исходное видео загружено: <b>{video_duration} сек</b>\n"
            f"💋 Стоимость: <b>{_video_price_text(model_key, video_duration, rate_or_flat)}</b>\n\n"
            f"⚙️ <b>Параметры</b> · {display_name}\n"
            f"{_video_params_hint(model_key, updated)}",
            reply_markup=_video_params_reply_markup(model_key, updated),
        )
        return

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
        reply_markup=video_back_kb(),
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
            reply_markup=video_back_kb(),
        )
        await state.set_state(VideoGenFSM.image_upload)
        return

    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    max_refs = _video_max_refs_for_state(data)

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
            reply_markup=multi_ref_kb(len(existing), max_refs, back_cb="vid_nav:back"),
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

    if model_key == SEEDANCE25_MODEL_KEY and updated.get("seedance_identity_transfer"):
        await state.update_data(seedance_identity_step="video")
        await state.set_state(VideoGenFSM.image_upload)
        await message.answer(
            f"✅ Фото внешности сохранены: <b>{_video_ref_count(updated)}</b>/3\n\n"
            "🎞️ Теперь загрузи <b>исходное видео 4–30 сек</b>. "
            "Seedance возьмёт из него движение, камеру, тайминг и сцену — не личность персонажа.",
            reply_markup=video_back_kb(),
        )
        return

    if model_key in GENJUTSU_MODEL_KEYS:
        await state.update_data(genjutsu_step="video")
        await state.set_state(VideoGenFSM.image_upload)
        await message.answer(
            f"✅ Референсы сохранены: <b>{_video_ref_count(updated)}</b>\n\n"
            f"🎞️ Теперь загрузи исходное видео длительностью от {GENJUTSU_MIN_DURATION_SECONDS} "
            f"до {GENJUTSU_MAX_DURATION_SECONDS} секунд. "
            "Genjutsu сохранит движение и тайминг ролика, применив твои референсы.",
            reply_markup=video_back_kb(),
        )
        return

    if _has_params(model_key):
        await state.set_state(VideoGenFSM.params_select)
        await message.answer(
            f"✅ Фото загружено!\n\n⚙️ <b>Параметры</b> · {display_name}\n"
            f"{_video_params_hint(model_key, updated)}",
            reply_markup=_video_params_reply_markup(model_key, updated),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await message.answer("✅ Фото загружено!\n\n✍️ Введи промпт:", reply_markup=video_back_kb())


@router.callback_query(VideoGenFSM.image_upload, F.data == "ref:add_more")
async def cb_video_ref_add_more(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    max_refs = _video_max_refs_for_state(data)
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
            reply_markup=video_back_kb(),
        )


async def _accept_video_parameter(call: CallbackQuery, state: FSMContext) -> bool:
    data = await state.get_data()
    model_key = data.get("model_key")
    if model_key:
        markup = _video_params_reply_markup(model_key, data)
        if any(button.callback_data == call.data for row in markup.inline_keyboard for button in row):
            return True
    await safe_answer_callback(call, "Этот параметр недоступен для текущей задачи.", show_alert=True)
    return False


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_dur:"))
async def cb_vpar_dur(call: CallbackQuery, state: FSMContext) -> None:
    if not await _accept_video_parameter(call, state):
        return
    dur = int(call.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(duration=dur)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_video_params_reply_markup(data["model_key"], data)
    )
    await call.answer(f"{dur} сек")


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_ratio:"))
async def cb_vpar_ratio(call: CallbackQuery, state: FSMContext) -> None:
    if not await _accept_video_parameter(call, state):
        return
    ratio = call.data.removeprefix("vpar_ratio:")  # type: ignore[union-attr]
    await state.update_data(aspect_ratio=ratio)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_video_params_reply_markup(data["model_key"], data)
    )
    await call.answer(ratio)


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_res:"))
async def cb_vpar_res(call: CallbackQuery, state: FSMContext) -> None:
    if not await _accept_video_parameter(call, state):
        return
    res = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(resolution=res)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=_video_params_reply_markup(data["model_key"], data)
    )
    await call.answer(res)


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_mode:"))
async def cb_vpar_mode(call: CallbackQuery, state: FSMContext) -> None:
    if not await _accept_video_parameter(call, state):
        return
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
    await safe_edit_message(call.message, text, reply_markup=video_back_kb())  # type: ignore[arg-type]
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
        await message.answer(f"❌ {escape(str(exc))}", reply_markup=video_back_kb())
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
    if data.get("video_review_edit") and data.get("review_prompt"):
        from bot.handlers.video_wizard import show_video_review
        await show_video_review(call.message, state, session, db_user, data["review_prompt"], edit=True)
        await safe_answer_callback(call)
        return
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
        await safe_answer_callback(call)
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
        f" · <code>{summary}</code>\n\n✍️ Введи дополнительные пожелания"
        + (
            " или отправь <code>-</code>, чтобы запустить с оптимальным промптом:"
            if data.get("seedance_identity_transfer") or data['model_key'] in GENJUTSU_MODEL_KEYS
            else ":"
        ),
        reply_markup=video_back_kb(),
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
            reply_markup=feed_video_models_kb(model_costs),
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




async def _show_video_cost_quote(
    source_message: Message, state: FSMContext, *, state_key: str,
    user_id: int, fingerprint: str, duration: int, credits: float,
    callback_prefix: str, context: dict,
) -> None:
    token = secrets.token_hex(8)
    credits_text = f"{credits:.6f}".rstrip("0").rstrip(".")
    await state.update_data(**{state_key: {
        **context, "token": token, "user_id": user_id, "fingerprint": fingerprint,
    }})
    await source_message.answer(
        "🔁 <b>Проверь стоимость повтора</b>\n\n"
        f"Длительность: <b>{duration} сек</b> (по исходному видео).\n"
        f"Итого: <b>{credits_text} 💋</b>.\n\n"
        "Параметры уточнены. Подтверди запуск по этой цене.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Запустить за {credits_text} 💋", callback_data=f"{callback_prefix}{token}")],
            [InlineKeyboardButton(text="Отмена", callback_data="menu:main")],
        ]),
    )


@router.callback_query(F.data.startswith("feed_video_confirm:"))
async def cb_feed_video_confirm(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    data = await state.get_data()
    quote = data.get("video_feed_quote")
    token = str(call.data or "").removeprefix("feed_video_confirm:")
    if (not isinstance(quote, dict) or quote.get("user_id") != db_user.id
            or not secrets.compare_digest(str(quote.get("token") or "").encode(), token.encode())
            or quote.get("model_key") != data.get("model_key")
            or any(data.get(key) and data[key] != quote.get("source_feed_gen_id")
                   for key in ("source_feed_gen_id", "feed_use_gen_id"))):
        await safe_answer_callback(call, "Это подтверждение устарело. Открой параметры повтора ещё раз.", show_alert=True)
        return
    source = await repo.get_public_feed_generation(session, quote["source_feed_gen_id"])
    parent_id = quote.get("parent_generation_id")
    parent = await repo.get_generation_by_id(session, parent_id) if parent_id else None
    if not source or (parent_id and (not parent or parent.user_id != db_user.id)):
        await safe_answer_callback(call, "Исходный пост больше недоступен", show_alert=True)
        return
    await safe_answer_callback(call)
    await _launch_video_generation_from_state(
        source_message=call.message, state=state, session=session, db_user=db_user, bot=bot,
        prompt=parent.prompt if parent else source.prompt,
        source_feed_gen_id=quote["source_feed_gen_id"], parent_generation_id=parent_id,
        hidden_feed_prompt=True, price_confirmation_token=token,
    )


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
    price_confirmation_token: str | None = None,
) -> bool:
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

    try:
        prompt, image_url, data, source_feed_gen_id = await _prepare_feed_video_inputs(
            session=session, db_user=db_user, source_feed_gen_id=source_feed_gen_id,
            model_key=model_key, prompt=prompt, image_url=image_url, data=data,
            parent_generation_id=parent_generation_id,
        )
    except FeedRemixUnavailable as exc:
        await source_message.answer(str(exc), reply_markup=main_menu_kb())
        return False

    content_edit = model_key == SEEDANCE25_MODEL_KEY and data.get("flow_id") == "genjutsu_face_clothing"
    seedance_kwargs = {}
    if content_edit:
        try:
            plan = restore_seedance_reference_plan(_url_list(image_url), data.get("seedance_reference_roles"))
            if len(_url_list(data.get("reference_video_url"))) != 1:
                raise ValueError("Сначала загрузи исходное видео.")
            build_seedance_content_edit_prompt(plan, data["seedance_content_edit"])
        except ValueError as exc:
            await source_message.answer(escape(str(exc)))
            return False
        image_url = list(plan.image_urls) or None
        seedance_kwargs = {"seedance_reference_roles": list(plan.roles),
                           "seedance_content_edit": dict(data["seedance_content_edit"])}
        data = {**data, "seedance_identity_transfer": False,
                "audio_ids": _seedance_repeat_without_identity_control(data.get("audio_ids"))}

    if model_key == SEEDANCE25_MODEL_KEY and data.get("seedance_repeat_editor"):
        source_video_url = str(
            data.get("seedance_repeat_source_video_url")
            or data.get("reference_video_url")
            or ""
        ).strip()
        if not source_video_url:
            await source_message.answer(
                "❌ Не удалось восстановить исходный ролик для точечного повтора.",
                reply_markup=main_menu_kb(),
            )
            return False

        clothing_reference_url = ""
        clothing_file_id = str(data.get("seedance_repeat_clothing_file_id") or "").strip()
        if clothing_file_id:
            clothing_reference_url = str(await mirror_telegram_file(bot, clothing_file_id) or "").strip()
            if not clothing_reference_url:
                await source_message.answer(
                    "❌ Не удалось подготовить фото одежды. Пришли референс ещё раз.",
                    reply_markup=main_menu_kb(),
                )
                return False

        try:
            existing_image_refs = _url_list(image_url)
            planned_images, identity_count, clothing_index, reference_roles = (
                build_seedance_repeat_reference_plan(
                    existing_image_refs,
                    stored_roles=data.get("seedance_reference_roles"),
                    legacy_identity_transfer=_seedance_repeat_has_legacy_identity(data),
                    clothing_reference_url=clothing_reference_url or None,
                )
            )
            prompt = build_seedance_repeat_prompt(
                prompt,
                number=data.get("seedance_repeat_number"),
                clothing=data.get("seedance_repeat_clothing"),
                identity_image_count=identity_count,
                clothing_image_index=clothing_index,
            )
            validate_video_prompt(model_key, prompt)
        except ValueError as exc:
            await source_message.answer(
                f"❌ {escape(str(exc))}",
                reply_markup=main_menu_kb(),
            )
            return False

        sanitized_audio_ids = _seedance_repeat_without_identity_control(data.get("audio_ids"))
        await state.update_data(
            mode="video",
            reference_video_url=source_video_url,
            audio_ids=sanitized_audio_ids,
            seedance_reference_roles=reference_roles,
            seedance_identity_transfer=False,
        )
        data = {
            **data,
            "mode": "video",
            "reference_video_url": source_video_url,
            "audio_ids": sanitized_audio_ids,
            "seedance_reference_roles": reference_roles,
            "seedance_identity_transfer": False,
        }
        image_url = planned_images or None

    edit_billing_duration = None
    if model_key == SEEDANCE25_MODEL_KEY:
        try:
            edit_billing_duration = await _seedance_edit_duration_from_state(
                prompt, data,
                force_edit=bool(
                    content_edit or data.get("seedance_identity_transfer")
                    or data.get("seedance_repeat_editor")
                ),
            )
        except ValueError as exc:
            await source_message.answer(
                f"❌ {escape(str(exc))}",
                reply_markup=main_menu_kb(),
            )
            return False
        if edit_billing_duration is not None:
            duration = edit_billing_duration
            aspect_ratio = "adaptive"
            await state.update_data(
                duration=duration,
                aspect_ratio=aspect_ratio,
                seedance_video_edit=True,
            )
            data = {
                **data,
                "duration": duration,
                "aspect_ratio": aspect_ratio,
                "seedance_video_edit": True,
            }

    has_gemini_omni_video_input = _has_gemini_omni_video_input(model_key, data)
    model_cost = await _resolve_video_model_cost(
        session,
        model_key,
        duration=duration,
        resolution=resolution,
        has_video_input=has_gemini_omni_video_input,
    )
    if content_edit and (not model_cost or not model_cost.is_active):
        await source_message.answer("Seedance 2.5 сейчас недоступен. Попробуй позже.")
        return False
    motion_credits = None if content_edit else data.get("motion_credits")
    if motion_credits is not None:
        credits = float(motion_credits)
    else:
        rate_or_flat = model_cost.credits if model_cost else float(data.get("credits", 0))
        credits = float(_video_total_credits(model_key, duration, rate_or_flat))

    if model_key == SEEDANCE25_MODEL_KEY and data.get("seedance_identity_transfer"):
        identity_tokens = [
            "__apix_seedance25:identity_transfer=true",
            "__apix_seedance25:generate_audio=false",
        ]
        audio_ids = [str(item) for item in (data.get("audio_ids") or []) if item]
        await state.update_data(audio_ids=list(dict.fromkeys([*audio_ids, *identity_tokens])))
        data = {
            **data,
            "audio_ids": list(dict.fromkeys([*audio_ids, *identity_tokens])),
        }

    if content_edit and data.get("gj_quoted_cost") != credits:
        await source_message.answer("Стоимость изменилась. Проверь новую цену перед запуском.")
        return False

    input_params = _video_input_params_from_generation_state(
        model_key=model_key,
        data=data,
        image_url=image_url,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        grok_mode=grok_mode,
    )
    if source_feed_gen_id and FEED_REMIX_CONTEXT_KEY in data:
        input_params[FEED_REMIX_CONTEXT_KEY] = feed_remix_context(source_feed_gen_id, prompt)
    if price_confirmation_token is not None or (
        source_feed_gen_id and model_key == SEEDANCE25_MODEL_KEY and edit_billing_duration is not None
    ):
        # Every feed-source edit needs a measured quote, even after a previous
        # preflight updated FSM duration. Pressing Next again is not consent.
        fingerprint = hashlib.sha256(json.dumps({
            "user_id": db_user.id, "source_feed_gen_id": source_feed_gen_id,
            "parent_generation_id": parent_generation_id, "model": model_key,
            "prompt": prompt, "input_params": input_params, "credits": credits,
        }, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        quote = data.get("video_feed_quote")
        if (price_confirmation_token is None or not isinstance(quote, dict)
                or quote.get("user_id") != db_user.id or quote.get("fingerprint") != fingerprint
                or not secrets.compare_digest(str(quote.get("token") or "").encode(), price_confirmation_token.encode())):
            await _show_video_cost_quote(
                source_message, state, state_key="video_feed_quote", user_id=db_user.id,
                fingerprint=fingerprint, duration=duration, credits=credits,
                callback_prefix="feed_video_confirm:", context={
                    "source_feed_gen_id": source_feed_gen_id, "parent_generation_id": parent_generation_id,
                    "model_key": model_key,
                },
            )
            return False
        # The Redis FSM quote is single use, including across an interrupted launch.
        await state.update_data(video_feed_quote=None)
    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await source_message.answer("❌ Недостаточно 💋.", reply_markup=main_menu_kb())
        await state.clear()
        return False

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

    submission_context = make_submission_context(session, gen_id, model_key, surface="telegram_bot")
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
            idempotency_key=f"apix-video-{gen_id}",
            **({"neironych_submission": submission_context} if submission_context else {}),
            **seedance_kwargs,
        )
    except NeironychPreSubmitFailure:
        if await handle_submission_not_sent(session, gen_id, submission_context):
            await status_msg.edit_text(
                "Запрос видео не отправлен. 💋 возвращены. Попробуй позже.",
                reply_markup=main_menu_kb(),
            )
            await state.clear()
        else:
            await _show_video_submission_review(status_msg, state, session, gen_id)
        return False
    except NeironychSubmissionUnknown:
        await handle_submission_unknown(session, gen_id, submission_context)
        await _show_video_submission_review(status_msg, state, session, gen_id)
        return True
    except Exception as e:
        if content_edit:
            logger.warning("flow=genjutsu_face_clothing provider_start_failed error_type=%s", type(e).__name__)
        else:
            logger.error("Video generation error: %s", e)
        await session.rollback()
        await repo.fail_generation_and_refund(
            session,
            gen_id,
            str(e),
            refund_note="bot_video_gen",
        )
        await status_msg.edit_text(
            ("❌ Seedance не принял задачу или временно недоступен. ROX возвращены. Попробуй другое видео или повтори позже."
             if content_edit else "❌ Ошибка запуска генерации. 💋 возвращены.\n\nПопробуй другую модель или повтори через минуту."),
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return False

    if submission_context and submission_context.started:
        try:
            saved = await persist_submission_result(
                session, gen_id, submission_context, result.task_id or "", surface="telegram_bot",
            )
        except Exception:
            logger.warning("Seedance bot result identity persistence deferred gen=%s", gen_id)
            await handle_submission_unknown(session, gen_id, submission_context)
            saved = False
        if not saved:
            await _show_video_submission_review(status_msg, state, session, gen_id)
            return True
    else:
        saved = await repo.update_generation_task(
            session, gen_id, result.task_id,
            **({"expected_task_id": ""} if submission_context else {}),
        )
        if submission_context and saved is False:
            await _show_video_submission_review(status_msg, state, session, gen_id)
            return
    await _show_video_task_started(status_msg, result.task_id)
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
        caption = "✅ <b>Видео готово!</b>" + provider_task_reference(result.task_id)
        if hidden_feed_prompt:
            caption += "\n\nСоздано по посту из ленты. Промпт автора скрыт."
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
                allow_publish=True,
                allow_library=not bool(source_feed_gen_id),
                allow_copy_prompt=not bool(source_feed_gen_id),
            ),
        )

    async def on_failure(err: str) -> None:
        async with AsyncSessionLocal() as bg_session:
            current = await repo.get_generation_by_id(bg_session, gen_id)
            current_status = getattr(getattr(current, "status", None), "value", getattr(current, "status", None))
            if current_status in {"done", "failed"}:
                return
            user_err = (
                "Ошибка на стороне генератора"
                if source_feed_gen_id or generation_prompt_is_protected(current)
                else escape(err)
            )
            _, refunded = await repo.fail_generation_and_refund(
                bg_session,
                gen_id,
                err,
                refund_note="bot_video_poll",
            )
        await status_msg.edit_text(
            f"❌ Ошибка: {user_err}\n💋 возвращены." + provider_task_reference(result.task_id),
            reply_markup=main_menu_kb(),
        )

    if getattr(result, "uses_webhook", False) or result.provider == "kieai":
        if result.provider == "comet":
            _start_video_polling(result, poll_fn, on_success, on_failure)
        await state.clear()
        return True

    _start_video_polling(result, poll_fn, on_success, on_failure)
    await state.clear()
    return True


# ── Prompt / motion video URL ─────────────────────────────────────────────────

@router.callback_query(VideoGenFSM.prompt_input, F.data == "vid_prompt:done")
async def finish_long_video_prompt(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    data = await state.get_data()
    model_key = str(data.get("model_key") or "")
    prompt = str(data.get("seedance_prompt_buffer") or "")
    limit = seedance_prompt_max_chars(model_key)
    if limit is None or not prompt:
        await call.answer("Нет собранного промпта", show_alert=True)
        return
    await call.answer()
    if call.message is None:
        return
    await _launch_collected_seedance_prompt(
        source_message=call.message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        prompt=prompt,
    )


@router.message(VideoGenFSM.prompt_input, F.text)
async def handle_video_prompt(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    data = await state.get_data()
    model_key: str = data["model_key"]
    motion_step: str | None = data.get("motion_step")
    raw_prompt = message.text or ""  # type: ignore[union-attr]
    prompt = raw_prompt.strip()

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
    if (model_key in GENJUTSU_MODEL_KEYS or data.get("seedance_identity_transfer")) and prompt == "-":
        prompt = ""
    if motion_step == "prompt":
        prompt = prompt if prompt != "-" else ""
        await state.update_data(motion_prompt=prompt, motion_step="done")

    # Telegram cannot carry a 20k/30k prompt in one text message: clients split
    # long pasted text into 4096-char messages. Reassemble those chunks verbatim
    # for Seedance instead of launching on (and losing everything after) part 1.
    prompt_limit = seedance_prompt_max_chars(model_key) if motion_step is None else None
    previous_prompt = str(data.get("seedance_prompt_buffer") or "")
    if prompt_limit is not None and (previous_prompt or len(raw_prompt) >= 4096):
        try:
            combined_prompt, awaiting_more = append_telegram_seedance_prompt_chunk(
                model_key, previous_prompt, raw_prompt
            )
        except ValueError:
            await state.update_data(seedance_prompt_buffer="")
            await message.answer(
                f"❌ Промпт длиннее максимума модели: {prompt_limit} символов. Отправь короче.",
                reply_markup=back_to_menu_kb(),
            )
            return
        if awaiting_more:
            await state.update_data(seedance_prompt_buffer=combined_prompt)
            await message.answer(
                f"🧩 Принял часть промпта: {len(combined_prompt)}/{prompt_limit}. "
                "Пришли продолжение — Telegram сам делит длинный текст. "
                "Если это всё, нажми «Готово».",
                reply_markup=_long_prompt_done_kb(),
            )
            return
        prompt = combined_prompt
        await state.update_data(seedance_prompt_buffer="")

    try:
        prompt = validate_video_prompt(model_key, prompt)
    except ValueError:
        limit = video_prompt_max_chars(model_key)
        await message.answer(
            f"❌ Промпт длиннее максимума модели: {limit} символов. Отправь короче.",
            reply_markup=back_to_menu_kb(),
        )
        return

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

    seedance_repeat_source_video_url = None
    if model_key == SEEDANCE25_MODEL_KEY:
        seedance_repeat_source_video_url = str(
            getattr(prev, "result_url", None)
            or repeat_data.get("reference_video_url")
            or ""
        ).strip() or None

    await state.clear()
    await state.update_data(
        **repeat_data,
        credits=model_cost.credits,
        parent_generation_id=prev.id,
        source_feed_gen_id=source_feed_gen_id,
        video_reuse_prompt=reuse_prompt,
        seedance_repeat_source_video_url=seedance_repeat_source_video_url,
        feed_use_gen_type=None,
        feed_use_prompt=None,
        feed_use_gen_id=None,
        feed_force_reference=None,
    )
    restored = await state.get_data()
    return model_key, model_cost.display_name, restored


@router.callback_query(VideoGenFSM.seedance_repeat_edit, F.data == "s25repeat:number")
async def cb_seedance_repeat_number(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.seedance_repeat_number)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🔢 <b>Число / цифры</b>\n\n"
        "Напиши, что должно быть в повторе: например <code>25</code>, <code>2026</code> или <code>№7</code>.\n"
        "Отправь <code>-</code>, чтобы не менять число.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.seedance_repeat_number, F.text)
async def handle_seedance_repeat_number(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if len(value) > 80:
        await message.answer("Слишком длинное значение. До 80 символов.")
        return
    await state.update_data(seedance_repeat_number="" if value == "-" else value)
    data = await state.get_data()
    await state.set_state(VideoGenFSM.seedance_repeat_edit)
    await message.answer(
        _seedance_repeat_edit_text(str(data.get("seedance_repeat_display_name") or "Seedance 2.5"), data),
        reply_markup=_seedance_repeat_edit_kb(),
    )


@router.callback_query(VideoGenFSM.seedance_repeat_edit, F.data == "s25repeat:clothing")
async def cb_seedance_repeat_clothing(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.seedance_repeat_clothing)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "👕 <b>Одежда</b>\n\n"
        "Пришли <b>фото нужной одежды</b> — бот сам назначит его как отдельный <code>@ImageN</code>.\n"
        "Можно вместо фото написать описание, например: <code>чёрная кожаная куртка</code>.\n"
        "Фото можно отправить с подписью — тогда Seedance получит и реф, и уточнение.\n\n"
        "Отправь <code>-</code>, чтобы оставить одежду без изменений.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.seedance_repeat_clothing, F.photo)
async def handle_seedance_repeat_clothing_photo(message: Message, state: FSMContext) -> None:
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    caption = str(message.caption or "").strip()
    if len(caption) > 300:
        await message.answer("Описание одежды слишком длинное. До 300 символов.")
        return
    await state.update_data(
        seedance_repeat_clothing_file_id=best.file_id,
        seedance_repeat_clothing=caption,
    )
    data = await state.get_data()
    await state.set_state(VideoGenFSM.seedance_repeat_edit)
    await message.answer(
        _seedance_repeat_edit_text(str(data.get("seedance_repeat_display_name") or "Seedance 2.5"), data),
        reply_markup=_seedance_repeat_edit_kb(),
    )


@router.message(VideoGenFSM.seedance_repeat_clothing, F.text)
async def handle_seedance_repeat_clothing(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if len(value) > 300:
        await message.answer("Описание одежды слишком длинное. До 300 символов.")
        return
    if value == "-":
        await state.update_data(
            seedance_repeat_clothing="",
            seedance_repeat_clothing_file_id=None,
        )
    else:
        await state.update_data(seedance_repeat_clothing=value)
    data = await state.get_data()
    await state.set_state(VideoGenFSM.seedance_repeat_edit)
    await message.answer(
        _seedance_repeat_edit_text(str(data.get("seedance_repeat_display_name") or "Seedance 2.5"), data),
        reply_markup=_seedance_repeat_edit_kb(),
    )


@router.callback_query(VideoGenFSM.seedance_repeat_edit, F.data == "s25repeat:params")
async def cb_seedance_repeat_params(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    model_key = str(data.get("model_key") or "")
    display_name = str(data.get("seedance_repeat_display_name") or model_key or "Seedance 2.5")
    await state.set_state(VideoGenFSM.params_select)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"⚙️ <b>Изменить параметры</b> · {escape(display_name)}\n"
        f"{_video_params_hint(model_key, data)}",
        reply_markup=_video_params_reply_markup(model_key, data),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.seedance_repeat_edit, F.data == "s25repeat:launch")
async def cb_seedance_repeat_launch(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    reuse_prompt = str(data.get("video_reuse_prompt") or "")
    if not reuse_prompt:
        await safe_answer_callback(call, "Не удалось восстановить исходный промпт", show_alert=True)
        return
    await safe_answer_callback(call, "Запускаю повтор")
    await _launch_video_generation_from_state(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        prompt=reuse_prompt,
        source_feed_gen_id=data.get("source_feed_gen_id"),
        parent_generation_id=data.get("parent_generation_id"),
        hidden_feed_prompt=bool(data.get("source_feed_gen_id")),
    )


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
    from bot.handlers.genjutsu_replace import restore_result
    if await restore_result(call, state, session, prev):
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
    from bot.handlers.genjutsu_replace import restore_result
    if await restore_result(call, state, session, prev):
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

    if model_key == SEEDANCE25_MODEL_KEY:
        await state.update_data(
            seedance_repeat_editor=True,
            seedance_repeat_display_name=display_name,
            seedance_repeat_number="",
            seedance_repeat_clothing="",
            seedance_repeat_clothing_file_id=None,
        )
        data = await state.get_data()
        await state.set_state(VideoGenFSM.seedance_repeat_edit)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            _seedance_repeat_edit_text(display_name, data),
            reply_markup=_seedance_repeat_edit_kb(),
        )
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
    parts = str(call.data or "").split(":")
    if len(parts) not in {3, 4} or not parts[2].isascii() or not parts[2].isdigit():
        await call.answer("Кнопка повтора устарела", show_alert=True)
        return
    gen_id = int(parts[2])
    confirmation_token = parts[3] if len(parts) == 4 else None
    quote = (await state.get_data()).get("video_regen_quote") if confirmation_token is not None else None
    if confirmation_token is not None and (
        not isinstance(quote, dict) or quote.get("user_id") != db_user.id
        or quote.get("generation_id") != gen_id
        or not secrets.compare_digest(str(quote.get("token") or "").encode(), confirmation_token.encode())
    ):
        await call.answer("Это подтверждение устарело. Нажми «Повторить» ещё раз.", show_alert=True)
        return
    prev = await repo.get_generation_by_id(session, gen_id)
    if not prev or prev.user_id != db_user.id or not prev.prompt:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    from bot.handlers.genjutsu_replace import restore_result
    if await restore_result(call, state, session, prev):
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
    if isinstance(reference_video_url, list):
        reference_video_url = _url_list(reference_video_url)
    elif reference_video_url:
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
    requested_duration = duration
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
    try:
        repeat_prompt, image_url, repeat_data, source_feed_gen_id = await _prepare_feed_video_inputs(
            session=session, db_user=db_user,
            source_feed_gen_id=getattr(prev, "source_feed_gen_id", None),
            model_key=model_key, prompt=prev.prompt, image_url=image_url, data=repeat_data,
            parent_generation_id=prev.id,
        )
    except FeedRemixUnavailable as exc:
        await call.answer(str(exc), show_alert=True)
        return
    reference_video_url = repeat_data.get("reference_video_url")
    repeat_data = {**repeat_data, "image_url": image_url}
    edit_billing_duration = None
    if model_key == SEEDANCE25_MODEL_KEY:
        try:
            edit_billing_duration = await _seedance_edit_duration_from_state(repeat_prompt, repeat_data)
        except ValueError as exc:
            await call.answer(str(exc), show_alert=True)
            return
        if edit_billing_duration is not None:
            duration = edit_billing_duration
            aspect_ratio = "adaptive"
            repeat_data = {
                **repeat_data, "duration": duration, "aspect_ratio": aspect_ratio,
                "seedance_video_edit": True,
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

    credits = float(_video_total_credits(model_key, duration, model_cost.credits))
    previous_credits = getattr(prev, "credits_spent", None)
    needs_quote = confirmation_token is not None or (
        edit_billing_duration is not None and (
            duration != requested_duration
            or (isinstance(previous_credits, (int, float)) and previous_credits != credits)
        )
    )
    if needs_quote:
        fingerprint = hashlib.sha256(json.dumps({
            "user_id": db_user.id, "generation_id": gen_id, "model": model_key,
            "prompt": repeat_prompt, "input_params": input_params, "credits": credits,
        }, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        if confirmation_token is None or quote.get("fingerprint") != fingerprint:
            # Production FSM is Redis-backed and updates are serialized per user.
            await _show_video_cost_quote(
                call.message, state, state_key="video_regen_quote", user_id=db_user.id,
                fingerprint=fingerprint, duration=duration, credits=credits,
                callback_prefix=f"regen:video:{gen_id}:", context={"generation_id": gen_id},
            )
            await safe_answer_callback(call)
            return
        # Consume before the existing spend/submit flow: a repeated click or a
        # restart after spending must never reuse this authorization.
        await state.update_data(video_regen_quote=None)
    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await call.answer("Недостаточно 💋", show_alert=True)
        return

    await safe_answer_callback(call, "🔁 Запускаю ещё вариант")
    gen = await repo.create_generation(
        session,
        db_user.id,
        model_key,
        GenerationType.video,
        repeat_prompt,
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

    submission_context = make_submission_context(session, gen_id, model_key, surface="telegram_bot")
    try:
        result = await video_service.generate_video(
            video_model,
            repeat_prompt,
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
            idempotency_key=f"apix-video-{gen_id}",
            **({"neironych_submission": submission_context} if submission_context else {}),
        )
    except NeironychPreSubmitFailure:
        if await handle_submission_not_sent(session, gen_id, submission_context):
            await status_msg.edit_text(
                "Запрос видео не отправлен. 💋 возвращены. Попробуй позже.",
                reply_markup=main_menu_kb(),
            )
            await state.clear()
        else:
            await _show_video_submission_review(status_msg, state, session, gen_id)
        return
    except NeironychSubmissionUnknown:
        await handle_submission_unknown(session, gen_id, submission_context)
        await _show_video_submission_review(status_msg, state, session, gen_id)
        return
    except Exception as exc:
        logger.error("Video regeneration error: %s", exc)
        await session.rollback()
        await repo.fail_generation_and_refund(
            session,
            gen_id,
            str(exc),
            refund_note="bot_video_repeat",
        )
        await status_msg.edit_text(
            "❌ Ошибка запуска повтора. 💋 возвращены.\n\nПопробуй другую модель или повтори через минуту.",
            reply_markup=main_menu_kb(),
        )
        await state.clear()
        return

    if submission_context and submission_context.started:
        try:
            saved = await persist_submission_result(
                session, gen_id, submission_context, result.task_id or "", surface="telegram_bot",
            )
        except Exception:
            logger.warning("Seedance bot result identity persistence deferred gen=%s", gen_id)
            await handle_submission_unknown(session, gen_id, submission_context)
            saved = False
        if not saved:
            await _show_video_submission_review(status_msg, state, session, gen_id)
            return
    else:
        saved = await repo.update_generation_task(
            session, gen_id, result.task_id,
            **({"expected_task_id": ""} if submission_context else {}),
        )
        if submission_context and saved is False:
            await _show_video_submission_review(status_msg, state, session, gen_id)
            return
    await _show_video_task_started(status_msg, result.task_id)
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
        caption = "✅ <b>Видео готово!</b>" + provider_task_reference(result.task_id)
        if source_feed_gen_id:
            caption += "\n\nСоздано по посту из ленты. Промпт автора скрыт."
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
                allow_publish=True,
                allow_library=not bool(source_feed_gen_id),
                allow_copy_prompt=not bool(source_feed_gen_id),
            ),
        )

    async def on_failure(err: str) -> None:
        async with AsyncSessionLocal() as bg_session:
            current = await repo.get_generation_by_id(bg_session, gen_id)
            current_status = getattr(getattr(current, "status", None), "value", getattr(current, "status", None))
            if current_status in {"done", "failed"}:
                return
            user_err = (
                "Ошибка на стороне генератора"
                if source_feed_gen_id or generation_prompt_is_protected(current)
                else escape(err)
            )
            _, refunded = await repo.fail_generation_and_refund(
                bg_session,
                gen_id,
                err,
                refund_note="bot_video_repeat_poll",
            )
        await status_msg.edit_text(
            f"❌ Ошибка: {user_err}\n💋 возвращены." + provider_task_reference(result.task_id),
            reply_markup=main_menu_kb(),
        )

    if getattr(result, "uses_webhook", False) or result.provider == "kieai":
        if result.provider == "comet":
            _start_video_polling(result, poll_fn, on_success, on_failure)
        await state.clear()
        return

    _start_video_polling(result, poll_fn, on_success, on_failure)
    await state.clear()
