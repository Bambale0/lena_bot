from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypeVar
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, BeforeValidator, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_auth import get_miniapp_user
from api.miniapp_routes import (
    _MJ_IMAGE_CAPS,
    _MJ_VIDEO_CAPS,
    GenerationOut,
    ImageGenRequest,
    PreSubmitRejection,
    VideoGenRequest,
    _normalize_image_request,
    create_image_generation,
    create_video_generation,
    quote_video_generation,
)
from api.public_files import save_public_file
from api.trend_assets import image_kind_from_upload, sign_uploaded_asset, verify_uploaded_asset
from bot.keyboards.models import IMAGE_CAPS, VIDEO_CAPS
from bot.utils.deep_links import build_start_payload
from core.config import settings
from core.gemini_omni import GEMINI_OMNI_DURATIONS, GEMINI_OMNI_VIDEO_MODEL
from core.model_pricing import split_pricing_variant_key
from core.repeat_duration import duration_offer, resolve_repeat_duration
from core.trend_user_fields import (
    TrendUserFieldsError,
    normalize_configured_trend_user_fields,
)
from core.trends import (
    DEFAULT_TREND_CATEGORY,
    TREND_TAG,
    build_trend_tags,
    is_trend_prompt,
    legacy_trend_category,
    mirror_trend_category_tag,
    trend_admin_payload,
    trend_is_public,
    trend_kind,
    trend_public_payload,
    trend_settings,
)
from db import repository as repo
from db.models import Generation, GenerationType, PromptCategory, User, UserPrompt
from db.prompt_repository import (
    approve_prompt,
    create_prompt,
    deactivate_prompt,
    get_prompt_by_id,
)
from db.session import get_session
from db.trend_category_repository import (
    TrendCategoryConflict,
    TrendCategoryMutationError,
    TrendCategoryPopulated,
    create_trend_category,
    get_admin_trend_category_catalog,
    get_existing_trend_category,
    get_public_category_shelves,
    get_public_category_trends,
    get_visible_trend_category_for_prompt,
    get_visible_trends,
    reassign_trend_prompt,
    reorder_trend_categories,
    require_existing_trend_category,
    update_trend_category,
)
from db.trend_run_claims import get_claim, release_pre_submit_claim, reserve_claim

router = APIRouter(prefix="/api/v1", tags=["trends"])
logger = logging.getLogger(__name__)

MAX_TREND_PREVIEW_BYTES = 50 * 1024 * 1024
MAX_TREND_USER_PHOTO_BYTES = 30 * 1024 * 1024
IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_CONTENT_TYPES = {"video/mp4", "video/webm", "video/quicktime"}


class TrendCreateRequest(BaseModel):
    kind: str = Field(pattern="^(image|video)$")
    title: str = Field(min_length=3, max_length=60)
    description: str = Field(default="", max_length=200)
    prompt_template: str = Field(min_length=1, max_length=8000)
    preview_url: str = Field(min_length=1, max_length=2048)
    model: str = Field(min_length=1, max_length=64)
    settings: dict[str, Any] = Field(default_factory=dict)
    user_fields: list[dict[str, Any]] | None = Field(default=None, max_length=6)


class TrendUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    prompt_template: str | None = Field(default=None, min_length=1, max_length=8000)
    preview_url: str | None = Field(default=None, min_length=1, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=64)
    settings: dict[str, Any] | None = None
    user_fields: list[dict[str, Any]] | None = Field(default=None, max_length=6)


class TrendRunRequest(BaseModel):
    asset_id: str = Field(min_length=20, max_length=4096)
    idempotency_key: str = Field(min_length=8, max_length=128)
    user_values: dict[str, str] = Field(default_factory=dict, max_length=6)
    quoted_credits: float | None = Field(default=None, ge=0)
    duration: int | None = Field(default=None, strict=True, ge=1, le=30)


class TrendUploadResponse(BaseModel):
    asset_id: str
    url: str
    kind: str
    filename: str
    content_type: str
    size: int


class TrendCategoryCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=1, strict=True)


class TrendCategoryUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    is_visible: bool | None = None
    confirm_populated: bool = False
    expected_revision: int = Field(ge=1, strict=True)


class TrendCategoryReorderRequest(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=100)
    expected_revision: int = Field(ge=1, strict=True)


class TrendCategoryReassignRequest(BaseModel):
    prompt_id: int = Field(ge=1, strict=True)
    expected_revision: int = Field(ge=1, strict=True)


def _require_admin(user: User) -> None:
    if not getattr(user, "tg_id", None) or user.tg_id not in settings.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")


