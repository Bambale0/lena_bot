from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import mimetypes
import shutil
import socket
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageFilter, ImageOps

from core.config import settings

UPLOAD_ROOT = Path(settings.STATIC_UPLOAD_DIR)
_MAX_IMAGE_MIRROR_BYTES = 30 * 1024 * 1024
_MAX_AUDIO_MIRROR_BYTES = 100 * 1024 * 1024
_MAX_VIDEO_MIRROR_BYTES = 500 * 1024 * 1024
_MIRROR_CHUNK_BYTES = 1024 * 1024


def get_static_upload_mount_path() -> str:
    return settings.STATIC_UPLOAD_URL_PATH


def get_static_upload_directory() -> Path:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return UPLOAD_ROOT


def _safe_upload_relative_path(filename: str) -> Path:
    rel = Path(str(filename).strip("/"))
    if rel.is_absolute() or ".." in rel.parts or not rel.name:
        raise ValueError("invalid upload filename")
    return rel


def _normalized_upload_url_path(value: str | None) -> str:
    cleaned = str(value or "").strip("/")
    return f"/{cleaned}" if cleaned else ""


def _public_upload_base_url() -> str:
    configured = str(getattr(settings, "STATIC_UPLOAD_PUBLIC_BASE_URL", "") or "").strip()
    return (configured or settings.WEBHOOK_URL).rstrip("/")


def _public_upload_url_path() -> str:
    configured = _normalized_upload_url_path(
        getattr(settings, "STATIC_UPLOAD_PUBLIC_URL_PATH", "")
    )
    return configured or _normalized_upload_url_path(settings.STATIC_UPLOAD_URL_PATH)


def public_upload_url(filename: str) -> str:
    base = _public_upload_base_url()
    path = _public_upload_url_path().strip("/")
    rel = str(_safe_upload_relative_path(filename)).replace("\\", "/")
    return f"{base}/{path}/{rel}"


def _configured_public_hosts() -> set[str]:
    hosts: set[str] = set()
    for value in (
        settings.WEBHOOK_URL,
        getattr(settings, "WEB_PUBLIC_URL", ""),
        getattr(settings, "STATIC_UPLOAD_PUBLIC_BASE_URL", ""),
    ):
        host = urlparse(str(value or "")).netloc.lower()
        if host:
            hosts.add(host)
    return hosts


def _configured_upload_prefixes() -> tuple[str, ...]:
    prefixes: list[str] = []
    for value in (
        settings.STATIC_UPLOAD_URL_PATH,
        getattr(settings, "STATIC_UPLOAD_PUBLIC_URL_PATH", ""),
    ):
        normalized = _normalized_upload_url_path(value)
        if normalized:
            prefix = normalized.rstrip("/") + "/"
            if prefix not in prefixes:
                prefixes.append(prefix)
    return tuple(prefixes)


def _public_url_for_local_path(path: Path) -> str | None:
    try:
        rel = path.relative_to(UPLOAD_ROOT)
    except ValueError:
        return None
    return public_upload_url(str(rel).replace("\\", "/"))


def local_upload_path_from_url(url: str | None) -> Path | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc and parsed.netloc.lower() not in _configured_public_hosts():
        return None
    path = unquote(parsed.path if parsed.scheme else url)
    upload_prefix = next(
        (prefix for prefix in _configured_upload_prefixes() if path.startswith(prefix)),
        None,
    )
    if upload_prefix is None:
        return None
    rel_raw = path.removeprefix(upload_prefix)
    try:
        rel = _safe_upload_relative_path(rel_raw)
    except ValueError:
        return None
    return UPLOAD_ROOT / rel


def public_url_is_available(url: str | None) -> bool:
    """
    Return False only for configured local upload URLs whose file is missing.

    External provider URLs are considered available because this process cannot
    cheaply or reliably prove their existence while serializing API data.
    """
    path = local_upload_path_from_url(url)
    if path is None:
        return bool(url)
    return path.exists() and path.is_file()


