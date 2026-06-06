"""Mini-app REST API — generation endpoints for the Telegram WebApp frontend."""
from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import math
import re
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import httpx
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import LabeledPrice
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import Date, String, cast, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api import image_service, midjourney_service, video_service
from api.assistant_service import generate_assistant_reply, generate_prompt_moderation_decision
from api.image_service import ImageModel, normalize_quality_for_aspect_ratio
from api.midjourney_service import MJDimensions, MJVideoMotion
from api.miniapp_auth import create_web_auth_token, get_miniapp_user, verify_telegram_login_data
from api.photo_prompt_service import generate_prompt_from_photo
from api.public_files import public_url_is_available
from api.video_service import VideoModel
from bot.keyboards.models import IMAGE_CAPS, VIDEO_CAPS, _IMAGE_MODEL_ORDER, _VIDEO_MODEL_ORDER
from bot.utils.deep_links import build_start_payload
from core.config import settings
from core.gemini_omni import (
    GEMINI_OMNI_MAX_AUDIO_IDS,
    GEMINI_OMNI_MAX_CHARACTER_IDS,
    GEMINI_OMNI_VIDEO_MODEL,
    normalize_gemini_omni_ids,
    normalize_gemini_omni_resolution,
    normalize_gemini_omni_seed,
    validate_gemini_omni_media_slots,
)
from db import repository as repo
from db.models import (
    CreditLedgerEntry,
    Generation,
    GenerationStatus,
    GenerationType,
    ImageGenerationAction,
    PaymentProvider,
    PromptStatus,
    ReferralWithdrawalRequest,
    Transaction,
    TransactionStatus,
    User,
    UserPrompt,
    WithdrawalStatus,
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
MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PHOTO_PROMPT_BYTES = 20 * 1024 * 1024
MAX_REFERENCE_REDIRECTS = 3

_TELEGRAM_STARS_RUB_PER_STAR = 10.5

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


def _is_prompt_public_approved(prompt: Any | None) -> bool:
    return bool(
        prompt
        and getattr(prompt, "status", None) == PromptStatus.approved
        and getattr(prompt, "is_public", False)
    )


def _can_view_prompt(prompt: Any | None, user: User | None) -> bool:
    if not prompt:
        return False
    if _is_prompt_public_approved(prompt):
        return True
    if user and getattr(prompt, "author_id", None) == getattr(user, "id", None):
        return True
    return _is_admin_user(user)


def _generation_prompt_hidden(gen: Any) -> bool:
    return bool(getattr(gen, "source_feed_gen_id", None))


def _is_midjourney_model(model_key: str) -> bool:
    return model_key in _MJ_ALL_MODELS

def _telegram_bot_username() -> str:
    return str(getattr(settings, "BOT_USERNAME", "") or "").strip().lstrip("@")


def _telegram_start_link(start_param: str) -> str:
    username = _telegram_bot_username()
    if not username:
        return ""
    return f"https://t.me/{username}?start={start_param}"


def _withdrawal_out(item: Any) -> "ReferralWithdrawalOut":
    status = getattr(getattr(item, "status", None), "value", None) or str(getattr(item, "status", "pending"))
    created_at = getattr(item, "created_at", None)
    return ReferralWithdrawalOut(
        id=int(getattr(item, "id", 0) or 0),
        amount_rub=float(getattr(item, "amount_rub", 0) or 0),
        payout_details=str(getattr(item, "payout_details", "") or ""),
        status=status,
        created_at=created_at.isoformat() if created_at else "",
    )


def _feed_card_out(card: Any, user: User) -> dict:
    generation = card.generation
    result_urls = _generation_result_urls(generation)
    gen_type = getattr(generation, "gen_type", "image")
    return {
        "id": generation.id,
        "model": generation.model,
        "gen_type": getattr(gen_type, "value", gen_type),
        "result_url": (result_urls[0] if result_urls else _generation_primary_result_url(generation)) or "",
        "result_urls": result_urls,
        "likes_count": generation.likes_count,
        "shares_count": generation.shares_count,
        "aspect_ratio": card.aspect_ratio,
        "author": card.username or card.full_name or "anon",
        "author_photo_url": getattr(card, "author_photo_url", None),
        "is_mine": generation.user_id == user.id,
        "remixes": card.remix_count,
        "score": getattr(card, "score", 0),
    }


async def _mark_prompt_used_after_generation(
    session: AsyncSession,
    *,
    prompt_id: int | None,
    user_id: int,
    credits_spent: float,
) -> None:
    if prompt_id is None:
        return
    try:
        from db.prompt_repository import use_prompt
        await use_prompt(session, prompt_id, user_id, credits_spent=int(credits_spent))
    except Exception as exc:
        logger.warning(
            "Failed to mark prompt used after generation prompt=%s user=%s: %s",
            prompt_id,
            user_id,
            exc,
        )


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
        result_urls: list[str] | None = None
        if gen.gen_type == GenerationType.image:
            if gen.model in _MIDJOURNEY_IMAGE_MODEL_KEYS:
                result_url = await midjourney_service.poll_mj_image(task_id)
            else:
                result_urls = await image_service.poll_kieai_result_urls(task_id)
                result_url = result_urls[0] if result_urls else None
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
        await repo.finish_generation(session, gen.id, result_url, result_urls=result_urls)
        if gen.image_session_id:
            await repo.update_image_session_last_result(session, gen.image_session_id, result_url, gen.id)
        return await repo.get_generation_by_id(session, gen.id)

    if age >= STALE_GENERATION_TIMEOUT:
        logger.warning(
            'Marking stale generation with unfinished task as failed: gen=%s model=%s task=%s age=%s',
            gen.id, gen.model, task_id, age,
        )
        if await repo.fail_generation(session, gen.id, 'Generation timed out before completion'):
            if gen.credits_spent:
                await repo.add_credits(session, gen.user_id, gen.credits_spent)
        return await repo.get_generation_by_id(session, gen.id)

    return gen


async def _finish_direct_image_result(session: AsyncSession, gen, result):
    result_urls = list(getattr(result, "result_urls", None) or [])
    result_url = getattr(result, "url", None)
    if result_url and result_url not in result_urls:
        result_urls.insert(0, result_url)
    result_urls = [url for url in result_urls if url]
    if not result_urls:
        raise RuntimeError("CometAPI image fallback returned no result URL")

    await repo.update_generation_task(session, gen.id, getattr(result, "task_id", None) or "comet:image:direct")
    await repo.finish_generation(session, gen.id, result_urls[0], result_urls=result_urls)
    if gen.image_session_id:
        await repo.update_image_session_last_result(session, gen.image_session_id, result_urls[0], gen.id)
    return await repo.get_generation_by_id(session, gen.id)


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


def _is_supported_reference_image(data: bytes, content_type: str | None) -> bool:
    content = (content_type or "").lower()
    if content and not content.startswith("image/"):
        return False
    return (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data.startswith(b"RIFF") and b"WEBP" in data[:16])
    )


def _url_has_safe_public_shape(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.hostname:
        return False

    host = parsed.hostname.strip("[]").lower()
    if host == "localhost" or host.endswith(".localhost"):
        return False

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


async def _resolve_public_host(hostname: str, port: int | None) -> None:
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo,
            hostname,
            port,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="Reference URL host cannot be resolved") from exc

    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            raise HTTPException(status_code=422, detail="Reference URL host resolved to an invalid address")
        if not ip.is_global:
            raise HTTPException(status_code=422, detail="Reference URL host is not public")


async def _validate_fetchable_public_url(url: str) -> None:
    if not _url_has_safe_public_shape(url):
        raise HTTPException(status_code=422, detail="Reference URL must be a public HTTP(S) URL")
    parsed = urlparse(url)
    await _resolve_public_host(parsed.hostname or "", parsed.port)


