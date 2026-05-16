from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.miniapp_auth import create_web_auth_token, verify_telegram_login_data
from api.web.deps import ok
from api.web.schemas import UserMe
from core.config import settings
from db import repository as repo
from db.session import get_session

router = APIRouter(tags=["web"])


class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


def _bot_username() -> str:
    return str(getattr(settings, "BOT_USERNAME", "") or "").strip().lstrip("@")


@router.get("/auth/config")
async def auth_config() -> dict:
    return ok({"bot_username": _bot_username()})


@router.post("/auth/telegram-login")
async def telegram_login(
    body: TelegramLoginRequest,
    session: AsyncSession = Depends(get_session),
) -> dict:
    tg_user = verify_telegram_login_data(body.model_dump())
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

    return ok(
        {
            "token": create_web_auth_token(user.tg_id),
            "token_type": "web",
            "expires_in": 30 * 24 * 60 * 60,
            "user": UserMe.from_user(user, admin_ids=settings.ADMIN_IDS).model_dump(),
        }
    )
