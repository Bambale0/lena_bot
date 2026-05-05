from __future__ import annotations

import hashlib
from pathlib import Path

from core.config import settings

UPLOAD_ROOT = Path(settings.STATIC_UPLOAD_DIR)


def get_static_upload_mount_path() -> str:
    return settings.STATIC_UPLOAD_URL_PATH


def get_static_upload_directory() -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return UPLOAD_ROOT


def public_upload_url(filename: str) -> str:
    base = settings.WEBHOOK_URL.rstrip("/")
    path = settings.STATIC_UPLOAD_URL_PATH.strip("/")
    return f"{base}/{path}/{filename}"


def detect_image_extension(data: bytes, content_type: str | None = None) -> str:
    """Return KIE-friendly image extension. Never return .bin for image refs."""
    ct = (content_type or "").lower()

    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "png" in ct:
        return ".png"
    if "webp" in ct:
        return ".webp"

    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return ".webp"

    # Telegram PhotoSize is JPEG in practice. KIE rejects .bin.
    return ".jpg"


def save_public_file(data: bytes, content_type: str | None = None) -> str:
    upload_dir = get_static_upload_directory()
    ext = detect_image_extension(data, content_type)
    digest = hashlib.sha256(data).hexdigest()[:32]
    filename = f"{digest}{ext}"
    path = upload_dir / filename
    path.write_bytes(data)
    return public_upload_url(filename)


async def mirror_url(url: str) -> str:
    """
    Backward-compatible helper.

    Older code imports mirror_url from api.public_files.
    For now it returns the URL as-is unless another implementation is needed.
    Generated Telegram uploads should use save_public_file(...), not this.
    """
    return url


async def mirror_telegram_file(bot, file_id: str) -> str:
    """
    Download Telegram file and mirror it to public static upload directory.
    Returns KIE-compatible public URL with real image extension.
    """
    file = await bot.get_file(file_id)
    downloaded = await bot.download_file(file.file_path)
    data = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    return save_public_file(data)
