# api/image_service.py
"""
Image generation service — единый провайдер KIE.AI.

Все модели:
  POST /api/v1/jobs/createTask   →  ImageResult(is_async=True, task_id=...)
  GET  /api/v1/jobs/recordInfo   →  poll_kieai_status

resultJson → {"resultUrls": ["https://..."]}
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from api import kieai_client

logger = logging.getLogger(__name__)


class ImageModel(StrEnum):
    # Seedream 4.5
    SEEDREAM_45      = "seedream/4.5-text-to-image"
    SEEDREAM_45_EDIT = "seedream/4.5-edit"
    # Grok Imagine
    GROK_T2I = "grok-imagine/text-to-image"
    GROK_I2I = "grok-imagine/image-to-image"
    # WAN 2.7 Image Pro
    WAN_27_PRO = "wan/2-7-image-pro"
    # Nano Banana
    NANO_BANANA   = "google/nano-banana"
    NANO_BANANA_2 = "nano-banana-2"
    NANO_BANANA_PRO = "nano-banana-pro"


# Models that support image input
_SUPPORTS_IMG2IMG: set[ImageModel] = {
    ImageModel.SEEDREAM_45_EDIT,
    ImageModel.GROK_I2I,
    ImageModel.WAN_27_PRO,
    ImageModel.NANO_BANANA_PRO,
}

# Models with quality param
_QUALITY_MODELS: set[ImageModel] = {
    ImageModel.SEEDREAM_45,
    ImageModel.SEEDREAM_45_EDIT,
}

# Models with count support
_COUNT_MODELS: set[ImageModel] = {
    ImageModel.WAN_27_PRO,
}

# Aspect ratio options per model
MODEL_ASPECT_RATIOS: dict[ImageModel, list[str]] = {
    ImageModel.SEEDREAM_45:      ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2"],
    ImageModel.SEEDREAM_45_EDIT: ["1:1", "4:3", "3:4", "16:9", "9:16"],
    ImageModel.GROK_T2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.GROK_I2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.WAN_27_PRO:       ["1:1", "4:3", "3:4", "16:9", "9:16"],
    ImageModel.NANO_BANANA:      ["1:1", "9:16", "16:9", "3:4", "4:3"],
    ImageModel.NANO_BANANA_2:    ["1:1", "9:16", "16:9", "3:4", "4:3", "2:1", "1:2"],
    ImageModel.NANO_BANANA_PRO:  ["1:1", "9:16", "16:9"],
}


@dataclass
class ImageResult:
    is_async: bool = False
    task_id: str | None = None
    url: str | None = None
    image_bytes: bytes | None = None
    mime_type: str = "image/png"


# ── Entry point ───────────────────────────────────────────────────────────────

async def generate_image(
    model: ImageModel,
    prompt: str,
    image_url: str | None = None,
    image_bytes: bytes | None = None,   # unused (kept for compat)
    image_mime: str = "image/jpeg",     # unused (kept for compat)
    aspect_ratio: str | None = None,
    size: str = "1K",                   # unused (kept for compat)
    n: int = 1,
    quality: str = "basic",             # "basic"=2K / "high"=4K (Seedream)
) -> ImageResult:
    inp = _build_input(model, prompt, image_url, aspect_ratio, n, quality)
    resp = await kieai_client.create_task({"model": model.value, "input": inp})
    task_id = str(resp.get("data", {}).get("taskId") or resp.get("taskId"))
    logger.info("KIE.AI image task %s: %s", model.value, task_id)
    return ImageResult(is_async=True, task_id=task_id)


def _build_input(
    model: ImageModel,
    prompt: str,
    image_url: str | None,
    aspect_ratio: str | None,
    n: int,
    quality: str,
) -> dict[str, Any]:
    m = model.value
    ratio = aspect_ratio or "1:1"

    # ── Seedream 4.5 T2I ─────────────────────────────────────────────────────
    if m == ImageModel.SEEDREAM_45:
        return {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "quality": quality,
            "nsfw_checker": False,
        }

    # ── Seedream 4.5 Edit ────────────────────────────────────────────────────
    if m == ImageModel.SEEDREAM_45_EDIT:
        return {
            "prompt": prompt,
            "image_url": image_url or "",
            "aspect_ratio": ratio,
            "quality": quality,
        }

    # ── Grok T2I ─────────────────────────────────────────────────────────────
    if m == ImageModel.GROK_T2I:
        return {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "nsfw_checker": False,
        }

    # ── Grok I2I ─────────────────────────────────────────────────────────────
    if m == ImageModel.GROK_I2I:
        return {
            "prompt": prompt,
            "image_url": image_url or "",
            "aspect_ratio": ratio,
        }

    # ── WAN 2.7 Image Pro ────────────────────────────────────────────────────
    if m == ImageModel.WAN_27_PRO:
        inp: dict[str, Any] = {
            "prompt": prompt,
            "resolution": "2K",
            "n": max(1, min(4, n)),
            "watermark": False,
        }
        if image_url:
            inp["input_urls"] = [image_url]
        else:
            inp["aspect_ratio"] = ratio
        return inp

    # ── Nano Banana (v1) ─────────────────────────────────────────────────────
    if m == ImageModel.NANO_BANANA:
        return {
            "prompt": prompt,
            "image_size": ratio,
            "output_format": "png",
        }

    # ── Nano Banana 2 ─────────────────────────────────────────────────────────
    if m == ImageModel.NANO_BANANA_2:
        return {
            "prompt": prompt,
            "image_size": ratio,
            "resolution": "2K",
            "output_format": "jpg",
        }

    # ── Nano Banana Pro ───────────────────────────────────────────────────────
    if m == ImageModel.NANO_BANANA_PRO:
        inp2: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": ratio,
            "resolution": "2K",
            "output_format": "jpg",
        }
        if image_url:
            inp2["image_input"] = [image_url]
        return inp2

    raise ValueError(f"Unknown image model: {model}")


# ── Poll functions ────────────────────────────────────────────────────────────

async def poll_kieai_status(task_id: str) -> str | None:
    """Universal poller for all KIE.AI image models."""
    resp = await kieai_client.get_task_status(task_id)
    data = resp.get("data", {})
    state = str(data.get("state", "")).lower()

    if state == "success":
        result_json_str = data.get("resultJson", "{}")
        try:
            parsed = json.loads(result_json_str)
        except json.JSONDecodeError:
            parsed = {}
        urls = parsed.get("resultUrls", [])
        if urls:
            return urls[0]
        raise RuntimeError("KIE.AI image: success but no resultUrls")

    if state == "fail":
        raise RuntimeError(f"KIE.AI image failed: {data.get('failMsg', 'unknown error')}")

    return None  # still processing


# Backward-compat aliases kept for old polling calls
poll_seedream_status = poll_kieai_status
poll_wan27pro_status = poll_kieai_status
