"""Production adapter from APIX Seedance product models to Neironych."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from typing import Any

from api.neironych_seedance import NeironychSeedanceClient
from api.public_files import save_public_file
from core.config import settings
from core.neironych_seedance_contract import build_seedance_payload

PRODUCT_MODELS = {
    "bytedance/seedance-2": "seedance-2.0",
    "bytedance/seedance-2-5": "seedance-2.5",
}


def _list(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    return list(dict.fromkeys(str(item).strip() for item in value if str(item or "").strip()))


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

    if edit:
        mode = "edit"
    elif has_refs:
        # APIX Seedance 2 and 2.5 have historically treated normal images as
        # references. Do not silently turn a single image into first-frame mode.
        mode = "reference"
    else:
        mode = "text"

    selected_resolution = str(resolution or "720p")
    selected_ratio = str(aspect_ratio or "16:9")
    # APIX exposes "adaptive" for Seedance 2.5. Neironych accepts adaptive only
    # for frame/edit. In text/reference mode omission means provider-auto.
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
) -> str:
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
    )
    client = _client()
    try:
        return await client.create_video(
            model=provider_model,
            payload=payload,
            idempotency_key=str(idempotency_key or uuid.uuid4()),
        )
    finally:
        await client.aclose()


async def poll_product_video(request_id: str) -> str | None:
    """Return a durable APIX-owned video URL once Neironych reports completion."""

    client = _client()
    try:
        status = await client.get_video(request_id)
        if status.failed:
            raise RuntimeError(status.error or f"Neironych Seedance failed: {status.status}")
        if not status.done:
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