async def _data_uri_from_url(url: str) -> str:
    current_url = url
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(MAX_REFERENCE_REDIRECTS + 1):
                await _validate_fetchable_public_url(current_url)
                async with client.stream("GET", current_url, follow_redirects=False) as resp:
                    if 300 <= resp.status_code < 400:
                        location = resp.headers.get("location")
                        if not location:
                            raise HTTPException(status_code=422, detail="Reference URL redirect has no location")
                        current_url = urljoin(str(resp.url), location)
                        continue

                    resp.raise_for_status()
                    content_type = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    if not content_type.startswith("image/"):
                        raise HTTPException(status_code=422, detail="Reference URL must point to an image")

                    content_length = resp.headers.get("content-length")
                    if content_length and int(content_length) > MAX_REFERENCE_IMAGE_BYTES:
                        raise HTTPException(status_code=413, detail="Reference image is too large")

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_REFERENCE_IMAGE_BYTES:
                            raise HTTPException(status_code=413, detail="Reference image is too large")
                        chunks.append(chunk)

                    data = b"".join(chunks)
                    if not _is_supported_reference_image(data, content_type):
                        raise HTTPException(status_code=422, detail="Reference URL must point to a JPEG, PNG or WebP image")
                    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"
            raise HTTPException(status_code=422, detail="Reference URL has too many redirects")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to fetch reference image: {exc}") from exc


def _mj_catalog_item(mc: Any) -> MidjourneyCatalogItem:
    raw_gen_type = getattr(mc, "gen_type", None)
    gen_type = getattr(raw_gen_type, "value", raw_gen_type)
    if not gen_type:
        gen_type = "video" if mc.model_key in _MJ_VIDEO_MODELS else "image"
    return MidjourneyCatalogItem(
        key=mc.model_key,
        display_name=_friendly_model_name(mc.model_key, mc.display_name),
        credits=float(mc.credits),
        gen_type=str(gen_type),
        available_in_studio=mc.model_key in (_MJ_STUDIO_IMAGE_MODELS | _MJ_VIDEO_MODELS),
    )


