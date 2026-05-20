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
import mimetypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass

from typing import Any

from api import kieai_client
from api.kie_model_specs import IMAGE_SPECS, build_kie_input, resolve_model_for_reference
from api.public_files import local_upload_path_from_url

logger = logging.getLogger(__name__)


class ImageModel(StrEnum):
    # Seedream 4.5
    SEEDREAM_45      = "seedream/4.5-text-to-image"
    SEEDREAM_45_EDIT = "seedream/4.5-edit"
    # Grok Imagine
    GROK_T2I = "grok-imagine/text-to-image"
    GROK_I2I = "grok-imagine/image-to-image"
    # WAN 2.7 Image
    WAN_27 = "wan/2-7-image"
    WAN_27_PRO = "wan/2-7-image-pro"
    # Nano Banana
    NANO_BANANA   = "google/nano-banana"
    NANO_BANANA_2 = "nano-banana-2"
    NANO_BANANA_PRO = "nano-banana-pro"
    # Qwen
    QWEN_T2I      = "qwen/text-to-image"
    QWEN_I2I      = "qwen/image-to-image"
    QWEN_EDIT     = "qwen/image-edit"
    QWEN2_T2I     = "qwen2/text-to-image"
    QWEN2_EDIT    = "qwen2/image-edit"
    # OpenRouter
    OPENROUTER_FREE = "openrouter/free"
    # GPT Image 2
    GPT_IMAGE_2_T2I = "gpt-image-2-text-to-image"
    GPT_IMAGE_2_I2I = "gpt-image-2-image-to-image"


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
    ImageModel.GPT_IMAGE_2_T2I,
    ImageModel.GPT_IMAGE_2_I2I,
}

# Models with count support
_COUNT_MODELS: set[ImageModel] = {
    ImageModel.WAN_27,
    ImageModel.WAN_27_PRO,
}

_SQUARE_4K_UNSUPPORTED_MODELS: set[ImageModel] = {
    ImageModel.NANO_BANANA_2,
    ImageModel.NANO_BANANA_PRO,
    ImageModel.GPT_IMAGE_2_T2I,
    ImageModel.GPT_IMAGE_2_I2I,
}
_KIE_UPLOAD_REFERENCE_MODELS = {
    "seedream/4.5-edit",
    ImageModel.QWEN_I2I.value,
    ImageModel.QWEN_EDIT.value,
    ImageModel.QWEN2_EDIT.value,
}

_PROMPT_MAX_LENGTH_BY_MODEL: dict[str, int] = {
    ImageModel.SEEDREAM_45.value: 2000,
    ImageModel.SEEDREAM_45_EDIT.value: 2000,
    ImageModel.QWEN_EDIT.value: 2000,
}


_REFERENCE_LOCK_MODELS: set[str] = {
    ImageModel.NANO_BANANA.value,
    ImageModel.NANO_BANANA_2.value,
    ImageModel.NANO_BANANA_PRO.value,
    ImageModel.GROK_I2I.value,
    ImageModel.QWEN_I2I.value,
    ImageModel.QWEN_EDIT.value,
    ImageModel.QWEN2_EDIT.value,
    ImageModel.GPT_IMAGE_2_I2I.value,
}

_REFERENCE_FLEX_MODELS: set[str] = {
    ImageModel.SEEDREAM_45_EDIT.value,
    ImageModel.WAN_27.value,
    ImageModel.WAN_27_PRO.value,
}

