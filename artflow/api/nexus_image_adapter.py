from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from api.nexusapi_client import NexusApiClient, NexusApiError, extract_result_urls

NEXUS_TASK_PREFIX = "nexus:"

# APIX keeps its historical/public model keys so Telegram/Mini App UX, history,
# pricing rows and repeat contracts stay stable. Only the provider boundary is
# translated to the live NexusAPI model ids.
NEXUS_IMAGE_MODEL_MAP: dict[str, str] = {
    "nano-banana-pro": "nano-banana-pro",
    "nano-banana-2": "nano-banana-2",
    "seedream/5-pro-text-to-image": "seedream-5.0-pro",
    "seedream/5-pro-image-to-image": "seedream-5.0-pro",
    "gpt-image-2-text-to-image": "gpt-image-2",
    "gpt-image-2-image-to-image": "gpt-image-2",
    "nano-banana-pro-vip": "nano-banana-pro-vip",
    "gpt-image-2-vip": "gpt-image-2-vip",
}

NEXUS_IMAGE_REFERENCE_LIMITS: dict[str, int] = {
    "nano-banana-pro": 4,
    "nano-banana-2": 4,
    "seedream-5.0-pro": 10,
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
_SEEDREAM_RATIOS = {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}
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
    "seedream-5.0-pro": _SEEDREAM_RATIOS,
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


def nexus_webhook_url(callback_url: str | None) -> str | None:
    value = str(callback_url or "").strip()
    if not value:
        return None
    parts = urlsplit(value)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["provider"] = "nexus"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


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
    if model_name in {"nano-banana-pro", "nano-banana-2"}:
        params["image_size"] = quality_value if quality_value in {"1K", "2K", "4K"} else "2K"
    elif model_name == "nano-banana-pro-vip":
        params["image_size"] = quality_value if quality_value in {"1K", "2K"} else "2K"
    elif model_name == "seedream-5.0-pro":
        resolution = {"basic": "1K", "high": "2K"}.get(quality_value, quality_value)
        params["resolution"] = resolution if resolution in {"1K", "1.5K", "2K"} else "2K"
        fmt = str(output_format or "").strip().lower()
        if fmt in {"jpeg", "jpg", "png"}:
            params["output_format"] = fmt

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
) -> str:
    params = build_nexus_image_params(
        model_key=model_key,
        prompt=prompt,
        image_urls=image_urls,
        aspect_ratio=aspect_ratio,
        quality=quality,
        callback_url=callback_url,
        output_format=output_format,
    )
    result = await NexusApiClient().create_params(params)
    return prefix_nexus_task_id(result.task_id)


async def get_nexus_task_payload(task_id: str) -> dict[str, Any]:
    return await NexusApiClient().get_task(strip_nexus_task_id(task_id))


async def poll_nexus_image_result_urls(task_id: str) -> list[str] | None:
    payload = await get_nexus_task_payload(task_id)
    status = str(payload.get("status") or "").strip().lower()
    if status == "completed":
        urls = extract_result_urls(payload)
        if not urls:
            raise NexusApiError("NexusAPI image task completed without result URL", payload=payload)
        return urls
    if status == "failed":
        raise NexusApiError(_task_error(payload), payload=payload)
    return None
