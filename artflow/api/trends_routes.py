from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_auth import get_miniapp_user
from api.miniapp_routes import (
    GenerationOut,
    ImageGenRequest,
    VideoGenRequest,
    create_image_generation,
    create_video_generation,
)
from api.public_files import save_public_file
from api.trend_assets import image_kind_from_upload, sign_uploaded_asset, verify_uploaded_asset
from core.config import settings
from core.trends import (
    TREND_TAG,
    build_trend_tags,
    is_trend_prompt,
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
    get_prompts_by_tag,
)
from db.session import get_session

router = APIRouter(prefix="/api/v1", tags=["trends"])

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


class TrendUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=60)
    description: str | None = Field(default=None, max_length=200)
    prompt_template: str | None = Field(default=None, min_length=1, max_length=8000)
    preview_url: str | None = Field(default=None, min_length=1, max_length=2048)
    model: str | None = Field(default=None, min_length=1, max_length=64)
    settings: dict[str, Any] | None = None


class TrendRunRequest(BaseModel):
    asset_id: str = Field(min_length=20, max_length=4096)
    idempotency_key: str = Field(min_length=8, max_length=128)


class TrendUploadResponse(BaseModel):
    asset_id: str
    url: str
    kind: str
    filename: str
    content_type: str
    size: int


def _require_admin(user: User) -> None:
    if not getattr(user, "tg_id", None) or user.tg_id not in settings.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")


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
    model = await repo.get_model_cost(session, model_key)
    if not model or not getattr(model, "is_active", True):
        raise HTTPException(status_code=422, detail="Selected model is not available")
    expected = GenerationType.video if kind == "video" else GenerationType.image
    if getattr(model, "gen_type", None) != expected:
        raise HTTPException(status_code=422, detail=f"Model {model_key} does not support {kind} trends")
    return model


async def _get_public_trend(session: AsyncSession, trend_id: int) -> UserPrompt:
    prompt = await get_prompt_by_id(session, trend_id)
    if not trend_is_public(prompt):
        raise HTTPException(status_code=404, detail="Trend not found")
    return prompt


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
    result = await session.execute(
        select(Generation)
        .where(Generation.user_id == user_id, Generation.input_params.like(f"%{marker}%"))
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
        }
    )
    generation.input_params = json.dumps(existing, ensure_ascii=False, separators=(",", ":"))
    await session.commit()


@router.get("/trends")
async def list_trends(
    kind: str | None = Query(default=None, pattern="^(image|video)$"),
    limit: int = Query(default=80, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> list[dict[str, Any]]:
    del user
    prompts = await get_prompts_by_tag(session, TREND_TAG, limit=limit)
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
        raise HTTPException(status_code=422, detail="Upload one JPEG, PNG, WebP, HEIC, HEIF or AVIF photo")
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
    return {**trend_public_payload(await _get_public_trend(session, trend_id)), "prompt_hidden": True}


@router.post("/trends/{trend_id}/run", status_code=202)
async def run_trend(
    trend_id: int,
    body: TrendRunRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    existing = await _find_idempotent_trend_run(
        session,
        user_id=user.id,
        idempotency_key=body.idempotency_key,
    )
    if existing is not None:
        await session.refresh(user)
        return {"ok": True, "task": _task_payload(GenerationOut.model_validate(existing, from_attributes=True)), "credits": _credits_out(user.credits)}

    trend = await _get_public_trend(session, trend_id)
    kind = trend_kind(trend)
    if not trend.model:
        raise HTTPException(status_code=409, detail="Trend has no configured model")
    await _validated_model(session, trend.model, kind)
    asset = verify_uploaded_asset(body.asset_id, user_id=user.id, expected_kind="image")
    asset["asset_id"] = body.asset_id
    settings_payload = trend_settings(trend)
    asset_url = str(asset["url"])

    if kind == "video":
        scenario = str(settings_payload.get("scenario") or "image").lower()
        mode = "image" if scenario in {"image", "imgtxt", "i2v"} else "image"
        task = await create_video_generation(
            body=VideoGenRequest(
                model=trend.model,
                prompt="Использовать скрытый трендовый промпт",
                prompt_id=trend.id,
                mode=mode,
                image_url=asset_url,
                reference_urls=[],
                duration=_safe_int(settings_payload.get("duration"), 5),
                aspect_ratio=settings_payload.get("ratio"),
                resolution=settings_payload.get("resolution"),
            ),
            session=session,
            user=user,
            surface="web",
        )
    else:
        task = await create_image_generation(
            body=ImageGenRequest(
                model=trend.model,
                prompt="Использовать скрытый трендовый промпт",
                prompt_id=trend.id,
                aspect_ratio=settings_payload.get("ratio"),
                quality=str(settings_payload.get("quality") or "basic"),
                count=max(1, min(6, _safe_int(settings_payload.get("count"), 1))),
                reference_url=asset_url,
                reference_urls=[asset_url],
            ),
            session=session,
            user=user,
            surface="web",
        )

    await _patch_trend_snapshot(
        session,
        generation_id=task.id,
        trend=trend,
        settings_payload=settings_payload,
        asset_payload=asset,
        idempotency_key=body.idempotency_key,
    )
    await session.refresh(user)
    return {"ok": True, "task": _task_payload(task), "credits": _credits_out(user.credits)}


@router.get("/trends/{trend_id}/link")
async def trend_link(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, str]:
    del user
    await _get_public_trend(session, trend_id)
    username = str(getattr(settings, "BOT_USERNAME", "") or "").strip().lstrip("@")
    link = f"https://t.me/{username}?startapp=trend_{trend_id}" if username else ""
    return {"link": link, "start_param": f"trend_{trend_id}"}


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
    valid = _looks_like_video(data, content_type) if kind == "video" else _looks_like_image(data, content_type)
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
    await _validated_model(session, body.model, body.kind)
    preview_url = _validate_preview_url(body.preview_url)
    prompt = await create_prompt(
        session,
        author_id=user.id,
        title=body.title.strip(),
        description=body.description.strip(),
        category=PromptCategory.photo if body.kind == "image" else PromptCategory.other,
        prompt_text=body.prompt_template.strip(),
        preview_url=preview_url,
        model=body.model,
        tags=build_trend_tags(body.kind, body.settings),
        is_public=True,
    )
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
    if body.model is not None:
        await _validated_model(session, body.model, kind)
        prompt.model = body.model
    if body.title is not None:
        prompt.title = body.title.strip()
    if body.description is not None:
        prompt.description = body.description.strip()
    if body.prompt_template is not None:
        prompt.prompt_text = body.prompt_template.strip()
    if body.preview_url is not None:
        prompt.preview_url = _validate_preview_url(body.preview_url)
    if body.settings is not None:
        prompt.tags = build_trend_tags(kind, body.settings)
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
