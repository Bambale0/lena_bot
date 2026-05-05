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
from api.kie_model_specs import IMAGE_SPECS, build_kie_input, resolve_model_for_reference

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
    ImageModel(spec.model)
    for spec in IMAGE_SPECS.values()
    if "image" in spec.supported_modes and spec.model in set(item.value for item in ImageModel)
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
    ImageModel.SEEDREAM_45:      ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.SEEDREAM_45_EDIT: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.GROK_T2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.GROK_I2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.WAN_27_PRO:       ["1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"],
    ImageModel.NANO_BANANA:      ["auto", "1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9"],
    ImageModel.NANO_BANANA_2:    ["auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"],
    ImageModel.NANO_BANANA_PRO:  ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
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
    callback_url: str | None = None,
) -> ImageResult:
    resolved_model, inp = _build_input(model, prompt, image_url, aspect_ratio, n, quality)
    resp = await kieai_client.create_task({"model": resolved_model, "input": inp}, callback_url=callback_url)
    if not isinstance(resp, dict):
        raise RuntimeError(f"KIE.AI image: invalid createTask response for {resolved_model}: {resp!r}")

    code = resp.get("code")
    if code not in (None, 200, "200"):
        raise RuntimeError(f"KIE.AI image createTask failed for {resolved_model}: {code} {resp.get('msg')}")

    data = resp.get("data")
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        raise RuntimeError(f"KIE.AI image: invalid createTask data for {resolved_model}: {data!r}")

    task_id = str(data.get("taskId") or resp.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"KIE.AI image: empty taskId for {resolved_model}: {resp!r}")

    logger.info("KIE.AI image task %s: %s", resolved_model, task_id)
    return ImageResult(is_async=True, task_id=task_id)


def _build_input(
    model: ImageModel,
    prompt: str,
    image_url: str | None,
    aspect_ratio: str | None,
    n: int,
    quality: str,
) -> tuple[str, dict[str, Any]]:
    ratio_value = aspect_ratio
    resolved_for_validation = resolve_model_for_reference(model.value) if image_url else model.value
    try:
        ratio_model = ImageModel(resolved_for_validation)
    except ValueError:
        ratio_model = model
    allowed_ratios = MODEL_ASPECT_RATIOS.get(ratio_model, [])
    if ratio_value and allowed_ratios and ratio_value not in allowed_ratios:
        logger.warning("Invalid aspect ratio for %s: %s. Falling back to %s", model.value, ratio_value, allowed_ratios[0])
        ratio_value = allowed_ratios[0]

    quality_value = quality
    resolution_value = None
    if model in {ImageModel.WAN_27_PRO, ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO}:
        resolution_value = quality_value if quality_value in {"1K", "2K", "4K"} else None

    if model in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO} and quality_value not in {"1K", "2K", "4K"}:
        quality_value = "1K" if model == ImageModel.NANO_BANANA_2 else "2K"
    elif model not in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO} and quality_value in {"1K", "2K", "4K"}:
        quality_value = "basic"

    return build_kie_input(
        model=model.value,
        prompt=prompt,
        reference_urls=image_url,
        params={
            "aspect_ratio": ratio_value,
            "n": n,
            "quality": quality_value,
            "resolution": resolution_value,
        },
    )


# ── Poll functions ────────────────────────────────────────────────────────────

async def poll_kieai_status(task_id: str) -> str | None:
    """Universal poller for all KIE.AI image models."""
    resp = await kieai_client.get_task_status(task_id)
    if not isinstance(resp, dict):
        raise RuntimeError(f"KIE.AI image: invalid status response for task {task_id}: {resp!r}")

    data = resp.get("data", {})
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        raise RuntimeError(f"KIE.AI image: invalid status data for task {task_id}: {data!r}")

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