def _normalize_public_urls(*urls: str | None) -> list[str]:
    normalized: list[str] = []
    for raw in urls:
        if not raw:
            continue
        if raw.startswith("blob:") or not _url_has_safe_public_shape(raw):
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
    if model_key == GEMINI_OMNI_VIDEO_MODEL:
        try:
            return normalize_gemini_omni_resolution(resolution)
        except ValueError:
            return resolution
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
    video_url: str | None = None,
    video_start: float | None = None,
    video_end: float | None = None,
    audio_ids: list[str] | None = None,
    character_ids: list[str] | None = None,
    seed: int | None = None,
    grok_mode: str | None = None,
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

    normalized_video_url: str | None = None
    if video_url:
        if "video" not in supported_modes:
            raise HTTPException(status_code=422, detail="Selected model does not support video input")
        video_urls = _normalize_public_urls(video_url)
        normalized_video_url = video_urls[0] if video_urls else None
    if normalized_mode == "video" and not normalized_video_url:
        raise HTTPException(status_code=422, detail="Selected mode requires video_url")

    duration_input = None if model_key == GEMINI_OMNI_VIDEO_MODEL and duration == 5 else duration
    normalized_duration = _normalize_int_choice(
        duration_input,
        caps.get("duration_options", []),
        field_name="duration",
        default=None if model_key == GEMINI_OMNI_VIDEO_MODEL else duration,
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

    normalized_audio_ids: list[str] = []
    normalized_character_ids: list[str] = []
    normalized_seed: int | None = None
    if model_key == GEMINI_OMNI_VIDEO_MODEL:
        try:
            normalized_audio_ids = normalize_gemini_omni_ids(
                audio_ids,
                max_items=GEMINI_OMNI_MAX_AUDIO_IDS,
                field_name="audio_ids",
            )
            normalized_character_ids = normalize_gemini_omni_ids(
                character_ids,
                max_items=GEMINI_OMNI_MAX_CHARACTER_IDS,
                field_name="character_ids",
            )
            normalized_seed = normalize_gemini_omni_seed(seed)
            validate_gemini_omni_media_slots(
                image_count=len(all_refs),
                video_count=1 if normalized_video_url else 0,
                character_count=len(normalized_character_ids),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    elif audio_ids or character_ids or seed is not None or normalized_video_url:
        raise HTTPException(status_code=422, detail="Gemini Omni extras are not supported by selected model")

    start = float(video_start or 0)
    end = video_end
    if normalized_video_url:
        end = float(end if end is not None else min(normalized_duration or 10, 10))
        if end <= start:
            raise HTTPException(status_code=422, detail="video_end must be greater than video_start")
        if end - start > 10:
            raise HTTPException(status_code=422, detail="Gemini Omni video trim must be 10 seconds or shorter")

    return {
        "mode": normalized_mode,
        "duration": normalized_duration,
        "aspect_ratio": normalized_aspect_ratio,
        "resolution": normalized_resolution,
        "image_url": normalized_image_url,
        "reference_video_url": normalized_video_url,
        "video_start": start if normalized_video_url else None,
        "video_end": end if normalized_video_url else None,
        "audio_ids": normalized_audio_ids,
        "character_ids": normalized_character_ids,
        "seed": normalized_seed,
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
    photo_url: str | None = None
    credits: float
    referral_code: str
    referral_link: str
    referral_balance: float
    referral_withdraw_min_rub: float
    language: str = "ru"


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
    aspect_ratio_modes: list[str] = Field(default_factory=list)
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
    supports_video_input: bool = False
    max_audio_ids: int = 0
    max_character_ids: int = 0
    has_seed: bool = False
    video_input_prices: dict[str, float] = Field(default_factory=dict)
    price_table: dict[str, dict[int, float]] = Field(default_factory=dict)


class GenerationOut(BaseModel):
    id: int
    model: str
    gen_type: str
    prompt: str
    prompt_hidden: bool = False
    prompt_actions_allowed: bool = True
    status: str
    result_url: str | None
    credits_spent: float
    created_at: str
    is_public_feed: bool = False
    is_prompt_library: bool = False
    result_urls: list[str] = Field(default_factory=list)


class ImageGenRequest(BaseModel):
    model: str
    prompt: str = Field(..., min_length=1, max_length=4000)
    prompt_id: int | None = None
    aspect_ratio: str | None = None
    quality: str = "basic"
    count: int = Field(default=1, ge=1, le=6)
    reference_url: str | None = None
    reference_urls: list[str] = []


class VideoGenRequest(BaseModel):
    model: str
    prompt: str = Field(..., min_length=1, max_length=4000)
    mode: str = "text"                    # "text" | "image" | "video"
    duration: int = Field(default=5, ge=2, le=30)
    aspect_ratio: str | None = None
    resolution: str | None = None
    image_url: str | None = None
    reference_urls: list[str] = []
    video_url: str | None = None
    video_start: float = Field(default=0, ge=0)
    video_end: float | None = None
    audio_ids: list[str] = []
    character_ids: list[str] = []
    seed: int | None = None
    grok_mode: str = "normal"


class FeedRemixRequest(BaseModel):
    model: str
    mode: str = "text"                    # "text" | "image"
    duration: int = Field(default=5, ge=2, le=30)
    aspect_ratio: str | None = None
    resolution: str | None = None
    image_url: str | None = None
    reference_urls: list[str] = []
    video_url: str | None = None
    video_start: float = Field(default=0, ge=0)
    video_end: float | None = None
    audio_ids: list[str] = []
    character_ids: list[str] = []
    seed: int | None = None
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


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    history: list[dict[str, str]] = Field(default_factory=list)


class AssistantChatResponse(BaseModel):
    reply: str


class LanguageRequest(BaseModel):
    language: str = Field(..., pattern="^(ru|en)$")


class ProfilePhotoRequest(BaseModel):
    photo_url: str | None = Field(default=None, max_length=2048)


class ReferralChildOut(BaseModel):
    id: int
    username: str | None
    full_name: str | None
    generations_count: int
    paid_rub: float


class ReferralWithdrawalOut(BaseModel):
    id: int
    amount_rub: float
    payout_details: str
    status: str
    created_at: str


class ReferralStatsOut(BaseModel):
    referral_code: str
    referral_link: str
    bonus_l1_credits: float
    commission_l1: float
    commission_l2: float
    commission_l3: float
    withdraw_min_rub: float
    counts: dict[str, int]
    balance: dict[str, float]
    feed_remix_reward_rub: float
    children: dict[str, list[ReferralChildOut]]
    withdrawals: list[ReferralWithdrawalOut]


class ReferralWithdrawalRequestIn(BaseModel):
    amount_rub: float = Field(..., gt=0)
    payout_details: str = Field(..., min_length=5, max_length=500)


class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


# ── user ─────────────────────────────────────────────────────────────────────

def _user_profile(user: User) -> UserProfile:
    return UserProfile(
        id=user.id,
        tg_id=user.tg_id,
        username=user.username,
        full_name=user.full_name,
        photo_url=getattr(user, "photo_url", None),
        credits=user.credits,
        referral_code=user.referral_code,
        referral_link=_telegram_start_link(user.referral_code),
        referral_balance=user.referral_balance,
        referral_withdraw_min_rub=settings.REFERRAL_WITHDRAW_MIN_RUB,
        language=getattr(user, "language", "ru") or "ru",
    )


@router.get("/auth/config")
async def web_auth_config() -> dict[str, str]:
    """Public auth config for the standalone website."""
    return {"bot_username": _telegram_bot_username()}


@router.post("/auth/telegram-login")
async def web_telegram_login(
    body: TelegramLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Login for the standalone website via Telegram Login Widget."""
    payload = body.model_dump()
    tg_user = verify_telegram_login_data(payload)
    first_name = str(tg_user.get("first_name") or "").strip()
    last_name = str(tg_user.get("last_name") or "").strip()
    full_name = " ".join(part for part in (first_name, last_name) if part).strip() or None
    username = str(tg_user.get("username") or "").strip() or None

    user = await repo.get_user_by_tg_id(session, int(tg_user["id"]))
    if not user:
        user = await repo.create_user(
            session,
            tg_id=int(tg_user["id"]),
            username=username,
            full_name=full_name,
            welcome_credits=settings.WELCOME_BONUS_CREDITS,
        )
    if user.is_banned:
        raise HTTPException(status_code=403, detail="User is banned")

    return {
        "token": create_web_auth_token(user.tg_id),
        "token_type": "web",
        "expires_in": 30 * 24 * 60 * 60,
        "user": _user_profile(user).model_dump(),
    }


@router.get("/me", response_model=UserProfile)
async def get_me(user: User = Depends(get_miniapp_user)) -> UserProfile:
    """Current user profile with balance."""
    return _user_profile(user)


@router.get("/me/feed")
async def get_my_feed(
    limit: int = 200,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[dict]:
    """Current user's public image feed posts."""
    cards = await repo.get_user_feed_generations(session, user.id, limit=max(1, min(limit, 500)))
    return [_feed_card_out(card, user) for card in cards]


@router.post("/me/photo", response_model=UserProfile)
async def set_me_photo(
    body: ProfilePhotoRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> UserProfile:
    """Save a profile photo uploaded by the current user."""
    photo_url = (body.photo_url or "").strip() or None
    if photo_url and (not photo_url.startswith("http") or not public_url_is_available(photo_url)):
        raise HTTPException(status_code=422, detail="Invalid profile photo URL")
    updated = await repo.set_user_photo_url(session, user.id, photo_url)
    return _user_profile(updated or user)


@router.post("/assistant", response_model=AssistantChatResponse)
async def miniapp_assistant(
    body: AssistantChatRequest,
    user: User = Depends(get_miniapp_user),
) -> AssistantChatResponse:
    """Assistant chat inside the mini app, backed by the same assistant as the bot."""
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="Message cannot be empty")

    history: list[dict[str, str]] = []
    for item in body.history[-10:]:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            history.append({"role": role, "content": content[:4000]})
    history.append({"role": "user", "content": message})

    try:
        reply = await generate_assistant_reply(history, admin_mode=_is_admin_user(user))
    except Exception as exc:  # pragma: no cover - external LLM/network failure
        logger.exception("Mini-app assistant failed: %s", exc)
        raise HTTPException(status_code=502, detail="Assistant service error") from exc
    return AssistantChatResponse(reply=reply)


@router.post("/settings/language")
async def miniapp_set_language(
    body: LanguageRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, str]:
    await repo.set_user_language(session, user.id, body.language)
    return {"language": body.language}


@router.get("/referrals", response_model=ReferralStatsOut)
async def miniapp_referrals(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> ReferralStatsOut:
    l1, l2, l3 = await repo.count_user_referrals(session, user.id)
    snapshot = await repo.get_user_referral_balance_snapshot(session, user.id)
    feed_reward = await repo.get_user_feed_remix_reward_rub(session, user.id)
    withdrawals = await repo.get_user_withdrawal_requests(session, user.id, limit=10)

    children: dict[str, list[ReferralChildOut]] = {}
    for level in (1, 2, 3):
        rows = await repo.get_referral_children(session, user.id, level=level, limit=10)
        children[f"l{level}"] = [
            ReferralChildOut(
                id=row.user.id,
                username=row.user.username,
                full_name=row.user.full_name,
                generations_count=row.generations_count,
                paid_rub=row.paid_rub,
            )
            for row in rows
        ]

    total = float(snapshot.total_earned if snapshot else getattr(user, "referral_balance", 0) or 0)
    pending = float(snapshot.pending_withdrawals if snapshot else 0)
    available = float(snapshot.available_to_withdraw if snapshot else total)
    return ReferralStatsOut(
        referral_code=user.referral_code,
        referral_link=_telegram_start_link(user.referral_code),
        bonus_l1_credits=float(settings.REFERRAL_L1_CREDITS),
        commission_l1=float(settings.REFERRAL_COMMISSION_L1),
        commission_l2=float(settings.REFERRAL_COMMISSION_L2),
        commission_l3=float(settings.REFERRAL_COMMISSION_L3),
        withdraw_min_rub=float(settings.REFERRAL_WITHDRAW_MIN_RUB),
        counts={"l1": l1, "l2": l2, "l3": l3},
        balance={
            "total_earned": total,
            "pending_withdrawals": pending,
            "available_to_withdraw": available,
        },
        feed_remix_reward_rub=float(feed_reward or 0),
        children=children,
        withdrawals=[_withdrawal_out(item) for item in withdrawals],
    )


@router.post("/referrals/withdrawals", response_model=ReferralWithdrawalOut, status_code=201)
async def miniapp_create_referral_withdrawal(
    body: ReferralWithdrawalRequestIn,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> ReferralWithdrawalOut:
    min_amount = float(settings.REFERRAL_WITHDRAW_MIN_RUB)
    if body.amount_rub < min_amount:
        raise HTTPException(status_code=422, detail=f"Минимальная сумма вывода — {min_amount:.0f}₽")
    try:
        item = await repo.create_withdrawal_request(
            session,
            user_id=user.id,
            amount_rub=body.amount_rub,
            payout_details=body.payout_details.strip(),
        )
    except repo.InsufficientReferralBalanceError as exc:
        raise HTTPException(
            status_code=402,
            detail=f"Доступно к выводу {exc.available_amount:.2f}₽",
        ) from exc

    from main import bot
    from bot.handlers.balance import withdrawal_request_admin_kb
    from bot.i18n import t

    admin_text = t(
        "withdraw_admin_notify", getattr(user, "language", "ru") or "ru",
        id=item.id,
        username=user.username or "—",
        tg_id=user.tg_id,
        full_name=user.full_name or "—",
        amount=float(item.amount_rub),
        details=item.payout_details,
    )
    if bot:
        for admin_id in settings.ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    admin_text,
                    reply_markup=withdrawal_request_admin_kb(item.id),
                )
            except (TelegramBadRequest, TelegramForbiddenError, Exception):
                continue

    return _withdrawal_out(item)


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
    if len(data) > MAX_PHOTO_PROMPT_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 20 MB)")

    mime = file.content_type or "image/jpeg"
    if not _is_supported_reference_image(data, mime):
        raise HTTPException(status_code=422, detail="Only JPEG, PNG and WebP images are supported")

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


@router.get("/help")
async def miniapp_help(
    topic: str = Query(default="main", pattern="^(main|stars)$"),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Help texts from the Telegram bot, exposed for the Mini App."""
    from bot.handlers.start import _help_text, _stars_help_text

    lang = getattr(user, "language", "ru") or "ru"
    text = _stars_help_text(lang) if topic == "stars" else _help_text(lang)
    return {"topic": topic, "language": lang, "text": text}


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
        caps: dict[str, Any] = IMAGE_CAPS.get(mc.model_key, _MJ_IMAGE_CAPS.get(mc.model_key, {}))
        quality_raw = caps.get("quality_options", [])
        quality_prices = await _resolve_image_quality_prices(session, mc.model_key, quality_raw, float(mc.credits))
        result.append(ModelInfo(
            key=mc.model_key,
            display_name=_friendly_model_name(mc.model_key, mc.display_name),
            credits=mc.credits,
            modes=caps.get("modes", ["text"]),
            aspect_ratios=caps.get("aspect_ratios", []),
            aspect_ratio_modes=caps.get("aspect_ratio_modes", caps.get("modes", ["text"])),
            aspect_ratio_min_refs=int(caps.get("aspect_ratio_min_refs", 0) or 0),
            quality_options=[{"value": value, "label": label} for value, label in quality_raw],
            quality_prices=quality_prices,
            counts=caps.get("counts", [1]),
            has_quality=bool(caps.get("has_quality")),
            max_refs=int(caps.get("max_refs", 1) or 1),
        ))
    order = {key: idx for idx, key in enumerate(_IMAGE_MODEL_ORDER)}
    return sorted(result, key=lambda item: (order.get(item.key, 10_000), item.display_name.lower()))


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
        caps: dict[str, Any] = VIDEO_CAPS.get(mc.model_key, _MJ_VIDEO_CAPS.get(mc.model_key, {}))
        is_per_sec, credits_per_sec = await _video_model_rate_info(session, mc.model_key, caps, mc.credits)
        result.append(ModelInfo(
            key=mc.model_key,
            display_name=_friendly_model_name(mc.model_key, mc.display_name),
            credits=credits_per_sec if is_per_sec and credits_per_sec is not None else mc.credits,
            modes=caps.get("modes", ["text"]),
            aspect_ratios=caps.get("aspect_ratios", []),
            aspect_ratio_modes=caps.get("aspect_ratio_modes", caps.get("modes", ["text"])),
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
            supports_video_input=bool(caps.get("supports_video_input")),
            max_audio_ids=int(caps.get("max_audio_ids", 0) or 0),
            max_character_ids=int(caps.get("max_character_ids", 0) or 0),
            has_seed=bool(caps.get("has_seed")),
            video_input_prices={str(k): float(v) for k, v in (caps.get("video_input_prices") or {}).items()},
            price_table={
                str(res): {int(duration): float(price) for duration, price in prices.items()}
                for res, prices in (caps.get("price_table") or {}).items()
            },
        ))
    order = {key: idx for idx, key in enumerate(_VIDEO_MODEL_ORDER)}
    return sorted(result, key=lambda item: (order.get(item.key, 10_000), item.display_name.lower()))


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
    model_costs = await repo.get_all_model_costs(session)
    return [
        _mj_catalog_item(mc)
        for mc in model_costs
        if _is_midjourney_model(mc.model_key) and getattr(mc, "is_active", True)
    ]


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
    effective_prompt = body.prompt.strip()
    prompt_source = None
    if body.prompt_id is not None:
        from db.prompt_repository import get_prompt_by_id

        prompt_source = await get_prompt_by_id(session, body.prompt_id)
        if not _is_prompt_public_approved(prompt_source):
            raise HTTPException(status_code=404, detail="Prompt not found or not public")
        effective_prompt = prompt_source.prompt_text.strip()

    if body.model in _MJ_STUDIO_IMAGE_MODELS:
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
        if body.model == "midjourney-imagine" and not effective_prompt:
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
        gen_prompt = effective_prompt or f"blend:{len(all_refs)}"
        image_session = await repo.create_image_session(session=session, user_id=user.id, model=body.model, mode="image" if all_refs else "text", aspect_ratio=normalized_ratio, quality="basic", count=1, base_prompt=gen_prompt, reference_file_id=None, reference_url=all_refs[0] if all_refs else None)
        gen = await repo.create_generation(session, user.id, body.model, GenerationType.image, gen_prompt, model_cost.credits, image_session_id=image_session.id, action_type=ImageGenerationAction.initial)
        try:
            if body.model == "midjourney-imagine":
                submitted_prompt = f"{all_refs[0]} {effective_prompt}".strip() if all_refs else effective_prompt
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
        await _mark_prompt_used_after_generation(
            session,
            prompt_id=getattr(prompt_source, "id", None),
            user_id=user.id,
            credits_spent=model_cost.credits,
        )
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
        base_prompt=effective_prompt,
        reference_file_id=None,
        reference_url=all_refs[0] if all_refs else None,
    )

    gen = await repo.create_generation(
        session, user.id, body.model, GenerationType.image,
        effective_prompt, model_cost.credits,
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
            effective_prompt,
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

    if not getattr(result, "is_async", True):
        gen = await _finish_direct_image_result(session, gen, result)
    else:
        await repo.update_generation_task(session, gen.id, result.task_id or "")
    await repo.update_image_session_last_prompt(session, image_session.id, effective_prompt)
    await _mark_prompt_used_after_generation(
        session,
        prompt_id=getattr(prompt_source, "id", None),
        user_id=user.id,
        credits_spent=model_cost.credits,
    )

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
        video_url=body.video_url,
        video_start=body.video_start,
        video_end=body.video_end,
        audio_ids=body.audio_ids,
        character_ids=body.character_ids,
        seed=body.seed,
        grok_mode=body.grok_mode,
    )
    has_gemini_omni_video_input = body.model == GEMINI_OMNI_VIDEO_MODEL and bool(normalized["reference_video_url"])
    model_cost = await repo.resolve_video_model_cost(
        session,
        body.model,
        duration=None if has_gemini_omni_video_input else normalized["duration"],
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
            reference_video_url=normalized["reference_video_url"],
            grok_mode=normalized["grok_mode"],
            audio_ids=normalized["audio_ids"],
            character_ids=normalized["character_ids"],
            video_start=normalized["video_start"],
            video_end=normalized["video_end"],
            seed=normalized["seed"],
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
    source: str = Query(default="recent", pattern="^(recent|top_day|top)$"),
    limit: int = Query(default=40, ge=1, le=300),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[dict]:
    """Public image feed — prompt is hidden from non-authors."""
    if source == "top_day":
        cards = await repo.get_top_day_generations(session, limit=limit)
    else:
        cards = await repo.get_feed_generations(session, limit=limit)
    return [_feed_card_out(c, user) for c in cards]


@router.post("/generations/{gen_id}/share", status_code=200)
async def share_generation(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Publish own generation to the public feed and return its repost link."""
    existing = await repo.get_generation_by_id(session, gen_id)
    if not existing or existing.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if _generation_prompt_hidden(existing):
        raise HTTPException(status_code=403, detail="Cannot publish a feed remix")

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

    user_refs = _normalize_public_urls(body.image_url, *(body.reference_urls or []))
    source_refs = _normalize_public_urls(source.result_url) if body.mode == "image" else []

    if body.model in (_MJ_STUDIO_IMAGE_MODELS | _MJ_VIDEO_MODELS):
        source_prompt = (source.prompt or "").strip()
        model_cost = await repo.get_model_cost(session, body.model)
        if not model_cost or not getattr(model_cost, "is_active", True):
            raise HTTPException(status_code=422, detail="Model not available")

        caps: dict[str, Any] = _MJ_IMAGE_CAPS.get(body.model, {})
        gen_type = "video" if body.model in _MJ_VIDEO_MODELS else "image"
        normalized_ratio: str | None = None
        normalized_quality = "basic"
        refs: list[str] = []
        motion_value = "low"

        if body.model == "midjourney-imagine":
            refs = user_refs or source_refs
            max_refs = int(caps.get("max_refs", 1) or 1)
            if len(refs) > max_refs:
                raise HTTPException(status_code=422, detail=f"Model supports at most {max_refs} reference image(s)")
            normalized_ratio = _normalize_choice(body.aspect_ratio, caps.get("aspect_ratios", []), field_name="aspect ratio")
            if not source_prompt:
                raise HTTPException(status_code=422, detail="Prompt is required")
        elif body.model == "midjourney-blend":
            refs = (source_refs + user_refs) if source_refs else user_refs
            max_refs = int(caps.get("max_refs", 5) or 5)
            if len(refs) < 2:
                raise HTTPException(status_code=422, detail="Blend requires at least 2 reference images")
            if len(refs) > max_refs:
                raise HTTPException(status_code=422, detail=f"Model supports at most {max_refs} reference image(s)")
            normalized_ratio = _normalize_choice(body.aspect_ratio, caps.get("aspect_ratios", []), field_name="aspect ratio")
        else:
            video_refs = user_refs or source_refs
            max_refs = int(_MJ_VIDEO_CAPS.get(body.model, {}).get("max_refs", 1) or 1)
            if not video_refs:
                raise HTTPException(status_code=422, detail="Midjourney Video requires a reference image")
            if len(video_refs) > max_refs:
                raise HTTPException(status_code=422, detail=f"Model supports at most {max_refs} reference image(s)")
            refs = video_refs
            motion_value = body.grok_mode if body.grok_mode in {"low", "high"} else "low"

        total_credits = model_cost.credits
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
                mode="image" if refs else "text",
                aspect_ratio=normalized_ratio,
                quality=normalized_quality,
                count=1,
                base_prompt=source_prompt,
                reference_file_id=None,
                reference_url=refs[0] if refs else None,
            )
            image_session_id = image_session.id

        from db.models import GenerationType as GT
        gen_type_enum = GT.video if gen_type == "video" else GT.image
        gen = await repo.create_generation(
            session, user.id, body.model, gen_type_enum,
            source_prompt, total_credits,
            image_session_id=image_session_id,
            parent_generation_id=source.id if gen_type == "image" else None,
            action_type=ImageGenerationAction.remix if gen_type == "image" else None,
            source_feed_gen_id=gen_id,
        )

        try:
            if body.model == "midjourney-imagine":
                submitted_prompt = f"{refs[0]} {source_prompt}".strip() if refs else source_prompt
                task_id = await midjourney_service.imagine(submitted_prompt, reference_url=refs[0] if refs else None)
            elif body.model == "midjourney-blend":
                blend_images = [await _data_uri_from_url(url) for url in refs]
                task_id = await midjourney_service.blend(
                    blend_images,
                    dimensions=MJDimensions(_MJ_BLEND_DIMENSIONS.get(normalized_ratio or "1:1", "SQUARE")),
                )
            else:
                task_id = await midjourney_service.submit_video(
                    image=refs[0],
                    motion=MJVideoMotion(motion_value),
                    prompt=source_prompt,
                )
        except Exception as exc:
            logger.error("feed Midjourney remix error user=%s gen=%s model=%s: %s", user.id, gen_id, body.model, exc)
            if await repo.fail_generation(session, gen.id, str(exc)):
                await repo.add_credits(session, user.id, total_credits)
            raise HTTPException(status_code=502, detail="Generation service error")

        await repo.update_generation_task(session, gen.id, task_id)
        await repo.increment_feed_share(session, gen_id)
        await session.refresh(gen)
        return _gen_out(gen)

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
        video_refs = user_refs or source_refs
        fallback_image_url = video_refs[0] if video_refs else None
        normalized_video = _normalize_video_request(
            model_key=body.model,
            mode=body.mode,
            duration=body.duration,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            image_url=fallback_image_url,
            reference_urls=video_refs[1:],
            video_url=body.video_url,
            video_start=body.video_start,
            video_end=body.video_end,
            audio_ids=body.audio_ids,
            character_ids=body.character_ids,
            seed=body.seed,
            grok_mode=body.grok_mode,
        )
        has_gemini_omni_video_input = (
            body.model == GEMINI_OMNI_VIDEO_MODEL
            and bool(normalized_video["reference_video_url"])
        )
        model_cost = await repo.resolve_video_model_cost(
            session,
            body.model,
            duration=None if has_gemini_omni_video_input else normalized_video["duration"],
            resolution=normalized_video["resolution"],
        )
    else:
        image_refs = user_refs or source_refs
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
                reference_video_url=normalized_video["reference_video_url"],
                grok_mode=normalized_video["grok_mode"],
                audio_ids=normalized_video["audio_ids"],
                character_ids=normalized_video["character_ids"],
                video_start=normalized_video["video_start"],
                video_end=normalized_video["video_end"],
                seed=normalized_video["seed"],
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

    if gen_type == "image" and not getattr(result, "is_async", True):
        gen = await _finish_direct_image_result(session, gen, result)
    else:
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
    """Returns a shareable Telegram deeplink for a public post using the viewer's referral code."""
    gen = await repo.increment_feed_share(session, gen_id)
    if not gen:
        raise HTTPException(status_code=404, detail="Public post not found")
    link = _telegram_start_link(build_start_payload(ref_code=user.referral_code, target_kind="feed", target_id=gen_id))
    return {"link": link, "gen_id": gen_id}


@router.post("/generations/{gen_id}/share-library", status_code=200)
async def share_to_library(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Opt this generation's prompt into the public prompt library."""
    existing = await repo.get_generation_by_id(session, gen_id)
    if not existing or existing.user_id != user.id:
        raise HTTPException(status_code=404, detail="Generation not found")
    if _generation_prompt_hidden(existing):
        raise HTTPException(status_code=403, detail="Cannot save a feed remix prompt")

    gen = await repo.share_to_library(session, gen_id, user.id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found or not ready")
    return {"id": gen.id, "is_prompt_library": gen.is_prompt_library}


@router.post("/generations/{gen_id}/remove-library", status_code=200)
async def remove_from_library(
    gen_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Remove own generation's prompt from the public prompt library."""
    gen = await repo.remove_from_library(session, gen_id, user.id)
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found in your library")
    return {"id": gen.id, "is_prompt_library": gen.is_prompt_library}


# ── prompt library ────────────────────────────────────────────────────────────

@router.get("/prompts")
async def list_prompts(
    category: str | None = Query(default=None),
    source: str = Query(default="catalog"),
    tag: str | None = Query(default=None, min_length=1, max_length=32),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_miniapp_user),
) -> dict:
    """Prompt marketplace: catalog plus bot-like top/popular/collection sources."""
    from db.models import PromptCategory
    from db.prompt_repository import (
        COLLECTION_TAGS,
        count_approved_prompts,
        get_approved_prompts,
        get_popular_prompts,
        get_prompts_by_tag,
        get_top_prompts,
    )

    cat = None
    if category:
        try:
            cat = PromptCategory(category)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown category: {category!r}")

    if source in {"top", "top_today", "best"}:
        prompts = await get_top_prompts(session, limit=limit)
        total = len(prompts)
    elif source in {"popular", "trending"}:
        prompts = await get_popular_prompts(session, limit=limit)
        total = len(prompts)
    elif source == "tag":
        prompts = await get_prompts_by_tag(session, tag or "best", limit=limit)
        total = len(prompts)
    elif source == "collections":
        return {
            "total": len(COLLECTION_TAGS),
            "page": page,
            "limit": limit,
            "items": [
                {"key": key, "title": title, "source": "tag", "tag": key}
                for key, title in COLLECTION_TAGS.items()
            ],
        }
    else:
        prompts = await get_approved_prompts(session, category=cat, limit=limit, offset=(page - 1) * limit)
        total = await count_approved_prompts(session, category=cat)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [_prompt_out(p) for p in prompts],
    }


@router.get("/prompts/my")
async def my_prompts(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Prompts submitted by the current user, including moderation status."""
    from db.prompt_repository import get_author_prompts, get_author_total_uses

    prompts = await get_author_prompts(session, user.id)
    return {
        "total": len(prompts),
        "total_uses": await get_author_total_uses(session, user.id),
        "items": [_prompt_out(p) for p in prompts],
    }


@router.get("/prompts/{prompt_id}")
async def get_prompt(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    from db.prompt_repository import get_prompt_by_id

    p = await get_prompt_by_id(session, prompt_id)
    if not _can_view_prompt(p, user):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return _prompt_out(p)


@router.post("/prompts/{prompt_id}/like")
async def like_prompt_web(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    from db.prompt_repository import get_prompt_by_id, like_prompt

    current = await get_prompt_by_id(session, prompt_id)
    if not _is_prompt_public_approved(current):
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt, like_status = await like_prompt(session, prompt_id, user.id)
    if like_status == "duplicate":
        current = await get_prompt_by_id(session, prompt_id)
        if not _is_prompt_public_approved(current):
            raise HTTPException(status_code=404, detail="Prompt not found")
        return {"status": "duplicate", "likes": current.likes}
    if like_status == "missing" or not _is_prompt_public_approved(prompt):
        raise HTTPException(status_code=404, detail="Prompt not found")
    return {"status": "liked", "likes": prompt.likes}


@router.get("/prompts/{prompt_id}/link")
async def get_prompt_share_link(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    from db.prompt_repository import get_prompt_by_id

    prompt = await get_prompt_by_id(session, prompt_id)
    if not _is_prompt_public_approved(prompt):
        raise HTTPException(status_code=404, detail="Prompt not found")
    link = _telegram_start_link(build_start_payload(ref_code=user.referral_code, target_kind="prompt", target_id=prompt_id))
    return {"link": link, "prompt_id": prompt_id}


@router.post("/prompts/{prompt_id}/use")
async def use_prompt_web(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Mark a prompt as used when it is loaded into the web studio."""
    from db.prompt_repository import use_prompt

    try:
        prompt, rewards = await use_prompt(session, prompt_id, user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Prompt not found or not public") from exc
    return {"prompt": _prompt_out(prompt), "rewards": rewards}


@router.post("/prompts/{prompt_id}/deactivate")
async def deactivate_prompt_web(
    prompt_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    from db.prompt_repository import deactivate_prompt, get_prompt_by_id

    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.author_id != user.id:
        raise HTTPException(status_code=404, detail="Prompt not found")
    prompt = await deactivate_prompt(session, prompt_id)
    return _prompt_out(prompt)


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



class AdminCreditsRequest(BaseModel):
    amount: float
    note: str | None = None


class AdminBanRequest(BaseModel):
    banned: bool


class AdminWithdrawalReviewRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    note: str | None = None


def _admin_guard(user: User | None) -> None:
    if not _is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required")


def _admin_iso(value: Any) -> str:
    return value.isoformat() if value else ""


def _admin_series(rows: list[tuple[Any, Any]], labels: list[str]) -> list[dict[str, Any]]:
    mapping = {str(day): float(value or 0) for day, value in rows}
    return [{"date": label, "value": mapping.get(label, 0)} for label in labels]


@router.get("/admin/overview")
async def admin_overview(
    days: int = Query(default=14, ge=7, le=60),
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _admin_guard(user)

    today = datetime.now(timezone.utc).date()
    since_day = today - timedelta(days=days - 1)
    since_dt = datetime.combine(since_day, datetime.min.time(), tzinfo=timezone.utc)
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    labels = [str(since_day + timedelta(days=i)) for i in range(days)]

    users_total = int((await session.execute(select(func.count(User.id)))).scalar() or 0)
    users_new_7d = int((await session.execute(select(func.count(User.id)).where(User.created_at >= seven_days_ago))).scalar() or 0)
    paid_users = int((await session.execute(select(func.count(func.distinct(Transaction.user_id))).where(Transaction.status == TransactionStatus.paid))).scalar() or 0)
    revenue_total = float((await session.execute(select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(Transaction.status == TransactionStatus.paid))).scalar() or 0)
    revenue_7d = float((await session.execute(select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(Transaction.status == TransactionStatus.paid, Transaction.created_at >= seven_days_ago))).scalar() or 0)
    generations_total = int((await session.execute(select(func.count(Generation.id)))).scalar() or 0)
    generations_7d = int((await session.execute(select(func.count(Generation.id)).where(Generation.created_at >= seven_days_ago))).scalar() or 0)
    image_7d = int((await session.execute(select(func.count(Generation.id)).where(Generation.created_at >= seven_days_ago, Generation.gen_type == GenerationType.image))).scalar() or 0)
    video_7d = int((await session.execute(select(func.count(Generation.id)).where(Generation.created_at >= seven_days_ago, Generation.gen_type == GenerationType.video))).scalar() or 0)
    music_7d = int((await session.execute(select(func.count(Generation.id)).where(Generation.created_at >= seven_days_ago, Generation.gen_type == GenerationType.music))).scalar() or 0)
    done_7d = int((await session.execute(select(func.count(Generation.id)).where(Generation.created_at >= seven_days_ago, Generation.status == GenerationStatus.done))).scalar() or 0)
    failed_7d = int((await session.execute(select(func.count(Generation.id)).where(Generation.created_at >= seven_days_ago, Generation.status == GenerationStatus.failed))).scalar() or 0)
    pending_withdrawals_count = int((await session.execute(select(func.count(ReferralWithdrawalRequest.id)).where(ReferralWithdrawalRequest.status == WithdrawalStatus.pending))).scalar() or 0)
    pending_withdrawals_amount = float((await session.execute(select(func.coalesce(func.sum(ReferralWithdrawalRequest.amount_rub), 0)).where(ReferralWithdrawalRequest.status == WithdrawalStatus.pending))).scalar() or 0)
    pending_prompts = int((await session.execute(select(func.count(UserPrompt.id)).where(UserPrompt.status == PromptStatus.pending))).scalar() or 0)

    users_rows = (await session.execute(
        select(cast(User.created_at, Date), func.count(User.id))
        .where(User.created_at >= since_dt)
        .group_by(cast(User.created_at, Date))
        .order_by(cast(User.created_at, Date))
    )).all()
    revenue_rows = (await session.execute(
        select(cast(Transaction.created_at, Date), func.coalesce(func.sum(Transaction.amount_rub), 0))
        .where(Transaction.status == TransactionStatus.paid, Transaction.created_at >= since_dt)
        .group_by(cast(Transaction.created_at, Date))
        .order_by(cast(Transaction.created_at, Date))
    )).all()
    generation_rows = (await session.execute(
        select(cast(Generation.created_at, Date), func.count(Generation.id))
        .where(Generation.created_at >= since_dt)
        .group_by(cast(Generation.created_at, Date))
        .order_by(cast(Generation.created_at, Date))
    )).all()
    top_models = (await session.execute(
        select(Generation.model, func.count(Generation.id).label("count"))
        .where(Generation.created_at >= seven_days_ago)
        .group_by(Generation.model)
        .order_by(desc("count"))
        .limit(8)
    )).all()
    providers = (await session.execute(
        select(Transaction.provider, func.count(Transaction.id), func.coalesce(func.sum(Transaction.amount_rub), 0))
        .where(Transaction.created_at >= thirty_days_ago)
        .group_by(Transaction.provider)
        .order_by(desc(func.count(Transaction.id)))
    )).all()

    return {
        "summary": {
            "users_total": users_total,
            "users_new_7d": users_new_7d,
            "paid_users": paid_users,
            "revenue_total": revenue_total,
            "revenue_7d": revenue_7d,
            "generations_total": generations_total,
            "generations_7d": generations_7d,
            "image_7d": image_7d,
            "video_7d": video_7d,
            "music_7d": music_7d,
            "success_rate_7d": round((done_7d / max(done_7d + failed_7d, 1)) * 100, 1),
            "pending_withdrawals_count": pending_withdrawals_count,
            "pending_withdrawals_amount": pending_withdrawals_amount,
            "pending_prompts": pending_prompts,
        },
        "charts": {
            "users": _admin_series(users_rows, labels),
            "revenue": _admin_series(revenue_rows, labels),
            "generations": _admin_series(generation_rows, labels),
        },
        "top_models": [{"model": str(model or "unknown"), "count": int(count or 0)} for model, count in top_models],
        "providers": [
            {"provider": getattr(provider, "value", str(provider or "unknown")), "count": int(count or 0), "revenue": float(revenue or 0)}
            for provider, count, revenue in providers
        ],
    }


@router.get("/admin/users")
async def admin_users(
    query: str | None = Query(default=None),
    limit: int = Query(default=25, ge=1, le=100),
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _admin_guard(user)

    cleaned = str(query or "").strip()
    stmt = select(User).order_by(desc(User.created_at)).limit(limit)
    if cleaned:
        like = f"%{cleaned}%"
        stmt = (
            select(User)
            .where(
                or_(
                    cast(User.id, String).ilike(like),
                    cast(User.tg_id, String).ilike(like),
                    func.coalesce(User.username, "").ilike(like),
                    func.coalesce(User.full_name, "").ilike(like),
                )
            )
            .order_by(desc(User.created_at))
            .limit(limit)
        )
    rows = list((await session.execute(stmt)).scalars().all())
    items = []
    for row in rows:
        generations_count = int((await session.execute(select(func.count(Generation.id)).where(Generation.user_id == row.id))).scalar() or 0)
        paid_rub = float((await session.execute(select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(Transaction.user_id == row.id, Transaction.status == TransactionStatus.paid))).scalar() or 0)
        items.append({
            "id": int(row.id),
            "tg_id": int(row.tg_id),
            "username": row.username,
            "full_name": row.full_name,
            "credits": float(row.credits or 0),
            "referral_balance": float(row.referral_balance or 0),
            "is_banned": bool(row.is_banned),
            "created_at": _admin_iso(row.created_at),
            "generations_count": generations_count,
            "paid_rub": paid_rub,
        })
    return {"items": items}


@router.get("/admin/users/{user_id}")
async def admin_user_detail(
    user_id: int,
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _admin_guard(user)
    target = await repo.get_user_by_id(session, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    generations = list((await session.execute(select(Generation).where(Generation.user_id == user_id).order_by(desc(Generation.created_at)).limit(20))).scalars().all())
    transactions = list((await session.execute(select(Transaction).where(Transaction.user_id == user_id).order_by(desc(Transaction.created_at)).limit(20))).scalars().all())
    ledger = list((await session.execute(select(CreditLedgerEntry).where(CreditLedgerEntry.user_id == user_id).order_by(desc(CreditLedgerEntry.created_at)).limit(20))).scalars().all())
    withdrawals = await repo.get_user_withdrawal_requests(session, user_id, limit=20)
    l1, l2, l3 = await repo.count_user_referrals(session, user_id)

    return {
        "user": {
            "id": int(target.id),
            "tg_id": int(target.tg_id),
            "username": target.username,
            "full_name": target.full_name,
            "photo_url": target.photo_url,
            "credits": float(target.credits or 0),
            "referral_balance": float(target.referral_balance or 0),
            "language": target.language,
            "is_banned": bool(target.is_banned),
            "created_at": _admin_iso(target.created_at),
        },
        "stats": {
            "generations_count": int((await session.execute(select(func.count(Generation.id)).where(Generation.user_id == user_id))).scalar() or 0),
            "paid_rub": float((await session.execute(select(func.coalesce(func.sum(Transaction.amount_rub), 0)).where(Transaction.user_id == user_id, Transaction.status == TransactionStatus.paid))).scalar() or 0),
            "payments_count": int((await session.execute(select(func.count(Transaction.id)).where(Transaction.user_id == user_id, Transaction.status == TransactionStatus.paid))).scalar() or 0),
            "referrals": {"l1": l1, "l2": l2, "l3": l3},
        },
        "generations": [
            {
                "id": int(item.id),
                "model": item.model,
                "gen_type": getattr(item.gen_type, "value", item.gen_type),
                "status": getattr(item.status, "value", item.status),
                "credits_spent": float(item.credits_spent or 0),
                "result_url": item.result_url,
                "created_at": _admin_iso(item.created_at),
            }
            for item in generations
        ],
        "transactions": [
            {
                "id": int(item.id),
                "provider": getattr(item.provider, "value", item.provider),
                "status": getattr(item.status, "value", item.status),
                "amount_rub": float(item.amount_rub or 0),
                "credits": float(item.credits or 0),
                "external_id": item.external_id,
                "created_at": _admin_iso(item.created_at),
            }
            for item in transactions
        ],
        "ledger": [
            {
                "id": int(item.id),
                "delta": float(item.delta or 0),
                "balance_after": float(item.balance_after or 0),
                "entry_type": item.entry_type,
                "note": item.note,
                "created_at": _admin_iso(item.created_at),
            }
            for item in ledger
        ],
        "withdrawals": [
            {
                "id": int(item.id),
                "amount_rub": float(item.amount_rub or 0),
                "status": getattr(item.status, "value", item.status),
                "payout_details": item.payout_details,
                "admin_note": item.admin_note,
                "created_at": _admin_iso(item.created_at),
                "reviewed_at": _admin_iso(item.reviewed_at),
            }
            for item in withdrawals
        ],
    }


@router.post("/admin/users/{user_id}/credits")
async def admin_user_credits(
    user_id: int,
    body: AdminCreditsRequest,
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    admin = user
    _admin_guard(admin)
    target = await repo.get_user_by_id(session, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    amount = float(body.amount or 0)
    if amount == 0:
        return {"ok": True, "balance": float(target.credits or 0)}
    if amount > 0:
        balance = await repo.add_credits(
            session,
            user_id,
            amount,
            entry_type="admin_adjustment",
            source_type="admin",
            source_id=str(getattr(admin, "tg_id", "")),
            note=body.note or "Admin credit adjustment",
        )
    else:
        spent = await repo.spend_credits(
            session,
            user_id,
            abs(amount),
            entry_type="admin_adjustment",
            source_type="admin",
            source_id=str(getattr(admin, "tg_id", "")),
            note=body.note or "Admin credit adjustment",
        )
        if not spent:
            raise HTTPException(status_code=400, detail="Insufficient user credits")
        refreshed = await repo.get_user_by_id(session, user_id)
        balance = float(getattr(refreshed, "credits", 0) or 0)
    return {"ok": True, "balance": float(balance)}


@router.post("/admin/users/{user_id}/ban")
async def admin_user_ban(
    user_id: int,
    body: AdminBanRequest,
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _admin_guard(user)
    target = await repo.get_user_by_id(session, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    changed = await (repo.ban_user(session, target.tg_id) if body.banned else repo.unban_user(session, target.tg_id))
    return {"ok": True, "changed": bool(changed), "banned": bool(body.banned)}


@router.get("/admin/withdrawals")
async def admin_withdrawals(
    status: str = Query(default="pending", pattern="^(pending|approved|rejected|all)$"),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _admin_guard(user)
    stmt = select(ReferralWithdrawalRequest, User).join(User, ReferralWithdrawalRequest.user_id == User.id)
    if status != "all":
        stmt = stmt.where(ReferralWithdrawalRequest.status == WithdrawalStatus(status))
    stmt = stmt.order_by(desc(ReferralWithdrawalRequest.created_at)).limit(limit)
    rows = (await session.execute(stmt)).all()
    items = []
    for request, owner in rows:
        items.append({
            "id": int(request.id),
            "status": getattr(request.status, "value", request.status),
            "amount_rub": float(request.amount_rub or 0),
            "payout_details": request.payout_details,
            "admin_note": request.admin_note,
            "created_at": _admin_iso(request.created_at),
            "reviewed_at": _admin_iso(request.reviewed_at),
            "user": {
                "id": int(owner.id),
                "tg_id": int(owner.tg_id),
                "username": owner.username,
                "full_name": owner.full_name,
            },
        })
    return {"items": items}


@router.post("/admin/withdrawals/{request_id}/review")
async def admin_withdrawal_review(
    request_id: int,
    body: AdminWithdrawalReviewRequest,
    user: User = Depends(get_miniapp_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _admin_guard(user)
    result = await repo.set_withdrawal_status(
        session,
        request_id,
        status=WithdrawalStatus.approved if body.action == "approve" else WithdrawalStatus.rejected,
        admin_tg_id=int(getattr(user, "tg_id", 0) or 0),
        admin_note=body.note,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Withdrawal request not found or already reviewed")
    return {
        "ok": True,
        "item": {
            "id": int(result.request.id),
            "status": getattr(result.request.status, "value", result.request.status),
            "reviewed_at": _admin_iso(result.request.reviewed_at),
            "admin_note": result.request.admin_note,
        },
    }

# ── payments ──────────────────────────────────────────────────────────────────



@router.get("/payment-methods")
async def list_payment_methods(
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    plans = await repo.get_active_price_plans(session)
    plan_keys = [str(plan.key) for plan in plans]
    methods: list[str] = []
    if settings.TBANK_TERMINAL_KEY and settings.TBANK_PASSWORD:
        methods.append("tbank")
    if settings.TELEGRAM_STARS_ENABLED:
        methods.append("stars")
    if settings.CRYPTOBOT_TOKEN:
        methods.append("crypto")
    if settings.LAVA_API_KEY and any(settings.lava_offer_id_for_plan(key) for key in plan_keys):
        methods.append("lava")
    return methods



@router.get("/payment-options")
async def list_payment_options(
    session: AsyncSession = Depends(get_session),
) -> dict:
    plans = await repo.get_active_price_plans(session)
    plan_keys = [str(plan.key) for plan in plans]
    lava_plan_keys = [key for key in plan_keys if settings.lava_offer_id_for_plan(key)]
    methods: list[str] = []
    if settings.TBANK_TERMINAL_KEY and settings.TBANK_PASSWORD:
        methods.append("tbank")
    if settings.TELEGRAM_STARS_ENABLED:
        methods.append("stars")
    if settings.CRYPTOBOT_TOKEN:
        methods.append("crypto")
    if settings.LAVA_API_KEY and lava_plan_keys:
        methods.append("lava")
    return {"methods": methods, "lava_plan_keys": lava_plan_keys}

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


@router.post("/topup/lava")
async def topup_lava(
    body: TopupRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict:
    """Create a Lava invoice. Returns `pay_url` to open checkout."""
    from db.models import PaymentProvider
    from payments.lava import create_invoice as lava_create_invoice

    plan = await repo.get_price_plan_by_key(session, body.plan_key)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        invoice = await lava_create_invoice(plan, user.id)
    except Exception as exc:
        logger.error("Lava invoice error user=%s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="Payment service error")

    tx = await repo.create_transaction(
        session=session,
        user_id=user.id,
        amount_rub=plan.price_rub,
        credits=plan.credits,
        provider=PaymentProvider.lava,
        external_id=invoice.invoice_id,
    )

    return {"pay_url": invoice.payment_url, "transaction_id": tx.id, "credits": plan.credits, "amount_rub": plan.price_rub}


# ── serializers ───────────────────────────────────────────────────────────────

def _generation_result_urls(gen) -> list[str]:
    raw = getattr(gen, "result_urls", None)
    urls: list[str] = []
    if raw:
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            parsed = []
        if isinstance(parsed, list):
            urls = [str(url) for url in parsed if url]
    urls = [url for url in urls if public_url_is_available(url)]
    if not urls and gen.result_url and public_url_is_available(str(gen.result_url)):
        urls = [str(gen.result_url)]
    return urls


def _generation_primary_result_url(gen) -> str | None:
    result_url = getattr(gen, "result_url", None)
    if result_url and public_url_is_available(str(result_url)):
        return str(result_url)
    urls = _generation_result_urls(gen)
    return urls[0] if urls else None


def _gen_out(gen) -> GenerationOut:
    prompt_hidden = _generation_prompt_hidden(gen)
    return GenerationOut(
        id=gen.id,
        model=gen.model,
        gen_type=gen.gen_type.value,
        prompt="" if prompt_hidden else (gen.prompt or ""),
        prompt_hidden=prompt_hidden,
        prompt_actions_allowed=not prompt_hidden,
        status=gen.status.value,
        result_url=_generation_primary_result_url(gen),
        credits_spent=gen.credits_spent,
        created_at=gen.created_at.isoformat() if gen.created_at else "",
        is_public_feed=bool(gen.is_public_feed),
        is_prompt_library=bool(getattr(gen, "is_prompt_library", False)),
        result_urls=_generation_result_urls(gen),
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
    if _generation_prompt_hidden(gen):
        raise HTTPException(status_code=403, detail="Cannot publish a feed remix")

    shared = await repo.share_to_feed(session, gen_id, user.id)
    if not shared:
        raise HTTPException(status_code=404, detail="Generation not found or not ready")
    gen = await repo.share_to_library(session, gen_id, user.id) or shared
    link = _telegram_start_link(build_start_payload(ref_code=user.referral_code, target_kind="feed", target_id=gen.id))

    return {
        "ok": True,
        "id": gen.id,
        "is_public_feed": gen.is_public_feed,
        "is_prompt_library": gen.is_prompt_library,
        "link": link,
    }