def _admin_category_out(item: Any) -> dict[str, Any]:
    category = getattr(item, "category", item)
    return {
        "key": str(category.key),
        "title": str(category.title),
        "sort_order": int(category.sort_order),
        "is_visible": bool(category.is_visible),
        "trend_count": int(getattr(item, "trend_count", 0) or 0),
        "published_count": int(getattr(item, "published_count", 0) or 0),
    }


CategoryMutationResult = TypeVar("CategoryMutationResult")


async def _run_category_mutation(
    session: AsyncSession,
    operation: Callable[[], Awaitable[CategoryMutationResult]],
) -> CategoryMutationResult:
    try:
        result = await operation()
        await session.commit()
        return result
    except TrendCategoryConflict as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "trend_category_revision_conflict",
                "message": str(exc),
                "revision": exc.revision,
            },
        ) from exc
    except TrendCategoryPopulated as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "trend_category_not_empty",
                "message": str(exc),
                "trend_count": exc.count,
            },
        ) from exc
    except TrendCategoryMutationError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception:
        await session.rollback()
        raise


def _credits_out(value: float | int | None) -> float:
    return round(float(value or 0), 2)


def _validate_preview_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="preview_url must be an absolute HTTP(S) URL")
    return url


def _looks_like_image(data: bytes, content_type: str) -> bool:
    return content_type in IMAGE_CONTENT_TYPES and (
        data.startswith(b"\xff\xd8\xff")
        or data.startswith(b"\x89PNG\r\n\x1a\n")
        or (data.startswith(b"RIFF") and b"WEBP" in data[:16])
    )


def _looks_like_video(data: bytes, content_type: str) -> bool:
    if content_type not in VIDEO_CONTENT_TYPES:
        return False
    if content_type == "video/webm":
        return data.startswith(b"\x1aE\xdf\xa3")
    return len(data) >= 12 and b"ftyp" in data[4:16]


async def _validated_model(session: AsyncSession, model_key: str, kind: str):
    runtime_model, _options = split_pricing_variant_key(model_key)
    caps = VIDEO_CAPS if kind == "video" else IMAGE_CAPS
    midjourney_caps = _MJ_VIDEO_CAPS if kind == "video" else _MJ_IMAGE_CAPS
    if runtime_model not in caps and runtime_model not in midjourney_caps:
        raise HTTPException(status_code=422, detail="Selected model is not available")
    model = await repo.get_model_cost(session, runtime_model)
    if not model or not getattr(model, "is_active", True):
        raise HTTPException(status_code=422, detail="Selected model is not available")
    expected = GenerationType.video if kind == "video" else GenerationType.image
    if getattr(model, "gen_type", None) != expected:
        raise HTTPException(
            status_code=422, detail=f"Model {model_key} does not support {kind} trends"
        )
    return model


def _runtime_model_and_settings(trend: UserPrompt) -> tuple[str, dict[str, Any]]:
    runtime_model, pricing_options = split_pricing_variant_key(str(trend.model or ""))
    resolved = trend_settings(trend)
    _merge_pricing_options(resolved, pricing_options)
    return runtime_model, resolved


def _merge_pricing_options(
    settings_payload: dict[str, Any], pricing_options: dict[str, str]
) -> None:
    for name, raw_value in pricing_options.items():
        if settings_payload.get(name) not in (None, ""):
            continue
        if name == "duration":
            try:
                settings_payload[name] = int(raw_value)
            except (TypeError, ValueError):
                settings_payload[name] = raw_value
        else:
            settings_payload[name] = raw_value


async def _get_public_trend(session: AsyncSession, trend_id: int) -> UserPrompt:
    prompt = await get_prompt_by_id(session, trend_id)
    if not trend_is_public(prompt):
        raise HTTPException(status_code=404, detail="Trend not found")
    category = await get_visible_trend_category_for_prompt(session, prompt)
    if category is None:
        raise HTTPException(status_code=404, detail="Trend not found")
    return prompt


async def _lock_public_trend_category(session: AsyncSession, prompt: UserPrompt) -> None:
    category = await get_visible_trend_category_for_prompt(session, prompt, lock=True)
    if category is None:
        raise HTTPException(status_code=404, detail="Trend not found")


