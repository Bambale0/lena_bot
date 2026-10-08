from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from api.neironych_image_adapter import (
    mirror_verified_nano_banana21_result as mirror_verified_nano_banana21_result,
)
from api.nexusapi_client import NexusApiClient, NexusApiError, extract_result_urls
from core.config import settings

NEXUS_TASK_PREFIX = "nexus:"
NEXUS_SUBMISSION_PREFIX = "nexus-submit:"


class NexusImageSubmissionUnknown(NexusApiError):
    """Nexus may have accepted a paid POST but no task id was returned."""

    def __init__(self, message: str, *, idempotency_key: str) -> None:
        super().__init__(message)
        self.idempotency_key = idempotency_key


class NexusImageTaskFailed(NexusApiError):
    """A successful canonical GET confirmed failure for this exact task."""

    def __init__(self, message: str, *, task_id: str, payload: dict[str, Any]) -> None:
        super().__init__(message, payload=payload)
        self.task_id = task_id

# APIX keeps its historical/public model keys so Telegram/Mini App UX, history,
# pricing rows and repeat contracts stay stable. Only the provider boundary is
# translated to the live NexusAPI model ids.
NEXUS_IMAGE_MODEL_MAP: dict[str, str] = {
    "nano-banana-pro": "nano-banana-pro",
    "nano-banana-2": "nano-banana-2",
    "nano-banana-2.1": "nano-banana-2.1",
    "gpt-image-2-text-to-image": "gpt-image-2",
    "gpt-image-2-image-to-image": "gpt-image-2",
    "nano-banana-pro-vip": "nano-banana-pro-vip",
    "gpt-image-2-vip": "gpt-image-2-vip",
}

NEXUS_IMAGE_REFERENCE_LIMITS: dict[str, int] = {
    "nano-banana-pro": 4,
    "nano-banana-2": 4,
    "nano-banana-2.1": 4,
    "gpt-image-2": 4,
    "nano-banana-pro-vip": 14,
    "gpt-image-2-vip": 4,
}

_NANO_RATIOS = {
    "auto",
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "5:4",
    "4:5",
    "21:9",
}
_NANO21_RATIOS = _NANO_RATIOS | {"1:4", "4:1", "1:8", "8:1"}
_GPT_RATIOS = {
    "auto",
    "1:1",
    "3:2",
    "2:3",
    "16:9",
    "9:16",
    "5:4",
    "4:5",
    "4:3",
    "3:4",
    "21:9",
    "9:21",
    "1:3",
    "3:1",
    "2:1",
    "1:2",
}

NEXUS_IMAGE_ASPECT_RATIOS: dict[str, set[str]] = {
    "nano-banana-pro": _NANO_RATIOS,
    "nano-banana-2": _NANO_RATIOS,
    "nano-banana-2.1": _NANO21_RATIOS,
    "gpt-image-2": _GPT_RATIOS,
    "nano-banana-pro-vip": _NANO_RATIOS,
    "gpt-image-2-vip": _GPT_RATIOS,
}


def is_nexus_image_model(model_key: str) -> bool:
    return str(model_key or "").strip() in NEXUS_IMAGE_MODEL_MAP


