from __future__ import annotations

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from api.public_files import save_public_file
from core.config import settings

logger = logging.getLogger(__name__)

OPENROUTER_TASK_PREFIX = "openrouter:"

IMAGE_MODEL_BY_SOURCE: dict[str, str] = {
    "nano-banana-2": "google/gemini-3.1-flash-image-preview",
    "nano-banana-pro": "google/gemini-3-pro-image-preview",
    "gpt-image-2-text-to-image": "openai/gpt-5.4-image-2",
    "gpt-image-2-image-to-image": "openai/gpt-5.4-image-2",
}

IMAGE_ONLY_MODELS = {
    "bytedance-seed/seedream-4.5",
    "x-ai/grok-imagine-image-quality",
}

VIDEO_MODEL_BY_SOURCE: dict[str, str] = {
    "wan/2-7-text-to-video": "alibaba/wan-2.7",
    "wan/2-7-image-to-video": "alibaba/wan-2.7",
    "veo3_fast": "google/veo-3.1-fast",
    "veo3": "google/veo-3.1",
    "kling-3.0/video": "kwaivgi/kling-v3.0-pro",
}

TEXT_MODEL_BY_SOURCE: dict[str, str] = {
    "gpt-5-2": "openai/gpt-5.2",
    "gpt-5.2": "openai/gpt-5.2",
    "gpt-5-4": "openai/gpt-5.4",
    "gpt-5.4": "openai/gpt-5.4",
    "gpt-5.4-mini": "openai/gpt-5.4-mini",
    "gpt-5-5": "openai/gpt-5.5",
    "gpt-5.5": "openai/gpt-5.5",
    "claude-sonnet-4-5": "anthropic/claude-sonnet-4.5",
    "claude-sonnet-4.5": "anthropic/claude-sonnet-4.5",
}

_client: httpx.AsyncClient | None = None


@dataclass(frozen=True)
class OpenRouterImageResult:
    urls: list[str]
    task_id: str = "openrouter:image:direct"


@dataclass(frozen=True)
class OpenRouterVideoResult:
    task_id: str
    provider: str = "openrouter"
    uses_webhook: bool = False


def configured() -> bool:
    return bool(str(getattr(settings, "OPENROUTER_API_KEY", "") or "").strip())


