from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db import repository as repo
from db.models import User
from db.session import get_session

MAX_INIT_DATA_AGE_SECONDS = 7 * 24 * 60 * 60


def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="Telegram initData is required")

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    data = dict(pairs)
    received_hash = data.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Telegram initData hash is missing")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Telegram initData is invalid")

    auth_date_raw = data.get("auth_date")
    if auth_date_raw:
        try:
            auth_date = datetime.fromtimestamp(int(auth_date_raw), tz=timezone.utc)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Telegram auth_date is invalid") from exc
        if (datetime.now(timezone.utc) - auth_date).total_seconds() > MAX_INIT_DATA_AGE_SECONDS:
            raise HTTPException(status_code=401, detail="Telegram initData is expired")

    user_raw = data.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="Telegram user is missing")

    try:
        data["user"] = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=401, detail="Telegram user payload is invalid") from exc
    return data


async def get_webapp_user(
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
    session: AsyncSession = Depends(get_session),
) -> User:
    data = verify_telegram_init_data(x_telegram_init_data, settings.BOT_TOKEN)
    try:
        tg_id = int(data["user"]["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Telegram user id is invalid") from exc

    user = await repo.get_user_by_tg_id(session, tg_id)
    if not user:
        raise HTTPException(status_code=404, detail="Сначала запусти бота командой /start")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="User is banned")
    return user
