from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageFilter, ImageOps

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


def detect_audio_extension(data: bytes, content_type: str | None = None) -> str:
    ct = (content_type or "").lower()

    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "wav" in ct or "wave" in ct:
        return ".wav"
    if "x-m4a" in ct or "m4a" in ct or "mp4a" in ct or "aac" in ct:
        return ".m4a"
    if "flac" in ct:
        return ".flac"
    if "ogg" in ct or "opus" in ct:
        return ".ogg"

    if data.startswith(b"ID3"):
        return ".mp3"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    if len(data) > 8 and data[4:8] == b"ftyp":
        return ".m4a"
    if data.startswith(b"fLaC"):
        return ".flac"
    if data.startswith(b"OggS"):
        return ".ogg"

    return ".mp3"


def is_audio_content_type(content_type: str | None) -> bool:
    ct = (content_type or "").lower()
    return any(kw in ct for kw in ("audio", "mpeg", "mp3", "wav", "wave", "m4a", "aac", "flac", "ogg", "opus"))


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


def ensure_provider_safe_png_url(url: str | None) -> str | None:
    """
    Return a PNG URL for local uploaded images so stricter providers like
    Nano Banana always receive a stable raster format.
    """
    image_url = ensure_public_image_url(url) or url
    path = local_upload_path_from_url(image_url)
    if not image_url or not path or not path.exists() or not path.is_file():
        return image_url

    try:
        with Image.open(path) as image:
            png_path = path.with_suffix('.png')
            if not png_path.exists():
                normalized = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
                normalized.save(png_path, format='PNG')
        return public_upload_url(png_path.name)
    except Exception:
        return image_url


def preview_public_image_url(url: str | None, *, max_size: int = 768, quality: int = 82) -> str | None:
    path = local_upload_path_from_url(ensure_public_image_url(url) or url)
    if not url or not path or not path.exists() or not path.is_file():
        return url

    if "_preview_" in path.stem and path.suffix.lower() == ".webp":
        return public_upload_url(path.name)

    try:
        stat = path.stat()
    except OSError:
        return url

    digest = hashlib.sha256(f"{path.name}:{stat.st_mtime_ns}:{max_size}:{quality}".encode()).hexdigest()[:16]
    preview_path = path.with_name(f"{path.stem}_preview_{max_size}_{digest}.webp")
    if preview_path.exists() and preview_path.is_file():
        return public_upload_url(preview_path.name)

    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            if "A" not in image.getbands():
                image = image.convert("RGB")
            image.save(preview_path, format="WEBP", quality=quality, method=6)
        return public_upload_url(preview_path.name)
    except Exception:
        return ensure_public_image_url(url) or url


def ensure_video_reference_aspect_url(
    url: str | None,
    *,
    min_ratio: float = 1 / 2.5,
    max_ratio: float = 2.5,
    max_side: int = 2048,
) -> str | None:
    """
    Return a local video-reference image URL whose aspect ratio provider APIs accept.

    Some video providers reject very tall/wide source images before generation
    starts. For local uploads we create a fitted JPEG with a blurred background
    instead of cropping the user reference. External URLs are returned unchanged.
    """
    image_url = ensure_public_image_url(url) or url
    path = local_upload_path_from_url(image_url)
    if not image_url or not path or not path.exists() or not path.is_file():
        return image_url

    try:
        stat = path.stat()
    except OSError:
        return image_url

    digest = hashlib.sha256(
        f"{path.name}:{stat.st_mtime_ns}:{min_ratio:.4f}:{max_ratio:.4f}:{max_side}".encode()
    ).hexdigest()[:16]
    fitted_path = path.with_name(f"{path.stem}_video_ref_{max_side}_{digest}.jpg")
    if fitted_path.exists() and fitted_path.is_file():
        return public_upload_url(fitted_path.name)

    try:
        with Image.open(path) as source:
            source = ImageOps.exif_transpose(source)
            if source.mode not in ("RGB", "RGBA"):
                source = source.convert("RGBA" if "A" in source.getbands() else "RGB")
            if "A" in source.getbands():
                base = Image.new("RGB", source.size, (8, 9, 18))
                base.paste(source, mask=source.getchannel("A"))
                source = base
            else:
                source = source.convert("RGB")

            width, height = source.size
            if width <= 0 or height <= 0:
                return image_url
            ratio = width / height
            needs_ratio_fit = ratio < min_ratio or ratio > max_ratio
            needs_resize = max(width, height) > max_side
            if not needs_ratio_fit and not needs_resize:
                return image_url

            target_width = width
            target_height = height
            if ratio < min_ratio:
                target_width = int(round(height * min_ratio))
            elif ratio > max_ratio:
                target_height = int(round(width / max_ratio))

            scale = min(1.0, max_side / max(target_width, target_height))
            canvas_size = (
                max(1, int(round(target_width * scale))),
                max(1, int(round(target_height * scale))),
            )
            background = ImageOps.fit(source.copy(), canvas_size, method=Image.Resampling.LANCZOS)
            background = background.filter(ImageFilter.GaussianBlur(radius=max(8, max(canvas_size) // 32)))
            background = ImageOps.autocontrast(background)

            foreground = ImageOps.contain(source.copy(), canvas_size, method=Image.Resampling.LANCZOS)
            offset = (
                (canvas_size[0] - foreground.size[0]) // 2,
                (canvas_size[1] - foreground.size[1]) // 2,
            )
            background.paste(foreground, offset)
            background.save(fitted_path, format="JPEG", quality=92, optimize=True)
            return public_upload_url(fitted_path.name)
    except Exception:
        return image_url


def save_public_file(data: bytes, content_type: str | None = None) -> str:
    upload_dir = get_static_upload_directory()
    if is_video_content_type(content_type):
        ext = detect_video_extension(data, content_type)
    elif is_audio_content_type(content_type):
        ext = detect_audio_extension(data, content_type)
    else:
        ext = detect_image_extension(data, content_type)
    digest = hashlib.sha256(data).hexdigest()[:32]
    filename = f"{digest}{ext}"
    path = upload_dir / filename
    path.write_bytes(data)
    return public_upload_url(filename)


def _download_public_url(url: str) -> tuple[bytes, str | None]:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; APIXMirror/1.0)"})
    with urlopen(req, timeout=25) as resp:
        data = resp.read()
        content_type = resp.headers.get("Content-Type")
    return data, content_type


async def mirror_url(url: str) -> str:
    """Mirror external public URLs into local static storage when possible."""
    if not url:
        return url

    local_path = local_upload_path_from_url(url)
    if local_path is not None:
        suffix = local_path.suffix.lower()
        if suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".mp4", ".webm", ".mov"}:
            return url
        return ensure_public_image_url(url) or url

    try:
        data, content_type = await asyncio.to_thread(_download_public_url, url)
    except Exception:
        return url

    try:
        return save_public_file(data, content_type)
    except Exception:
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
