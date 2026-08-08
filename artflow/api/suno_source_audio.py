"""User-facing Suno source-audio workflow shared by bot, Mini App and web."""
from __future__ import annotations

import asyncio
import mimetypes
import os
import subprocess
import tempfile
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from api import kieai_client, suno_full_service
from api.music_service import (
    default_music_callback_url,
    normalize_music_model,
    register_miniapp_task,
)
from db import repository as repo
from db.models import GenerationType

MAX_SOURCE_AUDIO_BYTES = 100 * 1024 * 1024
MAX_SOURCE_AUDIO_SECONDS = 480.0
SOURCE_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
DEFAULT_MUSIC_MODEL_KEY = "suno/v5.5"
DEFAULT_MUSIC_CREDITS = 20.0


class SunoSourceOperation(StrEnum):
    COVER = "cover"
    EXTEND = "extend"
    ADD_VOCALS = "add_vocals"
    ADD_INSTRUMENTAL = "add_instrumental"


def _operation(value: SunoSourceOperation | str) -> SunoSourceOperation:
    try:
        return value if isinstance(value, SunoSourceOperation) else SunoSourceOperation(str(value))
    except ValueError as exc:
        allowed = ", ".join(item.value for item in SunoSourceOperation)
        raise ValueError(f"Unsupported Suno source-audio operation. Allowed: {allowed}") from exc


