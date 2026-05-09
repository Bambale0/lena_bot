"""Telegram WebApp initData verification for the mini-app API."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, unquote

from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db import repository as repo
from db.models import User
from db.session import get_session


TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _verify_init_data(init_data: str) -> dict:
    """Verify Telegram WebApp initData HMAC and return parsed user dict."""
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", "")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram initData signature")

    try:
        auth_date = int(params.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed auth_date in initData")
    if auth_date <= 0 or time.time() - auth_date > TELEGRAM_INIT_DATA_MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Telegram initData expired")

    raw_user = params.get("user")
    if not raw_user:
        raise HTTPException(status_code=401, detail="Missing user in initData")

    try:
        return json.loads(unquote(raw_user))
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed user field in initData")


async def get_miniapp_user(
    x_telegram_init_data: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="X-Telegram-Init-Data header required")

    tg_user = _verify_init_data(x_telegram_init_data)
    tg_id = tg_user.get("id")
    if not tg_id:
        raise HTTPException(status_code=401, detail="No user id in initData")

    user = await repo.get_user_by_tg_id(session, int(tg_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not registered — open the bot first")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="User is banned")

    return user
