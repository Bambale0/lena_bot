# api/image_service.py
"""Image generation service — KIE.AI primary with CometAPI fallback."""
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

from api import comet_fallback, kieai_client
from api.kie_model_specs import IMAGE_SPECS, build_kie_input, resolve_model_for_reference
from api.public_files import ensure_provider_safe_png_url, local_upload_path_from_url

logger = logging.getLogger(__name__)


class ImageModel(StrEnum):
    # Seedream
    SEEDREAM_5_PRO_T2I = "seedream/5-pro-text-to-image"
    SEEDREAM_5_PRO_I2I = "seedream/5-pro-image-to-image"
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
    NANO_BANANA_2_LITE = "nano-banana-2-lite"
    NANO_BANANA_PRO = "nano-banana-pro"
    # Qwen
    QWEN_T2I      = "qwen/text-to-image"
    QWEN_I2I      = "qwen/image-to-image"
    QWEN_EDIT     = "qwen/image-edit"
    QWEN2_T2I     = "qwen2/text-to-image"
    QWEN2_EDIT    = "qwen2/image-edit"
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
    ImageModel.SEEDREAM_5_PRO_T2I,
    ImageModel.SEEDREAM_5_PRO_I2I,
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
    ImageModel.SEEDREAM_5_PRO_I2I.value,
    "seedream/4.5-edit",
    ImageModel.QWEN_I2I.value,
    ImageModel.QWEN_EDIT.value,
    ImageModel.QWEN2_EDIT.value,
}

_PROMPT_MAX_LENGTH_BY_MODEL: dict[str, int] = {
    ImageModel.SEEDREAM_5_PRO_T2I.value: 3000,
    ImageModel.SEEDREAM_5_PRO_I2I.value: 3000,
    ImageModel.SEEDREAM_45.value: 3000,
    ImageModel.SEEDREAM_45_EDIT.value: 3000,
    ImageModel.QWEN_EDIT.value: 2000,
}


_REFERENCE_LOCK_MODELS: set[str] = {
    ImageModel.NANO_BANANA.value,
    ImageModel.NANO_BANANA_2.value,
    ImageModel.NANO_BANANA_2_LITE.value,
    ImageModel.NANO_BANANA_PRO.value,
    ImageModel.GROK_I2I.value,
    ImageModel.QWEN_I2I.value,
    ImageModel.QWEN_EDIT.value,
    ImageModel.QWEN2_EDIT.value,
    ImageModel.GPT_IMAGE_2_I2I.value,
}

_PROMPT_FIRST_REFERENCE_LOCK_MODELS: set[str] = {
    ImageModel.QWEN_I2I.value,
    ImageModel.QWEN_EDIT.value,
    ImageModel.QWEN2_EDIT.value,
}

_REFERENCE_FLEX_MODELS: set[str] = {
    ImageModel.SEEDREAM_5_PRO_I2I.value,
    ImageModel.SEEDREAM_45_EDIT.value,
    ImageModel.WAN_27.value,
    ImageModel.WAN_27_PRO.value,
}

_REFERENCE_LOCK_PREFIX = (
    "PROMPT-DIRECTED REFERENCE TRANSFORMATION. HIGHEST PRIORITY.\n\n"
    "Use the reference image(s) to keep the same recognizable person, not to freeze the whole source photo.\n"
    "The user's prompt is the primary instruction for visible changes. Preserve identity and unmentioned details, but do not preserve reference details that conflict with the prompt.\n\n"
    "Preserve unless explicitly changed:\n"
    "- recognizable face identity, facial proportions, age impression, and natural skin tone\n"
    "- body proportions, hands, clothing, garment cut, accessories, styling, coverage level, background, and lighting only when the prompt does not ask to change them\n\n"
    "When requested by the prompt, actively change and prioritize:\n"
    "- hairstyle, hair length, volume, texture, waves or curls, hair color, and hair placement\n"
    "- makeup, lashes, brows, lips, skin finish, retouching, glowing skin, beauty lighting, and glamour styling\n"
    "- pose, head tilt, body angle, gesture, expression, camera angle, framing, crop, and composition\n"
    "- outfit, accessories, background, scene, mood, realism level, editorial/fashion/beauty style, and lighting setup\n\n"
    "If the prompt asks for long voluminous hair, wavy hair, smooth glowing retouched skin, makeup, a glamorous/editorial look, or the head tilted to the side, apply it even if the reference shows different hair, a plain realistic texture, or a straight-on pose.\n"
    "Preserve the referenced outfit, garment cut, accessories, styling, and coverage level unless the user explicitly asks to change outfit or coverage. Do not add extra clothing or make the look more covered on your own.\n"
    "Do not replace the person with a different person. Keep the likeness believable while following the requested transformation."
)

