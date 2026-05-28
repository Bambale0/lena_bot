from __future__ import annotations

import base64
import logging
import mimetypes
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

import httpx

from api import comet_client
from api.public_files import detect_image_extension, local_upload_path_from_url, save_public_file
from core.gemini_omni import GEMINI_OMNI_VIDEO_MODEL

logger = logging.getLogger(__name__)

COMET_TASK_PREFIX = "comet:"
_UNIVERSAL_IMAGE_MODEL = "doubao-seedream-4-5-251128"
_MAX_GEMINI_REFERENCE_BYTES = 30 * 1024 * 1024

_GEMINI_IMAGE_MODEL_BY_SOURCE = {
    "nano-banana-2": "gemini-3.1-flash-image-preview",
    "nano-banana-pro": "gemini-3-pro-image-preview",
}

_IMAGE_SIZE_BY_RATIO = {
    "1:1": "2048x2048",
    "4:3": "2304x1728",
    "3:4": "1728x2304",
    "16:9": "2848x1600",
    "9:16": "1600x2848",
    "3:2": "2496x1664",
    "2:3": "1664x2496",
    "21:9": "3024x1296",
}

_SEEDANCE_MODEL_BY_SOURCE = {
    "bytedance/seedance-2": "doubao-seedance-2-0",
    "bytedance/seedance-2-fast": "doubao-seedance-2-0-fast",
}

_VEO_MODEL_BY_SOURCE = {
    "veo3": "veo3",
    "veo3_fast": "veo3-fast",
    "veo3_lite": "veo3-fast",
}


@dataclass(frozen=True)
class CometImageResult:
    urls: list[str]
    task_id: str = "comet:image:direct"


@dataclass(frozen=True)
class CometVideoResult:
    task_id: str
    provider: str = "comet"
    uses_webhook: bool = False


def is_comet_task_id(task_id: str | None) -> bool:
    return bool(task_id and task_id.startswith(COMET_TASK_PREFIX))