_REFERENCE_LOCK_PREFIX = (
    "STRICT IDENTITY AND DETAIL PRESERVATION. HIGHEST PRIORITY.\n\n"
    "Treat the reference image(s) as the exact source of truth. "
    "Recreate the same person or people with no identity drift and no redesign.\n\n"
    "Preserve exactly and do not alter unless the prompt explicitly requests it:\n"
    "- face identity\n"
    "- head shape, facial proportions, bone structure\n"
    "- eyes, eyelids, iris color, eyebrows, eyelashes\n"
    "- nose, lips, teeth, smile line, ears\n"
    "- skin tone, undertone, texture, freckles, moles, scars, wrinkles, pores\n"
    "- age appearance and body proportions\n"
    "- hairstyle, hairline, hair density, hair texture, hair color\n"
    "- makeup style and intensity\n"
    "- outfit, fabric, folds, fit, seams, logos, prints, labels\n"
    "- accessories, jewelry, piercings, tattoos, glasses, headwear\n"
    "- pose, hand shape, fingers, nails, silhouette\n"
    "- colors, materials, textures, lighting logic, camera perspective\n\n"
    "STRICT FACE LOCK - ABSOLUTE PRIORITY:\n"
    "The face must match the reference exactly. Preserve every facial detail with no simplification and no beautification:\n"
    "- exact face oval, skull shape, forehead, cheekbones, jawline, chin\n"
    "- exact eye shape, eyelids, eye spacing, iris color, gaze character, eyelashes, eyebrows\n"
    "- exact nose bridge, nostrils, tip, width, length, profile\n"
    "- exact lips, mouth shape, cupid's bow, lip fullness, teeth, smile lines\n"
    "- exact ears, temples, hairline, sideburns\n"
    "- exact skin tone, undertone, pores, texture, freckles, moles, scars, wrinkles, nasolabial folds, dimples\n"
    "- exact facial asymmetry, age signs, expression style, makeup placement\n\n"
    "OUTFIT LOCK - ABSOLUTE PRIORITY:\n"
    "Keep the exact same clothing and wearable details from the reference unless the user explicitly asks to change them:\n"
    "- same garments, layers, sleeves, neckline, length, fit, silhouette\n"
    "- same fabric type, texture, folds, seams, stitching, buttons, zippers\n"
    "- same colors, color blocking, patterns, logos, prints, labels, trims\n"
    "- same shoes, bags, jewelry, glasses, hats, belts, gloves, watches and other accessories\n\n"
    "Do not make the face prettier, younger, older, smoother, slimmer, wider, more symmetrical, more generic, or more model-like. "
    "Do not replace the face with a similar-looking person. "
    "If the requested edit conflicts with face preservation, keep the face from the reference and apply the edit only outside the face."
)

_REFERENCE_FLEX_PREFIX = (
    "REFERENCE IDENTITY PRESERVATION WITH TRANSFORMATION. HIGH PRIORITY.\n\n"
    "Keep the same person from the reference with recognizable face identity, skin tone, hair, and overall likeness.\n"
    "But still follow the user's prompt as the main transformation instruction for pose, framing, composition, camera angle, expression, action, background, styling, outfit, and scene details.\n\n"
    "Important rules:\n"
    "- preserve identity, not the exact original photo composition\n"
    "- do not simply recreate the same pose or same framing unless the prompt asks for it\n"
    "- allow clear changes in body position, gesture, camera distance, and scene layout\n"
    "- if the prompt requests a new setting, mood, clothing, or action, apply it while keeping the same person recognizable\n"
    "- avoid background-only edits; perform the actual transformation requested in the prompt\n"
    "- keep the face believable and consistent, but do not freeze the full image"
)

# Aspect ratio options per model
MODEL_ASPECT_RATIOS: dict[ImageModel, list[str]] = {
    ImageModel.SEEDREAM_45:      ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.SEEDREAM_45_EDIT: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.GROK_T2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.GROK_I2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.WAN_27:           ["1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"],
    ImageModel.WAN_27_PRO:       ["1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"],
    ImageModel.NANO_BANANA:      ["auto", "1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9"],
    ImageModel.NANO_BANANA_2:    ["auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"],
    ImageModel.NANO_BANANA_PRO:  ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
    ImageModel.QWEN_T2I:         ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.QWEN_I2I:         ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.QWEN2_T2I:        ["1:1", "16:9", "9:16", "4:3", "3:4"],
    ImageModel.OPENROUTER_FREE:  ["1:1", "1:1"],
    ImageModel.GPT_IMAGE_2_T2I:  ["1:1", "9:16", "16:9", "4:3", "3:4"],
    ImageModel.GPT_IMAGE_2_I2I:  ["1:1", "9:16", "16:9", "4:3", "3:4"],
}


