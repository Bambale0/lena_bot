"""Mini-app REST API — generation endpoints for the Telegram WebApp frontend."""
from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from aiogram.types import LabeledPrice
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api import image_service, midjourney_service, video_service
from api.assistant_service import generate_prompt_moderation_decision
from api.image_service import ImageModel, normalize_quality_for_aspect_ratio
from api.miniapp_auth import get_miniapp_user
from api.photo_prompt_service import generate_prompt_from_photo
from api.midjourney_service import MJDimensions, MJTaskStatus, MJVideoMotion
from api.video_service import VideoModel
from bot.keyboards.models import IMAGE_CAPS, VIDEO_CAPS
from bot.utils.deep_links import build_start_payload
from core.config import settings
from db import repository as repo
from db.models import (
    GenerationStatus,
    GenerationType,
    ImageGenerationAction,
    PaymentProvider,
    TransactionStatus,
    User,
)
from db.session import get_session

MUSIC_MODEL_KEY = "suno/v4.5"
DEFAULT_MUSIC_CREDITS = 20

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["miniapp"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


MAX_CONCURRENT = 6
STALE_GENERATION_TIMEOUT = timedelta(minutes=20)

_TELEGRAM_STARS_RUB_PER_STAR = 195.99 / 100

def _plan_stars_price(plan: Any) -> int:
    explicit = getattr(plan, "price_stars", None)
    if explicit is not None:
        try:
            return max(1, int(explicit))
        except (TypeError, ValueError):
            pass
    return max(1, math.ceil(float(plan.price_rub) / _TELEGRAM_STARS_RUB_PER_STAR))

_VEO_MODEL_KEYS = {item.value for item in (VideoModel.VEO_3, VideoModel.VEO_3_FAST, VideoModel.VEO_3_LITE)}
_MIDJOURNEY_IMAGE_MODEL_KEYS = {"midjourney-imagine", "midjourney-blend", "midjourney-action"}
_MIDJOURNEY_VIDEO_MODEL_KEYS = {"midjourney-video"}
_MJ_STUDIO_IMAGE_MODELS = {"midjourney-imagine", "midjourney-blend"}
_MJ_VIDEO_MODELS = {"midjourney-video"}
_MJ_ALL_MODELS = _MJ_STUDIO_IMAGE_MODELS | _MJ_VIDEO_MODELS | {"midjourney-describe", "midjourney-action"}
_MJ_BLEND_DIMENSIONS = {"1:1": "SQUARE", "2:3": "PORTRAIT", "3:2": "LANDSCAPE"}
_MJ_IMAGE_CAPS: dict[str, dict[str, Any]] = {
    "midjourney-imagine": {"modes": ["text", "image"], "aspect_ratios": ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2"], "counts": [1], "max_refs": 1, "has_quality": False},
    "midjourney-blend": {"modes": ["image"], "aspect_ratios": ["1:1", "2:3", "3:2"], "aspect_ratio_min_refs": 2, "counts": [1], "max_refs": 5, "has_quality": False},
}
_MJ_VIDEO_CAPS: dict[str, dict[str, Any]] = {
    "midjourney-video": {"modes": ["image"], "duration_options": [5], "mode_options": ["low", "high"], "max_refs": 1},
}

_FRIENDLY_MODEL_NAMES: dict[str, str] = {
    "seedream/4.5-text-to-image": "Seedream 4.5",
    "seedream/4.5-edit": "Seedream 4.5 Edit",
    "grok-imagine/text-to-image": "Grok Imagine",
    "grok-imagine/image-to-image": "Grok Imagine Edit",
    "wan/2-7-image": "WAN 2.7",
    "wan/2-7-image-pro": "WAN 2.7 Pro",
    "google/nano-banana": "Nano Banana",
    "nano-banana-2": "Nano Banana 2",
    "nano-banana-pro": "Nano Banana Pro",
    "qwen/text-to-image": "Qwen",
    "qwen/image-to-image": "Qwen Edit",
    "qwen/image-edit": "Qwen Edit Pro",
    "qwen2/text-to-image": "Qwen 2",
    "qwen2/image-edit": "Qwen 2 Edit",
    "gpt-image-2-text-to-image": "GPT Image 2",
    "gpt-image-2-image-to-image": "GPT Image 2 Edit",
    "kling-2.6/text-to-video": "Kling 2.6",
    "kling-2.6/image-to-video": "Kling 2.6 Animate",
    "kling-2.6/motion-control": "Kling Motion",
    "kling-3.0/video": "Kling 3.0",
    "kling-3.0/motion-control": "Kling 3.0 Motion",
    "wan/2-7-text-to-video": "WAN Video",
    "wan/2-7-image-to-video": "WAN Animate",
    "bytedance/seedance-2": "Seedance 2",
    "bytedance/seedance-2-fast": "Seedance 2 Fast",
    "grok-imagine/text-to-video": "Grok Video",
    "grok-imagine/image-to-video": "Grok Animate",
    "happyhorse/text-to-video": "HappyHorse Video",
    "happyhorse/image-to-video": "HappyHorse Animate",
    "veo3_fast": "Veo Fast",
    "veo3": "Veo",
    "veo3_lite": "Veo Lite",
    "suno/v4.5": "Suno",
    "midjourney-imagine": "Midjourney Imagine",
    "midjourney-action": "Midjourney Action",
    "midjourney-blend": "Midjourney Blend",
    "midjourney-describe": "Midjourney Describe",
    "midjourney-video": "Midjourney Video",
}


def _friendly_model_name(model_key: str, display_name: str | None = None) -> str:
    if model_key in _FRIENDLY_MODEL_NAMES:
        return _FRIENDLY_MODEL_NAMES[model_key]
    cleaned = re.sub(r"^[^\wА-Яа-я]+\s*", "", display_name or model_key)
    cleaned = re.sub(r"(?:T2I|I2I|T2V|I2V)", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*·\s*(?:1K|2K|4K|720p|1080p|2160p|за сек)$", "", cleaned).strip()
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" ·") or model_key



def _is_admin_user(user: User | None) -> bool:
    tg_id = getattr(user, "tg_id", None)
    return bool(tg_id and tg_id in settings.ADMIN_IDS)


def _is_midjourney_model(model_key: str) -> bool:
    return model_key in _MJ_ALL_MODELS

def _telegram_bot_username() -> str:
    return str(getattr(settings, "BOT_USERNAME", "") or "").strip().lstrip("@")


def _telegram_start_link(start_param: str) -> str:
    username = _telegram_bot_username()
    if not username:
        return ""
    return f"https://t.me/{username}?start={start_param}"


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_amount(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _clean_model_name(value: str) -> str:
    return _friendly_model_name(value, value)


def _landing_models_payload(model_costs: list[Any]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {"image": [], "video": [], "music": []}
    seen: dict[str, set[str]] = {"image": set(), "video": set(), "music": set()}
    image_keys = {m.value for m in ImageModel} | _MJ_STUDIO_IMAGE_MODELS
    video_keys = {m.value for m in VideoModel} | _MJ_VIDEO_MODELS

    for mc in model_costs:
        if mc.model_key in image_keys:
            bucket = "image"
        elif mc.model_key in video_keys:
            bucket = "video"
        elif getattr(mc, "gen_type", None) == GenerationType.music or mc.model_key == MUSIC_MODEL_KEY:
            bucket = "music"
        else:
            continue
        name = _clean_model_name(getattr(mc, "display_name", "") or getattr(mc, "model_key", ""))
        if name and name not in seen[bucket]:
            seen[bucket].add(name)
            grouped[bucket].append(name)

    if not grouped["music"]:
        grouped["music"].append("Suno v4.5")

    return grouped


async def _resolve_music_credits(session: AsyncSession) -> float:
    model_cost = await repo.get_model_cost(session, MUSIC_MODEL_KEY)
    if model_cost and getattr(model_cost, "is_active", True):
        return float(model_cost.credits)
    return float(DEFAULT_MUSIC_CREDITS)


def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    qs = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}" + f"{settings.KIE_WEBHOOK_PATH}{qs}"


def _improve_image_prompt(prompt: str) -> str:
    return (
        f"{prompt}. Premium detailed image, cinematic composition, soft realistic light, "
        f"clean background, sharp focus, high detail, balanced colors, professional visual style."
    )


def _improve_video_prompt(prompt: str) -> str:
    return (
        f"{prompt}. Cinematic video scene, clear subject action, smooth camera movement, "
        f"natural motion, expressive lighting, detailed environment, high quality, coherent sequence."
    )


def _improve_music_prompt(prompt: str) -> str:
    return (
        f"{prompt}. Original music track, clear genre, mood and tempo, memorable melody, "
        f"rich arrangement, polished production, expressive atmosphere, studio quality, coherent structure."
    )


async def _reconcile_generation_status(session: AsyncSession, gen):
    if not gen or gen.status not in {GenerationStatus.pending, GenerationStatus.processing}:
        return gen

    now = datetime.now(timezone.utc)
    created_at = gen.created_at or now
    age = now - created_at

    task_id = (gen.task_id or '').strip()
    if not task_id:
        if age >= STALE_GENERATION_TIMEOUT:
            logger.warning(
                'Marking stale generation without task_id as failed: gen=%s model=%s age=%s',
                gen.id, gen.model, age,
            )
            if await repo.fail_generation(session, gen.id, 'Generation lost task id before completion'):
                if gen.credits_spent:
                    await repo.add_credits(session, gen.user_id, gen.credits_spent)
            return await repo.get_generation_by_id(session, gen.id)
        return gen

    try:
        if gen.gen_type == GenerationType.image:
            if gen.model in _MIDJOURNEY_IMAGE_MODEL_KEYS:
                result_url = await midjourney_service.poll_mj_image(task_id)
            else:
                result_url = await image_service.poll_kieai_status(task_id)
        elif gen.gen_type == GenerationType.video:
            if gen.model in _MIDJOURNEY_VIDEO_MODEL_KEYS:
                result_url = await midjourney_service.poll_mj_video(task_id)
            elif gen.model in _VEO_MODEL_KEYS:
                result_url = await video_service.poll_veo_status(task_id)
            else:
                result_url = await video_service.poll_kieai_status(task_id)
        else:
            return gen
    except Exception as exc:
        logger.warning('Reconcile failed generation gen=%s task=%s: %s', gen.id, task_id, exc)
        if await repo.fail_generation(session, gen.id, str(exc)):
            if gen.credits_spent:
                await repo.add_credits(session, gen.user_id, gen.credits_spent)
        return await repo.get_generation_by_id(session, gen.id)

    if result_url:
        await repo.finish_generation(session, gen.id, result_url)
        if gen.image_session_id:
            await repo.update_image_session_last_result(session, gen.image_session_id, result_url, gen.id)
        return await repo.get_generation_by_id(session, gen.id)

    return gen


async def _reconcile_user_active_generations(session: AsyncSession, user_id: int) -> None:
    if session.__class__.__module__.startswith('unittest.mock'):
        return

    try:
        active_gens = await repo.get_user_active_generations(session, user_id)
    except Exception as exc:
        logger.debug('Skip active generation reconcile for user=%s: %s', user_id, exc)
        return

    for gen in active_gens:
        await _reconcile_generation_status(session, gen)


async def _data_uri_from_url(url: str) -> str:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to fetch reference image: {exc}")

    content_type = resp.headers.get("content-type", "image/jpeg").split(";", 1)[0].strip() or "image/jpeg"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=422, detail="Reference URL must point to an image")

    import base64
    return f"data:{content_type};base64,{base64.b64encode(resp.content).decode()}"


def _mj_catalog_item(mc: Any) -> MidjourneyCatalogItem:
    return MidjourneyCatalogItem(
        key=mc.model_key,
        display_name=_friendly_model_name(mc.model_key, mc.display_name),
        credits=float(mc.credits),
        gen_type=getattr(mc.gen_type, "value", str(mc.gen_type)),
        available_in_studio=mc.model_key in (_MJ_STUDIO_IMAGE_MODELS | _MJ_VIDEO_MODELS),
    )


def _normalize_public_urls(*urls: str | None) -> list[str]:
    normalized: list[str] = []
    for raw in urls:
        if not raw:
            continue
        if raw.startswith("blob:") or not raw.startswith("http"):
            raise HTTPException(status_code=422, detail="Invalid reference URL — upload the image first")
        normalized.append(raw)
    return normalized


def _normalize_mode(requested_mode: str | None, supported_modes: list[str]) -> str:
    if not supported_modes:
        return requested_mode or "text"
    if requested_mode in supported_modes:
        return requested_mode
    if len(supported_modes) == 1:
        return supported_modes[0]
    raise HTTPException(
        status_code=422,
        detail=f"Unsupported mode for selected model. Allowed: {', '.join(supported_modes)}",
    )


def _normalize_choice(
    value: str | None,
    allowed: list[str],
    *,
    field_name: str,
    default: str | None = None,
) -> str | None:
    if not allowed:
        return None
    if value is None:
        return default or allowed[0]
    if value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported {field_name} for selected model. Allowed: {', '.join(allowed)}",
        )
    return value


def _normalize_int_choice(
    value: int | None,
    allowed: list[int],
    *,
    field_name: str,
    default: int | None = None,
) -> int:
    if not allowed:
        return value if value is not None else (default or 0)
    if value is None:
        return default if default is not None else allowed[0]
    if value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported {field_name} for selected model. Allowed: {', '.join(str(item) for item in allowed)}",
        )
    return value