def _refs(value: str | list[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [item for item in value if item]


def _prefixed_task_id(kind: str, raw_task_id: str) -> str:
    return f"{COMET_TASK_PREFIX}{kind}:{raw_task_id}"


def prefixed_task_id(kind: str, raw_task_id: str) -> str:
    if is_comet_task_id(raw_task_id):
        return raw_task_id
    return _prefixed_task_id(kind, raw_task_id)


def _split_prefixed_task_id(task_id: str) -> tuple[str, str]:
    if not is_comet_task_id(task_id):
        raise ValueError(f"Not a Comet fallback task id: {task_id!r}")
    rest = task_id[len(COMET_TASK_PREFIX):]
    kind, sep, raw = rest.partition(":")
    if not sep or not kind or not raw:
        raise ValueError(f"Malformed Comet fallback task id: {task_id!r}")
    return kind, raw


def _image_size(aspect_ratio: str | None) -> str:
    return _IMAGE_SIZE_BY_RATIO.get(str(aspect_ratio or ""), "2048x2048")


def _gemini_image_size(resolution: str | None) -> str | None:
    value = str(resolution or "").strip().upper()
    return value if value in {"1K", "2K", "4K"} else None


def _video_ratio(aspect_ratio: str | None, default: str = "16:9") -> str:
    value = str(aspect_ratio or default)
    return value if value in {"1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"} else default


def _veo_size(aspect_ratio: str | None) -> str:
    ratio = _video_ratio(aspect_ratio)
    return ratio.replace(":", "x")


def _seedance_size(aspect_ratio: str | None, resolution: str | None) -> str:
    ratio = _video_ratio(aspect_ratio)
    if resolution == "1080p":
        return {
            "16:9": "1920x1080",
            "9:16": "1080x1920",
            "4:3": "1440x1080",
            "3:4": "1080x1440",
            "1:1": "1440x1440",
            "21:9": "1920x832",
        }.get(ratio, "1920x1080")
    if resolution == "480p":
        return {
            "16:9": "864x496",
            "9:16": "496x864",
            "4:3": "752x560",
            "3:4": "560x752",
            "1:1": "640x640",
            "21:9": "992x432",
        }.get(ratio, ratio)
    return {
        "16:9": "1280x720",
        "9:16": "720x1280",
        "4:3": "960x720",
        "3:4": "720x960",
        "1:1": "960x960",
        "21:9": "1280x576",
    }.get(ratio, ratio)


def _extract_task_id(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("id", "task_id", "taskId", "video_id", "videoId"):
            item = value.get(key)
            if item:
                return str(item)
        for nested in value.values():
            task_id = _extract_task_id(nested)
            if task_id:
                return task_id
        request_id = value.get("request_id")
        if request_id:
            return str(request_id)
    if isinstance(value, list):
        for item in value:
            task_id = _extract_task_id(item)
            if task_id:
                return task_id
    return None


def _urls_from_value(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key in ("inlineData", "inline_data"):
            inline_data = value.get(key)
            if isinstance(inline_data, dict):
                inline_url = _url_from_inline_image(inline_data)
                if inline_url:
                    urls.append(inline_url)
        if ("mimeType" in value or "mime_type" in value) and isinstance(value.get("data"), str):
            inline_url = _url_from_inline_image(value)
            if inline_url:
                urls.append(inline_url)
        for key in (
            "url",
            "video_url",
            "videoUrl",
            "image_url",
            "imageUrl",
            "result_url",
            "resultUrl",
        ):
            item = value.get(key)
            if isinstance(item, str) and item.startswith("http"):
                urls.append(item)
        for key in ("urls", "video_urls", "videoUrls", "image_urls", "imageUrls", "result_urls", "resultUrls"):
            items = value.get(key)
            if isinstance(items, list):
                urls.extend(str(item) for item in items if str(item).startswith("http"))
        b64_json = value.get("b64_json")
        if isinstance(b64_json, str) and b64_json:
            try:
                urls.append(save_public_file(base64.b64decode(b64_json), "image/png"))
            except Exception as exc:
                logger.warning("Failed to persist CometAPI b64 image fallback: %s", exc)
        for key, nested in value.items():
            if key in {"inlineData", "inline_data"}:
                continue
            urls.extend(_urls_from_value(nested))
    elif isinstance(value, list):
        for item in value:
            urls.extend(_urls_from_value(item))
    return list(dict.fromkeys(urls))


def _url_from_inline_image(value: dict[str, Any]) -> str | None:
    data = value.get("data")
    if not isinstance(data, str) or not data:
        return None
    if data.startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    mime_type = str(value.get("mimeType") or value.get("mime_type") or "image/png")
    try:
        return save_public_file(base64.b64decode(data), mime_type)
    except Exception as exc:
        logger.warning("Failed to persist CometAPI inline image fallback: %s", exc)
        return None


def _mode_from_resolution(resolution: str | None) -> str:
    return "pro" if resolution in {"pro", "1080p", "2K", "4K"} else "std"


def _callback_url_for_kind(callback_url: str | None, kind: str) -> str | None:
    if not callback_url:
        return None
    parts = urlsplit(callback_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["provider"] = "comet"
    query["comet_kind"] = kind
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _mime_type_for_image_bytes(data: bytes, content_type: str | None = None, fallback_name: str | None = None) -> str:
    if content_type and content_type.lower().startswith("image/"):
        return content_type.split(";", 1)[0].strip().lower()
    guessed, _ = mimetypes.guess_type(fallback_name or "")
    if guessed and guessed.lower().startswith("image/"):
        return guessed.lower()
    ext = detect_image_extension(data)
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(ext, "image/jpeg")


async def _inline_image_part_from_url(url: str) -> dict[str, Any]:
    local_path = local_upload_path_from_url(url)
    if local_path and local_path.exists() and local_path.is_file():
        data = local_path.read_bytes()
        if len(data) > _MAX_GEMINI_REFERENCE_BYTES:
            raise RuntimeError(f"CometAPI Gemini reference is too large: {url}")
        mime_type = _mime_type_for_image_bytes(data, fallback_name=local_path.name)
        return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode("ascii")}}

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise RuntimeError(f"CometAPI Gemini reference must be an HTTP URL: {url!r}")
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.content
    if len(data) > _MAX_GEMINI_REFERENCE_BYTES:
        raise RuntimeError(f"CometAPI Gemini reference is too large: {url}")
    mime_type = _mime_type_for_image_bytes(data, resp.headers.get("content-type"), parsed.path)
    return {"inlineData": {"mimeType": mime_type, "data": base64.b64encode(data).decode("ascii")}}


async def _generate_gemini_image(
    *,
    source_model: str,
    gemini_model: str,
    prompt: str,
    reference_urls: list[str],
    aspect_ratio: str | None,
    resolution: str | None,
) -> CometImageResult:
    parts: list[dict[str, Any]] = [{"text": prompt}]
    for url in reference_urls:
        parts.append(await _inline_image_part_from_url(url))

    image_config: dict[str, Any] = {}
    if aspect_ratio and aspect_ratio != "auto":
        image_config["aspectRatio"] = aspect_ratio
    image_size = _gemini_image_size(resolution)
    if image_size:
        image_config["imageSize"] = image_size

    generation_config: dict[str, Any] = {"responseModalities": ["IMAGE"]}
    if image_config:
        generation_config["imageConfig"] = image_config

    resp = await comet_client.post(
        f"/v1beta/models/{quote(gemini_model, safe='')}:generateContent",
        {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config,
        },
    )
    urls = _urls_from_value(resp)
    if not urls:
        raise RuntimeError(f"CometAPI Gemini image fallback returned no image URLs for {source_model}: {resp!r}")
    logger.info("CometAPI Gemini image fallback %s/%s -> %s result(s)", source_model, gemini_model, len(urls))
    return CometImageResult(urls=urls)


async def generate_image(
    *,
    model_key: str,
    prompt: str,
    reference_urls: str | list[str] | None = None,
    aspect_ratio: str | None = None,
    count: int = 1,
    resolution: str | None = None,
) -> CometImageResult:
    refs = _refs(reference_urls)[:14]
    gemini_model = _GEMINI_IMAGE_MODEL_BY_SOURCE.get(model_key)
    if gemini_model:
        return await _generate_gemini_image(
            source_model=model_key,
            gemini_model=gemini_model,
            prompt=prompt,
            reference_urls=refs,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )

    safe_count = max(1, min(int(count or 1), max(1, 15 - len(refs))))
    payload: dict[str, Any] = {
        "model": _UNIVERSAL_IMAGE_MODEL,
        "prompt": prompt,
        "response_format": "url",
        "size": _image_size(aspect_ratio),
        "n": safe_count,
        "watermark": False,
    }
    if refs:
        payload["image"] = refs
    if safe_count > 1:
        payload["sequential_image_generation"] = "auto"
        payload["sequential_image_generation_options"] = {"max_images": safe_count}

    resp = await comet_client.post("/v1/images/generations", payload)
    urls = _urls_from_value(resp)
    if not urls:
        raise RuntimeError(f"CometAPI image fallback returned no image URLs for {model_key}: {resp!r}")
    logger.info("CometAPI image fallback %s -> %s result(s)", model_key, len(urls))
    return CometImageResult(urls=urls)


async def generate_video(
    *,
    model_key: str,
    prompt: str,
    reference_urls: str | list[str] | None = None,
    last_frame_url: str | None = None,
    reference_video_url: str | None = None,
    duration: int = 5,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    grok_mode: str | None = None,
    audio_ids: list[str] | None = None,
    character_ids: list[str] | None = None,
    video_start: float | int | None = None,
    video_end: float | int | None = None,
    seed: int | None = None,
    callback_url: str | None = None,
) -> CometVideoResult:
    if model_key.startswith("grok-imagine/"):
        return await _generate_grok_video(
            prompt=prompt,
            reference_urls=reference_urls,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            callback_url=callback_url,
        )
    if model_key.startswith("kling-"):
        return await _generate_kling_video(
            prompt=prompt,
            reference_urls=reference_urls,
            last_frame_url=last_frame_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            callback_url=callback_url,
        )
    return await _generate_v1_video(
        model_key=model_key,
        prompt=prompt,
        reference_urls=reference_urls,
        last_frame_url=last_frame_url,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        callback_url=callback_url,
    )


async def _generate_grok_video(
    *,
    prompt: str,
    reference_urls: str | list[str] | None,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    callback_url: str | None,
) -> CometVideoResult:
    refs = _refs(reference_urls)
    payload: dict[str, Any] = {
        "model": "grok-imagine-video",
        "prompt": prompt,
        "duration": max(1, min(15, int(duration or 1))),
        "aspect_ratio": _video_ratio(aspect_ratio),
        "resolution": resolution if resolution in {"480p", "720p"} else "480p",
    }
    if refs:
        payload["image"] = {"url": refs[0]}
    resp = await comet_client.post("/grok/v1/videos/generations", payload)
    task_id = str(resp.get("request_id") or _extract_task_id(resp) or "").strip()
    if not task_id:
        raise RuntimeError(f"CometAPI Grok fallback returned no request_id: {resp!r}")
    return CometVideoResult(task_id=_prefixed_task_id("grok", task_id))


async def _generate_kling_video(
    *,
    prompt: str,
    reference_urls: str | list[str] | None,
    last_frame_url: str | None,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    callback_url: str | None,
) -> CometVideoResult:
    refs = _refs(reference_urls)
    safe_duration = str(10 if int(duration or 5) >= 10 else 5)
    common = {
        "prompt": prompt[:500],
        "duration": safe_duration,
        "mode": _mode_from_resolution(resolution),
    }
    if len(refs) >= 2:
        payload: dict[str, Any] = {
            **common,
            "model_name": "kling-v1-6",
            "image_list": [{"image": url} for url in refs[:4]],
        }
        kind = "kling-multi-image2video"
        webhook_url = _callback_url_for_kind(callback_url, kind)
        if webhook_url:
            payload["callback_url"] = webhook_url
        resp = await comet_client.post("/kling/v1/videos/multi-image2video", payload)
    elif refs:
        payload = {**common, "image": refs[0]}
        if last_frame_url:
            payload["image_tail"] = last_frame_url
        kind = "kling-image2video"
        webhook_url = _callback_url_for_kind(callback_url, kind)
        if webhook_url:
            payload["callback_url"] = webhook_url
        resp = await comet_client.post("/kling/v1/videos/image2video", payload)
    else:
        payload = {**common, "aspect_ratio": _video_ratio(aspect_ratio)}
        kind = "kling-text2video"
        webhook_url = _callback_url_for_kind(callback_url, kind)
        if webhook_url:
            payload["callback_url"] = webhook_url
        resp = await comet_client.post("/kling/v1/videos/text2video", payload)

    task_id = _extract_task_id(resp)
    if not task_id:
        raise RuntimeError(f"CometAPI Kling fallback returned no task id: {resp!r}")
    return CometVideoResult(task_id=_prefixed_task_id(kind, task_id), uses_webhook=bool(webhook_url))


async def _generate_v1_video(
    *,
    model_key: str,
    prompt: str,
    reference_urls: str | list[str] | None,
    last_frame_url: str | None,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    callback_url: str | None,
) -> CometVideoResult:
    refs = _refs(reference_urls)
    if last_frame_url:
        refs.append(last_frame_url)
    if model_key in _VEO_MODEL_BY_SOURCE:
        comet_model = _VEO_MODEL_BY_SOURCE[model_key]
        size = _veo_size(aspect_ratio)
    elif model_key == GEMINI_OMNI_VIDEO_MODEL:
        comet_model = "gemini-omni-flash"
        size = _seedance_size(aspect_ratio, resolution)
    else:
        comet_model = _SEEDANCE_MODEL_BY_SOURCE.get(model_key, "doubao-seedance-2-0")
        size = _seedance_size(aspect_ratio, resolution)

    files: list[tuple[str, Any]] = [
        ("model", (None, comet_model)),
        ("prompt", (None, prompt)),
        ("size", (None, size)),
    ]
    if model_key not in _VEO_MODEL_BY_SOURCE:
        files.append(("seconds", (None, str(max(1, min(15, int(duration or 5)))))))
    for url in refs[:9]:
        files.append(("input_reference", (None, url)))
    webhook_url = _callback_url_for_kind(callback_url, "video")
    if webhook_url:
        files.append(("callback_url", (None, webhook_url)))

    resp = await comet_client.post_multipart("/v1/videos", data={}, files=files)
    task_id = _extract_task_id(resp)
    if not task_id:
        raise RuntimeError(f"CometAPI video fallback returned no task id for {model_key}: {resp!r}")
    return CometVideoResult(task_id=_prefixed_task_id("video", task_id), uses_webhook=bool(webhook_url))


async def poll_status(task_id: str) -> str | None:
    kind, raw_task_id = _split_prefixed_task_id(task_id)
    if kind == "grok":
        return await _poll_grok(raw_task_id)
    if kind.startswith("kling-"):
        return await _poll_kling(raw_task_id, kind.removeprefix("kling-"))
    if kind == "video":
        return await _poll_v1_video(raw_task_id)
    if kind == "image":
        raise RuntimeError("CometAPI image fallback is synchronous and cannot be polled")
    raise ValueError(f"Unknown Comet fallback task kind: {kind}")


async def _poll_v1_video(task_id: str) -> str | None:
    resp = await comet_client.get(f"/v1/videos/{quote(task_id, safe='')}")
    status = str(resp.get("status") or resp.get("state") or "").lower()
    if status in {"completed", "succeeded", "success", "done"}:
        urls = _urls_from_value(resp)
        if urls:
            return urls[0]
        raise RuntimeError(f"CometAPI video task succeeded without URL: {resp!r}")
    if status in {"failed", "error", "cancelled", "canceled"}:
        raise RuntimeError(str(resp.get("error") or resp.get("message") or "CometAPI video task failed"))
    return None


async def _poll_grok(task_id: str) -> str | None:
    resp = await comet_client.get(f"/grok/v1/videos/{quote(task_id, safe='')}")
    status = str(resp.get("status") or "").lower()
    if status in {"done", "completed", "succeeded", "success"}:
        urls = _urls_from_value(resp)
        if urls:
            return urls[0]
        raise RuntimeError(f"CometAPI Grok task succeeded without URL: {resp!r}")
    if status in {"failed", "error", "cancelled", "canceled"}:
        raise RuntimeError(str(resp.get("error") or resp.get("message") or "CometAPI Grok task failed"))
    return None


async def _poll_kling(task_id: str, action2: str) -> str | None:
    resp = await comet_client.get(f"/kling/v1/videos/{action2}/{quote(task_id, safe='')}")
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    status = str(data.get("task_status") or resp.get("task_status") or resp.get("status") or "").lower()
    if status in {"succeed", "succeeded", "success", "completed", "done"}:
        urls = _urls_from_value(data.get("task_result") or data or resp)
        if urls:
            return urls[0]
        raise RuntimeError(f"CometAPI Kling task succeeded without URL: {resp!r}")
    if status in {"failed", "error", "cancelled", "canceled"}:
        raise RuntimeError(str(data.get("task_status_msg") or resp.get("message") or "CometAPI Kling task failed"))
    return None
