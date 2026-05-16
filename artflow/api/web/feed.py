from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import FeedCard
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


@router.get("/feed")
async def feed(
    source: str = Query(default="feed", pattern="^(feed|recent|top|top_day)$"),
    limit: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if source in {"top", "top_day"}:
        cards = await repo.get_top_day_generations(session, limit=limit)
    else:
        cards = await repo.get_feed_generations(session, limit=limit)
    return ok([FeedCard.from_feed_card(card).model_dump() for card in cards])


@router.get("/feed/top")
async def feed_top(
    limit: int = Query(default=40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> dict:
    cards = await repo.get_top_day_generations(session, limit=limit)
    return ok([FeedCard.from_feed_card(card).model_dump() for card in cards])


@router.post("/feed/{generation_id}/like")
async def feed_like(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")
    if await repo.get_public_feed_generation(session, generation_id) is None:
        return error_response(404, "Generation not found")
    generation = await repo.like_feed_generation(session, generation_id)
    if generation is None:
        return error_response(404, "Generation not found")
    return ok({"id": generation.id, "likes": generation.likes_count})


@router.post("/feed/{generation_id}/share")
async def feed_share(
    generation_id: int,
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
) -> dict:
    if user is None:
        return error_response(401, "Authentication required")
    if await repo.get_public_feed_generation(session, generation_id) is None:
        return error_response(404, "Generation not found")
    generation = await repo.increment_feed_share(session, generation_id)
    if generation is None:
        return error_response(404, "Generation not found")
    return ok({"id": generation.id, "shares": generation.shares_count})
