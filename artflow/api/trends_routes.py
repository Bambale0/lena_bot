from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_auth import get_miniapp_user
from api.public_files import save_public_file
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
from db.models import GenerationType, PromptCategory, User, UserPrompt
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


def _require_admin(user: User) -> None:
    if not getattr(user, "tg_id", None) or user.tg_id not in settings.ADMIN_IDS:
        raise HTTPException(status_code=403, detail="Admin access required")


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


@router.post("/trends/{trend_id}/prepare")
async def prepare_trend(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, Any]:
    del user
    prompt = await _get_public_trend(session, trend_id)
    if not prompt.model:
        raise HTTPException(status_code=409, detail="Trend has no model")
    await _validated_model(session, prompt.model, trend_kind(prompt))
    return {
        "id": prompt.id,
        "prompt_id": prompt.id,
        "kind": trend_kind(prompt),
        "title": prompt.title,
        "description": prompt.description,
        "preview_url": prompt.preview_url,
        "model": prompt.model,
        "settings": trend_settings(prompt),
        "prompt_hidden": True,
    }


@router.get("/trends/{trend_id}/link")
async def trend_link(
    trend_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_miniapp_user),
) -> dict[str, str]:
    del user
    await _get_public_trend(session, trend_id)
    username = str(getattr(settings, "BOT_USERNAME", "") or "").strip().lstrip("@")
    link = f"https://t.me/{username}?start=trend_{trend_id}" if username else ""
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