def force_migrated_models() -> bool:
    return bool(getattr(settings, "OPENROUTER_FORCE_MIGRATED_MODELS", False))


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=str(getattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")).rstrip("/"),
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()


def image_model_for_source(source_model: str) -> str | None:
    return IMAGE_MODEL_BY_SOURCE.get(str(source_model or "").strip())


def video_model_for_source(source_model: str) -> str | None:
    return VIDEO_MODEL_BY_SOURCE.get(str(source_model or "").strip())


def _video_model_for_request(source_model: str, resolution: str | None) -> str | None:
    if source_model == "kling-3.0/video" and str(resolution or "").strip() == "std":
        return "kwaivgi/kling-v3.0-std"
    return video_model_for_source(source_model)


def text_model_for_source(source_model: str | None) -> str | None:
    value = str(source_model or "").strip()
    if not value:
        return None
    if "/" in value:
        return value
    return TEXT_MODEL_BY_SOURCE.get(value, value)


def is_openrouter_task_id(task_id: str | None) -> bool:
    return bool(task_id and task_id.startswith(OPENROUTER_TASK_PREFIX))


def prefixed_task_id(kind: str, raw_task_id: str) -> str:
    if is_openrouter_task_id(raw_task_id):
        return raw_task_id
    return f"{OPENROUTER_TASK_PREFIX}{kind}:{raw_task_id}"


def _split_task_id(task_id: str) -> tuple[str, str]:
    if not is_openrouter_task_id(task_id):
        raise ValueError(f"Not an OpenRouter task id: {task_id!r}")
    rest = task_id[len(OPENROUTER_TASK_PREFIX):]
    kind, sep, raw = rest.partition(":")
    if not sep or not kind or not raw:
        raise ValueError(f"Malformed OpenRouter task id: {task_id!r}")
    return kind, raw


def _refs(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [item for item in value if item]


def _quality_to_image_size(quality: str | None, resolution: str | None) -> str | None:
    value = str(resolution or quality or "").strip()
    mapping = {"basic": "2K", "high": "4K", "0.5K": "0.5K", "1K": "1K", "2K": "2K", "4K": "4K"}
    return mapping.get(value)


def _data_url_to_public_url(url: str) -> str | None:
    if not url.startswith("data:") or "," not in url:
        return None
    header, data = url.split(",", 1)
    mime_type = header.removeprefix("data:").split(";", 1)[0] or "image/png"
    try:
        return save_public_file(base64.b64decode(data), mime_type)
    except Exception as exc:
        logger.warning("Failed to persist OpenRouter image data URL: %s", exc)
        return None


def _urls_from_image_value(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        image_url = value.get("image_url") or value.get("imageUrl")
        if isinstance(image_url, dict):
            raw_url = image_url.get("url")
            if isinstance(raw_url, str) and raw_url:
                urls.append(_data_url_to_public_url(raw_url) or raw_url)
        for key in ("url", "result_url", "resultUrl"):
            raw_url = value.get(key)
            if isinstance(raw_url, str) and raw_url:
                urls.append(_data_url_to_public_url(raw_url) or raw_url)
        for key in ("images", "content", "data", "result", "results"):
            urls.extend(_urls_from_image_value(value.get(key)))
    elif isinstance(value, list):
        for item in value:
            urls.extend(_urls_from_image_value(item))
    return list(dict.fromkeys(urls))


async def _request_with_retry(method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
    client = get_client()
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            resp = await client.request(method, path, json=json)
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"OpenRouter returned non-object payload: {payload!r}")
            if payload.get("error"):
                raise RuntimeError(f"{payload['error']!r}")
            return payload
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            logger.warning("OpenRouter HTTP %s: %s (attempt %d)", exc.response.status_code, path, attempt + 1)
            if exc.response.status_code < 500:
                raise
        except (httpx.RequestError, RuntimeError, ValueError) as exc:
            last_exc = exc
            logger.warning("OpenRouter request error: %s (attempt %d)", exc, attempt + 1)
        await asyncio.sleep(1.5 ** attempt)
    raise RuntimeError(f"OpenRouter max retries exceeded for {method} {path}: {last_exc}") from last_exc


async def chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_completion_tokens: int = 4096,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if not configured():
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_completion_tokens": max_completion_tokens,
    }
    if reasoning_effort and model.startswith("openai/"):
        payload["reasoning_effort"] = reasoning_effort
    return await _request_with_retry("POST", "/chat/completions", json=payload)


async def generate_image(
    *,
    source_model: str,
    prompt: str,
    reference_urls: str | list[str] | None = None,
    aspect_ratio: str | None = None,
    count: int = 1,
    resolution: str | None = None,
    quality: str | None = None,
) -> OpenRouterImageResult:
    if not configured():
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    model = image_model_for_source(source_model)
    if not model:
        raise RuntimeError(f"OpenRouter has no mapped image model for {source_model}")

    refs = _refs(reference_urls)[:14]
    content: str | list[dict[str, Any]]
    if refs:
        content_parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content_parts.extend({"type": "image_url", "image_url": {"url": url}} for url in refs)
        content = content_parts
    else:
        content = prompt

    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image"] if model in IMAGE_ONLY_MODELS else ["image", "text"],
        "stream": False,
    }
    image_config: dict[str, Any] = {}
    if aspect_ratio and aspect_ratio != "auto":
        image_config["aspect_ratio"] = aspect_ratio
    image_size = _quality_to_image_size(quality, resolution)
    if image_size:
        image_config["image_size"] = image_size
    if image_config:
        payload["image_config"] = image_config

    urls: list[str] = []
    safe_count = max(1, min(int(count or 1), 4))
    for _ in range(safe_count):
        resp = await _request_with_retry("POST", "/chat/completions", json=payload)
        urls.extend(_urls_from_image_value(resp.get("choices") or resp))

    urls = list(dict.fromkeys(urls))
    if not urls:
        raise RuntimeError(f"OpenRouter image generation returned no images for {source_model}")
    logger.info("OpenRouter image %s -> %s produced %d result(s)", source_model, model, len(urls))
    return OpenRouterImageResult(urls=urls)


def _video_resolution(value: str | None) -> str | None:
    value = str(value or "").strip()
    if value in {"480p", "720p", "1080p", "1K", "2K", "4K"}:
        return value
    if value == "std":
        return "720p"
    if value in {"pro"}:
        return "1080p"
    return None


def _video_aspect_ratio(value: str | None) -> str | None:
    value = str(value or "").strip()
    allowed = {"16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9", "9:21"}
    return value if value in allowed else None


async def generate_video(
    *,
    source_model: str,
    prompt: str,
    reference_urls: str | list[str] | None = None,
    last_frame_url: str | None = None,
    duration: int = 5,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    seed: int | None = None,
) -> OpenRouterVideoResult:
    if not configured():
        raise RuntimeError("OPENROUTER_API_KEY is not configured")
    model = _video_model_for_request(source_model, resolution)
    if not model:
        raise RuntimeError(f"OpenRouter has no mapped video model for {source_model}")

    refs = _refs(reference_urls)
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "duration": max(1, min(int(duration or 5), 30)),
    }
    normalized_resolution = _video_resolution(resolution)
    if normalized_resolution:
        payload["resolution"] = normalized_resolution
    normalized_ratio = _video_aspect_ratio(aspect_ratio)
    if normalized_ratio:
        payload["aspect_ratio"] = normalized_ratio
    if seed is not None:
        payload["seed"] = seed

    if refs:
        frame_images = [
            {
                "type": "image_url",
                "image_url": {"url": refs[0]},
                "frame_type": "first_frame",
            }
        ]
        if last_frame_url:
            frame_images.append(
                {
                    "type": "image_url",
                    "image_url": {"url": last_frame_url},
                    "frame_type": "last_frame",
                }
            )
        payload["frame_images"] = frame_images
        if len(refs) > 1:
            payload["input_references"] = [
                {"type": "image_url", "image_url": {"url": url}}
                for url in refs[1:9]
            ]

    resp = await _request_with_retry("POST", "/videos", json=payload)
    raw_task_id = str(resp.get("id") or resp.get("job_id") or resp.get("task_id") or "").strip()
    if not raw_task_id:
        raise RuntimeError(f"OpenRouter video returned no job id for {source_model}: {resp!r}")
    logger.info("OpenRouter video %s -> %s task %s", source_model, model, raw_task_id)
    return OpenRouterVideoResult(task_id=prefixed_task_id("video", raw_task_id))


def _video_urls_from_status(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("unsigned_urls", "signed_urls", "urls", "video_urls", "result_urls"):
        items = payload.get(key)
        if isinstance(items, list):
            urls.extend(str(item) for item in items if item)
    for key in ("url", "video_url", "result_url"):
        item = payload.get(key)
        if isinstance(item, str) and item:
            urls.append(item)
    return list(dict.fromkeys(urls))


async def poll_video_status(task_id: str) -> str | None:
    kind, raw_task_id = _split_task_id(task_id)
    if kind != "video":
        raise ValueError(f"OpenRouter task kind is not video: {kind}")
    resp = await _request_with_retry("GET", f"/videos/{quote(raw_task_id, safe='')}")
    status = str(resp.get("status") or "").lower()
    if status == "completed":
        urls = _video_urls_from_status(resp)
        if urls:
            return urls[0]
        raise RuntimeError(f"OpenRouter video completed without URL: {resp!r}")
    if status in {"failed", "cancelled", "canceled", "expired", "error"}:
        raise RuntimeError(str(resp.get("error") or resp.get("message") or "OpenRouter video generation failed"))
    return None
