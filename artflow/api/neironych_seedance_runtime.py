"""Production adapter from APIX Seedance product models to Neironych."""
from __future__ import annotations

import logging
import math
import tempfile
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api import media_gateway, public_files
from api.media_gateway import MediaProbe
from api.neironych_seedance import NeironychSeedanceClient
from api.public_files import save_public_file
from core.config import settings
from core.neironych_seedance_contract import (
    SEEDANCE_FIXED_ASPECT_RATIOS,
    SeedanceContractError,
    build_seedance_payload,
    get_seedance_spec,
)

logger = logging.getLogger(__name__)

TASK_PREFIX = "neironych:"


@dataclass(slots=True)
class SubmissionContext:
    client_request_id: str
    before_submit: Callable[[str, str], Awaitable[None]]
    started: bool = False


class NeironychVideoTaskFailed(RuntimeError):
    """Provider confirmed a terminal failure; unlike HTTP/transport/download errors."""

    def __init__(self, request_id: str, message: str, *, state: str = "failed") -> None:
        self.request_id = decode_task_id(request_id)
        self.state = state
        super().__init__(str(message or f"Neironych Seedance {state}")[:1000])


class NeironychVideoReconciliationRequired(RuntimeError):
    """An explicit uncertain submit requires review, not replay or false refund."""

    def __init__(self, request_id: str) -> None:
        self.request_id = decode_task_id(request_id)
        super().__init__("Neironych video submission requires reconciliation")


PRODUCT_MODELS = {
    "bytedance/seedance-2": "seedance-2.0",
    "bytedance/seedance-2-5": "seedance-2.5",
}


def encode_task_id(request_id: str) -> str:
    raw = str(request_id or "").strip()
    if not raw:
        raise ValueError("Neironych request id is empty")
    return raw if raw.startswith(TASK_PREFIX) else f"{TASK_PREFIX}{raw}"


def is_task_id(task_id: str | None) -> bool:
    return str(task_id or "").startswith(TASK_PREFIX)


def decode_task_id(task_id: str) -> str:
    raw = str(task_id or "").strip()
    return raw[len(TASK_PREFIX):] if raw.startswith(TASK_PREFIX) else raw


def _list(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item or "").strip()))


def _source_reference_controls(source: MediaProbe | None, model: str) -> tuple[int, str]:
    """Resolve mixed-edit output controls from owned media, never UI -1/adaptive.

    Reference mode cannot inherit dimensions like provider edit does. Use the
    same ceil(source seconds) as precharge and the closest supported aspect.
    """
    if source is None:
        raise SeedanceContractError("Seedance mixed edit requires verified source video metadata.")
    seconds = source.duration_seconds
    spec = get_seedance_spec(model)
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or not spec.min_duration <= seconds <= spec.max_duration
    ):
        raise SeedanceContractError("Seedance mixed edit source duration is invalid.")
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in (source.width, source.height)):
        raise SeedanceContractError("Seedance mixed edit source dimensions are invalid.")
    source_ratio = source.width / source.height
    ratio = min(
        SEEDANCE_FIXED_ASPECT_RATIOS,
        key=lambda value: abs(source_ratio / (int(value.split(":")[0]) / int(value.split(":")[1])) - 1),
    )
    return math.ceil(seconds), ratio


def build_product_payload(
    *,
    product_model: str,
    prompt: str,
    image_urls: str | list[str] | None = None,
    video_urls: str | list[str] | None = None,
    audio_urls: str | list[str] | None = None,
    duration: int = 5,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    edit: bool = False,
    source_probe: MediaProbe | None = None,
) -> tuple[str, dict[str, Any]]:
    """Translate stable APIX product semantics into the documented provider contract."""

    try:
        provider_model = PRODUCT_MODELS[str(product_model)]
    except KeyError as exc:
        raise ValueError(f"Unsupported Neironych product model: {product_model}") from exc

    images = _list(image_urls)
    videos = _list(video_urls)
    audios = _list(audio_urls)
    has_refs = bool(images or videos or audios)

    if edit and len(videos) != 1:
        raise SeedanceContractError("Seedance product edit requires exactly one source video.")
    mixed_edit = edit and bool(images or audios)
    if edit and not mixed_edit:
        mode = "edit"
    elif has_refs:
        # APIX Seedance 2 and 2.5 have historically treated normal images as
        # references. Do not silently turn a single image into first-frame mode.
        mode = "reference"
    else:
        mode = "text"

    selected_resolution = str(resolution or "720p")
    selected_ratio = str(aspect_ratio or "16:9")
    if mixed_edit:
        if provider_model != "seedance-2.5":
            raise SeedanceContractError("Mixed edit is supported only for Seedance 2.5.")
        duration, selected_ratio = _source_reference_controls(source_probe, provider_model)
    # Generic reference requests with adaptive retain the provider default.
    # Mixed edits above must instead resolve the real source ratio explicitly.
    if provider_model == "seedance-2.5" and selected_ratio == "adaptive" and mode != "edit":
        selected_ratio = ""

    payload = build_seedance_payload(
        model=provider_model,
        mode=mode,
        prompt=prompt,
        resolution=selected_resolution,
        duration=None if mode == "edit" else int(duration),
        aspect_ratio=None if mode == "edit" else selected_ratio,
        image_urls=images,
        video_urls=videos,
        audio_urls=audios,
    )
    if not selected_ratio:
        payload.pop("aspect_ratio", None)
    return provider_model, payload


