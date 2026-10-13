from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_routes import _MJ_IMAGE_CAPS
from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import ImageSessionCard, ImageSessionCreateRequest
from bot.keyboards.models import IMAGE_CAPS
from core.feed_remix_prompt import generation_prompt_is_protected
from db import repository as repo
from db.models import Generation, ImageSessionStatus
from db.session import get_session

router = APIRouter(tags=["web"])


async def _session_has_protected_prompt(session: AsyncSession, image_session_id: int) -> bool:
    # Protection survives later ordinary generations: legacy session fields can
    # still contain an earlier author's prompt, regardless of the latest result.
    result = await session.execute(
        select(Generation.source_feed_gen_id, Generation.input_params)
        .where(Generation.image_session_id == image_session_id)
    )
    return any(generation_prompt_is_protected(generation) for generation in result.all())


@router.get("/image-sessions/active")
async def active_image_session(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    image_session = await repo.get_active_image_session(session, user.id)
    if image_session is None:
        return ok(None)
    hide_prompt = await _session_has_protected_prompt(session, image_session.id)
    return ok(ImageSessionCard.from_image_session(image_session, hide_prompt=hide_prompt).model_dump())


@router.post("/image-sessions")
async def create_image_session(
    body: ImageSessionCreateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    model = body.model.strip()
    reference_urls = list(dict.fromkeys(
        value.strip() for value in [body.reference_url, *body.reference_urls]
        if value and value.strip()
    ))
    caps = IMAGE_CAPS.get(model) or _MJ_IMAGE_CAPS.get(model, {})
    max_refs = int(caps.get("max_refs", 1) or 1)
    # The repository archives the previous active series, so validate first.
    # Empty draft sessions remain valid even for reference-required models.
    if len(reference_urls) > max_refs:
        return error_response(422, f"Model supports at most {max_refs} reference image(s)")
    image_session = await repo.create_image_session(
        session=session,
        user_id=user.id,
        model=model,
        mode=body.mode.strip(),
        aspect_ratio=(body.aspect_ratio or "").strip() or None,
        quality=body.quality.strip(),
        count=body.count,
        base_prompt=(body.base_prompt or "").strip() or None,
        reference_url=reference_urls[0] if reference_urls else None,
        reference_urls=reference_urls,
        # This endpoint creates solely from the authenticated user's input.
        # The request schema intentionally has no prompt_provenance field.
        prompt_provenance="user_supplied",
    )
    return ok(ImageSessionCard.from_image_session(image_session).model_dump())


@router.post("/image-sessions/{session_id}/archive")
async def archive_image_session(
    session_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    image_session = await repo.get_image_session(session, session_id, user_id=user.id)
    if image_session is None:
        return error_response(404, "Image session not found")
    image_session.status = ImageSessionStatus.archived
    image_session.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(image_session)
    hide_prompt = await _session_has_protected_prompt(session, image_session.id)
    return ok(ImageSessionCard.from_image_session(image_session, hide_prompt=hide_prompt).model_dump())