async def _trend_cost_credits(session: AsyncSession, trend: UserPrompt, duration_override: int | None = None) -> float:
    if not trend.model:
        raise HTTPException(status_code=409, detail="Trend has no configured model")
    kind = trend_kind(trend)
    runtime_model, settings_payload = _runtime_model_and_settings(trend)
    if kind == "video":
        duration = _resolve_trend_duration(runtime_model, settings_payload, duration_override)
        from api.wan30_contract import WAN30_MODELS, Wan30Request
        from api.wan30_launch import get_wan30_quote

        if runtime_model in WAN30_MODELS:
            defaults = VIDEO_CAPS.get(runtime_model, {})
            default_resolution = next(iter(defaults.get("resolutions") or []), "720p")
            default_ratio = next(iter(defaults.get("aspect_ratios") or []), "adaptive")
            try:
                quote = await get_wan30_quote(
                    session,
                    Wan30Request(
                        model=runtime_model,
                        prompt="Trend price quote",
                        duration=duration,
                        resolution=str(settings_payload.get("resolution") or default_resolution),
                        aspect_ratio=str(settings_payload.get("ratio") or default_ratio),
                        mode="text",
                    ),
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            return quote.credits
        model_cost = await repo.resolve_video_model_cost(
            session,
            runtime_model,
            duration=duration,
            resolution=settings_payload.get("resolution"),
        )
        if not model_cost:
            raise HTTPException(status_code=422, detail="Model not available")
        credits = float(model_cost.credits)
        if VIDEO_CAPS.get(runtime_model, {}).get("billing_mode") == "per_second":
            credits *= duration
        return round(credits, 6)

    _ratio, quality = _normalize_image_request(
        model_key=runtime_model,
        reference_urls=["trend-reference"],
        aspect_ratio=settings_payload.get("ratio"),
        quality=str(settings_payload.get("quality") or "basic"),
    )
    model_cost = await repo.resolve_image_model_cost(session, runtime_model, quality=quality)
    if not model_cost:
        model_cost = await repo.get_model_cost(session, runtime_model)
    if not model_cost or not getattr(model_cost, "is_active", True):
        raise HTTPException(status_code=422, detail="Model not available")
    return round(float(model_cost.credits), 6)


def _trend_video_duration(model: str, settings_payload: dict[str, Any]) -> int:
    raw = settings_payload.get("duration")
    fallback = GEMINI_OMNI_DURATIONS[0] if model == GEMINI_OMNI_VIDEO_MODEL else 5
    duration = _safe_int(raw, fallback)
    # Previously published Gemini trends stored the old five-second default.
    # The provider adapter already interpreted that value as four seconds.
    if model == GEMINI_OMNI_VIDEO_MODEL and duration == 5:
        return GEMINI_OMNI_DURATIONS[0]
    if model == GEMINI_OMNI_VIDEO_MODEL and duration not in GEMINI_OMNI_DURATIONS:
        raise HTTPException(status_code=422, detail="Unsupported Gemini Omni trend duration")
    return duration


def _resolve_trend_duration(model: str, settings_payload: dict[str, Any], override: int | None) -> int:
    from api.kling4_contract import KLING4_MODELS

    if model in KLING4_MODELS:
        raise HTTPException(status_code=422, detail="Открой Kling 4 в студии: роли материалов требуют отдельного подтверждения")
    try:
        return resolve_repeat_duration(model, _trend_video_duration(model, settings_payload), override)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _validate_trend_video_settings(model: str, settings_payload: dict[str, Any]) -> None:
    if model == GEMINI_OMNI_VIDEO_MODEL:
        if _safe_int(settings_payload.get("duration"), GEMINI_OMNI_DURATIONS[0]) == 5:
            raise HTTPException(status_code=422, detail="Unsupported Gemini Omni trend duration")
        _trend_video_duration(model, settings_payload)


def _trend_request_hash(trend_id: int, body: TrendRunRequest) -> str:
    identity = [trend_id, body.asset_id, body.user_values, body.quoted_credits]
    if body.duration is not None:
        identity.append(body.duration)
    encoded = json.dumps(
        identity,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _recommended_checkout_plan(plans: list[Any], deficit: float) -> Any | None:
    active = [plan for plan in plans if float(getattr(plan, "credits", 0) or 0) > 0]
    if not active:
        return None
    enough = [plan for plan in active if float(plan.credits) >= deficit]
    pool = enough or active
    return (
        min(pool, key=lambda plan: (float(plan.credits), float(getattr(plan, "price_rub", 0) or 0)))
        if enough
        else max(pool, key=lambda plan: float(plan.credits))
    )


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _task_payload(task: GenerationOut) -> dict[str, Any]:
    payload = task.model_dump()
    payload["cost"] = payload.get("credits_spent", 0)
    payload["type"] = payload.get("gen_type")
    return payload


async def _find_idempotent_trend_run(
    session: AsyncSession,
    *,
    user_id: int,
    idempotency_key: str,
) -> Generation | None:
    marker = json.dumps({"trend_run_key": idempotency_key}, separators=(",", ":"))[1:-1]
    marker = marker.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    result = await session.execute(
        select(Generation)
        .where(
            Generation.user_id == user_id, Generation.input_params.like(f"%{marker}%", escape="\\")
        )
        .order_by(desc(Generation.created_at), desc(Generation.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _patch_trend_snapshot(
    session: AsyncSession,
    *,
    generation_id: int,
    trend: UserPrompt,
    settings_payload: dict[str, Any],
    asset_payload: dict[str, Any],
    idempotency_key: str,
    user_values: dict[str, str] | None = None,
    requested_duration: int | None = None,
) -> None:
    generation = await repo.get_generation_by_id(session, generation_id)
    if not generation:
        return
    try:
        existing = json.loads(generation.input_params or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        existing = {}
    existing.update(
        {
            "source": "trend",
            "trend_id": int(trend.id),
            "trend_kind": trend_kind(trend),
            "trend_settings_version": int(settings_payload.get("settings_version") or 1),
            "trend_run_key": idempotency_key,
            "user_asset_id": asset_payload.get("asset_id", ""),
            "user_asset_url": asset_payload.get("url", ""),
            "resolved_settings": settings_payload,
            "trend_user_values": dict(user_values or {}),
        }
    )
    if requested_duration is not None:
        existing["trend_requested_duration"] = requested_duration
    generation.input_params = json.dumps(existing, ensure_ascii=False, separators=(",", ":"))
    await session.commit()


def _public_trend_in_category(prompt: UserPrompt, category: Any) -> dict[str, Any]:
    payload = trend_public_payload(prompt)
    payload.update(
        {
            "category": str(category.key),
            "category_title": str(category.title),
            "category_emoji": "",
        }
    )
    return payload


@router.get("/trend-categories")
async def list_trend_categories(
    limit: int = Query(default=24, ge=1, le=24),
    cursor: str | None = Query(default=None, max_length=512),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    del user
    try:
        page = await get_public_category_shelves(
            session,
            limit=limit,
            cursor=cursor,
            preview_limit=5,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "items": [
            {
                "key": str(item.category.key),
                "title": str(item.category.title),
                "sort_order": int(item.category.sort_order),
                "trend_count": int(item.trend_count),
                "preview_items": [
                    _public_trend_in_category(prompt, item.category)
                    for prompt in item.previews
                ],
            }
            for item in page.items
        ],
        "has_more": page.has_more,
        "next_cursor": page.next_cursor,
    }


@router.get("/trend-categories/{key}/trends")
async def list_trend_category_items(
    key: str,
    limit: int = Query(default=48, ge=1, le=48),
    cursor: str | None = Query(default=None, max_length=512),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    del user
    try:
        page = await get_public_category_trends(
            session,
            key=key,
            limit=limit,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if page is None:
        raise HTTPException(status_code=404, detail="Trend category not found")
    return {
        "category": {
            "key": str(page.category.key),
            "title": str(page.category.title),
            "sort_order": int(page.category.sort_order),
        },
        "items": [
            _public_trend_in_category(prompt, page.category) for prompt in page.items
        ],
        "has_more": page.has_more,
        "next_cursor": page.next_cursor,
    }


@router.get("/trends")
async def list_trends(
    kind: str | None = Query(default=None, pattern="^(image|video)$"),
    limit: int = Query(default=80, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[dict[str, Any]]:
    del user
    prompts = await get_visible_trends(session, limit=limit)
    if kind:
        prompts = [item for item in prompts if trend_kind(item) == kind]
    return [trend_public_payload(item) for item in prompts]


@router.get("/trends/{trend_id}")
async def get_trend(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    del user
    return trend_public_payload(await _get_public_trend(session, trend_id))


@router.post("/trends/upload", response_model=TrendUploadResponse)
async def upload_trend_photo(
    file: UploadFile = File(...),
    user: User = Depends(get_miniapp_user),
) -> TrendUploadResponse:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty photo")
    if len(data) > MAX_TREND_USER_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Photo is too large (max 30 MB)")
    content_type = str(file.content_type or "application/octet-stream").split(";", 1)[0].lower()
    filename = str(file.filename or "photo")[:180]
    if not image_kind_from_upload(data, content_type, filename):
        raise HTTPException(
            status_code=422, detail="Upload one JPEG, PNG, WebP, HEIC, HEIF or AVIF photo"
        )
    url = save_public_file(data, content_type, subdir="trends")
    asset_id = sign_uploaded_asset(
        user_id=user.id,
        url=url,
        kind="image",
        filename=filename,
        content_type=content_type,
        size=len(data),
    )
    return TrendUploadResponse(
        asset_id=asset_id,
        url=url,
        kind="image",
        filename=filename,
        content_type=content_type,
        size=len(data),
    )


@router.post("/trends/{trend_id}/prepare")
async def prepare_trend(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    # Backward-compatible endpoint, intentionally no longer leaks model/settings.
    del user
    return {
        **trend_public_payload(await _get_public_trend(session, trend_id)),
        "prompt_hidden": True,
    }


@router.post("/trends/{trend_id}/run", status_code=202)
async def run_trend(
    trend_id: int,
    body: TrendRunRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    user_id = int(user.id)
    request_hash = _trend_request_hash(trend_id, body)
    claim = await get_claim(session, user_id, body.idempotency_key)
    if claim is not None:
        return await _existing_trend_run_response(session, user, claim, trend_id, request_hash)
    existing = await _find_idempotent_trend_run(
        session,
        user_id=user_id,
        idempotency_key=body.idempotency_key,
    )
    if existing is not None:
        try:
            previous = json.loads(existing.input_params or "{}")
        except (TypeError, ValueError):
            previous = {}
        if (
            previous.get("trend_id") != trend_id
            or previous.get("user_asset_id") != body.asset_id
            or previous.get("trend_user_values", {}) != body.user_values
            or previous.get("trend_requested_duration") != body.duration
        ):
            raise HTTPException(
                status_code=409, detail="Request key already belongs to a different trend run"
            )
        await session.refresh(user)
        return {
            "ok": True,
            "task": _task_payload(GenerationOut.model_validate(existing, from_attributes=True)),
            "credits": _credits_out(user.credits),
        }

    trend = await _get_public_trend(session, trend_id)
    kind = trend_kind(trend)
    if not trend.model:
        raise HTTPException(status_code=409, detail="Trend has no configured model")
    runtime_model, settings_payload = _runtime_model_and_settings(trend)
    await _validated_model(session, runtime_model, kind)
    asset = verify_uploaded_asset(body.asset_id, user_id=user_id, expected_kind="image")
    asset["asset_id"] = body.asset_id
    asset_url = str(asset["url"])

    if kind == "video":
        settings_payload["duration"] = _resolve_trend_duration(runtime_model, settings_payload, body.duration)
        request = VideoGenRequest(
            model=runtime_model,
            prompt="Использовать скрытый трендовый промпт",
            prompt_id=trend.id,
            mode="image",
            image_url=asset_url,
            reference_urls=[],
            duration=_trend_video_duration(runtime_model, settings_payload),
            aspect_ratio=settings_payload.get("ratio"),
            resolution=settings_payload.get("resolution"),
            trend_user_values=body.user_values,
        )
        from api.wan30_contract import WAN30_MODELS

        if runtime_model in WAN30_MODELS or body.duration is not None:
            quote = await quote_video_generation(request, session, user)
            if body.quoted_credits is None or round(body.quoted_credits, 6) != round(
                float(quote["cost_credits"]), 6
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "trend_quote_stale",
                        "message": "Цена тренда изменилась. Проверь стоимость и подтверди запуск.",
                    },
                )
            request.quoted_credits = float(quote["cost_credits"])
    else:
        if body.duration is not None:
            raise HTTPException(status_code=422, detail="Длительность доступна только для видео")
        request = ImageGenRequest(
            model=runtime_model,
            prompt="Использовать скрытый трендовый промпт",
            prompt_id=trend.id,
            aspect_ratio=settings_payload.get("ratio"),
            quality=str(settings_payload.get("quality") or "basic"),
            count=max(1, min(6, _safe_int(settings_payload.get("count"), 1))),
            reference_url=asset_url,
            reference_urls=[asset_url],
            trend_user_values=body.user_values,
        )

    # Hold a shared category-row lock through durable claim reservation. A hide
    # committed first blocks this run; a run admitted first is allowed to finish.
    await _lock_public_trend_category(session, trend)
    claim, created = await reserve_claim(
        session,
        user_id=user_id,
        request_key=body.idempotency_key,
        request_hash=request_hash,
        trend_id=trend_id,
    )
    if not created:
        return await _existing_trend_run_response(session, user, claim, trend_id, request_hash)

    try:
        if kind == "video":
            task = await create_video_generation(
                body=request, session=session, user=user, surface="web"
            )
        else:
            task = await create_image_generation(
                body=request, session=session, user=user, surface="web"
            )
    except PreSubmitRejection:
        await session.rollback()
        await release_pre_submit_claim(
            session,
            user_id=user_id,
            request_key=body.idempotency_key,
            request_hash=request_hash,
        )
        logger.info("Trend run rejected before submit trend=%s user=%s", trend_id, user_id)
        raise
    except HTTPException as exc:
        await session.rollback()
        if 400 <= exc.status_code < 500:
            await release_pre_submit_claim(
                session,
                user_id=user_id,
                request_key=body.idempotency_key,
                request_hash=request_hash,
            )
        else:
            claim = await get_claim(session, user_id, body.idempotency_key)
            if claim is not None:
                claim.status = "uncertain"
                await session.commit()
        logger.warning(
            "Trend run stopped trend=%s user=%s failure=HTTPException status=%s",
            trend_id,
            user_id,
            exc.status_code,
        )
        raise
    except Exception as exc:
        await session.rollback()
        claim = await get_claim(session, user_id, body.idempotency_key)
        if claim is not None:
            claim.status = "uncertain"
            await session.commit()
        logger.warning(
            "Trend run stopped trend=%s user=%s failure=%s", trend_id, user_id, type(exc).__name__
        )
        raise

    await _patch_trend_snapshot(
        session,
        generation_id=task.id,
        trend=trend,
        settings_payload=settings_payload,
        asset_payload=asset,
        idempotency_key=body.idempotency_key,
        user_values=body.user_values,
        requested_duration=body.duration,
    )
    claim.generation_id = task.id
    claim.status = "complete"
    await session.commit()
    logger.info("Trend run completed trend=%s generation=%s user=%s", trend_id, task.id, user_id)
    await session.refresh(user)
    return {"ok": True, "task": _task_payload(task), "credits": _credits_out(user.credits)}


async def _existing_trend_run_response(
    session: AsyncSession,
    user: User,
    claim,
    trend_id: int,
    request_hash: str,
) -> dict[str, Any]:
    if claim.trend_id != trend_id or claim.request_hash != request_hash:
        raise HTTPException(
            status_code=409, detail="Request key already belongs to a different trend run"
        )
    if claim.generation_id is None:
        raise HTTPException(
            status_code=409, detail="Trend run is already processing; check history before retrying"
        )
    generation = await repo.get_generation_by_id(session, claim.generation_id)
    if generation is None or generation.user_id != user.id:
        raise HTTPException(status_code=409, detail="Trend run result is unavailable")
    await session.refresh(user)
    return {
        "ok": True,
        "task": _task_payload(GenerationOut.model_validate(generation, from_attributes=True)),
        "credits": _credits_out(user.credits),
    }


def _parse_duration_query(value: Any) -> int | None:
    if value is None or type(value) is int:
        return value
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) <= 2:
        return int(value)
    raise ValueError("Duration must be an integer")


@router.get("/trends/{trend_id}/checkout")
async def trend_checkout(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
    duration: Annotated[int | None, BeforeValidator(_parse_duration_query)] = None,
) -> dict[str, Any]:
    trend = await _get_public_trend(session, trend_id)
    requested = duration
    offer = {}
    if trend_kind(trend) == "video":
        runtime_model, saved = _runtime_model_and_settings(trend)
        effective = _resolve_trend_duration(runtime_model, saved, requested)
        offer = duration_offer(runtime_model, _trend_video_duration(runtime_model, saved), effective)
    elif requested is not None:
        raise HTTPException(status_code=422, detail="Длительность доступна только для видео")
    cost = await _trend_cost_credits(session, trend, requested) if requested is not None else await _trend_cost_credits(session, trend)
    balance = _credits_out(user.credits)
    deficit = round(max(0.0, cost - balance), 6)
    plan = None
    if deficit > 0:
        recommended = _recommended_checkout_plan(
            await repo.get_active_price_plans(session), deficit
        )
        if recommended is not None:
            plan = {
                "key": str(recommended.key),
                "label": str(recommended.label),
                "credits": _credits_out(recommended.credits),
                "price_rub": _credits_out(recommended.price_rub),
            }
    return {
        "cost_credits": round(cost, 6),
        "balance_credits": balance,
        "can_run": deficit <= 0,
        "deficit_credits": round(deficit, 6),
        "recommended_plan": plan,
        **offer,
    }


@router.get("/trends/{trend_id}/link")
async def trend_link(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, str]:
    await _get_public_trend(session, trend_id)
    share_payload = build_start_payload(
        ref_code=str(getattr(user, "referral_code", "") or "").strip() or None,
        target_kind="trend",
        target_id=trend_id,
    )
    username = str(getattr(settings, "BOT_USERNAME", "") or "").strip().lstrip("@")
    link = f"https://t.me/{username}?start={share_payload}" if username and share_payload else ""
    return {"link": link, "start_param": share_payload}


@router.get("/admin/trends")
async def admin_list_trends(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[dict[str, Any]]:
    _require_admin(user)
    result = await session.execute(
        select(UserPrompt)
        .where(UserPrompt.tags.any(TREND_TAG))
        .order_by(desc(UserPrompt.created_at))
    )
    return [trend_admin_payload(item) for item in result.scalars().all()]


@router.get("/admin/trend-categories")
async def admin_list_trend_categories(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    catalog = await get_admin_trend_category_catalog(session)
    return {
        "revision": int(catalog.revision),
        "items": [_admin_category_out(item) for item in catalog.items],
    }


@router.post("/admin/trend-categories", status_code=201)
async def admin_create_trend_category(
    body: TrendCategoryCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    category, revision = await _run_category_mutation(
        session,
        lambda: create_trend_category(
            session,
            title=body.title,
            expected_revision=body.expected_revision,
            actor_tg_id=int(user.tg_id),
            source="web",
        ),
    )
    logger.info(
        "trend_category_created key=%s revision=%s actor=%s",
        category.key,
        revision,
        user.tg_id,
    )
    return {"revision": revision, "category": _admin_category_out(category)}


@router.post("/admin/trend-categories/reorder")
async def admin_reorder_trend_categories(
    body: TrendCategoryReorderRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    categories, revision = await _run_category_mutation(
        session,
        lambda: reorder_trend_categories(
            session,
            keys=body.keys,
            expected_revision=body.expected_revision,
            actor_tg_id=int(user.tg_id),
            source="web",
        ),
    )
    logger.info(
        "trend_categories_reordered count=%s revision=%s actor=%s",
        len(categories),
        revision,
        user.tg_id,
    )
    return {
        "revision": revision,
        "items": [_admin_category_out(item) for item in categories],
    }


@router.post("/admin/trend-categories/{key}/update")
async def admin_update_trend_category(
    key: str,
    body: TrendCategoryUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    category, revision = await _run_category_mutation(
        session,
        lambda: update_trend_category(
            session,
            key=key,
            title=body.title,
            is_visible=body.is_visible,
            confirm_populated=body.confirm_populated,
            expected_revision=body.expected_revision,
            actor_tg_id=int(user.tg_id),
            source="web",
        ),
    )
    logger.info(
        "trend_category_updated key=%s visible=%s revision=%s actor=%s",
        category.key,
        category.is_visible,
        revision,
        user.tg_id,
    )
    return {"revision": revision, "category": _admin_category_out(category)}


@router.post("/admin/trend-categories/{key}/reassign")
async def admin_reassign_trend_category(
    key: str,
    body: TrendCategoryReassignRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    prompt, category, revision = await _run_category_mutation(
        session,
        lambda: reassign_trend_prompt(
            session,
            prompt_id=body.prompt_id,
            target_key=key,
            expected_revision=body.expected_revision,
            actor_tg_id=int(user.tg_id),
            source="web",
        ),
    )
    logger.info(
        "trend_category_reassigned prompt=%s key=%s revision=%s actor=%s",
        prompt.id,
        category.key,
        revision,
        user.tg_id,
    )
    return {
        "ok": True,
        "prompt_id": int(prompt.id),
        "category_key": str(category.key),
        "revision": revision,
    }


@router.post("/admin/trends/upload")
async def admin_upload_trend_preview(
    kind: str = Form(pattern="^(image|video)$"),
    file: UploadFile = File(...),
    user: User = Depends(get_miniapp_user),
) -> dict[str, str]:
    _require_admin(user)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Empty preview file")
    if len(data) > MAX_TREND_PREVIEW_BYTES:
        raise HTTPException(status_code=413, detail="Preview is too large (max 50 MB)")
    content_type = str(file.content_type or "").split(";", 1)[0].lower()
    valid = (
        _looks_like_video(data, content_type)
        if kind == "video"
        else _looks_like_image(data, content_type)
    )
    if not valid:
        supported = "MP4, WEBM or MOV" if kind == "video" else "JPEG, PNG or WEBP"
        raise HTTPException(status_code=422, detail=f"Preview must be {supported}")
    return {"url": save_public_file(data, content_type), "kind": kind}


@router.post("/admin/trends", status_code=201)
async def admin_create_trend(
    body: TrendCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    runtime_model, pricing_options = split_pricing_variant_key(body.model)
    await _validated_model(session, runtime_model, body.kind)
    preview_url = _validate_preview_url(body.preview_url)
    raw_user_fields = (
        body.user_fields if body.user_fields is not None else body.settings.get("user_fields", [])
    )
    try:
        configured_user_fields = normalize_configured_trend_user_fields(raw_user_fields)
    except TrendUserFieldsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    tag_settings = dict(body.settings)
    tag_settings.pop("user_fields", None)
    _merge_pricing_options(tag_settings, pricing_options)
    if body.kind == "video":
        _validate_trend_video_settings(runtime_model, tag_settings)
    try:
        category = await require_existing_trend_category(
            session, tag_settings.get("category") or DEFAULT_TREND_CATEGORY
        )
        tag_settings["category"] = category.key
        trend_tags = build_trend_tags(body.kind, tag_settings)
        trend_tags = mirror_trend_category_tag(trend_tags, category.key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    prompt = await create_prompt(
        session,
        author_id=user.id,
        title=body.title.strip(),
        description=body.description.strip(),
        category=PromptCategory.photo if body.kind == "image" else PromptCategory.other,
        prompt_text=body.prompt_template.strip(),
        preview_url=preview_url,
        model=runtime_model,
        tags=trend_tags,
        is_public=True,
        trend_category_id=int(category.id),
    )
    prompt.trend_user_fields = configured_user_fields
    await session.commit()
    approved = await approve_prompt(session, prompt.id)
    if approved is None:
        raise HTTPException(status_code=500, detail="Failed to publish trend")
    return trend_admin_payload(approved)


@router.post("/admin/trends/{trend_id}/update")
async def admin_update_trend(
    trend_id: int,
    body: TrendUpdateRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    prompt = await get_prompt_by_id(session, trend_id)
    if not is_trend_prompt(prompt):
        raise HTTPException(status_code=404, detail="Trend not found")
    kind = trend_kind(prompt)
    original_legacy_category = legacy_trend_category(prompt)
    incoming_category = (
        body.settings.get("category")
        if body.settings is not None and "category" in body.settings
        else None
    )
    if incoming_category is not None:
        try:
            resolved_category = await require_existing_trend_category(session, incoming_category)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        try:
            resolved_category = await get_existing_trend_category(
                session, original_legacy_category or DEFAULT_TREND_CATEGORY
            )
        except ValueError:
            # Old malformed keys remain evidence until an administrator
            # explicitly resolves them; unrelated edits must not rewrite them.
            resolved_category = None
    if resolved_category is not None:
        prompt.trend_category_id = int(resolved_category.id)
    if body.model is not None:
        runtime_model, pricing_options = split_pricing_variant_key(body.model)
        await _validated_model(session, runtime_model, kind)
        prompt.model = runtime_model
    else:
        runtime_model, pricing_options = split_pricing_variant_key(str(prompt.model or ""))
        prompt.model = runtime_model
    if body.title is not None:
        prompt.title = body.title.strip()
    if body.description is not None:
        prompt.description = body.description.strip()
    if body.prompt_template is not None:
        prompt.prompt_text = body.prompt_template.strip()
    if body.preview_url is not None:
        prompt.preview_url = _validate_preview_url(body.preview_url)

    settings_user_fields = (
        body.settings.get("user_fields")
        if body.settings is not None and "user_fields" in body.settings
        else None
    )
    if body.user_fields is not None or settings_user_fields is not None:
        raw_user_fields = body.user_fields if body.user_fields is not None else settings_user_fields
        try:
            prompt.trend_user_fields = normalize_configured_trend_user_fields(raw_user_fields)
        except TrendUserFieldsError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    if body.settings is not None or pricing_options:
        merged_settings = trend_settings(prompt)
        incoming_settings = dict(body.settings or {})
        incoming_settings.pop("user_fields", None)
        merged_settings.update(incoming_settings)
        _merge_pricing_options(merged_settings, pricing_options)
        merged_settings.pop("user_fields", None)
        try:
            prompt.tags = build_trend_tags(kind, merged_settings)
            mirrored_key = (
                str(resolved_category.key)
                if resolved_category is not None
                else original_legacy_category
            )
            if mirrored_key:
                prompt.tags = mirror_trend_category_tag(prompt.tags, mirrored_key)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if kind == "video" and (body.model is not None or body.settings is not None):
        _validate_trend_video_settings(runtime_model, trend_settings(prompt))
    await session.commit()
    await session.refresh(prompt)
    return trend_admin_payload(prompt)


@router.post("/admin/trends/{trend_id}/archive")
async def admin_archive_trend(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    _require_admin(user)
    prompt = await get_prompt_by_id(session, trend_id)
    if not is_trend_prompt(prompt):
        raise HTTPException(status_code=404, detail="Trend not found")
    archived = await deactivate_prompt(session, trend_id)
    if archived is None:
        raise HTTPException(status_code=404, detail="Trend not found")
    return trend_admin_payload(archived)
