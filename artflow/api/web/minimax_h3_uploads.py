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
from api.web.deps import error_response, get_web_user_or_none, ok

router = APIRouter(tags=["web"])

MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
MAX_AUDIO_BYTES = 15 * 1024 * 1024
MIN_MEDIA_SECONDS = 2.0
MAX_MEDIA_SECONDS = 15.0
MIN_DIMENSION = 256
MAX_DIMENSION = 5760
MIN_ASPECT = 0.4
MAX_ASPECT = 2.5
MIN_FPS = 23.976
MAX_FPS = 60.0

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
_VIDEO_EXTENSIONS = {".mp4", ".mov"}
_AUDIO_EXTENSIONS = {".mp3", ".wav"}


def _auth_required(user):
    if user is None:
        return error_response(401, "Authentication required")
    return None


def _fraction(value: str | None) -> float:
    raw = str(value or "0").strip()
    if "/" in raw:
        numerator, denominator = raw.split("/", 1)
        try:
            denominator_f = float(denominator)
            return float(numerator) / denominator_f if denominator_f else 0.0
        except ValueError:
            return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


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
            candidate = float(stream.get("duration") or 0)
        except (TypeError, ValueError):
            candidate = 0.0
        duration = max(duration, candidate)
    return duration


def _video_stream(payload: dict[str, Any]) -> dict[str, Any] | None:
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") == "video":
            return stream
    return None


def _audio_stream(payload: dict[str, Any]) -> dict[str, Any] | None:
    for stream in payload.get("streams") or []:
        if stream.get("codec_type") == "audio":
            return stream
    return None


def _validate_duration(duration: float, label: str) -> str | None:
    if duration < MIN_MEDIA_SECONDS or duration > MAX_MEDIA_SECONDS:
        return f"{label} duration must be between 2 and 15 seconds"
    return None


def _validate_video_probe(payload: dict[str, Any]) -> str | None:
    stream = _video_stream(payload)
    if not stream:
        return "Video stream not found"
    codec = str(stream.get("codec_name") or "").lower()
    if codec not in {"h264", "hevc", "h265"}:
        return "MiniMax H3 video references require H.264/AVC or H.265/HEVC"
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    if not (MIN_DIMENSION <= width <= MAX_DIMENSION and MIN_DIMENSION <= height <= MAX_DIMENSION):
        return "MiniMax H3 video dimensions must be between 256 and 5760 px"
    ratio = width / height if height else 0
    if ratio < MIN_ASPECT or ratio > MAX_ASPECT:
        return "MiniMax H3 video aspect ratio must be between 0.4 and 2.5"
    fps = _fraction(stream.get("avg_frame_rate") or stream.get("r_frame_rate"))
    if fps and (fps < MIN_FPS - 0.01 or fps > MAX_FPS + 0.01):
        return "MiniMax H3 video frame rate must be between 23.976 and 60 FPS"
    duration_error = _validate_duration(_duration_from_probe(payload), "Video")
    if duration_error:
        return duration_error
    audio = _audio_stream(payload)
    if audio:
        audio_codec = str(audio.get("codec_name") or "").lower()
        if audio_codec not in {"aac", "mp3"}:
            return "MiniMax H3 reference-video audio codec must be AAC or MP3"
    return None


def _validate_audio_probe(payload: dict[str, Any]) -> str | None:
    stream = _audio_stream(payload)
    if not stream:
        return "Audio stream not found"
    codec = str(stream.get("codec_name") or "").lower()
    if codec not in {"mp3", "pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le", "pcm_f64le"}:
        return "MiniMax H3 audio references require MP3 or WAV"
    return _validate_duration(_duration_from_probe(payload), "Audio")


async def _probe_bytes(data: bytes, suffix: str) -> dict[str, Any]:
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


def _kind_and_limit(file: UploadFile) -> tuple[str | None, int, str | None]:
    suffix = Path(str(file.filename or "")).suffix.lower()
    content_type = str(file.content_type or "").lower()
    if suffix in _IMAGE_EXTENSIONS or content_type.startswith("image/"):
        if suffix and suffix not in _IMAGE_EXTENSIONS:
            return None, 0, "MiniMax H3 images must be JPG, JPEG, PNG, WEBP, HEIC or HEIF"
        return "image", MAX_IMAGE_BYTES, None
    if suffix in _VIDEO_EXTENSIONS or content_type in {"video/mp4", "video/quicktime"}:
        if suffix not in _VIDEO_EXTENSIONS:
            return None, 0, "MiniMax H3 video references must be MP4 or MOV"
        return "video", MAX_VIDEO_BYTES, None
    if suffix in _AUDIO_EXTENSIONS or content_type in {"audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav"}:
        if suffix not in _AUDIO_EXTENSIONS:
            return None, 0, "MiniMax H3 audio references must be MP3 or WAV"
        return "audio", MAX_AUDIO_BYTES, None
    return None, 0, "Unsupported MiniMax H3 reference format"


@router.post("/h3/upload-reference")
async def upload_h3_reference(
    file: UploadFile = File(...),
    user=Depends(get_web_user_or_none),
):
    if auth_error := _auth_required(user):
        return auth_error

    kind, limit, kind_error = _kind_and_limit(file)
    if kind_error:
        return error_response(422, kind_error)
    data = await file.read()
    if not data:
        return error_response(422, "Empty file")
    if len(data) > limit:
        return error_response(413, f"MiniMax H3 {kind} file is too large")

    if kind in {"video", "audio"}:
        try:
            probe = await _probe_bytes(data, Path(str(file.filename or "")).suffix.lower())
        except Exception:
            return error_response(422, f"Could not inspect MiniMax H3 {kind} reference")
        probe_error = _validate_video_probe(probe) if kind == "video" else _validate_audio_probe(probe)
        if probe_error:
            return error_response(422, probe_error)

    content_type = file.content_type
    if not content_type:
        suffix = Path(str(file.filename or "")).suffix.lower()
        content_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
        }.get(suffix, "application/octet-stream")

    url = save_public_file(data, content_type, subdir=f"h3/{kind}")
    return ok({"url": url, "kind": kind, "content_type": content_type, "size": len(data)})