def _required(value: str | None, field: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise ValueError(f"{field} is required")
    return clean


def _probe_audio(path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return float((result.stdout or "0").strip() or 0)


async def inspect_source_audio(
    data: bytes,
    *,
    filename: str | None,
    content_type: str | None,
) -> tuple[float, str, str]:
    if not data:
        raise ValueError("Empty audio file")
    if len(data) > MAX_SOURCE_AUDIO_BYTES:
        raise ValueError("Audio file is too large (APIX limit: 100 MB)")

    suffix = Path(filename or "source.mp3").suffix.lower()
    if suffix not in SOURCE_AUDIO_EXTENSIONS:
        raise ValueError("Supported audio: MP3, WAV, M4A, AAC, FLAC, OGG, OPUS")
    mime = str(content_type or mimetypes.guess_type(f"audio{suffix}")[0] or "audio/mpeg")
    if content_type and not (mime.startswith("audio/") or suffix in SOURCE_AUDIO_EXTENSIONS):
        raise ValueError("Uploaded file is not audio")

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(data)
            temp_path = handle.name
        try:
            duration = await asyncio.to_thread(_probe_audio, temp_path)
        except Exception as exc:
            raise ValueError("Could not read audio duration") from exc
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    if duration <= 0:
        raise ValueError("Audio duration must be greater than zero")
    if duration > MAX_SOURCE_AUDIO_SECONDS + 0.05:
        raise ValueError("Suno source audio must be 8 minutes or shorter")
    safe_name = f"source{suffix}"
    return duration, safe_name, mime


async def upload_source_audio(
    data: bytes,
    *,
    filename: str | None,
    content_type: str | None,
) -> dict[str, Any]:
    duration, safe_name, mime = await inspect_source_audio(
        data,
        filename=filename,
        content_type=content_type,
    )
    url = await kieai_client.upload_file_stream(
        data,
        filename=safe_name,
        content_type=mime,
        upload_path="audio/apix-suno-inputs",
    )
    if not url:
        raise RuntimeError("Suno source-audio upload returned no URL")
    return {
        "url": url,
        "duration_seconds": round(duration, 2),
        "filename": filename or safe_name,
        "content_type": mime,
        "size": len(data),
    }


def validate_source_url(url: str) -> str:
    clean = _required(url, "upload_url")
    parsed = urlparse(clean)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("upload_url must be a public HTTP(S) URL")
    return clean


async def start_source_audio_task(
    *,
    operation: SunoSourceOperation | str,
    upload_url: str,
    prompt: str,
    model_key: str | None = None,
    instrumental: bool = False,
    style: str | None = None,
    title: str | None = None,
    continue_at: float | None = None,
) -> suno_full_service.SunoTask:
    selected_operation = _operation(operation)
    source_url = validate_source_url(upload_url)
    clean_prompt = _required(prompt, "prompt")
    provider_model = normalize_music_model(model_key)
    callback = default_music_callback_url()
    clean_style = str(style or "").strip()
    clean_title = str(title or "").strip()

    if selected_operation == SunoSourceOperation.COVER:
        custom = bool(clean_style or clean_title)
        if custom and (not clean_style or not clean_title):
            raise ValueError("Cover custom mode requires both style and title")
        return await suno_full_service.upload_and_cover(
            source_url,
            clean_prompt,
            model=provider_model,
            custom_mode=custom,
            instrumental=bool(instrumental),
            style=clean_style or None,
            title=clean_title or None,
            callback_url=callback,
        )

    if selected_operation == SunoSourceOperation.EXTEND:
        if continue_at is None or float(continue_at) <= 0:
            raise ValueError("continue_at must be greater than zero")
        custom = bool(clean_style or clean_title)
        if custom and (not clean_style or not clean_title):
            raise ValueError("Extend custom mode requires both style and title")
        return await suno_full_service.upload_and_extend(
            source_url,
            clean_prompt,
            model=provider_model,
            use_custom_parameters=custom,
            instrumental=bool(instrumental),
            style=clean_style or None,
            title=clean_title or None,
            continue_at=float(continue_at),
            callback_url=callback,
        )

    if selected_operation == SunoSourceOperation.ADD_VOCALS:
        return await suno_full_service.add_vocals(
            source_url,
            prompt=clean_prompt,
            style=_required(clean_style, "style"),
            title=_required(clean_title, "title"),
            model=suno_full_service.SunoModel.V4_5PLUS,
            callback_url=callback,
        )

    return await suno_full_service.add_instrumental(
        source_url,
        title=_required(clean_title, "title"),
        tags=_required(clean_style or clean_prompt, "style/tags"),
        model=suno_full_service.SunoModel.V4_5PLUS,
        callback_url=callback,
    )


async def _resolve_model_cost(session, model_key: str | None):
    requested = str(model_key or "").strip()
    if requested:
        row = await repo.get_model_cost(session, requested)
        if row and getattr(row, "gen_type", None) == GenerationType.music and getattr(row, "is_active", True):
            return row
    for key in (DEFAULT_MUSIC_MODEL_KEY, "suno/v5.0", "suno/v4.5"):
        row = await repo.get_model_cost(session, key)
        if row and getattr(row, "gen_type", None) == GenerationType.music and getattr(row, "is_active", True):
            return row
    return None


async def create_source_audio_generation(
    *,
    session,
    user,
    operation: SunoSourceOperation | str,
    upload_url: str,
    prompt: str,
    model_key: str | None = None,
    instrumental: bool = False,
    style: str | None = None,
    title: str | None = None,
    continue_at: float | None = None,
    source_duration: float | None = None,
    surface: str = "miniapp",
):
    selected_operation = _operation(operation)
    clean_prompt = _required(prompt, "prompt")
    if selected_operation == SunoSourceOperation.EXTEND and continue_at is not None and source_duration:
        if float(continue_at) >= float(source_duration):
            raise ValueError("continue_at must be shorter than the uploaded audio")

    model_cost = await _resolve_model_cost(session, model_key)
    selected_key = str(getattr(model_cost, "model_key", None) or model_key or DEFAULT_MUSIC_MODEL_KEY)
    credits = float(getattr(model_cost, "credits", DEFAULT_MUSIC_CREDITS) or DEFAULT_MUSIC_CREDITS)
    if float(getattr(user, "credits", 0) or 0) < credits:
        raise PermissionError(f"Insufficient credits: need {credits:g}")

    active = await repo.count_user_active_generations(session, user.id)
    if active >= 6:
        raise RuntimeError("Too many concurrent generations")
    if not await repo.spend_credits(session, user.id, credits):
        raise PermissionError("Failed to spend credits")

    input_params = {
        "suno_source_operation": selected_operation.value,
        "source_audio_url": upload_url,
        "source_duration": source_duration,
        "continue_at": continue_at,
        "instrumental": bool(instrumental),
        "style": style,
        "title": title,
    }
    gen = await repo.create_generation(
        session,
        user.id,
        selected_key,
        GenerationType.music,
        clean_prompt,
        credits,
        input_params=input_params,
    )
    try:
        task = await start_source_audio_task(
            operation=selected_operation,
            upload_url=upload_url,
            prompt=clean_prompt,
            model_key=selected_key,
            instrumental=instrumental,
            style=style,
            title=title,
            continue_at=continue_at,
        )
    except Exception as exc:
        if await repo.fail_generation(session, gen.id, str(exc)):
            await repo.add_credits(session, user.id, credits)
        raise

    stored_task_id = task.task_id
    if str(surface).lower() == "web":
        stored_task_id = f"web:{stored_task_id}"
    await repo.update_generation_task(session, gen.id, stored_task_id)
    register_miniapp_task(task.task_id, gen.id)
    await session.refresh(gen)
    return gen
