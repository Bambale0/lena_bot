from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.web.deps import error_response, get_web_user_or_none, ok
from api.web.schemas import UserMe
from core.config import settings
from db.session import get_session

router = APIRouter(tags=["web"])


@router.get("/me")
async def me(
    session: AsyncSession = Depends(get_session),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")
    return ok(UserMe.from_user(user, admin_ids=settings.ADMIN_IDS).model_dump())