def _client() -> NeironychSeedanceClient:
    return NeironychSeedanceClient(
        settings.NEIRONYCH_API_KEY,
        settings.NEIRONYCH_API_BASE_URL,
        timeout_seconds=settings.NEIRONYCH_HTTP_TIMEOUT_SECONDS,
    )


async def generate_product_video(
    *,
    product_model: str,
    prompt: str,
    image_urls: str | list[str] | None = None,
    video_urls: str | list[str] | None = None,
    audio_urls: str | list[str] | None = None,
    duration: int = 5,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    edit: bool = False,
    idempotency_key: str | None = None,
    submission_context: SubmissionContext | None = None,
) -> str:
    source_probe = None
    if edit and (_list(image_urls) or _list(audio_urls)):
        videos = _list(video_urls)
        if len(videos) != 1:
            raise SeedanceContractError("Seedance mixed edit requires exactly one source video.")
        local_path = public_files.local_upload_path_from_url(videos[0])
        if local_path is None:
            # Do not add a remote fetch/SSRF path to the provider adapter.
            raise SeedanceContractError("Seedance mixed edit requires an uploaded source video.")
        source_probe = await media_gateway.probe_local_media(local_path, media_gateway.MediaKind.VIDEO)
    provider_model, payload = build_product_payload(
        product_model=product_model,
        prompt=prompt,
        image_urls=image_urls,
        video_urls=video_urls,
        audio_urls=audio_urls,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        edit=edit,
        source_probe=source_probe,
    )
    logger.info(
        "neironych_seedance_route model=%s product_edit=%s provider_mode=%s images=%d videos=%d audios=%d duration=%s aspect_ratio=%s",
        provider_model, edit, payload.get("omni_reference_task_type", "text"),
        len(payload.get("reference_images", [])), len(payload.get("reference_videos", [])),
        len(payload.get("reference_audios", [])), payload.get("duration"), payload.get("aspect_ratio"),
    )
    client = _client()
    try:
        return await client.create_video(
            model=provider_model,
            payload=payload,
            idempotency_key=str(idempotency_key or uuid.uuid4()),
            client_request_id=submission_context.client_request_id if submission_context else None,
            before_submit=submission_context.before_submit if submission_context else None,
        )
    finally:
        # Resource cleanup must not turn an accepted/unknown submission into
        # a generic routing failure that could create a second paid job.
        try:
            await client.aclose()
        except Exception:
            logger.warning("Neironych submission client cleanup failed", exc_info=True)


async def lookup_submission(
    client_request_id: str, *, product_model: str, idempotency_key: str,
) -> str | None:
    client = _client()
    try:
        return await client.lookup_submission(
            client_request_id, model=PRODUCT_MODELS[product_model], idempotency_key=idempotency_key,
        )
    finally:
        await client.aclose()


async def poll_product_video(request_id: str) -> str | None:
    """Return a durable APIX-owned video URL once Neironych reports completion."""

    request_id = decode_task_id(request_id)
    client = _client()
    try:
        status = await client.get_video(request_id)
        if status.failed:
            raise NeironychVideoTaskFailed(
                request_id, status.error or f"Neironych Seedance failed: {status.status}",
                state=status.status,
            )
        if not status.done:
            if (
                getattr(status, "status", "") == "reconciliation_required"
                or str(getattr(status, "error", "")).strip() == "submission_outcome_unknown"
            ):
                raise NeironychVideoReconciliationRequired(request_id)
            return None

        handle = tempfile.NamedTemporaryFile(
            prefix="apix-neironych-seedance-",
            suffix=".mp4",
            delete=False,
        )
        path = Path(handle.name)
        handle.close()
        try:
            await client.download_content_to(
                request_id,
                path,
                max_bytes=settings.NEIRONYCH_MAX_VIDEO_BYTES,
            )
            return save_public_file(
                path.read_bytes(),
                "video/mp4",
                subdir="provider-results",
            )
        finally:
            path.unlink(missing_ok=True)
    finally:
        await client.aclose()