def _reject_private_url_targets(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("unsupported mirror URL")
    if parsed.username or parsed.password:
        raise ValueError("credentials are not allowed in mirror URL")

    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("mirror URL host does not resolve") from exc

    checked: set[str] = set()
    for info in infos:
        ip_text = str(info[4][0])
        if ip_text in checked:
            continue
        checked.add(ip_text)
        ip = ipaddress.ip_address(ip_text)
        if not ip.is_global:
            raise ValueError("mirror URL host resolves to a non-public address")


def _mirror_size_limit(content_type: str | None) -> int:
    if is_video_content_type(content_type):
        return _MAX_VIDEO_MIRROR_BYTES
    if is_audio_content_type(content_type):
        return _MAX_AUDIO_MIRROR_BYTES
    return _MAX_IMAGE_MIRROR_BYTES


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
        return _public_url_for_local_path(path) or url

    image_path = path.with_suffix(ext)
    if not image_path.exists():
        image_path.write_bytes(data)
    return _public_url_for_local_path(image_path) or url


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
        return _public_url_for_local_path(png_path) or image_url
    except Exception:
        return image_url


def preview_public_image_url(url: str | None, *, max_size: int = 768, quality: int = 82) -> str | None:
    path = local_upload_path_from_url(ensure_public_image_url(url) or url)
    if not url or not path or not path.exists() or not path.is_file():
        return url

    if "_preview_" in path.stem and path.suffix.lower() == ".webp":
        return _public_url_for_local_path(path) or url

    try:
        stat = path.stat()
    except OSError:
        return url

    digest = hashlib.sha256(f"{path.name}:{stat.st_mtime_ns}:{max_size}:{quality}".encode()).hexdigest()[:16]
    preview_path = path.with_name(f"{path.stem}_preview_{max_size}_{digest}.webp")
    if preview_path.exists() and preview_path.is_file():
        return _public_url_for_local_path(preview_path) or url

    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            if "A" not in image.getbands():
                image = image.convert("RGB")
            image.save(preview_path, format="WEBP", quality=quality, method=6)
        return _public_url_for_local_path(preview_path) or url
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
        return _public_url_for_local_path(fitted_path) or image_url

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
            return _public_url_for_local_path(fitted_path) or image_url
    except Exception:
        return image_url


def save_public_file(data: bytes, content_type: str | None = None, *, subdir: str | None = None) -> str:
    upload_dir = get_static_upload_directory()
    if is_video_content_type(content_type):
        ext = detect_video_extension(data, content_type)
    elif is_audio_content_type(content_type):
        ext = detect_audio_extension(data, content_type)
    else:
        ext = detect_image_extension(data, content_type)
    digest = hashlib.sha256(data).hexdigest()[:32]
    filename = f"{digest}{ext}"
    rel_name = f"{subdir.strip('/')}/{filename}" if subdir else filename
    rel = _safe_upload_relative_path(rel_name)
    path = upload_dir / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return public_upload_url(str(rel))


def _download_public_url(url: str) -> tuple[bytes, str | None]:
    _reject_private_url_targets(url)
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; APIXMirror/1.0)"})
    with urlopen(req, timeout=25) as resp:
        final_url = getattr(resp, "url", "") or resp.geturl()
        content_type = resp.headers.get("Content-Type")
        _reject_private_url_targets(final_url)
        max_bytes = _mirror_size_limit(content_type)
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > max_bytes:
            raise ValueError("mirror URL response is too large")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(_MIRROR_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError("mirror URL response exceeded size limit")
            chunks.append(chunk)
        data = b"".join(chunks)
    return data, content_type


async def mirror_url(url: str, *, subdir: str | None = None) -> str:
    """Mirror public URLs into local static storage when possible.

    Pass ``subdir="feed"`` for public feed media so long-lived feed files are
    isolated from temporary user uploads and safer to back up/retain.
    """
    if not url:
        return url

    local_path = local_upload_path_from_url(url)
    if local_path is not None:
        suffix = local_path.suffix.lower()
        if subdir:
            try:
                rel = local_path.relative_to(UPLOAD_ROOT)
            except ValueError:
                rel = Path(local_path.name)
            if rel.parts and rel.parts[0] == subdir and local_path.exists():
                return _public_url_for_local_path(local_path) or url
            if not local_path.exists() or not local_path.is_file():
                return url
            target_dir = get_static_upload_directory() / subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / local_path.name
            if target.resolve() != local_path.resolve():
                await asyncio.to_thread(shutil.copy2, local_path, target)
            return _public_url_for_local_path(target) or url
        if suffix in {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".opus", ".mp4", ".webm", ".mov"}:
            return _public_url_for_local_path(local_path) or url
        return ensure_public_image_url(url) or url

    try:
        data, content_type = await asyncio.to_thread(_download_public_url, url)
    except Exception:
        return url

    try:
        return save_public_file(data, content_type, subdir=subdir)
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
