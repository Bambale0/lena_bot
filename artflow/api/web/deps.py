from __future__ import annotations

from typing import Any

from fastapi import Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from api.miniapp_auth import verify_web_auth_token
from api.web_auth_constants import WEB_AUTH_COOKIE_NAME
from db import repository as repo
from db.session import get_session


_MISSING = object()


def ok(data: Any = _MISSING) -> dict[str, Any]:
    if data is _MISSING:
        return {"ok": True}
    return {"ok": True, "data": data}


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"ok": False, "error": message})


def _dev_auth_enabled() -> bool:
    if str(getattr(settings, "ENV", "")).lower() == "production":
        return False
    return bool(getattr(settings, "APIX_WEB_DEV_AUTH", False))


async def get_web_user_or_none(
    request: Request,
    session: AsyncSession = Depends(get_session),
    x_dev_tg_id: str | None = Header(default=None, alias="X-Dev-Tg-Id"),
    x_web_auth_token: str | None = Header(default=None, alias="X-Web-Auth-Token"),
):
    web_auth_token = x_web_auth_token or request.cookies.get(WEB_AUTH_COOKIE_NAME)
    if web_auth_token:
        tg_id = verify_web_auth_token(web_auth_token)
        user = await repo.get_user_by_tg_id(session, tg_id)
        if not user or getattr(user, "is_banned", False):
            return None
        return user

    if not _dev_auth_enabled():
        return None
    if not x_dev_tg_id:
        return None
    try:
        tg_id = int(x_dev_tg_id)
    except (TypeError, ValueError):
        return None
    user = await repo.get_user_by_tg_id(session, tg_id)
    if not user or getattr(user, "is_banned", False):
        return None
    return user