_REFERENCE_LOCK_PROMPT_FIRST_SUFFIX = (
    "PROMPT-DIRECTED REFERENCE EDITING. Keep the same recognizable person and preserve unmentioned details. "
    "Preserve the referenced outfit, garment cut, accessories, styling, and coverage level unless the user explicitly asks to change them. Do not add extra clothing or increase coverage on your own. "
    "The user instruction is the primary edit request: if it asks to change hairstyle, hair length, hair texture, hair color, makeup, skin finish, retouching, outfit, pose, head tilt, expression, background, lighting, framing, or glamour/editorial styling, apply that change even when the reference differs. "
    "Do not replace the person with a different person."
)

_REFERENCE_FLEX_PREFIX = (
    "REFERENCE IDENTITY PRESERVATION WITH TRANSFORMATION. HIGH PRIORITY.\n\n"
    "Keep the same person from the reference with recognizable face identity, natural skin tone, and overall likeness.\n"
    "But still follow the user's prompt as the main transformation instruction for pose, framing, composition, camera angle, expression, action, background, styling, outfit, and scene details.\n\n"
    "Important rules:\n"
    "- preserve identity, not the exact original photo composition\n"
    "- do not simply recreate the same pose, same hair, same skin texture, or same framing unless the prompt asks for it\n"
    "- allow clear changes in body position, gesture, camera distance, and scene layout\n"
    "- if the prompt asks for makeup, retouched/glowing skin, longer or wavy hair, beauty lighting, or a glamorous/editorial finish, apply those style changes\n"
    "- if the prompt requests a new setting, mood, clothing, or action, apply it while keeping the same person recognizable\n"
    "- use the reference background only when the prompt explicitly asks to keep or preserve it\n"
    "- if the prompt asks for a new background, scene, location, mood, or set design, replace the reference background completely\n"
    "- do not carry over reference background artifacts, clutter, text, books, wall decor, glitches, or props unless requested\n"
    "- prioritize the requested scene and composition over the original reference environment\n"
    "- avoid background-only edits; perform the actual transformation requested in the prompt\n"
    "- keep the face believable and consistent, but do not freeze the full image"
)

_MULTI_REFERENCE_FLEX_PREFIX = (
    "MULTI-REFERENCE IDENTITY AND DETAIL CONTROL. HIGHEST PRIORITY.\n\n"
    "Use the first reference image as the primary identity source for the main person: face, head shape, natural skin tone, body proportions, and likeness.\n"
    "Use the additional reference images only for the details requested by the user, such as clothing, lingerie, accessories, fabric, color, pattern, object design, scene, or style.\n\n"
    "Important rules:\n"
    "- do not replace the first person's face with a face from any later reference\n"
    "- do not copy another person's identity, body, expression, age, or facial features from clothing or style references\n"
    "- do not lock the first reference hairstyle, skin texture, pose, or framing when the prompt asks to change them\n"
    "- if the prompt asks for makeup, retouched/glowing skin, longer or wavy hair, beauty lighting, or a glamorous/editorial finish, apply those style changes\n"
    "- if a later reference shows a garment on another person, transfer only the garment design, fabric, fit, color, and visible construction\n"
    "- keep the first reference background only when the user explicitly asks to preserve it\n"
    "- if the prompt asks for a new background, scene, location, mood, or set design, remove old reference background clutter, glitches, books, wall decor, and props\n"
    "- use additional references as background or scene sources only when the prompt specifically asks for that\n"
    "- preserve the main person's recognizable identity while applying the requested visual details from the other references\n"
    "- if references conflict, identity from the first reference wins; requested outfit/product/style details from later references come second"
)

