from __future__ import annotations

import mimetypes
from pathlib import Path
from uuid import uuid4

import httpx
from aiogram import Bot

from core.config import settings


UPLOAD_ROOT = Path(settings.STATIC_UPLOAD_DIR)

_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
}


def public_upload_url(filename: str) -> str:
    base = settings.WEBHOOK_URL.rstrip("/")
    path = settings.STATIC_UPLOAD_URL_PATH.strip("/")
    return f"{base}/{path}/{filename}"


def _extension(content_type: str | None, fallback_url: str | None = None) -> str:
    if content_type:
        clean_type = content_type.split(";", 1)[0].strip().lower()
        if clean_type in _EXT_BY_CONTENT_TYPE:
            return _EXT_BY_CONTENT_TYPE[clean_type]
        guessed = mimetypes.guess_extension(clean_type)
        if guessed:
            return guessed

    if fallback_url:
        suffix = Path(fallback_url.split("?", 1)[0]).suffix.lower()
        if suffix:
            return suffix[:12]

    return ".bin"


async def save_bytes(data: bytes, *, content_type: str | None = None, fallback_url: str | None = None) -> str:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{_extension(content_type, fallback_url)}"
    path = UPLOAD_ROOT / filename
    path.write_bytes(data)
    return public_upload_url(filename)


async def mirror_url(url: str) -> str:
    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return await save_bytes(resp.content, content_type=resp.headers.get("content-type"), fallback_url=url)


async def mirror_telegram_file(bot: Bot, file_id: str | None) -> str | None:
    if not file_id:
        return None
    file = await bot.get_file(file_id)
    telegram_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    return await mirror_url(telegram_url)
