# api/image_service.py
"""
Единый интерфейс генерации изображений для всех моделей через CometAPI.
Возвращает task_id (для async моделей) или сразу url (для sync).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from api import comet_client

logger = logging.getLogger(__name__)


class ImageModel(StrEnum):
    SEEDREAM_45 = "seedream-4.5"
    NANO_BANANO_PRO = "nano-banano-pro"
    NANO_BANANO_2 = "nano-banano-2"
    WAN_27 = "wan-2.7"
    GPT_IMAGE_1 = "gpt-image-1"


# CometAPI model strings
_MODEL_MAP: dict[ImageModel, str] = {
    ImageModel.SEEDREAM_45: "seedream-4.5",
    ImageModel.NANO_BANANO_PRO: "seedream-3-pro",
    ImageModel.NANO_BANANO_2: "seedream-3",
    ImageModel.WAN_27: "wan-2.7",
    ImageModel.GPT_IMAGE_1: "gpt-image-1",
}

# Which models use the SeedEdit async endpoint
_SEEDREAM_ASYNC = {ImageModel.SEEDREAM_45, ImageModel.NANO_BANANO_PRO, ImageModel.NANO_BANANO_2}


@dataclass
class ImageResult:
    is_async: bool
    task_id: str | None = None
    url: str | None = None


async def generate_image(
    model: ImageModel,
    prompt: str,
    image_url: str | None = None,  # for img2img
    size: str = "1024x1024",
) -> ImageResult:
    api_model = _MODEL_MAP[model]

    if model in _SEEDREAM_ASYNC:
        return await _seedream_generate(api_model, prompt, image_url)
    elif model == ImageModel.WAN_27:
        return await _standard_generate(api_model, prompt, size)
    elif model == ImageModel.GPT_IMAGE_1:
        return await _gpt_image_generate(prompt, size)
    else:
        return await _standard_generate(api_model, prompt, size)


async def _seedream_generate(
    api_model: str, prompt: str, image_url: str | None
) -> ImageResult:
    """SeedEdit/Seedream — async generation, returns task_id."""
    path = "/seededit/image/generate"
    payload: dict = {"model": api_model, "prompt": prompt}
    if image_url:
        payload["image_url"] = image_url
    resp = await comet_client.post(path, payload)
    task_id = resp.get("task_id") or resp.get("data", {}).get("task_id")
    logger.info("Seedream task created: %s", task_id)
    return ImageResult(is_async=True, task_id=task_id)


async def _standard_generate(
    api_model: str, prompt: str, size: str
) -> ImageResult:
    """Standard /v1/images/generations — sync, returns url immediately."""
    resp = await comet_client.post(
        "/v1/images/generations",
        {"model": api_model, "prompt": prompt, "n": 1, "size": size},
    )
    url = resp["data"][0]["url"]
    return ImageResult(is_async=False, url=url)


async def _gpt_image_generate(prompt: str, size: str) -> ImageResult:
    resp = await comet_client.post(
        "/v1/images/generations",
        {"model": "gpt-image-1", "prompt": prompt, "n": 1, "size": size, "quality": "high"},
    )
    url = resp["data"][0]["url"]
    return ImageResult(is_async=False, url=url)


async def poll_seedream_status(task_id: str) -> str | None:
    """Returns image URL when done, None if still processing."""
    resp = await comet_client.get(f"/seededit/task/{task_id}")
    status = resp.get("status") or resp.get("data", {}).get("status")
    if status == "succeed":
        return resp.get("image_url") or resp.get("data", {}).get("image_url")
    if status in ("failed", "error"):
        raise RuntimeError(f"Seedream failed: {resp.get('message', 'unknown error')}")
    return None  # still processing
