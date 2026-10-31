"""Exact-model Neironych fallback for definitively failed Nexus images.

At-most-one submit per persisted generation identity. A timeout, 5xx or
unusable synchronous response is an unknown paid outcome, never a retry signal.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import io
import logging
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
from PIL import Image

from api import neironych_image_adapter as native
from api.public_files import save_public_file
from core.config import settings
from core.image_fallback_policy import EXACT_MODELS

logger = logging.getLogger(__name__)

# Only the common contract verified by both providers is used. Unsupported
# ratios/quality/counts abort fallback before any second supplier POST.
_COMMON_RATIOS = frozenset({
    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
    "5:4", "4:5", "21:9",
})
_NANO_RESOLUTIONS = frozenset({"1K", "2K", "4K"})


def build_fallback_image_payload(
    *, model_key: str, prompt: str, image_urls: list[str] | None = None,
    aspect_ratio: str | None = None, quality: str | None = None,
) -> dict[str, Any]:
    try:
        model = EXACT_MODELS[model_key]
    except KeyError as exc:
        raise ValueError(f"Unsupported Neironych exact-model fallback: {model_key}") from exc
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Image prompt is required")
    ratio = str(aspect_ratio or "1:1").strip()
    if ratio not in _COMMON_RATIOS:
        raise ValueError(f"Unsupported fallback image aspect ratio: {ratio}")
    refs = native._normalized_references(image_urls)
    payload: dict[str, Any] = {
        "model": model, "prompt": prompt, "n": 1,
        "aspect_ratio": ratio, "response_format": "b64_json",
    }
    if model in {"nano-banana-pro", "nano-banana-2"}:
        resolution = str(quality or "2K").strip().upper()
        if resolution == "BASIC":
            resolution = "2K"
        if resolution not in _NANO_RESOLUTIONS:
            raise ValueError("Unsupported Nano Banana fallback resolution")
        payload["resolution"] = resolution.lower()
    # GPT Image 2 does not expose the Nano Banana resolution parameter.
    if refs:
        payload["images"] = [{"image_url": ref} for ref in refs]
    return payload


async def generate_fallback_image(
    *, model_key: str, prompt: str, request_id: str,
    image_urls: list[str] | None = None,
    aspect_ratio: str | None = None, quality: str | None = None,
) -> str:
    payload = build_fallback_image_payload(
        model_key=model_key, prompt=prompt, image_urls=image_urls,
        aspect_ratio=aspect_ratio, quality=quality,
    )
    rid = str(uuid.UUID(request_id))
    key = str(settings.NEIRONYCH_API_KEY or "").strip()
    if not key:
        raise native.NeironychImageRejected(
            "Neironych image credential unavailable", status_code=401, request_id=rid
        )
    url = native._https_base_url() + (
        "/v1/images/edits" if payload.get("images") else "/v1/images/generations"
    )
    headers = {
        "Authorization": f"Bearer {key}", "Idempotency-Key": rid,
        "X-Client-Request-Id": rid, "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.NEIRONYCH_IMAGE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.RequestError as exc:
        logger.warning("Fallback image submission unresolved request_id=%s type=%s", rid, type(exc).__name__)
        raise native.NeironychImageError(
            "Neironych fallback submission outcome unknown", request_id=rid
        ) from exc
    if response.status_code != 200:
        try:
            body = response.json()
        except ValueError:
            body = {}
        code = native._error_code(body)
        cls = (
            native.NeironychImageRejected
            if response.status_code in native._DEFINITE_REJECTION_STATUSES
            or (response.status_code == 422 and code in native._MODEL_REJECTION_CODES)
            else native.NeironychImageError
        )
        logger.warning("Fallback provider response request_id=%s status=%d code=%s", rid, response.status_code, code)
        raise cls(f"Neironych fallback HTTP {response.status_code}", request_id=rid, status_code=response.status_code)
    try:
        body = response.json()
        data = body.get("data")
        encoded = data[0].get("b64_json") if isinstance(data, list) and data else None
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("Neironych image response did not include b64_json")
        if len(encoded) > settings.NEIRONYCH_IMAGE_MAX_BYTES * 4 // 3 + 16:
            raise ValueError("Oversized provider image")
        image = base64.b64decode(encoded, validate=True)
        if not image or len(image) > settings.NEIRONYCH_IMAGE_MAX_BYTES:
            raise ValueError("Invalid provider image size")
        await asyncio.to_thread(native._verified_image_bytes, image)
        with Image.open(io.BytesIO(image)) as frame:
            media_type = Image.MIME[frame.format]
        url = save_public_file(
            image, media_type, subdir=f"generated/{EXACT_MODELS[model_key]}",
        )
    except (ValueError, KeyError, TypeError, IndexError, binascii.Error, OSError) as exc:
        logger.error("Unusable Neironych fallback result request_id=%s type=%s", rid, type(exc).__name__)
        raise native.NeironychImageError(
            "Neironych fallback returned an unusable image", request_id=rid
        ) from exc
    logger.info("Nexus image fallback completed request_id=%s model=%s", rid, model_key)
    return url


async def fetch_fallback_status(request_id: str, *, model_key: str) -> dict[str, Any]:
    rid = str(uuid.UUID(request_id))
    expected_model = EXACT_MODELS[model_key]
    key = str(settings.NEIRONYCH_API_KEY or "").strip()
    if not key:
        raise native.NeironychImageError("Neironych credentials missing", request_id=rid)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                native._https_base_url() + f"/api/v1/generations/by-client-request-id/{rid}",
                headers={"Authorization": f"Bearer {key}"},
            )
    except httpx.RequestError as exc:
        raise native.NeironychImageError("Neironych fallback status unavailable", request_id=rid) from exc
    if response.status_code == 404:
        return {"status": "not_found", "result_url": None}
    if response.status_code != 200:
        raise native.NeironychImageError(
            f"Neironych fallback status HTTP {response.status_code}",
            status_code=response.status_code, request_id=rid,
        )
    try:
        body = response.json()
        if not isinstance(body, dict) or body.get("model_slug") != expected_model:
            raise ValueError("Provider generation model mismatch")
        state = str(body.get("status") or "").lower()
        if state not in {
            "completed", "failed", "cancelled", "timeout", "queued",
            "submitting", "processing", "running", "reconciliation_required",
        }:
            raise ValueError("Unknown provider generation status")
        urls = body.get("result_urls") or []
        url = body.get("result_url") or (urls[0] if isinstance(urls, list) and urls else None)
        if url is not None and (not isinstance(url, str) or urlparse(url).scheme != "https"):
            raise ValueError("Invalid provider result URL")
    except (ValueError, TypeError, IndexError) as exc:
        raise native.NeironychImageError("Invalid fallback status response", request_id=rid) from exc
    return {"status": state, "result_url": url, "error_code": str(body.get("public_error_code") or "")}


async def mirror_fallback_result(url: str, *, model_key: str) -> str:
    from api.public_files import download_public_url
    if model_key not in EXACT_MODELS:
        raise ValueError('Unsupported model')
    data, _ = await download_public_url(url)
    if not data or len(data) > settings.NEIRONYCH_IMAGE_MAX_BYTES:
        raise ValueError('Invalid image data size')
    await asyncio.to_thread(native._verified_image_bytes, data)
    with Image.open(io.BytesIO(data)) as im:
        media_type = Image.MIME[im.format]
    return save_public_file(data, media_type, subdir='generated/' + EXACT_MODELS[model_key])