@dataclass
class ImageResult:
    is_async: bool = False
    task_id: str | None = None
    url: str | None = None
    image_bytes: bytes | None = None
    mime_type: str = "image/png"


def _apply_reference_detail_preservation(
    model: ImageModel | str,
    prompt: str,
    image_url: str | list[str] | None,
) -> str:
    if not image_url:
        return prompt
    model_key = model.value if isinstance(model, ImageModel) else str(model)
    if any(marker in prompt for marker in (
        "STRICT REFERENCE ADHERENCE",
        "STRICT IDENTITY AND DETAIL PRESERVATION",
        "REFERENCE IDENTITY PRESERVATION WITH TRANSFORMATION",
    )):
        return prompt
    if model_key in _REFERENCE_FLEX_MODELS:
        return _REFERENCE_FLEX_PREFIX + "\n\n" + prompt.strip()
    if model_key in _REFERENCE_LOCK_MODELS:
        return _REFERENCE_LOCK_PREFIX + "\n\n" + prompt.strip()
    return prompt


def _normalize_prompt_for_model(model: ImageModel | str, prompt: str) -> str:
    model_key = model.value if isinstance(model, ImageModel) else str(model)
    max_length = _PROMPT_MAX_LENGTH_BY_MODEL.get(model_key)
    if not max_length or len(prompt) <= max_length:
        return prompt

    trimmed = prompt[:max_length].rstrip()
    logger.warning(
        "Truncating prompt for %s from %s to %s chars to satisfy provider limit",
        model_key,
        len(prompt),
        len(trimmed),
    )
    return trimmed


def normalize_quality_for_aspect_ratio(
    model: ImageModel | str,
    aspect_ratio: str | None,
    quality: str | None,
) -> str | None:
    try:
        image_model = model if isinstance(model, ImageModel) else ImageModel(model)
    except ValueError:
        return quality

    if image_model in _SQUARE_4K_UNSUPPORTED_MODELS and aspect_ratio == "1:1" and quality == "4K":
        return "2K"
    return quality


def _reference_list(image_url: str | list[str] | None) -> list[str]:
    if not image_url:
        return []
    if isinstance(image_url, str):
        return [image_url]
    return [url for url in image_url if url]


def _restore_reference_shape(original: str | list[str] | None, urls: list[str]) -> str | list[str] | None:
    if not urls:
        return None
    if isinstance(original, str):
        return urls[0]
    return urls


