from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import GenerationCard
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


@router.get("/history")
async def history(
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    generations = await repo.get_user_history(session, user.id, limit=limit)
    return ok([GenerationCard.from_generation(item).model_dump() for item in generations])