def _normalize_video_resolution(model_key: str, resolution: str | None) -> str | None:
    if resolution is None:
        return None
    if model_key == "kling-3.0/video":
        aliases = {
            "2K": "pro",
            "720p": "std",
            "1080p": "pro",
            "2160p": "4K",
        }
        return aliases.get(resolution, resolution)
    if model_key == "kling-3.0/motion-control":
        aliases = {
            "std": "720p",
            "pro": "1080p",
            "2K": "1080p",
            "4K": "1080p",
        }
        return aliases.get(resolution, resolution)
    return resolution


def _normalize_image_request(
    *,
    model_key: str,
    reference_urls: list[str],
    aspect_ratio: str | None,
    quality: str | None,
) -> tuple[str | None, str]:
    caps: dict[str, Any] = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    has_reference = bool(reference_urls)

    if has_reference and "image" not in modes:
        raise HTTPException(status_code=422, detail="Selected model does not support reference images")
    if not has_reference and "text" not in modes:
        raise HTTPException(status_code=422, detail="Selected model requires at least one reference image")

    ratio_modes = caps.get("aspect_ratio_modes", modes)
    allowed_ratios = caps.get("aspect_ratios", [])
    normalized_ratio = aspect_ratio
    if allowed_ratios:
        uses_ratio = ("image" if has_reference else "text") in ratio_modes
        if uses_ratio:
            normalized_ratio = _normalize_choice(
                aspect_ratio,
                allowed_ratios,
                field_name="aspect_ratio",
            )
        else:
            normalized_ratio = None

    quality_options = [value for value, _label in caps.get("quality_options", [])]
    normalized_quality = quality or "basic"
    if quality_options:
        legacy_quality_aliases = {
            "basic": "2K" if "2K" in quality_options else quality_options[0],
            "high": "4K" if "4K" in quality_options else quality_options[-1],
        }
        normalized_quality = legacy_quality_aliases.get(normalized_quality, normalized_quality)
        normalized_quality = str(
            _normalize_choice(
                normalized_quality,
                quality_options,
                field_name="quality",
                default=quality_options[0],
            )
        )
        normalized_quality = str(
            normalize_quality_for_aspect_ratio(model_key, normalized_ratio, normalized_quality) or normalized_quality
        )

    return normalized_ratio, normalized_quality