def nexus_model_name(model_key: str) -> str:
    key = str(model_key or "").strip()
    try:
        return NEXUS_IMAGE_MODEL_MAP[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported Nexus image model: {key}") from exc


def prefix_nexus_task_id(task_id: str) -> str:
    value = str(task_id or "").strip()
    if not value:
        raise ValueError("Nexus task_id is required")
    return value if value.startswith(NEXUS_TASK_PREFIX) else f"{NEXUS_TASK_PREFIX}{value}"


def strip_nexus_task_id(task_id: str) -> str:
    value = str(task_id or "").strip()
    if value.startswith(NEXUS_TASK_PREFIX):
        value = value[len(NEXUS_TASK_PREFIX) :]
    if not value:
        raise ValueError("Nexus task_id is required")
    return value


def is_nexus_task_id(task_id: str | None) -> bool:
    return str(task_id or "").strip().startswith(NEXUS_TASK_PREFIX)


def encode_submission_id(idempotency_key: str) -> str:
    return NEXUS_SUBMISSION_PREFIX + str(uuid.UUID(idempotency_key))


def decode_submission_id(task_id: str | None) -> str | None:
    value = str(task_id or "").strip().removeprefix("web:")
    if not value.startswith(NEXUS_SUBMISSION_PREFIX):
        return None
    try:
        return str(uuid.UUID(value[len(NEXUS_SUBMISSION_PREFIX):]))
    except (ValueError, AttributeError):
        return None


def nexus_webhook_url(callback_url: str | None) -> str | None:
    value = str(callback_url or "").strip()
    if not value:
        return None
    parts = urlsplit(value)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["provider"] = "nexus"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def correlated_webhook_url(callback_url: str | None, request_id: str) -> str | None:
    """Bind a lost create response to its durable submission without another POST."""
    if not callback_url:
        return None
    parts = urlsplit(callback_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    secret = query.get("secret", "")
    if not secret:
        raise ValueError("Nexus recoverable submissions require an authenticated webhook")
    query["nexus_request_id"] = str(uuid.UUID(request_id))
    query["nexus_signature"] = submission_signature(request_id, secret)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def submission_signature(request_id: str, secret: str) -> str:
    return hmac.new(secret.encode(), ("nano21:" + str(uuid.UUID(request_id))).encode(), hashlib.sha256).hexdigest()


def submission_snapshot(params: dict[str, Any], request_id: str, client: NexusApiClient) -> dict[str, Any]:
    """Freeze provider inputs; never store the callback secret or API credential."""
    encoded = json.dumps({"params": params}, sort_keys=True, separators=(",", ":"))
    safe_params = json.loads(json.dumps(params))
    safe_params.pop("webhook_url", None)
    return {
        "version": 1,
        "request_id": str(uuid.UUID(request_id)),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "params": safe_params,
        "has_webhook": bool(params.get("webhook_url")),
        "payload_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "provider_scope_sha256": provider_scope_fingerprint(client),
    }


def provider_scope_fingerprint(client: NexusApiClient | None = None) -> str:
    client = client or NexusApiClient()
    return hashlib.sha256((client.base_url + "\0" + client.api_key).encode()).hexdigest()


def submission_scope_matches(input_params: Any) -> bool:
    if isinstance(input_params, str):
        try:
            input_params = json.loads(input_params)
        except ValueError:
            return False
    snapshot = input_params.get("nexus_submission", {}) if isinstance(input_params, dict) else {}
    if not isinstance(snapshot, dict):
        return False
    fingerprint = snapshot.get("provider_scope_sha256")
    # Legacy rows have no credential namespace evidence. They are never replayed.
    if fingerprint is None:
        return True
    return isinstance(fingerprint, str) and hmac.compare_digest(fingerprint, provider_scope_fingerprint())


def _clean_refs(values: Iterable[str] | None) -> list[str]:
    refs: list[str] = []
    for raw in values or []:
        value = str(raw or "").strip()
        if not value or value in refs:
            continue
        if not value.startswith(("http://", "https://", "data:image/")):
            raise ValueError("Nexus image reference must be a public http(s) URL or data:image URL")
        refs.append(value)
    return refs


def _validate_ratio(model_name: str, aspect_ratio: str | None) -> str | None:
    value = str(aspect_ratio or "").strip() or None
    if value is None:
        return None
    allowed = NEXUS_IMAGE_ASPECT_RATIOS[model_name]
    if value not in allowed:
        raise ValueError(f"Unsupported aspect ratio {value} for Nexus {model_name}")
    return value


def _task_error(payload: dict[str, Any]) -> str:
    for source in (
        payload,
        payload.get("error") if isinstance(payload.get("error"), dict) else {},
        payload.get("result") if isinstance(payload.get("result"), dict) else {},
    ):
        if not isinstance(source, dict):
            continue
        for key in ("message", "detail", "error", "fail_reason", "failReason"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return "NexusAPI generation failed"


def build_nexus_image_params(
    *,
    model_key: str,
    prompt: str,
    image_urls: Iterable[str] | None = None,
    aspect_ratio: str | None = None,
    quality: str | None = None,
    callback_url: str | None = None,
    output_format: str | None = None,
) -> dict[str, Any]:
    prompt_value = str(prompt or "").strip()
    if not prompt_value:
        raise ValueError("Image prompt is required")

    model_name = nexus_model_name(model_key)
    refs = _clean_refs(image_urls)
    limit = NEXUS_IMAGE_REFERENCE_LIMITS[model_name]
    if len(refs) > limit:
        raise ValueError(f"{model_name} supports at most {limit} reference images")

    ratio = _validate_ratio(model_name, aspect_ratio)
    params: dict[str, Any] = {
        "model_name": model_name,
        "prompt": prompt_value,
    }
    if refs:
        params["image_urls"] = refs
    if ratio is not None:
        params["aspect_ratio"] = ratio

    quality_value = str(quality or "").strip()
    if model_name in {"nano-banana-pro", "nano-banana-2", "nano-banana-2.1"}:
        params["image_size"] = quality_value if quality_value in {"1K", "2K", "4K"} else "2K"
    elif model_name == "nano-banana-pro-vip":
        params["image_size"] = quality_value if quality_value in {"1K", "2K"} else "2K"
    # The live GptImage2Params/GptImage2VipParams schemas intentionally expose
    # no resolution field. APIX keeps its existing quality control for UX and
    # billing continuity, but does not send an unsupported provider parameter.

    webhook = nexus_webhook_url(callback_url)
    if webhook:
        params["webhook_url"] = webhook
    return params


async def create_nexus_image_task(
    *,
    model_key: str,
    prompt: str,
    image_urls: Iterable[str] | None = None,
    aspect_ratio: str | None = None,
    quality: str | None = None,
    callback_url: str | None = None,
    output_format: str | None = None,
    idempotency_key: str | None = None,
    before_submit: Callable[[str, dict[str, Any]], Awaitable[None]] | None = None,
) -> str:
    if model_key == "nano-banana-2.1" and idempotency_key:
        if before_submit and not callback_url:
            query = urlencode({"secret": settings.KIE_WEBHOOK_SECRET})
            callback_url = f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}?{query}"
        callback_url = correlated_webhook_url(callback_url, idempotency_key)
    params = build_nexus_image_params(
        model_key=model_key,
        prompt=prompt,
        image_urls=image_urls,
        aspect_ratio=aspect_ratio,
        quality=quality,
        callback_url=callback_url,
        output_format=output_format,
    )
    persisted_key = (
        str(uuid.UUID(idempotency_key)) if idempotency_key else None
    )
    client = NexusApiClient()
    if persisted_key and before_submit:
        await before_submit(persisted_key, submission_snapshot(params, persisted_key, client))
    try:
        result = await client.create_params(
            params,
            idempotency_key=persisted_key,
        )
    except NexusApiError as exc:
        status = exc.status_code
        if persisted_key and (
            status is None or status >= 500 or 200 <= status < 300
        ):
            raise NexusImageSubmissionUnknown(
                "Nexus submission outcome unknown; do not refund or resubmit with a new key",
                idempotency_key=persisted_key,
            ) from exc
        raise
    return prefix_nexus_task_id(result.task_id)


async def get_nexus_task_payload(task_id: str) -> dict[str, Any]:
    return await NexusApiClient().get_task(strip_nexus_task_id(task_id))


async def poll_nexus_image_result_urls(task_id: str, *, strict: bool = False) -> list[str] | None:
    payload = await get_nexus_task_payload(task_id)
    raw_task_id = strip_nexus_task_id(task_id)
    if strict and str(payload.get("task_id") or "") != raw_task_id:
        raise NexusApiError("Nexus canonical task identity mismatch")
    status = str(payload.get("status") or "").strip().lower()
    if status == "completed":
        urls = extract_result_urls(payload)
        if not urls:
            raise NexusApiError("NexusAPI image task completed without result URL", payload=payload)
        return urls
    if status == "failed":
        if strict:
            raise NexusImageTaskFailed(_task_error(payload), task_id=raw_task_id, payload=payload)
        raise NexusApiError(_task_error(payload), payload=payload)
    return None
