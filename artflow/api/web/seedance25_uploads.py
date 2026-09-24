from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile

from api.public_files import save_public_file
from api.seedance25_adapter import validate_reference_video_metadata
from api.web.deps import error_response, get_web_user_or_none, ok

router = APIRouter(tags=["web"])

MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
_VIDEO_EXTENSIONS = {".mp4", ".mov"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".m4a", ".ogg"}


def _kind_and_limit(file: UploadFile) -> tuple[str | None, int, str | None]:
    suffix = Path(str(file.filename or "")).suffix.lower()
    content_type = str(file.content_type or "").lower()

    if suffix in _IMAGE_EXTENSIONS or content_type.startswith("image/"):
        if suffix and suffix not in _IMAGE_EXTENSIONS:
            return None, 0, "Seedance 2.5: unsupported image format"
        return "image", MAX_IMAGE_BYTES, None
    if suffix in _VIDEO_EXTENSIONS or content_type.startswith("video/"):
        if suffix not in _VIDEO_EXTENSIONS:
            return None, 0, "Seedance 2.5: reference video must be MP4 or MOV"
        return "video", MAX_VIDEO_BYTES, None
    if suffix in _AUDIO_EXTENSIONS or content_type.startswith("audio/"):
        if suffix and suffix not in _AUDIO_EXTENSIONS:
            return None, 0, "Seedance 2.5: unsupported audio format"
        return "audio", MAX_AUDIO_BYTES, None
    return None, 0, "Seedance 2.5: unsupported reference format"


def _ffprobe(path: str) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    return payload if isinstance(payload, dict) else {}


def _video_stream(payload: dict[str, Any]) -> dict[str, Any] | None:
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") == "video":
            return stream
    return None


def _duration_from_probe(payload: dict[str, Any]) -> float:
    fmt = payload.get("format") or {}
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration > 0:
        return duration
    for stream in payload.get("streams") or []:
        try:
            duration = max(duration, float(stream.get("duration") or 0))
        except (TypeError, ValueError):
            continue
    return duration


def _validate_video_probe(payload: dict[str, Any]) -> str | None:
    stream = _video_stream(payload)
    if not stream:
        return "Seedance 2.5 reference video stream not found"
    return validate_reference_video_metadata(
        width=stream.get("width"),
        height=stream.get("height"),
        duration_seconds=_duration_from_probe(payload),
    )


async def _probe_video_bytes(data: bytes, suffix: str) -> dict[str, Any]:
    path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(data)
            path = handle.name
        return await asyncio.to_thread(_ffprobe, path)
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


@router.post("/seedance25/upload-reference")
async def upload_seedance25_reference(
    file: UploadFile = File(...),
    user=Depends(get_web_user_or_none),
):
    if user is None:
        return error_response(401, "Authentication required")

    kind, limit, error = _kind_and_limit(file)
    if error:
        return error_response(422, error)

    data = await file.read()
    if not data:
        return error_response(422, "Empty file")
    if len(data) > limit:
        return error_response(413, f"Seedance 2.5 {kind} reference is too large")

    if kind == "video":
        try:
            probe = await _probe_video_bytes(
                data,
                Path(str(file.filename or "")).suffix.lower(),
            )
        except Exception:
            return error_response(422, "Could not inspect Seedance 2.5 reference video")
        probe_error = _validate_video_probe(probe)
        if probe_error:
            return error_response(422, probe_error)

    content_type = str(file.content_type or "application/octet-stream")
    url = save_public_file(data, content_type, subdir=f"seedance25/{kind}")
    return ok({"url": url, "kind": kind, "content_type": content_type, "size": len(data)})
