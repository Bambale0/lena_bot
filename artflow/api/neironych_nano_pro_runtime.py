"""Production Nano Banana Pro contract and exact completed-response recovery."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from api import neironych_image_adapter as transport
from api.public_files import local_upload_path_from_url
from core.config import settings

MODEL = "nano-banana-pro"
SNAPSHOT_KEY = "neironych_nano_pro_submission"
RATIOS = frozenset({"1:1", "16:9", "9:16", "4:3", "3:4", "21:9"})
QUALITIES = frozenset({"1K", "2K", "4K"})


def normalized_quality(value: str) -> str:
    return "2K" if str(value).lower() == "basic" else str(value).upper()


def supports(*, image_urls: list[str], aspect_ratio: str | None, quality: str, n: int) -> bool:
    if n != 1 or len(image_urls) > 4 or aspect_ratio not in RATIOS or normalized_quality(quality) not in QUALITIES:
        return False
    return all(_https_reference(ref) for ref in image_urls)


def _https_reference(ref: str) -> bool:
    try:
        parsed = urlparse(ref)
        return parsed.scheme == "https" and bool(parsed.hostname) and not (parsed.username or parsed.password)
    except ValueError:
        return False


def build_payload(*, prompt: str, image_urls: list[str], aspect_ratio: str | None, quality: str) -> dict[str, Any]:
    if not str(prompt).strip() or not supports(image_urls=image_urls, aspect_ratio=aspect_ratio, quality=quality, n=1):
        raise ValueError("Unsupported Nano Banana Pro request")
    for ref in image_urls:
        parsed = urlparse(ref)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Nano Banana Pro references must be public HTTPS URLs")
    payload: dict[str, Any] = {
        "model": MODEL, "prompt": str(prompt).strip(), "n": 1,
        "aspect_ratio": aspect_ratio or "1:1", "resolution": normalized_quality(quality).lower(),
        "response_format": "b64_json",
    }
    if image_urls:
        payload["images"] = [{"image_url": ref} for ref in image_urls]
    return payload


def credential_scope() -> str:
    return hashlib.sha256((transport._https_base_url() + "\0" + settings.NEIRONYCH_API_KEY).encode()).hexdigest()


def snapshot(payload: dict, request_id: str) -> dict:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {
        "version": 1, "request_id": str(uuid.UUID(request_id)), "model_key": MODEL,
        "endpoint": "edits" if payload.get("images") else "generations",
        "body_json": body, "body_sha256": hashlib.sha256(body.encode()).hexdigest(),
        "credential_scope": credential_scope(), "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


async def generate(
    *, prompt: str, image_urls: list[str], aspect_ratio: str | None, quality: str,
    request_id: str | None, before_submit: Callable[[str, dict], Awaitable[None]] | None,
) -> str:
    from api.image_errors import ImageReferenceUnavailable
    for ref in image_urls:
        local = local_upload_path_from_url(ref)
        if local is not None and not local.is_file():
            raise ImageReferenceUnavailable("Не удалось загрузить исходное изображение. Загрузи фото заново.")
    payload = build_payload(prompt=prompt, image_urls=image_urls, aspect_ratio=aspect_ratio, quality=quality)
    rid = str(uuid.UUID(request_id)) if request_id else str(uuid.uuid4())
    if before_submit:
        await before_submit(rid, snapshot(payload, rid))
    return await transport._generate_image(payload, request_id=rid, subdir=MODEL, timeout_seconds=settings.NANO_BANANA_PRO_IMAGE_TIMEOUT_SECONDS)


async def recover_completed(saved: dict, request_id: str) -> str:
    """Only called after authenticated GET confirms this original task completed.

    Neironych permanently fences its tenant-scoped key and body hash. This exact
    replay reads retained bytes; it never starts another provider generation.
    """
    rid = str(uuid.UUID(request_id))
    if not isinstance(saved, dict) or saved.get("version") != 1 or saved.get("model_key") != MODEL or saved.get("request_id") != rid:
        raise ValueError("Missing original Nano Banana Pro request snapshot")
    body = saved.get("body_json")
    if not isinstance(body, str) or len(body) > 131072:
        raise ValueError("Invalid original Nano Banana Pro body")
    if not hmac.compare_digest(str(saved.get("body_sha256", "")), hashlib.sha256(body.encode()).hexdigest()):
        raise ValueError("Original Nano Banana Pro body changed")
    if not hmac.compare_digest(str(saved.get("credential_scope", "")), credential_scope()):
        raise ValueError("Original Nano Banana Pro credential scope changed")
    payload = json.loads(body)
    refs = [item["image_url"] for item in payload.get("images", [])]
    expected = build_payload(prompt=payload["prompt"], image_urls=refs, aspect_ratio=payload.get("aspect_ratio"), quality=payload["resolution"])
    if payload != expected or saved.get("endpoint") != ("edits" if refs else "generations"):
        raise ValueError("Original Nano Banana Pro contract changed")
    return await transport._generate_image(payload, request_id=rid, subdir=MODEL, timeout_seconds=settings.NANO_BANANA_PRO_IMAGE_TIMEOUT_SECONDS)
