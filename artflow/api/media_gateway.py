"""Shared media preparation for provider-bound generation requests.

Local APIX uploads are validated before provider billing, probed for image/video
metadata and moved to KIE file storage. External HTTPS URLs are preserved
because providers fetch them directly; callers may pass trusted metadata when
pre-validating remote uploads at the Telegram/Mini App boundary.
"""
from __future__ import annotations

import asyncio
import json
import mimetypes
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image

from api import kieai_client
from api.public_files import local_upload_path_from_url


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


@dataclass(frozen=True)
class MediaProbe:
    width: int | None = None
    height: int | None = None
    duration_seconds: float | None = None

    @property
    def aspect_ratio(self) -> float | None:
        if not self.width or not self.height:
            return None
        return self.width / self.height


@dataclass(frozen=True)
class MediaPolicy:
    kind: MediaKind
    max_bytes: int | None = None
    max_items: int | None = None
    upload_path: str | None = None
    allowed_mime_types: frozenset[str] = frozenset()
    allowed_mime_prefixes: tuple[str, ...] = ()
    min_width: int | None = None
    min_height: int | None = None
    min_aspect_ratio: float | None = None
    max_aspect_ratio: float | None = None
    min_duration_seconds: float | None = None
    max_duration_seconds: float | None = None


IMAGE_POLICY = MediaPolicy(
    kind=MediaKind.IMAGE,
    upload_path="images/apix-refs",
    allowed_mime_types=frozenset({"image/jpeg", "image/png", "image/webp"}),
)
GROK_IMAGE_POLICY = MediaPolicy(
    kind=MediaKind.IMAGE,
    max_bytes=10 * 1024 * 1024,
    max_items=1,
    upload_path="images/apix-grok-refs",
    allowed_mime_types=frozenset({"image/jpeg", "image/png", "image/webp"}),
)
VIDEO_POLICY = MediaPolicy(
    kind=MediaKind.VIDEO,
    upload_path="videos/apix-refs",
    allowed_mime_types=frozenset(
        {
            "video/mp4",
            "video/quicktime",
            "video/x-matroska",
            "video/webm",
        }
    ),
)
AUDIO_POLICY = MediaPolicy(
    kind=MediaKind.AUDIO,
    upload_path="audio/apix-refs",
    allowed_mime_types=frozenset(
        {
            "audio/mpeg",
            "audio/mp3",
            "audio/wav",
            "audio/x-wav",
            "audio/mp4",
            "audio/aac",
            "audio/flac",
            "audio/ogg",
            "audio/opus",
        }
    ),
)
KLING_ELEMENT_IMAGE_POLICY = MediaPolicy(
    kind=MediaKind.IMAGE,
    max_bytes=10 * 1024 * 1024,
    max_items=4,
    upload_path="images/apix-kling-elements",
    allowed_mime_types=frozenset({"image/jpeg", "image/png"}),
)
KLING_MOTION_26_IMAGE_POLICY = MediaPolicy(
    kind=MediaKind.IMAGE,
    max_bytes=10 * 1024 * 1024,
    max_items=1,
    upload_path="images/apix-kling-motion",
    allowed_mime_types=frozenset({"image/jpeg", "image/png"}),
)
KLING_MOTION_30_IMAGE_POLICY = MediaPolicy(
    kind=MediaKind.IMAGE,
    max_bytes=10 * 1024 * 1024,
    max_items=1,
    upload_path="images/apix-kling-motion",
    allowed_mime_types=frozenset({"image/jpeg", "image/png"}),
    min_width=341,
    min_height=341,
    min_aspect_ratio=2 / 5,
    max_aspect_ratio=5 / 2,
)
KLING_MOTION_26_VIDEO_POLICY = MediaPolicy(
    kind=MediaKind.VIDEO,
    max_bytes=100 * 1024 * 1024,
    max_items=1,
    upload_path="videos/apix-kling-motion",
    allowed_mime_types=frozenset({"video/mp4", "video/quicktime", "video/x-matroska"}),
    min_duration_seconds=3,
    max_duration_seconds=30,
)
KLING_MOTION_30_VIDEO_POLICY = MediaPolicy(
    kind=MediaKind.VIDEO,
    max_bytes=100 * 1024 * 1024,
    max_items=1,
    upload_path="videos/apix-kling-motion",
    allowed_mime_types=frozenset({"video/mp4", "video/quicktime"}),
    min_width=341,
    min_height=341,
    min_aspect_ratio=2 / 5,
    max_aspect_ratio=5 / 2,
    min_duration_seconds=3,
    max_duration_seconds=30,
)


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return (guessed or "application/octet-stream").split(";", 1)[0].lower()


def _probe_image(path: Path) -> MediaProbe:
    try:
        with Image.open(path) as image:
            return MediaProbe(width=int(image.width), height=int(image.height))
    except Exception as exc:
        raise ValueError(f"Could not read image metadata for {path.name}: {exc}") from exc