# Aspect ratio options per model
MODEL_ASPECT_RATIOS: dict[ImageModel, list[str]] = {
    ImageModel.SEEDREAM_5_PRO_T2I: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2"],
    ImageModel.SEEDREAM_5_PRO_I2I: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2"],
    ImageModel.SEEDREAM_45:      ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.SEEDREAM_45_EDIT: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.GROK_T2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.GROK_I2I:         ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.WAN_27:           ["1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"],
    ImageModel.WAN_27_PRO:       ["1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"],
    ImageModel.NANO_BANANA:      ["auto", "1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9"],
    ImageModel.NANO_BANANA_2:    ["auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"],
    ImageModel.NANO_BANANA_2_LITE: ["auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"],
    ImageModel.NANO_BANANA_PRO:  ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
    ImageModel.QWEN_T2I:         ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.QWEN_I2I:         ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.QWEN2_T2I:        ["1:1", "16:9", "9:16", "4:3", "3:4"],
    ImageModel.GPT_IMAGE_2_T2I:  ["1:1", "9:16", "16:9", "4:3", "3:4"],
    ImageModel.GPT_IMAGE_2_I2I:  ["1:1", "9:16", "16:9", "4:3", "3:4"],
}


@dataclass
class ImageResult:
    is_async: bool = False
    task_id: str | None = None
    url: str | None = None
    result_urls: list[str] = field(default_factory=list)
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
        "STRICT REFERENCE PRESERVATION",
        "PROMPT-DIRECTED REFERENCE TRANSFORMATION",
        "PROMPT-DIRECTED REFERENCE EDITING",
        "REFERENCE IDENTITY PRESERVATION WITH TRANSFORMATION",
        "MULTI-REFERENCE IDENTITY AND DETAIL CONTROL",
    )):
        return prompt
    reference_count = len(_reference_list(image_url))
    if model_key in _REFERENCE_FLEX_MODELS and reference_count > 1:
        return _MULTI_REFERENCE_FLEX_PREFIX + "\n\n" + prompt.strip()
    if model_key in _REFERENCE_FLEX_MODELS:
        return _REFERENCE_FLEX_PREFIX + "\n\n" + prompt.strip()
    if model_key in _PROMPT_FIRST_REFERENCE_LOCK_MODELS:
        return prompt.strip() + "\n\n" + _REFERENCE_LOCK_PROMPT_FIRST_SUFFIX
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
    comet_aspect_ratio = str(inp.get("aspect_ratio") or inp.get("image_size") or "") or None
    comet_resolution = str(inp.get("resolution") or "") or None
    try:
        comet_count = int(inp.get("n") or inp.get("num_images") or n or 1)
    except (TypeError, ValueError):
        comet_count = 1

    try:
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
    except Exception as kie_exc:
        logger.warning(
            "KIE.AI image create failed for %s; trying CometAPI fallback: %s",
            resolved_model,
            kie_exc,
        )
        try:
            result = await comet_fallback.generate_image(
                model_key=resolved_model,
                prompt=str(inp.get("prompt") or prompt),
                reference_urls=prepared_image_url,
                aspect_ratio=comet_aspect_ratio,
                count=comet_count,
                resolution=comet_resolution,
            )
        except Exception as comet_exc:
            raise RuntimeError(
                f"Image generation failed via KIE.AI and CometAPI fallback: "
                f"KIE={kie_exc}; CometAPI={comet_exc}"
            ) from comet_exc

        return ImageResult(
            is_async=False,
            task_id=result.task_id,
            url=result.urls[0],
            result_urls=result.urls,
        )


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
    elif model in {ImageModel.NANO_BANANA_2_LITE} and quality_value not in {"1K", "2K"}:
        quality_value = "1K"
    elif model not in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO, ImageModel.NANO_BANANA_2_LITE, ImageModel.GPT_IMAGE_2_T2I, ImageModel.GPT_IMAGE_2_I2I} and quality_value in {"1K", "2K", "4K"}:
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

    prepared_reference_urls = image_url
    if model in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO}:
        if isinstance(image_url, str):
            prepared_reference_urls = ensure_provider_safe_png_url(image_url)
        elif isinstance(image_url, list):
            prepared_reference_urls = [ensure_provider_safe_png_url(url) or url for url in image_url]

    prompt_with_reference_lock = _apply_reference_detail_preservation(resolved_for_validation, prompt, prepared_reference_urls)
    normalized_prompt = _normalize_prompt_for_model(resolved_for_validation, prompt_with_reference_lock)

    return build_kie_input(
        model=model.value,
        prompt=normalized_prompt,
        reference_urls=prepared_reference_urls,
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
