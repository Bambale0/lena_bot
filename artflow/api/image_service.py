# api/image_service.py
"""
Единый интерфейс генерации изображений для всех моделей через CometAPI.

Модели и их endpoint-ы:
  seedream-4.5      → /seededit/image/generate  (async, poll, returns URL)
  nano-banano-pro   → /v1beta/models/gemini-3-pro-image-preview:generateContent  (sync, base64)
  nano-banano-2     → /v1beta/models/gemini-3.1-flash-image-preview:generateContent  (sync, base64)
  wan-2.7           → /v1/images/generations  (sync, URL)
  gpt-image-1       → /v1/images/generations  (sync, URL)

ImageResult.image_bytes — установлен для Gemini-моделей (base64 decoded)
ImageResult.url         — установлен для остальных (прямая ссылка или task_id для async)
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)


class ImageModel(StrEnum):
    SEEDREAM_45 = "seedream-4.5"
    NANO_BANANO_PRO = "nano-banano-pro"
    NANO_BANANO_2 = "nano-banano-2"
    WAN_27 = "wan-2.7"
    GPT_IMAGE_1 = "gpt-image-1"
    WAN_27_PRO = "wan-2.7-pro"   # kie.ai — async image gen/editing


# Gemini model strings на стороне CometAPI
_GEMINI_MODEL_MAP: dict[ImageModel, str] = {
    ImageModel.NANO_BANANO_PRO: "gemini-3-pro-image-preview",
    ImageModel.NANO_BANANO_2: "gemini-3.1-flash-image-preview",
}

_GEMINI_MODELS = {ImageModel.NANO_BANANO_PRO, ImageModel.NANO_BANANO_2}
_SEEDREAM_ASYNC = {ImageModel.SEEDREAM_45}
_KIEAI_ASYNC = {ImageModel.WAN_27_PRO}


@dataclass
class ImageResult:
    is_async: bool = False
    task_id: str | None = None      # только для async (seedream)
    url: str | None = None          # для sync URL-based моделей
    image_bytes: bytes | None = None  # для Gemini — уже декодированные байты
    mime_type: str = "image/png"    # для Gemini


async def generate_image(
    model: ImageModel,
    prompt: str,
    image_bytes: bytes | None = None,
    image_url: str | None = None,       # для img2img (URL или Gemini)
    image_mime: str = "image/jpeg",
    aspect_ratio: str = "1:1",
    size: str = "1K",                   # только Gemini: 512px / 1K / 2K / 4K
) -> ImageResult:
    if model in _GEMINI_MODELS:
        return await _gemini_generate(
            model, prompt, image_bytes=image_bytes, image_mime=image_mime, aspect_ratio=aspect_ratio, size=size
        )
    elif model == ImageModel.SEEDREAM_45:
        return await _seedream_generate(prompt, image_url)
    elif model == ImageModel.GPT_IMAGE_1:
        return await _gpt_image_generate(prompt)
    elif model == ImageModel.WAN_27_PRO:
        return await _wan27pro_generate(prompt, image_url=image_url)
    else:
        return await _standard_generate(model.value, prompt)


# ─── Gemini Image Generation ──────────────────────────────────────────────────

async def _gemini_generate(
    model: ImageModel,
    prompt: str,
    image_bytes: bytes | None,
    image_mime: str,
    aspect_ratio: str,
    size: str,
) -> ImageResult:
    """
    POST /v1beta/models/{model}:generateContent
    Ответ содержит inlineData (base64).
    Auth: Bearer (CometAPI поддерживает оба заголовка).
    """
    api_model = _GEMINI_MODEL_MAP[model]
    url = f"{settings.COMET_BASE_URL}/v1beta/models/{api_model}:generateContent"

    # Строим parts
    parts: list[dict[str, Any]] = [{"text": prompt}]
    if image_bytes:
        parts.append({
            "inline_data": {
                "mime_type": image_mime,
                "data": base64.b64encode(image_bytes).decode(),
            }
        })

    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": aspect_ratio,
                "imageSize": size,
            },
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.COMET_API_KEY}",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    # Извлекаем inlineData из первого кандидата
    raw_b64: str | None = None
    mime: str = "image/png"
    try:
        candidates = data["candidates"]
        for part in candidates[0]["content"]["parts"]:
            if "inlineData" in part:
                raw_b64 = part["inlineData"]["data"]
                mime = part["inlineData"].get("mimeType", "image/png")
                break
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Gemini: неожиданный формат ответа: {e}\n{data}") from e

    if not raw_b64:
        raise RuntimeError(f"Gemini: изображение не найдено в ответе: {data}")

    decoded = base64.b64decode(raw_b64)
    logger.info("Gemini image generated: model=%s size=%d bytes", api_model, len(decoded))
    return ImageResult(is_async=False, image_bytes=decoded, mime_type=mime)


# ─── Seedream (async) ─────────────────────────────────────────────────────────

async def _seedream_generate(
    prompt: str, image_url: str | None
) -> ImageResult:
    from api import comet_client
    path = "/seededit/image/generate"
    payload: dict[str, Any] = {"model": "seedream-4.5", "prompt": prompt}
    if image_url:
        payload["image_url"] = image_url
    resp = await comet_client.post(path, payload)
    task_id = resp.get("task_id") or resp.get("data", {}).get("task_id")
    logger.info("Seedream task created: %s", task_id)
    return ImageResult(is_async=True, task_id=task_id)


async def poll_seedream_status(task_id: str) -> str | None:
    """Returns image URL when done, None if still processing."""
    from api import comet_client
    resp = await comet_client.get(f"/seededit/task/{task_id}")
    status = resp.get("status") or resp.get("data", {}).get("status")
    if status == "succeed":
        return resp.get("image_url") or resp.get("data", {}).get("image_url")
    if status in ("failed", "error"):
        raise RuntimeError(f"Seedream failed: {resp.get('message', 'unknown error')}")
    return None


# ─── Standard /v1/images/generations ─────────────────────────────────────────

async def _standard_generate(api_model: str, prompt: str) -> ImageResult:
    from api import comet_client
    resp = await comet_client.post(
        "/v1/images/generations",
        {"model": api_model, "prompt": prompt, "n": 1, "size": "1024x1024"},
    )
    url = resp["data"][0]["url"]
    return ImageResult(is_async=False, url=url)


async def _gpt_image_generate(prompt: str) -> ImageResult:
    from api import comet_client
    resp = await comet_client.post(
        "/v1/images/generations",
        {"model": "gpt-image-1", "prompt": prompt, "n": 1, "size": "1024x1024", "quality": "high"},
    )
    url = resp["data"][0]["url"]
    return ImageResult(is_async=False, url=url)


# ── Wan 2.7 Image Pro (kie.ai) ────────────────────────────────────────────────

async def _wan27pro_generate(
    prompt: str,
    input_urls: list[str] | None = None,
    image_url: str | None = None,
    aspect_ratio: str = "1:1",
    resolution: str = "2K",
    n: int = 1,
) -> "ImageResult":
    """Async image generation via kie.ai — returns task_id."""
    from api import kieai_client
    inp: dict = {"prompt": prompt, "resolution": resolution, "n": n, "watermark": False}
    urls = input_urls or ([image_url] if image_url else None)
    if urls:
        inp["input_urls"] = urls
    else:
        inp["aspect_ratio"] = aspect_ratio
    payload = {"model": "wan/2-7-image-pro", "input": inp}
    resp = await kieai_client.post("/api/v1/jobs/createTask", payload)
    task_id = str(resp.get("data", {}).get("taskId") or resp.get("taskId"))
    logger.info("Wan 2.7 Pro task: %s", task_id)
    return ImageResult(is_async=True, task_id=task_id)


async def poll_wan27pro_status(task_id: str) -> str | None:
    """Returns first image URL when done, None if still processing."""
    from api import kieai_client
    resp = await kieai_client.get(f"/api/v1/jobs/{task_id}/detail")
    # Common kie.ai response shapes
    data = resp.get("data", resp)
    status = str(data.get("status", data.get("state", ""))).lower()
    if status in ("success", "completed", "finish", "done"):
        # Extract first image URL
        result = data.get("result") or data.get("output") or {}
        if isinstance(result, list) and result:
            return result[0] if isinstance(result[0], str) else result[0].get("url")
        if isinstance(result, dict):
            urls = result.get("imageUrls") or result.get("urls") or result.get("images") or []
            if urls:
                return urls[0] if isinstance(urls[0], str) else urls[0].get("url")
    if status in ("failed", "error", "failure"):
        raise RuntimeError(f"Wan 2.7 Pro failed: {data.get('message', 'unknown')}")
    return None
