"""Telegram WebApp initData verification for the mini-app API."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, unquote

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from db import repository as repo
from db.models import User
from db.session import get_session

TELEGRAM_INIT_DATA_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
WEB_AUTH_TOKEN_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _web_auth_secret(bot_token: str | None = None) -> bytes:
    raw = f"apix-web-auth:{bot_token or settings.BOT_TOKEN}:{settings.WEBHOOK_SECRET}".encode()
    return hashlib.sha256(raw).digest()


def create_web_auth_token(tg_id: int, *, now: int | None = None) -> str:
    issued_at = int(now or time.time())
    payload = {
        "tg_id": int(tg_id),
        "iat": issued_at,
        "exp": issued_at + WEB_AUTH_TOKEN_MAX_AGE_SECONDS,
    }
    payload_part = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(_web_auth_secret(), payload_part.encode(), hashlib.sha256).digest()
    return f"{payload_part}.{_b64encode(signature)}"


def verify_web_auth_token(token: str) -> int:
    try:
        payload_part, signature_part = token.split(".", 1)
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed web auth token")

    expected = hmac.new(_web_auth_secret(), payload_part.encode(), hashlib.sha256).digest()
    try:
        received = _b64decode(signature_part)
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed web auth token")
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=401, detail="Invalid web auth token signature")

    try:
        payload = json.loads(_b64decode(payload_part))
        tg_id = int(payload.get("tg_id") or 0)
        exp = int(payload.get("exp") or 0)
    except Exception:
        raise HTTPException(status_code=401, detail="Malformed web auth token")
    if tg_id == 0 or exp <= int(time.time()):
        raise HTTPException(status_code=401, detail="Web auth token expired")
    return tg_id


def _verify_init_data(init_data: str, bot_token: str | None = None) -> dict:
    """Verify Telegram WebApp initData HMAC and return parsed user dict."""
    params = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = params.pop("hash", "")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    token = bot_token or settings.BOT_TOKEN
    secret_key = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
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


def verify_telegram_login_data(data: dict, bot_token: str | None = None) -> dict:
    """Verify Telegram Login Widget payload and return the authenticated user data."""
    received_hash = str(data.get("hash") or "")
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing Telegram login hash")

    check_items = []
    for key, value in data.items():
        if key == "hash" or value is None:
            continue
        check_items.append((key, str(value)))
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(check_items))
    secret_key = hashlib.sha256((bot_token or settings.BOT_TOKEN).encode()).digest()
    computed_hash = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram login signature")

    try:
        auth_date = int(data.get("auth_date") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Malformed auth_date in Telegram login data")
    if auth_date <= 0 or time.time() - auth_date > TELEGRAM_INIT_DATA_MAX_AGE_SECONDS:
        raise HTTPException(status_code=401, detail="Telegram login data expired")

    try:
        tg_id = int(data.get("id") or 0)
    except (TypeError, ValueError):
        tg_id = 0
    if tg_id <= 0:
        raise HTTPException(status_code=401, detail="Missing Telegram user id")

    return {**data, "id": tg_id}


async def get_miniapp_user(
    x_telegram_init_data: str | None = Header(default=None),
    x_web_auth_token: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    if x_telegram_init_data:
        tg_user = _verify_init_data(x_telegram_init_data)
        tg_id = tg_user.get("id")
    elif x_web_auth_token:
        tg_id = verify_web_auth_token(x_web_auth_token)
    else:
        raise HTTPException(status_code=401, detail="X-Telegram-Init-Data or X-Web-Auth-Token header required")
    if not tg_id:
        raise HTTPException(status_code=401, detail="No user id in initData")

    user = await repo.get_user_by_tg_id(session, int(tg_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not registered — open the bot first")
    if user.is_banned:
        raise HTTPException(status_code=403, detail="User is banned")

    return user
