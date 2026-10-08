"""Nano Banana 2.1 on Neironych's synchronous Images API.

Never submit an automatic second paid request after timeout, network loss or 5xx:
Neironych explicitly documents these as potentially ambiguous outcomes.
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

from api.public_files import download_public_url, save_public_file
from core.config import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "nano-banana-2.1"
_SUPPORTED_RESOLUTIONS = frozenset({"1K", "2K", "4K"})
_SUPPORTED_RATIOS = frozenset({
    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
    "5:4", "4:5", "21:9", "1:4", "4:1", "1:8", "8:1",
})
_MAX_REFERENCES = 4  # The common, verified limit: Neironych 14, Nexus 4.
_DEFINITE_REJECTION_STATUSES = frozenset({401, 402, 403, 404, 429})
_MODEL_REJECTION_CODES = frozenset({"unknown_model_contract", "model_protocol_mismatch"})


class NeironychImageError(RuntimeError):
    """A request may have been charged upstream. Never fail over automatically."""

    def __init__(self, message: str, *, status_code: int | None = None, request_id: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


class NeironychImageRejected(NeironychImageError):
    """Provider definitely rejected the request without accepting a generation."""


_TASK_PREFIX = "neironych-image:"


def client_request_id_for_generation(generation_id: int) -> str:
    """Deterministic UUID for a persisted APIX generation, even across restarts."""
    if int(generation_id) <= 0:
        raise ValueError("generation_id must be positive")
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{settings.WEBHOOK_URL}:artflow:nano-banana-2.1:{generation_id}"))


def encode_task_id(request_id: str) -> str:
    return _TASK_PREFIX + str(uuid.UUID(request_id))


def decode_task_id(task_id: str | None) -> str | None:
    value = str(task_id or "").removeprefix("web:")
    if not value.startswith(_TASK_PREFIX):
        return None
    try:
        return str(uuid.UUID(value[len(_TASK_PREFIX):]))
    except (ValueError, AttributeError):
        return None


def _https_base_url() -> str:
    base = str(settings.NEIRONYCH_API_BASE_URL or "").strip().rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Neironych API requires an HTTPS base URL without credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Neironych API base URL must not contain a path or query")
    return base


def _verified_image_bytes(data: bytes) -> bytes:
    """Validate complete raster decoding to reject corrupt provider JPEG/PNG/WebP bytes."""
    with Image.open(io.BytesIO(data)) as im:
        if im.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Unsupported provider image format")
        if im.width < 1 or im.height < 1 or im.width * im.height > settings.NEIRONYCH_IMAGE_MAX_PIXELS:
            raise ValueError("Provider image dimensions are unsafe")
        im.verify()
    with Image.open(io.BytesIO(data)) as im:
        im.load()
    return data


async def mirror_verified_nano_banana21_result(url: str) -> str:
    """Download, fully decode and persist a reconciled provider image."""
    data, content_type = await download_public_url(url)
    if not data or len(data) > settings.NEIRONYCH_IMAGE_MAX_BYTES:
        raise ValueError("Reconciled image is empty or oversized")
    await asyncio.to_thread(_verified_image_bytes, data)
    return save_public_file(
        data,
        content_type,
        subdir="generated/nano-banana-2.1",
    )


def _normalized_references(image_urls: list[str] | None) -> list[str]:
    refs: list[str] = []
    for raw in image_urls or []:
        ref = str(raw or "").strip()
        if not ref or ref in refs:
            continue
        if not ref.startswith(("https://", "http://", "data:image/")):
            raise ValueError("Reference image must be an http(s) URL or data:image URL")
        refs.append(ref)
    if len(refs) > _MAX_REFERENCES:
        raise ValueError(f"Nano Banana 2.1 supports at most {_MAX_REFERENCES} reference images")
    return refs


def build_nano_banana21_payload(
    *,
    prompt: str,
    image_urls: list[str] | None = None,
    aspect_ratio: str | None = None,
    quality: str | None = None,
) -> dict[str, Any]:
    prompt = str(prompt or "").strip()
    if not prompt:
        raise ValueError("Image prompt is required")
    ratio = str(aspect_ratio or "1:1").strip()
    if ratio not in _SUPPORTED_RATIOS:
        raise ValueError(f"Unsupported aspect ratio {ratio} for Nano Banana 2.1")
    resolution = str(quality or "2K").strip().upper()
    if resolution == "BASIC":
        resolution = "2K"
    if resolution not in _SUPPORTED_RESOLUTIONS:
        raise ValueError(f"Unsupported quality {quality} for Nano Banana 2.1")

    payload: dict[str, Any] = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "n": 1,
        "aspect_ratio": ratio,
        "resolution": resolution.lower(),
        "response_format": "b64_json",
    }
    refs = _normalized_references(image_urls)
    if refs:
        payload["images"] = [{"image_url": ref} for ref in refs]
    return payload


def _error_code(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("code") or error.get("type") or "").strip()
    detail = body.get("detail")
    if isinstance(detail, dict):
        return str(detail.get("code") or "").strip()
    return str(body.get("code") or "").strip()


async def generate_nano_banana21_image(
    *,
    prompt: str,
    image_urls: list[str] | None = None,
    aspect_ratio: str | None = None,
    quality: str | None = None,
    request_id: str | None = None,
) -> str:
    """Generate once; save the returned base64 as a durable APIX public URL."""
    payload = build_nano_banana21_payload(
        prompt=prompt, image_urls=image_urls, aspect_ratio=aspect_ratio, quality=quality
    )
    request_id = str(uuid.UUID(request_id)) if request_id else str(uuid.uuid4())
    base_url = _https_base_url()  # Fail closed before constructing bearer headers.
    api_key = str(settings.NEIRONYCH_API_KEY or "").strip()
    if not api_key:
        raise NeironychImageRejected(
            "Neironych image API key is not configured", status_code=401, request_id=request_id
        )

    endpoint = "edits" if payload.get("images") else "generations"
    url = f"{base_url}/v1/images/{endpoint}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Idempotency-Key": request_id,
        "X-Client-Request-Id": request_id,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=settings.NEIRONYCH_IMAGE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.RequestError as exc:
        logger.error("Neironych image outcome unknown request_id=%s reason=%s", request_id, type(exc).__name__)
        raise NeironychImageError(
            "Neironych image submission outcome unknown; do not retry with another provider",
            request_id=request_id,
        ) from exc

    if response.status_code != 200:
        try:
            body = response.json()
        except ValueError:
            body = {}
        error_code = _error_code(body)
        logger.warning(
            "Neironych image response request_id=%s status=%s code=%s",
            request_id, response.status_code, error_code,
        )
        error_cls = (
            NeironychImageRejected
            if response.status_code in _DEFINITE_REJECTION_STATUSES
            or (response.status_code == 422 and error_code in _MODEL_REJECTION_CODES)
            else NeironychImageError
        )
        raise error_cls(
            f"Neironych image HTTP {response.status_code} ({error_code or 'rejected_or_unknown'})",
            status_code=response.status_code, request_id=request_id,
        )

    try:
        document = response.json()
        items = document.get("data", [])
        encoded = items[0]["b64_json"] if isinstance(items, list) and items else None
        if not isinstance(encoded, str) or not encoded:
            raise ValueError("missing data[0].b64_json")
        # Reject unexpectedly large payloads before decoding into memory.
        max_bytes = settings.NEIRONYCH_IMAGE_MAX_BYTES
        if len(encoded) > (max_bytes * 4 // 3 + 16):
            raise ValueError("image exceeds configured maximum size")
        image = base64.b64decode(encoded, validate=True)
        if not image or len(image) > max_bytes:
            raise ValueError("invalid or oversized image")
        await asyncio.to_thread(_verified_image_bytes, image)
        saved_url = save_public_file(image, subdir="generated/nano-banana-2.1")
    except (ValueError, KeyError, TypeError, IndexError, binascii.Error, OSError) as exc:
        logger.exception("Neironych image response/persistence error request_id=%s", request_id)
        raise NeironychImageError(
            "Neironych image returned an unusable result; no automatic provider failover",
            request_id=request_id,
        ) from exc
    logger.info("Neironych image completed model=%s request_id=%s", MODEL_NAME, request_id)
    return saved_url

async def fetch_nano_banana21_status(request_id: str) -> dict[str, Any]:
    """Read persisted provider status by correlation UUID. A missing record is not a failure."""
    rid = str(uuid.UUID(request_id))
    base = _https_base_url()
    api_key = str(settings.NEIRONYCH_API_KEY or "").strip()
    if not api_key:
        raise NeironychImageError("Neironych API key is unavailable for reconciliation", request_id=rid)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{base}/api/v1/generations/by-client-request-id/{rid}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
    except httpx.RequestError as exc:
        raise NeironychImageError("Neironych reconciliation unavailable", request_id=rid) from exc
    if response.status_code == 404:
        return {"status": "not_found", "result_url": None}
    if response.status_code != 200:
        raise NeironychImageError(
            f"Neironych reconciliation HTTP {response.status_code}",
            status_code=response.status_code, request_id=rid,
        )
    try:
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("status response must be an object")
        if body.get("model_slug") != MODEL_NAME:
            raise ValueError("reconciled generation model mismatch")
        state = str(body.get("status") or "").lower()
        if state not in {
            "completed", "failed", "cancelled", "timeout", "queued",
            "submitting", "processing", "running", "reconciliation_required",
        }:
            raise ValueError("unknown generation status")
        urls = body.get("result_urls") or []
        url = body.get("result_url") or (urls[0] if isinstance(urls, list) and urls else None)
        if url and (not isinstance(url, str) or urlparse(url).scheme != "https"):
            raise ValueError("invalid result URL")
        return {
            "status": state, "result_url": url,
            "error_code": str(body.get("public_error_code") or ""),
        }
    except (ValueError, TypeError, IndexError) as exc:
        raise NeironychImageError("Invalid reconciliation response", request_id=rid) from exc
