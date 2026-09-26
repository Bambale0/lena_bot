"""Higgsfield Seedance 2.5 Video Edit admin-evaluation adapter.

This module is intentionally isolated from APIX production Seedance routing.
It exposes the provider's published video-edit payload for controlled admin
quality tests while reusing APIX's authenticated Higgsfield transport.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

from api import higgsfield_client
from api.public_files import mirror_url
from core.config import settings

ENDPOINT = "bytedance/seedance-2.5/video-edit"
RESOLUTIONS = ("480p", "720p")
BITRATE_MODES = ("standard", "high")
MAX_IMAGE_REFS = 30
MAX_VIDEO_REFS = 10
MAX_AUDIO_REFS = 10

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    value = str(settings.HIGGSFIELD_CREDENTIALS or "").strip()
    key_id, sep, key_secret = value.partition(":")
    return bool(sep and key_id.strip() and key_secret.strip())


def _public_url(value: Any, *, label: str) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label} must be a public HTTP(S) URL")
    return url


def _urls(values: Any, *, label: str, limit: int) -> list[str]:
    if not values:
        return []
    raw = [values] if isinstance(values, str) else list(values)
    normalized = list(
        dict.fromkeys(
            _public_url(value, label=label)
            for value in raw
            if str(value or "").strip()
        )
    )
    if len(normalized) > limit:
        raise ValueError(f"Seedance 2.5 Video Edit supports at most {limit} {label}s")
    return normalized


def build_video_edit_payload(
    *,
    prompt: str,
    video_url: str,
    image_urls: Any = None,
    video_urls: Any = None,
    audio_urls: Any = None,
    resolution: str = "720p",
    bitrate_mode: str = "high",
    generate_audio: bool = True,
) -> dict[str, Any]:
    text = str(prompt or "").strip()
    if not text:
        raise ValueError("Seedance 2.5 Video Edit prompt is required")

    source_video = _public_url(video_url, label="source video")
    selected_resolution = str(resolution or "720p").strip()
    if selected_resolution not in RESOLUTIONS:
        raise ValueError(
            "Seedance 2.5 Video Edit resolution must be 480p or 720p"
        )
    selected_bitrate = str(bitrate_mode or "high").strip().lower()
    if selected_bitrate not in BITRATE_MODES:
        raise ValueError(
            "Seedance 2.5 Video Edit bitrate must be standard or high"
        )

    images = _urls(image_urls, label="image reference", limit=MAX_IMAGE_REFS)
    videos = _urls(video_urls, label="video reference", limit=MAX_VIDEO_REFS)
    audios = _urls(audio_urls, label="audio reference", limit=MAX_AUDIO_REFS)

    payload: dict[str, Any] = {
        "prompt": text,
        "video_url": source_video,
    }
    if images:
        payload["image_urls"] = images
    if videos:
        payload["video_urls"] = videos
    if audios:
        payload["audio_urls"] = audios
    payload["resolution"] = selected_resolution
    payload["bitrate_mode"] = selected_bitrate
    payload["generate_audio"] = bool(generate_audio)
    return payload


async def create_video_edit_task(**kwargs: Any) -> str:
    payload = build_video_edit_payload(**kwargs)
    request_id = await higgsfield_client.submit(ENDPOINT, payload)
    logger.info(
        "Higgsfield Seedance 2.5 Video Edit submitted request_id=%s images=%d videos=%d audios=%d resolution=%s bitrate=%s",
        request_id,
        len(payload.get("image_urls") or []),
        len(payload.get("video_urls") or []),
        len(payload.get("audio_urls") or []),
        payload["resolution"],
        payload["bitrate_mode"],
    )
    return request_id


async def poll_video_edit(request_id: str) -> str | None:
    url = await higgsfield_client.poll_video_status(request_id)
    if not url:
        return None
    mirrored = await mirror_url(url, subdir="provider-results")
    if mirrored != url:
        logger.info(
            "Higgsfield Seedance 2.5 Video Edit result mirrored request_id=%s",
            request_id,
        )
    return mirrored
