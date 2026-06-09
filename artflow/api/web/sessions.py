from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import ImageSessionCard, ImageSessionCreateRequest
from db import repository as repo
from db.models import ImageSessionStatus
from db.session import get_session

router = APIRouter(tags=["web"])


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
    last_generation = await repo.get_last_session_generation(session, image_session.id)
    hide_prompt = bool(getattr(last_generation, "source_feed_gen_id", None))
    return ok(ImageSessionCard.from_image_session(image_session, hide_prompt=hide_prompt).model_dump())


@router.post("/image-sessions")
async def create_image_session(
    body: ImageSessionCreateRequest,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    image_session = await repo.create_image_session(
        session=session,
        user_id=user.id,
        model=body.model.strip(),
        mode=body.mode.strip(),
        aspect_ratio=(body.aspect_ratio or "").strip() or None,
        quality=body.quality.strip(),
        count=body.count,
        base_prompt=(body.base_prompt or "").strip() or None,
        reference_url=(body.reference_url or "").strip() or None,
        reference_urls=[item.strip() for item in body.reference_urls if item and item.strip()],
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
    return ok(ImageSessionCard.from_image_session(image_session).model_dump())
