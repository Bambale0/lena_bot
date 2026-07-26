"""Shared media preparation for provider-bound generation requests.

The gateway validates local APIX uploads before provider billing and moves them
to KIE file storage. External HTTPS URLs are preserved because providers fetch
them directly, while URL reachability remains a provider concern.
"""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from api import kieai_client
from api.public_files import local_upload_path_from_url


class MediaKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


@dataclass(frozen=True)
class MediaPolicy:
    kind: MediaKind
    max_bytes: int | None = None
    max_items: int | None = None
    upload_path: str | None = None
    allowed_mime_types: frozenset[str] = frozenset()
    allowed_mime_prefixes: tuple[str, ...] = ()


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


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return (guessed or "application/octet-stream").split(";", 1)[0].lower()


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
