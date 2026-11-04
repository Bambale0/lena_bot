"""GPT Image 2/2.5 native requests with durable identity and completed-response recovery."""
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

MODELS = {
    "gpt-image-2-text-to-image": "gpt-image-2",
    "gpt-image-2-image-to-image": "gpt-image-2",
    "gpt-image-2.5-sunburst": "gpt-image-2.5-sunburst",
}
SNAPSHOT_KEY = "neironych_gpt_image_submission"
SIZES = {
    "1:1": ("2048x2048", "4096x4096"),
    "16:9": ("2048x1152", "3840x2160"),
    "9:16": ("1152x2048", "2160x3840"),
    "3:2": ("2048x1360", "3840x2560"),
    "2:3": ("1360x2048", "2560x3840"),
}


def supports(*, image_urls: list[str], aspect_ratio: str | None, quality: str, n: int) -> bool:
    if n != 1 or len(image_urls) > 4 or aspect_ratio not in SIZES or quality not in {"basic", "2K", "4K"}:
        return False
    try:
        return all(urlparse(url).scheme == "https" and urlparse(url).hostname
                   and not (urlparse(url).username or urlparse(url).password) for url in image_urls)
    except ValueError:
        return False


def build_payload(*, model_key: str, prompt: str, image_urls: list[str],
                  aspect_ratio: str | None, quality: str) -> dict[str, Any]:
    if model_key not in MODELS or not str(prompt or "").strip() or not supports(
        image_urls=image_urls, aspect_ratio=aspect_ratio, quality=quality, n=1,
    ):
        raise ValueError("Unsupported GPT Image request")
    if model_key.endswith("image-to-image") and not image_urls:
        raise ValueError("GPT Image edit requires a reference")
    payload: dict[str, Any] = {
        "model": MODELS[model_key], "prompt": prompt.strip(), "n": 1,
        "size": SIZES[aspect_ratio][int(quality == "4K")],
        "quality": "high" if quality == "4K" else "medium", "response_format": "b64_json",
    }
    if image_urls:
        payload["images"] = [{"image_url": ref} for ref in image_urls]
    return payload


def credential_scope() -> str:
    return hashlib.sha256((transport._https_base_url() + "\0" + settings.NEIRONYCH_API_KEY).encode()).hexdigest()


def snapshot(payload: dict, request_id: str, *, model_key: str) -> dict:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return {"version": 1, "request_id": str(uuid.UUID(request_id)), "model_key": model_key,
            "endpoint": "edits" if payload.get("images") else "generations", "body_json": body,
            "body_sha256": hashlib.sha256(body.encode()).hexdigest(), "credential_scope": credential_scope(),
            "submitted_at": datetime.now(timezone.utc).isoformat()}


async def generate(*, model_key: str, prompt: str, image_urls: list[str], aspect_ratio: str | None,
                   quality: str, request_id: str | None,
                   before_submit: Callable[[str, dict], Awaitable[None]] | None) -> str:
    from api.image_errors import ImageReferenceUnavailable
    for ref in image_urls:
        local = local_upload_path_from_url(ref)
        if local is not None and not local.is_file():
            raise ImageReferenceUnavailable("Загрузи исходное фото заново.")
    payload = build_payload(model_key=model_key, prompt=prompt, image_urls=image_urls,
                            aspect_ratio=aspect_ratio, quality=quality)
    rid = str(uuid.UUID(request_id)) if request_id else str(uuid.uuid4())
    if before_submit:
        await before_submit(rid, snapshot(payload, rid, model_key=model_key))
    return await transport._generate_image(
        payload, request_id=rid, subdir=payload["model"], timeout_seconds=settings.GPT_IMAGE_TIMEOUT_SECONDS,
    )


async def recover_completed(saved: dict, request_id: str, *, model_key: str) -> str:
    rid = str(uuid.UUID(request_id))
    if (not isinstance(saved, dict) or saved.get("version") != 1 or model_key not in MODELS
            or saved.get("model_key") != model_key or saved.get("request_id") != rid):
        raise ValueError("Missing original GPT Image submission")
    body = saved.get("body_json")
    if not isinstance(body, str) or len(body) > 131072:
        raise ValueError("Invalid original GPT Image body")
    if not hmac.compare_digest(str(saved.get("body_sha256", "")), hashlib.sha256(body.encode()).hexdigest()):
        raise ValueError("Original GPT Image body changed")
    if not hmac.compare_digest(str(saved.get("credential_scope", "")), credential_scope()):
        raise ValueError("Original GPT Image credential scope changed")
    payload = json.loads(body)
    refs = [item["image_url"] for item in payload.get("images", [])]
    size = payload.get("size")
    match = next(((ratio, "4K" if index else "2K") for ratio, values in SIZES.items()
                  for index, value in enumerate(values) if value == size), None)
    if match is None:
        raise ValueError("Original GPT Image size changed")
    expected = build_payload(model_key=model_key, prompt=payload["prompt"], image_urls=refs,
                             aspect_ratio=match[0], quality=match[1])
    if payload != expected or saved.get("endpoint") != ("edits" if refs else "generations"):
        raise ValueError("Original GPT Image contract changed")
    return await transport._generate_image(
        payload, request_id=rid, subdir=payload["model"], timeout_seconds=settings.GPT_IMAGE_TIMEOUT_SECONDS,
    )