def _content_type_for_path(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and guessed.startswith("image/"):
        return guessed
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if path.suffix.lower() == ".png":
        return "image/png"
    if path.suffix.lower() == ".webp":
        return "image/webp"
    return "application/octet-stream"


async def _upload_local_kie_reference(url: str) -> str | None:
    path = local_upload_path_from_url(url)
    if not path or not path.exists() or not path.is_file():
        return None
    return await kieai_client.upload_file_stream(
        path.read_bytes(),
        filename=path.name,
        content_type=_content_type_for_path(path),
    )


async def _prepare_reference_urls_for_model(
    model: ImageModel,
    image_url: str | list[str] | None,
) -> str | list[str] | None:
    urls = _reference_list(image_url)
    if not urls:
        return image_url

    resolved_model = resolve_model_for_reference(model.value)
    if resolved_model not in _KIE_UPLOAD_REFERENCE_MODELS:
        return image_url

    prepared: list[str] = []
    changed = False
    for url in urls:
        uploaded_url: str | None = None
        try:
            uploaded_url = await _upload_local_kie_reference(url)
        except Exception as exc:
            logger.warning("Failed to upload local reference to KIE storage url=%s: %s", url, exc)
        if uploaded_url:
            prepared.append(uploaded_url)
            changed = True
        else:
            prepared.append(url)

    if changed:
        logger.info("Uploaded %d local reference(s) to KIE storage for %s", len(prepared), resolved_model)
    return _restore_reference_shape(image_url, prepared)


# ── Entry point ───────────────────────────────────────────────────────────────

async def generate_image(
    model: ImageModel,
    prompt: str,
    image_url: str | list[str] | None = None,
    image_bytes: bytes | None = None,   # unused (kept for compat)
    image_mime: str = "image/jpeg",     # unused (kept for compat)
    aspect_ratio: str | None = None,
    size: str = "1K",                   # unused (kept for compat)
    n: int = 1,
    quality: str = "basic",             # "basic"=2K / "high"=4K (Seedream)
    callback_url: str | None = None,
) -> ImageResult:
    prepared_image_url = await _prepare_reference_urls_for_model(model, image_url)
    resolved_model, inp = _build_input(model, prompt, prepared_image_url, aspect_ratio, n, quality)
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
    image_url: str | list[str] | None,
    aspect_ratio: str | None,
    n: int,
    quality: str,
) -> tuple[str, dict[str, Any]]:
    ratio_value = aspect_ratio
    if model in {ImageModel.GPT_IMAGE_2_T2I, ImageModel.GPT_IMAGE_2_I2I} and ratio_value == "auto":
        # KIE's GPT Image 2 docs show `auto`, but in practice our paid 2K/4K
        # flow can fail on that combo. Treat stale `auto` input as "unspecified"
        # so we don't force an invalid provider fallback.
        ratio_value = None
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
    if model in {ImageModel.WAN_27, ImageModel.WAN_27_PRO, ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO, ImageModel.GPT_IMAGE_2_T2I, ImageModel.GPT_IMAGE_2_I2I}:
        resolution_value = quality_value if quality_value in {"1K", "2K", "4K"} else None

    if model in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO} and quality_value not in {"1K", "2K", "4K"}:
        quality_value = "1K" if model == ImageModel.NANO_BANANA_2 else "2K"
    elif model not in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO, ImageModel.GPT_IMAGE_2_T2I, ImageModel.GPT_IMAGE_2_I2I} and quality_value in {"1K", "2K", "4K"}:
        quality_value = "basic"

    normalized_quality = normalize_quality_for_aspect_ratio(model, ratio_value, quality_value)
    if normalized_quality != quality_value:
        logger.info(
            "Adjusting %s quality from %s to %s for unsupported aspect ratio %s",
            model.value,
            quality_value,
            normalized_quality,
            ratio_value,
        )
        quality_value = normalized_quality
        resolution_value = normalized_quality if normalized_quality in {"1K", "2K", "4K"} else resolution_value

    prompt_with_reference_lock = _apply_reference_detail_preservation(resolved_for_validation, prompt, image_url)
    normalized_prompt = _normalize_prompt_for_model(resolved_for_validation, prompt_with_reference_lock)

    return build_kie_input(
        model=model.value,
        prompt=normalized_prompt,
        reference_urls=image_url,
        params={
            "aspect_ratio": ratio_value,
            "n": n,
            "quality": quality_value,
            "resolution": resolution_value,
        },
    )


# ── Poll functions ────────────────────────────────────────────────────────────

async def poll_kieai_result_urls(task_id: str) -> list[str] | None:
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
            return [str(url) for url in urls if url]
        raise RuntimeError("KIE.AI image: success but no resultUrls")

    if state == "fail":
        raise RuntimeError(f"KIE.AI image failed: {data.get('failMsg', 'unknown error')}")

    return None  # still processing


async def poll_kieai_status(task_id: str) -> str | None:
    urls = await poll_kieai_result_urls(task_id)
    return urls[0] if urls else None


# Backward-compat aliases kept for old polling calls
poll_seedream_status = poll_kieai_status
poll_wan27pro_status = poll_kieai_status
