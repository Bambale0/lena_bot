from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse

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


def local_upload_path_from_url(url: str | None) -> Path | None:
    if not url:
        return None
    parsed = urlparse(url)
    path = unquote(parsed.path if parsed.scheme else url)
    upload_prefix = "/" + settings.STATIC_UPLOAD_URL_PATH.strip("/") + "/"
    if not path.startswith(upload_prefix):
        return None
    filename = Path(path.removeprefix(upload_prefix)).name
    if not filename:
        return None
    return UPLOAD_ROOT / filename


def public_url_is_available(url: str | None) -> bool:
    """
    Return False only for local /static/upload URLs whose file is missing.

    External provider/CDN URLs are considered available because this process
    cannot cheaply or reliably prove their existence while serializing API data.
    """
    path = local_upload_path_from_url(url)
    if path is None:
        return bool(url)
    return path.exists() and path.is_file()


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


def detect_video_extension(data: bytes, content_type: str | None = None) -> str:
    """Return KIE-friendly video extension based on content type or magic bytes."""
    ct = (content_type or "").lower()

    if "mp4" in ct or "mpeg" in ct:
        return ".mp4"
    if "webm" in ct:
        return ".webm"
    if "mov" in ct or "quicktime" in ct:
        return ".mov"
    if "ogg" in ct or "ogv" in ct:
        return ".ogg"

    # Telegram video files are typically mp4
    if data[:4] == b"ftyp":
        return ".mp4"
    if data[:4] == b"RIFF":
        return ".webm"

    return ".mp4"


def is_video_content_type(content_type: str | None) -> bool:
    ct = (content_type or "").lower()
    return any(kw in ct for kw in ("video", "mp4", "webm", "mov", "ogg", "quicktime"))


def ensure_public_image_url(url: str | None) -> str | None:
    """
    Return a Telegram/KIE-friendly public image URL.

    Early mirrored Telegram photos could be stored under .bin names even when
    their bytes were JPEG. Telegram is much more reliable with a real image
    extension, so lazily create a sibling file with the detected suffix.
    """
    path = local_upload_path_from_url(url)
    if not url or not path or not path.exists() or not path.is_file():
        return url

    data = path.read_bytes()
    ext = detect_image_extension(data)
    if path.suffix.lower() == ext:
        return url

    image_path = path.with_suffix(ext)
    if not image_path.exists():
        image_path.write_bytes(data)
    return public_upload_url(image_path.name)


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


async def mirror_telegram_file(bot, file_id: str, is_video: bool = False) -> str:
    """
    Download Telegram file and mirror it to public static upload directory.
    Returns KIE-compatible public URL with real image/video extension.
    """
    file = await bot.get_file(file_id)
    downloaded = await bot.download_file(file.file_path)
    data = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)

    # Detect if this is actually a video file based on content
    # (aiogram File object has no mime_type, so derive from file path)
    guessed_mime, _ = mimetypes.guess_type(file.file_path or "")
    if not is_video and is_video_content_type(guessed_mime):
        is_video = True

    if is_video:
        upload_dir = get_static_upload_directory()
        ext = detect_video_extension(data, guessed_mime)
        digest = hashlib.sha256(data).hexdigest()[:32]
        filename = f"{digest}{ext}"
        video_path = upload_dir / filename
        video_path.write_bytes(data)
        return public_upload_url(filename)

    return save_public_file(data)