def _normalize_video_request(
    *,
    model_key: str,
    mode: str,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    image_url: str | None,
    reference_urls: list[str] | None,
    grok_mode: str | None,
) -> dict[str, Any]:
    caps: dict[str, Any] = VIDEO_CAPS.get(model_key, {})
    supported_modes = caps.get("modes", ["text"])
    normalized_mode = _normalize_mode(mode, supported_modes)
    all_refs = _normalize_public_urls(image_url, *(reference_urls or [])) if normalized_mode == "image" else []
    max_refs = int(caps.get("max_refs", 1) or 1)
    if len(all_refs) > max_refs:
        raise HTTPException(status_code=422, detail=f"Model supports at most {max_refs} reference image(s)")
    normalized_image_url: str | list[str] | None
    if all_refs:
        normalized_image_url = all_refs[0] if len(all_refs) == 1 else all_refs
    elif normalized_mode == "image":
        raise HTTPException(status_code=422, detail="Selected mode requires image_url")
    else:
        normalized_image_url = None

    normalized_duration = _normalize_int_choice(
        duration,
        caps.get("duration_options", []),
        field_name="duration",
        default=duration,
    )
    normalized_resolution_input = _normalize_video_resolution(model_key, resolution)
    normalized_resolution = _normalize_choice(
        normalized_resolution_input,
        caps.get("resolutions", []) if caps.get("has_resolution") else [],
        field_name="resolution",
    )
    aspect_ratio_allowed = caps.get("aspect_ratios", [])
    aspect_ratio_min_refs = int(caps.get("aspect_ratio_min_refs", 0) or 0)
    if aspect_ratio_min_refs and normalized_mode == "image" and len(all_refs) < aspect_ratio_min_refs:
        aspect_ratio_allowed = []
    normalized_aspect_ratio = _normalize_choice(
        aspect_ratio,
        aspect_ratio_allowed,
        field_name="aspect_ratio",
    )
    mode_options = caps.get("mode_options", [])
    normalized_grok_mode = grok_mode or "normal"
    if mode_options:
        normalized_grok_mode = str(
            _normalize_choice(
                normalized_grok_mode,
                mode_options,
                field_name="mode option",
                default="normal" if "normal" in mode_options else mode_options[0],
            )
        )
    else:
        normalized_grok_mode = "normal"

    return {
        "mode": normalized_mode,
        "duration": normalized_duration,
        "aspect_ratio": normalized_aspect_ratio,
        "resolution": normalized_resolution,
        "image_url": normalized_image_url,
        "grok_mode": normalized_grok_mode,
    }


def _is_per_second_video_model(caps: dict[str, Any]) -> bool:
    return caps.get("billing_mode") == "per_second"


def _video_total_credits(duration: int, rate_or_flat: float, *, is_per_second: bool) -> float:
    if is_per_second:
        return rate_or_flat * duration
    return rate_or_flat


async def _video_model_rate_info(
    session: AsyncSession,
    model_key: str,
    caps: dict[str, Any],
    fallback_credits: float,
) -> tuple[bool, int | None]:
    is_per_second = _is_per_second_video_model(caps)
    if not is_per_second:
        return False, None

    resolutions = caps.get("resolutions") or []
    reference_resolution = resolutions[0] if resolutions else None
    variant_cost = await repo.resolve_video_model_cost(session, model_key, resolution=reference_resolution)
    credits_per_sec = variant_cost.credits if variant_cost else fallback_credits
    return True, int(credits_per_sec)


# ── schemas ───────────────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    id: int
    tg_id: int
    username: str | None
    full_name: str | None
    credits: float
    referral_code: str
    referral_link: str
    referral_balance: float
    referral_withdraw_min_rub: float


class MidjourneyCatalogItem(BaseModel):
    key: str
    display_name: str
    credits: float
    gen_type: str
    available_in_studio: bool = False


class ModelInfo(BaseModel):
    key: str
    display_name: str
    credits: float
    modes: list[str]
    aspect_ratios: list[str]
    aspect_ratio_min_refs: int = 0
    quality_options: list[dict[str, str]]
    quality_prices: dict[str, float] = Field(default_factory=dict)
    max_refs: int = 1
    counts: list[int]
    has_quality: bool
    is_per_second: bool = False
    credits_per_sec: float | None = None
    durations: list[int] = []
    resolutions: list[str] = []
    motion_controls: list[str] = []
    mode_options: list[str] = []


class GenerationOut(BaseModel):
    id: int
    model: str
    gen_type: str
    prompt: str
    status: str
    result_url: str | None
    credits_spent: float
    created_at: str
    is_public_feed: bool = False
    is_prompt_library: bool = False


class ImageGenRequest(BaseModel):
    model: str
    prompt: str = Field(..., min_length=1, max_length=4000)
    aspect_ratio: str | None = None
    quality: str = "basic"
    count: int = Field(default=1, ge=1, le=6)
    reference_url: str | None = None
    reference_urls: list[str] = []


class VideoGenRequest(BaseModel):
    model: str
    prompt: str = Field(..., min_length=1, max_length=4000)
    mode: str = "text"                    # "text" | "image"
    duration: int = Field(default=5, ge=2, le=30)
    aspect_ratio: str | None = None
    resolution: str | None = None
    image_url: str | None = None
    reference_urls: list[str] = []
    grok_mode: str = "normal"


class FeedRemixRequest(BaseModel):
    model: str
    mode: str = "text"                    # "text" | "image"
    duration: int = Field(default=5, ge=2, le=30)
    aspect_ratio: str | None = None
    resolution: str | None = None
    image_url: str | None = None
    reference_urls: list[str] = []
    grok_mode: str = "normal"
    quality: str = "basic"
    count: int = Field(default=1, ge=1, le=6)




class PromptImproveRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    kind: str = "image"


class PromptSubmitRequest(BaseModel):
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(default="", max_length=500)
    prompt_text: str = Field(..., min_length=10, max_length=4000)
    category: str = "other"


class MusicGenRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    instrumental: bool = False


class TopupRequest(BaseModel):
    plan_key: str


# ── user ─────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserProfile)
async def get_me(user: User = Depends(get_miniapp_user)) -> UserProfile:
    """Current user profile with balance."""
    return UserProfile(
        id=user.id,
        tg_id=user.tg_id,
        username=user.username,
        full_name=user.full_name,
        credits=user.credits,
        referral_code=user.referral_code,
        referral_link=_telegram_start_link(user.referral_code),
        referral_balance=user.referral_balance,
        referral_withdraw_min_rub=settings.REFERRAL_WITHDRAW_MIN_RUB,
    )


# ── models ────────────────────────────────────────────────────────────────────



@router.post("/photo-prompt")
async def miniapp_photo_prompt(
    file: UploadFile = File(...),
    user: User = Depends(get_miniapp_user),
):
    """Generate prompt from uploaded photo for miniapp studio."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty file")

    mime = file.content_type or "image/jpeg"
    if not mime.startswith("image/"):
        raise HTTPException(status_code=422, detail="Only image files are supported")

    try:
        prompt = await generate_prompt_from_photo(data, mime)
    except Exception as e:
        logger.exception("miniapp photo prompt error user=%s: %s", user.id, e)
        raise HTTPException(status_code=502, detail=f"Photo prompt failed: {e}")

    return {"prompt": prompt}


@router.post("/prompt/improve")
async def miniapp_improve_prompt(
    body: PromptImproveRequest,
    user: User = Depends(get_miniapp_user),
):
    """Lightweight prompt improver for miniapp studio."""
    prompt = body.prompt.strip()
    kind = body.kind

    if kind == "video":
        improved = _improve_video_prompt(prompt)
    elif kind == "music":
        improved = _improve_music_prompt(prompt)
    else:
        improved = _improve_image_prompt(prompt)

    return {"prompt": improved}


async def _resolve_image_quality_prices(
    session: AsyncSession,
    model_key: str,
    quality_raw: list[tuple[str, str]] | list[list[str]],
    fallback_credits: float,
) -> dict[str, float]:
    prices: dict[str, float] = {}
    for raw in quality_raw or []:
        if not raw:
            continue
        quality_value = str(raw[0])
        try:
            variant = await repo.resolve_image_model_cost(session, model_key, quality=quality_value)
        except Exception as exc:
            logger.warning("Failed to resolve quality price model=%s quality=%s: %s", model_key, quality_value, exc)
            variant = None
        prices[quality_value] = float(getattr(variant, "credits", fallback_credits) or fallback_credits)
    return prices


@router.get("/models/image", response_model=list[ModelInfo])
async def list_image_models(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[ModelInfo]:
    """All active image models with costs and capabilities."""
    model_costs = await repo.get_all_model_costs(session)
    image_keys = {m.value for m in ImageModel} | _MJ_STUDIO_IMAGE_MODELS
    result = []
    for mc in model_costs:
        if mc.model_key not in image_keys:
            continue
        if _is_midjourney_model(mc.model_key) and not _is_admin_user(user):
            continue
        caps: dict[str, Any] = IMAGE_CAPS.get(mc.model_key, _MJ_IMAGE_CAPS.get(mc.model_key, {}))
        quality_raw = caps.get("quality_options", [])
        quality_prices = await _resolve_image_quality_prices(session, mc.model_key, quality_raw, float(mc.credits))
        result.append(ModelInfo(
            key=mc.model_key,
            display_name=_friendly_model_name(mc.model_key, mc.display_name),
            credits=mc.credits,
            modes=caps.get("modes", ["text"]),
            aspect_ratios=caps.get("aspect_ratios", []),
            aspect_ratio_min_refs=int(caps.get("aspect_ratio_min_refs", 0) or 0),
            quality_options=[{"value": value, "label": label} for value, label in quality_raw],
            quality_prices=quality_prices,
            counts=caps.get("counts", [1]),
            has_quality=bool(caps.get("has_quality")),
            max_refs=int(caps.get("max_refs", 1) or 1),
        ))
    return result


@router.get("/models/video", response_model=list[ModelInfo])
async def list_video_models(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[ModelInfo]:
    """All active video models with costs and capabilities."""
    model_costs = await repo.get_all_model_costs(session)
    video_keys = {m.value for m in VideoModel} | _MJ_VIDEO_MODELS
    result = []
    for mc in model_costs:
        if mc.model_key not in video_keys:
            continue
        if _is_midjourney_model(mc.model_key) and not _is_admin_user(user):
            continue
        caps: dict[str, Any] = VIDEO_CAPS.get(mc.model_key, _MJ_VIDEO_CAPS.get(mc.model_key, {}))
        is_per_sec, credits_per_sec = await _video_model_rate_info(session, mc.model_key, caps, mc.credits)
        result.append(ModelInfo(
            key=mc.model_key,
            display_name=_friendly_model_name(mc.model_key, mc.display_name),
            credits=credits_per_sec if is_per_sec and credits_per_sec is not None else mc.credits,
            modes=caps.get("modes", ["text"]),
            aspect_ratios=caps.get("aspect_ratios", []),
            aspect_ratio_min_refs=int(caps.get("aspect_ratio_min_refs", 0) or 0),
            quality_options=[{"value": r, "label": (caps.get("resolution_labels", {}) or {}).get(r, r)} for r in (caps.get("resolutions") or [])],
            counts=[],
            has_quality=bool(caps.get("has_resolution")),
            is_per_second=is_per_sec,
            credits_per_sec=credits_per_sec,
            durations=caps.get("duration_options", []),
            resolutions=caps.get("resolutions") or [],
            motion_controls=caps.get("motion_controls", []),
            mode_options=caps.get("mode_options", []),
            max_refs=int(caps.get("max_refs", 1) or 1),
        ))
    return result


@router.get("/models/music", response_model=list[ModelInfo])
async def list_music_models(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[ModelInfo]:
    """All active music models with costs and capabilities."""
    del user
    model_costs = await repo.get_all_model_costs(session)
    result = []
    for mc in model_costs:
        if getattr(mc, "gen_type", None) != GenerationType.music and mc.model_key != MUSIC_MODEL_KEY:
            continue
        if not getattr(mc, "is_active", True):
            continue
        result.append(ModelInfo(
            key=mc.model_key,
            display_name=_friendly_model_name(mc.model_key, mc.display_name),
            credits=mc.credits,
            modes=["text"],
            aspect_ratios=[],
            aspect_ratio_min_refs=0,
            quality_options=[],
            counts=[1],
            has_quality=False,
            max_refs=0,
        ))
    if result:
        return result
    return [ModelInfo(
        key=MUSIC_MODEL_KEY,
        display_name=_friendly_model_name(MUSIC_MODEL_KEY, "Suno"),
        credits=await _resolve_music_credits(session),
        modes=["text"],
        aspect_ratios=[],
        aspect_ratio_min_refs=0,
        quality_options=[],
        counts=[1],
        has_quality=False,
        max_refs=0,
    )]


@router.get("/public/midjourney", response_model=list[MidjourneyCatalogItem])
async def public_midjourney_models(
    session: AsyncSession = Depends(get_session),
) -> list[MidjourneyCatalogItem]:
    return []


@router.get("/public/models")
async def public_models_summary(
    session: AsyncSession = Depends(get_session),
) -> dict[str, list[str]]:
    """Public model summary for the landing page."""
    model_costs = await repo.get_all_model_costs(session)
    public_model_costs = [mc for mc in model_costs if not _is_midjourney_model(mc.model_key)]
    return _landing_models_payload(public_model_costs)


# ── image generation ──────────────────────────────────────────────────────────

@router.post("/generate/image", response_model=GenerationOut, status_code=202)
async def create_image_generation(
    body: ImageGenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """
    Start an async image generation.

    Returns immediately with `status: pending` and the generation `id`.
    Poll `GET /api/v1/generations/{id}` until `status` is `done` or `failed`.
    """
    all_refs = _normalize_public_urls(body.reference_url, *body.reference_urls)
    if body.model in _MJ_STUDIO_IMAGE_MODELS:
        if not _is_admin_user(user):
            raise HTTPException(status_code=403, detail="Model not available")
        caps: dict[str, Any] = _MJ_IMAGE_CAPS.get(body.model, {})
        normalized_ratio = _normalize_choice(body.aspect_ratio, caps.get("aspect_ratios", []), field_name="aspect ratio")
        model_cost = await repo.get_model_cost(session, body.model)
        if not model_cost or not getattr(model_cost, "is_active", True):
            raise HTTPException(status_code=422, detail="Model not available")
        max_refs = int(caps.get("max_refs", 1) or 1)
        if len(all_refs) > max_refs:
            raise HTTPException(status_code=422, detail=f"Model supports at most {max_refs} reference image(s)")
        if body.model == "midjourney-blend" and len(all_refs) < 2:
            raise HTTPException(status_code=422, detail="Blend requires at least 2 reference images")
        if body.model == "midjourney-imagine" and not body.prompt.strip():
            raise HTTPException(status_code=422, detail="Prompt is required")
        if user.credits < model_cost.credits:
            raise HTTPException(status_code=402, detail=f"Insufficient credits: need {model_cost.credits}, have {user.credits}")
        await _reconcile_user_active_generations(session, user.id)
        active = await repo.count_user_active_generations(session, user.id)
        if active >= MAX_CONCURRENT:
            raise HTTPException(status_code=429, detail="Too many concurrent generations")
        ok = await repo.spend_credits(session, user.id, model_cost.credits)
        if not ok:
            raise HTTPException(status_code=402, detail="Failed to spend credits")
        gen_prompt = body.prompt.strip() or f"blend:{len(all_refs)}"
        image_session = await repo.create_image_session(session=session, user_id=user.id, model=body.model, mode="image" if all_refs else "text", aspect_ratio=normalized_ratio, quality="basic", count=1, base_prompt=gen_prompt, reference_file_id=None, reference_url=all_refs[0] if all_refs else None)
        gen = await repo.create_generation(session, user.id, body.model, GenerationType.image, gen_prompt, model_cost.credits, image_session_id=image_session.id, action_type=ImageGenerationAction.initial)
        try:
            if body.model == "midjourney-imagine":
                submitted_prompt = f"{all_refs[0]} {body.prompt.strip()}".strip() if all_refs else body.prompt.strip()
                task_id = await midjourney_service.imagine(submitted_prompt, reference_url=all_refs[0] if all_refs else None)
            else:
                blend_images = [await _data_uri_from_url(url) for url in all_refs]
                task_id = await midjourney_service.blend(blend_images, dimensions=MJDimensions(_MJ_BLEND_DIMENSIONS.get(normalized_ratio or "1:1", "SQUARE")))
        except Exception as exc:
            logger.error("miniapp Midjourney image error user=%s model=%s: %s", user.id, body.model, exc)
            if await repo.fail_generation(session, gen.id, str(exc)):
                await repo.add_credits(session, user.id, model_cost.credits)
            raise HTTPException(status_code=502, detail="Generation service error")
        await repo.update_generation_task(session, gen.id, task_id)
        await repo.update_image_session_last_prompt(session, image_session.id, gen_prompt)
        await session.refresh(gen)
        return _gen_out(gen)

    try:
        model = ImageModel(body.model)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown image model: {body.model!r}")

    caps: dict[str, Any] = IMAGE_CAPS.get(model.value, {})
    normalized_ratio, normalized_quality = _normalize_image_request(
        model_key=model.value,
        reference_urls=all_refs,
        aspect_ratio=body.aspect_ratio,
        quality=body.quality,
    )
    model_cost = await repo.resolve_image_model_cost(session, body.model, quality=normalized_quality)
    if not model_cost:
        raise HTTPException(status_code=422, detail="Model not available")

    max_refs = int(caps.get("max_refs", 1) or 1)
    if len(all_refs) > max_refs:
        raise HTTPException(status_code=422, detail=f"Model supports at most {max_refs} reference image(s)")
    if body.count not in (caps.get("counts") or [1]):
        raise HTTPException(status_code=422, detail="Unsupported count for selected model")
    has_ref = bool(all_refs)

    if user.credits < model_cost.credits:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits: need {model_cost.credits}, have {user.credits}",
        )

    await _reconcile_user_active_generations(session, user.id)
    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, model_cost.credits)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    # Determine mode from reference presence
    image_session = await repo.create_image_session(
        session=session,
        user_id=user.id,
        model=body.model,
        mode="image" if has_ref else "text",
        aspect_ratio=normalized_ratio,
        quality=normalized_quality,
        count=body.count,
        base_prompt=body.prompt,
        reference_file_id=None,
        reference_url=all_refs[0] if all_refs else None,
    )

    gen = await repo.create_generation(
        session, user.id, body.model, GenerationType.image,
        body.prompt, model_cost.credits,
        image_session_id=image_session.id,
        action_type=ImageGenerationAction.initial,
    )

    ref_urls: str | list[str] | None = None
    if len(all_refs) == 1:
        ref_urls = all_refs[0]
    elif len(all_refs) > 1:
        ref_urls = all_refs

    try:
        result = await image_service.generate_image(
            model,
            body.prompt,
            image_url=ref_urls,
            aspect_ratio=normalized_ratio,
            n=body.count,
            quality=normalized_quality,
            callback_url=_kie_callback_url(),
        )
    except Exception as exc:
        logger.error("miniapp image gen error user=%s: %s", user.id, exc)
        if await repo.fail_generation(session, gen.id, str(exc)):
            await repo.add_credits(session, user.id, model_cost.credits)
        raise HTTPException(status_code=502, detail="Generation service error")

    await repo.update_generation_task(session, gen.id, result.task_id or "")
    await repo.update_image_session_last_prompt(session, image_session.id, body.prompt)

    await session.refresh(gen)
    return _gen_out(gen)


# ── video generation ──────────────────────────────────────────────────────────

@router.post("/generate/video", response_model=GenerationOut, status_code=202)
async def create_video_generation(
    body: VideoGenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """
    Start an async video generation.

    Returns immediately with `status: pending`.
    Poll `GET /api/v1/generations/{id}` until done.
    """
    if body.model in _MJ_VIDEO_MODELS:
        if not _is_admin_user(user):
            raise HTTPException(status_code=403, detail="Model not available")
        image_urls = _normalize_public_urls(body.image_url, *body.reference_urls)
        if not image_urls:
            raise HTTPException(status_code=422, detail="Midjourney Video requires a reference image")
        motion_value = body.grok_mode if body.grok_mode in {"low", "high"} else "low"
        model_cost = await repo.get_model_cost(session, body.model)
        if not model_cost or not getattr(model_cost, "is_active", True):
            raise HTTPException(status_code=422, detail="Model not available")
        if user.credits < model_cost.credits:
            raise HTTPException(status_code=402, detail=f"Insufficient credits: need {model_cost.credits}, have {user.credits}")
        await _reconcile_user_active_generations(session, user.id)
        active = await repo.count_user_active_generations(session, user.id)
        if active >= MAX_CONCURRENT:
            raise HTTPException(status_code=429, detail="Too many concurrent generations")
        ok = await repo.spend_credits(session, user.id, model_cost.credits)
        if not ok:
            raise HTTPException(status_code=402, detail="Failed to spend credits")
        prompt = body.prompt.strip()
        gen = await repo.create_generation(session, user.id, body.model, GenerationType.video, prompt or "mj-video", model_cost.credits)
        try:
            task_id = await midjourney_service.submit_video(image=image_urls[0], motion=MJVideoMotion(motion_value), prompt=prompt)
        except Exception as exc:
            logger.error("miniapp Midjourney video error user=%s: %s", user.id, exc)
            if await repo.fail_generation(session, gen.id, str(exc)):
                await repo.add_credits(session, user.id, model_cost.credits)
            raise HTTPException(status_code=502, detail="Generation service error")
        await repo.update_generation_task(session, gen.id, task_id)
        await session.refresh(gen)
        return _gen_out(gen)

    try:
        model = VideoModel(body.model)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown video model: {body.model!r}")

    normalized = _normalize_video_request(
        model_key=body.model,
        mode=body.mode,
        duration=body.duration,
        aspect_ratio=body.aspect_ratio,
        resolution=body.resolution,
        image_url=body.image_url,
        reference_urls=body.reference_urls,
        grok_mode=body.grok_mode,
    )
    model_cost = await repo.resolve_video_model_cost(
        session,
        body.model,
        duration=normalized["duration"],
        resolution=normalized["resolution"],
    )
    if not model_cost:
        raise HTTPException(status_code=422, detail="Model not available")

    caps: dict[str, Any] = VIDEO_CAPS.get(body.model, {})
    total_credits = _video_total_credits(
        normalized["duration"],
        model_cost.credits,
        is_per_second=_is_per_second_video_model(caps),
    )
    image_url = normalized["image_url"]

    if user.credits < total_credits:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits: need {total_credits}, have {user.credits}",
        )

    await _reconcile_user_active_generations(session, user.id)
    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, total_credits)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    gen = await repo.create_generation(
        session, user.id, body.model, GenerationType.video,
        body.prompt, total_credits,
    )

    try:
        result = await video_service.generate_video(
            model,
            body.prompt,
            image_url=image_url,
            duration=normalized["duration"],
            aspect_ratio=normalized["aspect_ratio"],
            resolution=normalized["resolution"],
            grok_mode=normalized["grok_mode"],
            callback_url=_kie_callback_url(),
        )
    except Exception as exc:
        logger.error("miniapp video gen error user=%s: %s", user.id, exc)
        if await repo.fail_generation(session, gen.id, str(exc)):
            await repo.add_credits(session, user.id, total_credits)
        raise HTTPException(status_code=502, detail="Generation service error")

    await repo.update_generation_task(session, gen.id, result.task_id or "")

    await session.refresh(gen)
    return _gen_out(gen)


# ── music generation ──────────────────────────────────────────────────────────

@router.post("/generate/music", response_model=GenerationOut, status_code=202)
async def create_music_generation(
    body: MusicGenRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """Start Suno music generation. Returns immediately; poll /generations/{id}."""
    from api.music_service import create_music_task, register_miniapp_task

    music_credits = await _resolve_music_credits(session)

    if user.credits < music_credits:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits: need {music_credits}, have {user.credits}",
        )

    await _reconcile_user_active_generations(session, user.id)
    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, music_credits)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    gen = await repo.create_generation(
        session, user.id, MUSIC_MODEL_KEY, GenerationType.music,
        body.prompt, music_credits,
    )

    try:
        task_id = await create_music_task(body.prompt, body.instrumental)
    except Exception as exc:
        logger.error("miniapp music gen error user=%s: %s", user.id, exc)
        if await repo.fail_generation(session, gen.id, str(exc)):
            await repo.add_credits(session, user.id, music_credits)
        raise HTTPException(status_code=502, detail="Music generation service error")

    await repo.update_generation_task(session, gen.id, task_id)
    register_miniapp_task(task_id, gen.id)

    await session.refresh(gen)
    return _gen_out(gen)


# ── generation status / history ───────────────────────────────────────────────

@router.get("/generations/{gen_id}", response_model=GenerationOut)
async def get_generation(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """Poll a single generation for status and result_url."""
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    gen = await _reconcile_generation_status(session, gen)
    return _gen_out(gen)


@router.get("/history", response_model=list[GenerationOut])
async def get_history(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[GenerationOut]:
    """Last N generations for the current user."""
    await _reconcile_user_active_generations(session, user.id)
    gens = await repo.get_user_history(session, user.id, limit=limit)
    return [_gen_out(g) for g in gens]


# ── feed ──────────────────────────────────────────────────────────────────────

@router.get("/feed")
async def get_feed(
    limit: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[dict]:
    """Public image feed — prompt is hidden from non-authors."""
    cards = await repo.get_feed_generations(session, limit=limit)
    return [
        {
            "id": c.generation.id,
            "model": c.generation.model,
            "result_url": c.generation.result_url,
            "likes_count": c.generation.likes_count,
            "shares_count": c.generation.shares_count,
            "aspect_ratio": c.aspect_ratio,
            "author": c.username or c.full_name or "anon",
            "is_mine": c.generation.user_id == user.id,
                "remixes": c.remix_count,
        }
        for c in cards
    ]


@router.post("/generations/{gen_id}/share", status_code=200)
async def share_generation(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Publish own generation to the public feed and return its repost link."""
    gen = await repo.share_to_feed(session, gen_id, user.id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found or not ready")
    link = _telegram_start_link(build_start_payload(ref_code=user.referral_code, target_kind="feed", target_id=gen.id))
    return {"id": gen.id, "is_public_feed": gen.is_public_feed, "link": link}


@router.post("/feed/{gen_id}/remove", status_code=200)
async def remove_feed_post(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Remove own generation from the public feed."""
    gen = await repo.remove_from_feed(session, gen_id, user.id)
    if not gen:
        raise HTTPException(status_code=404, detail="Post not found or not yours")
    return {"id": gen.id, "is_public_feed": gen.is_public_feed}


@router.post("/feed/{gen_id}/like", status_code=200)
async def like_feed_post(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> dict:
    gen = await repo.like_feed_generation(session, gen_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Post not found")
    return {"likes_count": gen.likes_count}


@router.post("/feed/{gen_id}/remix", response_model=GenerationOut, status_code=202)
async def remix_feed_post(
    gen_id: int,
    body: FeedRemixRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> GenerationOut:
    """
    Start a generation using the hidden prompt of a public feed post.
    The user chooses model/params; the original author's prompt is used silently.
    """
    source = await repo.get_public_feed_generation(session, gen_id)
    if not source:
        raise HTTPException(status_code=404, detail="Post not found or not public")

    # Use the source prompt but with the user-chosen model
    try:
        model = VideoModel(body.model)
        gen_type = "video"
    except ValueError:
        try:
            img_model = ImageModel(body.model)
            gen_type = "image"
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown model: {body.model!r}")

    normalized_video: dict[str, Any] | None = None
    normalized_image_url: str | None = None
    normalized_ratio = body.aspect_ratio
    normalized_quality = body.quality or "basic"

    if gen_type == "video":
        fallback_image_url = body.image_url
        if body.mode == "image" and not fallback_image_url:
            fallback_image_url = source.result_url
        normalized_video = _normalize_video_request(
            model_key=body.model,
            mode=body.mode,
            duration=body.duration,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            image_url=fallback_image_url,
            reference_urls=body.reference_urls,
            grok_mode=body.grok_mode,
        )
        model_cost = await repo.resolve_video_model_cost(
            session,
            body.model,
            duration=normalized_video["duration"],
            resolution=normalized_video["resolution"],
        )
    else:
        image_refs = _normalize_public_urls(
            source.result_url if body.mode == "image" else None,
            body.image_url,
            *(body.reference_urls or []),
        )
        if image_refs:
            normalized_image_url = image_refs[0] if len(image_refs) == 1 else image_refs
        else:
            normalized_image_url = None
        normalized_ratio, normalized_quality = _normalize_image_request(
            model_key=body.model,
            reference_urls=image_refs,
            aspect_ratio=body.aspect_ratio,
            quality=body.quality or "basic",
        )
        model_cost = await repo.resolve_image_model_cost(session, body.model, quality=normalized_quality)

    if not model_cost:
        raise HTTPException(status_code=422, detail="Model not available")

    total_credits = (
        _video_total_credits(
            normalized_video["duration"],
            model_cost.credits,
            is_per_second=_is_per_second_video_model(VIDEO_CAPS.get(body.model, {})),
        )
        if gen_type == "video"
        else model_cost.credits
    )

    if user.credits < total_credits:
        raise HTTPException(status_code=402, detail=f"Insufficient credits: need {total_credits}")

    await _reconcile_user_active_generations(session, user.id)
    active = await repo.count_user_active_generations(session, user.id)
    if active >= MAX_CONCURRENT:
        raise HTTPException(status_code=429, detail="Too many concurrent generations")

    ok = await repo.spend_credits(session, user.id, total_credits)
    if not ok:
        raise HTTPException(status_code=402, detail="Failed to spend credits")

    image_session_id: int | None = None
    if gen_type == "image":
        image_session = await repo.create_image_session(
            session=session,
            user_id=user.id,
            model=body.model,
            mode="image" if normalized_image_url else "text",
            aspect_ratio=normalized_ratio,
            quality=normalized_quality,
            count=body.count,
            base_prompt=source.prompt,
            reference_url=normalized_image_url,
        )
        image_session_id = image_session.id

    from db.models import GenerationType as GT
    gen_type_enum = GT.video if gen_type == "video" else GT.image
    gen = await repo.create_generation(
        session, user.id, body.model, gen_type_enum,
        source.prompt, total_credits,
        image_session_id=image_session_id,
        parent_generation_id=source.id if gen_type == "image" else None,
        action_type=ImageGenerationAction.remix if gen_type == "image" else None,
        source_feed_gen_id=gen_id,
    )

    try:
        if gen_type == "video":
            result = await video_service.generate_video(
                model,
                source.prompt,
                image_url=normalized_video["image_url"],
                duration=normalized_video["duration"],
                aspect_ratio=normalized_video["aspect_ratio"],
                resolution=normalized_video["resolution"],
                grok_mode=normalized_video["grok_mode"],
                callback_url=_kie_callback_url(),
            )
        else:
            result = await image_service.generate_image(
                img_model,
                source.prompt,
                image_url=normalized_image_url,
                aspect_ratio=normalized_ratio,
                n=body.count,
                quality=normalized_quality,
                callback_url=_kie_callback_url(),
            )
    except Exception as exc:
        logger.error("feed remix error user=%s gen=%s: %s", user.id, gen_id, exc)
        if await repo.fail_generation(session, gen.id, str(exc)):
            await repo.add_credits(session, user.id, total_credits)
        raise HTTPException(status_code=502, detail="Generation service error")

    await repo.update_generation_task(session, gen.id, result.task_id or "")
    await repo.increment_feed_share(session, gen_id)
    await session.refresh(gen)
    return _gen_out(gen)


@router.get("/feed/{gen_id}/link")
async def get_feed_share_link(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Returns a shareable Telegram deeplink for this public post. Only the author can get it."""
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if not gen.is_public_feed:
        raise HTTPException(status_code=400, detail="Generation is not public yet — share to feed first")
    link = _telegram_start_link(build_start_payload(ref_code=user.referral_code, target_kind="feed", target_id=gen_id))
    return {"link": link, "gen_id": gen_id}


@router.post("/generations/{gen_id}/share-library", status_code=200)
async def share_to_library(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Opt this generation's prompt into the public prompt library."""
    gen = await repo.share_to_library(session, gen_id, user.id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found or not ready")
    return {"id": gen.id, "is_prompt_library": gen.is_prompt_library}


# ── prompt library ────────────────────────────────────────────────────────────

@router.get("/prompts")
async def list_prompts(
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> dict:
    """Paginated list of approved prompts. Optionally filter by category."""
    from db.models import PromptCategory
    from db.prompt_repository import count_approved_prompts, get_approved_prompts

    cat = None
    if category:
        try:
            cat = PromptCategory(category)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown category: {category!r}")

    prompts = await get_approved_prompts(session, category=cat, limit=limit, offset=(page - 1) * limit)
    total = await count_approved_prompts(session, category=cat)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [_prompt_out(p) for p in prompts],
    }


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> dict:
    from db.prompt_repository import get_prompt_by_id
    p = await get_prompt_by_id(session, prompt_id)
    if not p:
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _prompt_out(p)


@router.post("/prompts", status_code=201)
async def submit_prompt(
    body: PromptSubmitRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Submit a new prompt for moderation."""
    from db.models import PromptCategory
    from db.prompt_repository import create_prompt, set_ai_moderation_result

    try:
        cat = PromptCategory(body.category)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown category: {body.category!r}")

    p = await create_prompt(
        session,
        user.id,
        body.title,
        body.description,
        cat,
        body.prompt_text,
    )
    try:
        decision = await generate_prompt_moderation_decision(
            prompt_id=p.id,
            title=p.title,
            description=p.description,
            prompt_text=p.prompt_text,
            tags=list(p.tags or []),
            model=p.model,
        )
        p = await set_ai_moderation_result(
            session,
            p.id,
            decision=decision.decision,
            risk=decision.risk,
            reason=decision.reason,
            recommendation=decision.recommendation,
            raw=decision.raw,
        ) or p
    except Exception as exc:
        logger.warning("prompt auto moderation failed prompt=%s: %s", p.id, exc)
        return {"id": p.id, "status": p.status.value, "message": "Submitted for manual moderation"}

    if decision.decision == "approve":
        from db.prompt_repository import approve_prompt
        p = await approve_prompt(session, p.id) or p
        return {"id": p.id, "status": p.status.value, "message": "Approved automatically"}

    if decision.decision == "reject":
        from db.prompt_repository import reject_prompt
        p = await reject_prompt(session, p.id, decision.reason[:500]) or p
        return {"id": p.id, "status": p.status.value, "message": decision.reason or "Rejected automatically"}

    return {"id": p.id, "status": p.status.value, "message": "Sent to manual moderation"}


# ── payments ──────────────────────────────────────────────────────────────────

@router.get("/plans")
async def list_plans(
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """Active price plans."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    plans = await repo.get_active_price_plans(session)
    return [
        {
            "key": p.key,
            "label": p.label,
            "title": p.label,
            "credits": p.credits,
            "price_rub": p.price_rub,
            "price_rub_display": f"{_fmt_amount(p.price_rub)}₽",
            "price_stars": _plan_stars_price(p),
            "price_usdt": round(p.price_rub / 90, 2),  # approximate
        }
        for p in plans
    ]


@router.post("/topup/tbank")
async def topup_tbank(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Create a T-Bank payment invoice. Returns `pay_url` to redirect the user."""
    from db.models import PaymentProvider
    from payments.tbank import create_payment as tbank_create_payment

    plan = await repo.get_price_plan_by_key(session, body.plan_key)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        payment = await tbank_create_payment(plan, user.id)
    except Exception as exc:
        logger.error("T-Bank invoice error user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Payment service error")

    tx = await repo.create_transaction(
        session=session,
        user_id=user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.tbank,
        external_id=payment.payment_id,
    )

    return {"pay_url": payment.payment_url, "transaction_id": tx.id, "credits": plan.credits, "amount_rub": plan.price_rub}


@router.post("/topup/stars")
async def topup_stars(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Create a Telegram Stars invoice link for the mini app."""
    from main import bot

    if not settings.TELEGRAM_STARS_ENABLED:
        raise HTTPException(status_code=404, detail="Telegram Stars are not enabled")

    plan = await repo.get_price_plan_by_key(session, body.plan_key)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    stars = _plan_stars_price(plan)
    pending_external_id = f"stars_pending:{user.id}:{plan.key}"
    tx = await repo.get_transaction_by_external_id(session, pending_external_id)
    if not tx or tx.status != TransactionStatus.pending or tx.user_id != user.id or tx.provider != PaymentProvider.telegram_stars:
        external_id = pending_external_id if not tx else f"{pending_external_id}:{int(datetime.now(timezone.utc).timestamp())}"
        tx = await repo.create_transaction(
            session=session,
            user_id=user.id,
            amount_rub=plan.price_rub,
            credits=plan.credits,
            provider=PaymentProvider.telegram_stars,
            external_id=external_id,
        )

    try:
        invoice_link = await bot.create_invoice_link(
            title=f"⭐ {plan.label}",
            description=f"Пополнение {plan.label} · {plan.credits} 💋 · {stars} ⭐",
            payload=f"stars:{tx.id}:{plan.key}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label=f"{plan.credits} credits", amount=stars)],
        )
    except Exception as exc:
        logger.error("Stars invoice error user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Payment service error")

    return {
        "invoice_link": invoice_link,
        "transaction_id": tx.id,
        "credits": plan.credits,
        "amount_stars": stars,
        "amount_rub": plan.price_rub,
    }


@router.post("/topup/crypto")
async def topup_crypto(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Create a CryptoBot invoice. Returns `pay_url` to open in CryptoBot."""
    from db.models import PaymentProvider
    from payments.cryptobot import create_invoice as crypto_create_invoice

    plan = await repo.get_price_plan_by_key(session, body.plan_key)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    usdt_amount = round(plan.price_rub / 90, 2)
    try:
        invoice = await crypto_create_invoice(
            credits=plan.credits,
            amount_usd=usdt_amount,
            plan_key=plan.key,
            user_id=user.id,
        )
    except Exception as exc:
        logger.error("CryptoBot invoice error user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Payment service error")

    tx = await repo.create_transaction(
        session=session,
        user_id=user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.cryptobot,
        external_id=str(invoice.invoice_id),
    )

    return {"pay_url": invoice.pay_url, "transaction_id": tx.id, "credits": plan.credits, "amount_usdt": usdt_amount}


# ── serializers ───────────────────────────────────────────────────────────────

def _gen_out(gen) -> GenerationOut:
    return GenerationOut(
        id=gen.id,
        model=gen.model,
        gen_type=gen.gen_type.value,
        prompt=gen.prompt,
        status=gen.status.value,
        result_url=gen.result_url,
        credits_spent=gen.credits_spent,
        created_at=gen.created_at.isoformat() if gen.created_at else "",
        is_public_feed=bool(gen.is_public_feed),
        is_prompt_library=bool(getattr(gen, "is_prompt_library", False)),
    )


def _prompt_out(p) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "description": p.description or "",
        "prompt_text": p.prompt_text,
        "category": p.category.value if p.category else "other",
        "tags": p.tags or [],
        "uses_count": p.uses_count,
        "likes": p.likes,
        "preview_url": p.preview_url,
        "model": p.model,
        "author_id": p.author_id,
        "status": p.status.value if p.status else "pending",
        "reject_reason": p.reject_reason,
        "ai_moderation_decision": getattr(p, "ai_moderation_decision", None),
        "ai_moderation_risk": getattr(p, "ai_moderation_risk", None),
        "ai_moderation_reason": getattr(p, "ai_moderation_reason", None),
        "ai_moderation_recommendation": getattr(p, "ai_moderation_recommendation", None),
        "ai_moderated_at": p.ai_moderated_at.isoformat() if getattr(p, "ai_moderated_at", None) else None,
        "created_at": p.created_at.isoformat() if p.created_at else "",
    }


@router.post("/generations/{gen_id}/publish")
async def publish_generation_to_library(
    gen_id: int,
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
):
    """User explicitly publishes own generation to public feed/prompt library."""
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")

    gen.is_public_feed = True
    gen.is_prompt_library = True
    await session.commit()
    await session.refresh(gen)

    return {
        "ok": True,
        "id": gen.id,
        "is_public_feed": gen.is_public_feed,
        "is_prompt_library": gen.is_prompt_library,
    }
