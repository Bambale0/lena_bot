"""Bounded server-owned Kling 4 sources, shared by bot and web uploads."""

from __future__ import annotations

import math
import secrets
from pathlib import Path

from api.media_gateway import MediaKind, probe_local_media
from api.public_files import get_static_upload_directory, public_upload_url

MAX_ASSET_BYTES = 100 * 1024 * 1024  # APIX product upload limit, not a KIE model claim.
EXTENSIONS = {
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".aac": "audio",
    ".flac": "audio",
    ".ogg": "audio",
    ".opus": "audio",
}


async def store_kling4_asset(data: bytes, filename: str, *, user_id: int) -> dict:
    suffix = Path(filename).suffix.lower()
    kind = EXTENSIONS.get(suffix)
    if not kind or not data or len(data) > MAX_ASSET_BYTES:
        raise ValueError("Поддерживаются фото, видео и аудио до 100 МБ (лимит APIX)")
    name = f"kling4/{int(user_id)}/{secrets.token_hex(24)}{suffix}"
    path = get_static_upload_directory() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(data)
        probe = await probe_local_media(path, MediaKind(kind))
        if kind == "image" and (
            not probe.width or not probe.height or probe.width * probe.height > 40_000_000
        ):
            raise ValueError("Изображение: лимит APIX 40 Мп")
        if kind != "image" and (
            not probe.duration_seconds or not math.isfinite(probe.duration_seconds)
        ):
            raise ValueError("Не удалось прочитать медиафайл")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {
        "url": public_upload_url(name),
        "kind": kind,
        "size": len(data),
        "duration_seconds": probe.duration_seconds,
        "width": probe.width,
        "height": probe.height,
    }