def _probe_video_sync(path: Path) -> MediaProbe:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        process = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ffprobe is required for provider video validation") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Video metadata probe timed out for {path.name}") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "ffprobe failed").strip()
        raise ValueError(f"Could not read video metadata for {path.name}: {details}") from exc

    try:
        payload = json.loads(process.stdout or "{}")
        streams = payload.get("streams") or []
        stream = streams[0] if streams and isinstance(streams[0], dict) else {}
        format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
        duration_raw = format_data.get("duration")
        duration = float(duration_raw) if duration_raw not in (None, "") else None
        return MediaProbe(
            width=int(stream["width"]) if stream.get("width") else None,
            height=int(stream["height"]) if stream.get("height") else None,
            duration_seconds=duration,
        )
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError(f"Malformed ffprobe output for {path.name}") from exc


async def probe_local_media(path: Path, kind: MediaKind) -> MediaProbe:
    if kind == MediaKind.IMAGE:
        return await asyncio.to_thread(_probe_image, path)
    if kind == MediaKind.VIDEO:
        return await asyncio.to_thread(_probe_video_sync, path)
    return MediaProbe()


def _validate_probe(path: Path, policy: MediaPolicy, probe: MediaProbe) -> None:
    if policy.min_width is not None and (probe.width is None or probe.width < policy.min_width):
        raise ValueError(f"{path.name} width must be at least {policy.min_width}px")
    if policy.min_height is not None and (probe.height is None or probe.height < policy.min_height):
        raise ValueError(f"{path.name} height must be at least {policy.min_height}px")

    ratio = probe.aspect_ratio
    if policy.min_aspect_ratio is not None and (ratio is None or ratio < policy.min_aspect_ratio):
        raise ValueError(f"{path.name} aspect ratio is below {policy.min_aspect_ratio:g}")
    if policy.max_aspect_ratio is not None and (ratio is None or ratio > policy.max_aspect_ratio):
        raise ValueError(f"{path.name} aspect ratio exceeds {policy.max_aspect_ratio:g}")

    duration = probe.duration_seconds
    if policy.min_duration_seconds is not None and (
        duration is None or duration < policy.min_duration_seconds
    ):
        raise ValueError(
            f"{path.name} duration must be at least {policy.min_duration_seconds:g} seconds"
        )
    if policy.max_duration_seconds is not None and (
        duration is None or duration > policy.max_duration_seconds
    ):
        raise ValueError(
            f"{path.name} duration must not exceed {policy.max_duration_seconds:g} seconds"
        )


def _validate_local_file(path: Path, policy: MediaPolicy) -> str:
    if not path.exists() or not path.is_file():
        raise ValueError(f"Media file does not exist: {path.name}")
    if policy.max_bytes is not None and path.stat().st_size > policy.max_bytes:
        raise ValueError(
            f"{policy.kind.value} file {path.name} exceeds {policy.max_bytes} bytes"
        )
    content_type = _content_type(path)
    allowed = not policy.allowed_mime_types and not policy.allowed_mime_prefixes
    if content_type in policy.allowed_mime_types:
        allowed = True
    if any(content_type.startswith(prefix) for prefix in policy.allowed_mime_prefixes):
        allowed = True
    if not allowed:
        raise ValueError(
            f"Unsupported {policy.kind.value} MIME type {content_type} for {path.name}"
        )
    return content_type


def _validate_external_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Provider media URL must be HTTP(S): {url!r}")


async def prepare_media_url(
    url: str | None,
    *,
    policy: MediaPolicy,
) -> str | None:
    if not url:
        return None
    value = str(url).strip()
    if not value:
        return None

    local_path = local_upload_path_from_url(value)
    if local_path is None:
        _validate_external_url(value)
        return value

    content_type = _validate_local_file(local_path, policy)
    requires_probe = any(
        item is not None
        for item in (
            policy.min_width,
            policy.min_height,
            policy.min_aspect_ratio,
            policy.max_aspect_ratio,
            policy.min_duration_seconds,
            policy.max_duration_seconds,
        )
    )
    if requires_probe:
        probe = await probe_local_media(local_path, policy.kind)
        _validate_probe(local_path, policy, probe)

    uploaded = await kieai_client.upload_file_stream(
        local_path.read_bytes(),
        filename=local_path.name,
        content_type=content_type,
        upload_path=policy.upload_path or f"{policy.kind.value}/apix-refs",
    )
    if not uploaded:
        raise RuntimeError(f"KIE upload returned no URL for {local_path.name}")
    return uploaded


async def prepare_media_urls(
    urls: list[str] | tuple[str, ...] | None,
    *,
    policy: MediaPolicy,
) -> list[str]:
    values = [str(item).strip() for item in (urls or []) if str(item).strip()]
    if policy.max_items is not None and len(values) > policy.max_items:
        raise ValueError(
            f"{policy.kind.value} references support at most {policy.max_items} item(s)"
        )
    prepared: list[str] = []
    for value in values:
        uploaded = await prepare_media_url(value, policy=policy)
        if uploaded:
            prepared.append(uploaded)
    return prepared
