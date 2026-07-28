# api/image_service.py
"""Image generation with exact provider/model contracts.

Only Nano Banana 2 and Nano Banana Pro intentionally use Comet/Gemini as their
primary provider. KIE-backed models are never silently substituted with a
universal Seedream request when their provider fails.
"""
from __future__ import annotations

import json
import logging
import mimetypes
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass

from api import comet_fallback, kieai_client
from api.kie_model_specs import IMAGE_SPECS, build_kie_input, resolve_model_for_reference
from api.public_files import ensure_provider_safe_png_url, local_upload_path_from_url

logger = logging.getLogger(__name__)


class ImageModel(StrEnum):
    # Seedream
    SEEDREAM_5_PRO_T2I = "seedream/5-pro-text-to-image"
    SEEDREAM_5_PRO_I2I = "seedream/5-pro-image-to-image"
    SEEDREAM_45 = "seedream/4.5-text-to-image"
    SEEDREAM_45_EDIT = "seedream/4.5-edit"
    # Grok Imagine
    GROK_T2I = "grok-imagine/text-to-image"
    GROK_I2I = "grok-imagine/image-to-image"
    # WAN 2.7 Image
    WAN_27 = "wan/2-7-image"
    WAN_27_PRO = "wan/2-7-image-pro"
    # Nano Banana
    NANO_BANANA = "google/nano-banana"
    NANO_BANANA_2 = "nano-banana-2"
    NANO_BANANA_2_LITE = "nano-banana-2-lite"
    NANO_BANANA_PRO = "nano-banana-pro"
    # Qwen
    QWEN_T2I = "qwen/text-to-image"
    QWEN_I2I = "qwen/image-to-image"
    QWEN_EDIT = "qwen/image-edit"
    QWEN2_T2I = "qwen2/text-to-image"
    QWEN2_EDIT = "qwen2/image-edit"
    # GPT Image 2
    GPT_IMAGE_2_T2I = "gpt-image-2-text-to-image"
    GPT_IMAGE_2_I2I = "gpt-image-2-image-to-image"


_SUPPORTS_IMG2IMG: set[ImageModel] = {
    ImageModel(spec.model)
    for spec in IMAGE_SPECS.values()
    if "image" in spec.supported_modes and spec.model in {item.value for item in ImageModel}
}

_QUALITY_MODELS: set[ImageModel] = {
    ImageModel.SEEDREAM_5_PRO_T2I,
    ImageModel.SEEDREAM_5_PRO_I2I,
    ImageModel.SEEDREAM_45,
    ImageModel.SEEDREAM_45_EDIT,
    ImageModel.GPT_IMAGE_2_T2I,
    ImageModel.GPT_IMAGE_2_I2I,
}

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

_GPT_IMAGE_2_MODELS = {
    ImageModel.GPT_IMAGE_2_T2I,
    ImageModel.GPT_IMAGE_2_I2I,
}
_MAX_GPT_IMAGE_2_REFERENCES = 16

_COMET_PRIMARY_IMAGE_MODELS = {
    ImageModel.NANO_BANANA_2,
    ImageModel.NANO_BANANA_PRO,
}

# Models whose official KIE workflow requires or benefits from provider-hosted
# media. Local APIX files are always uploaded before createTask.
_KIE_UPLOAD_REFERENCE_MODELS = {
    ImageModel.SEEDREAM_5_PRO_I2I.value,
    ImageModel.SEEDREAM_45_EDIT.value,
    ImageModel.GROK_I2I.value,
    ImageModel.WAN_27.value,
    ImageModel.WAN_27_PRO.value,
    ImageModel.QWEN_I2I.value,
    ImageModel.QWEN_EDIT.value,
    ImageModel.QWEN2_EDIT.value,
    ImageModel.GPT_IMAGE_2_I2I.value,
}
_STRICT_UPLOAD_MODELS = set(_KIE_UPLOAD_REFERENCE_MODELS)

_REFERENCE_LIMITS: dict[str, int] = {
    ImageModel.SEEDREAM_5_PRO_I2I.value: 10,
    ImageModel.SEEDREAM_45_EDIT.value: 3,
    ImageModel.GROK_I2I.value: 7,
    ImageModel.WAN_27.value: 9,
    ImageModel.WAN_27_PRO.value: 9,
    ImageModel.NANO_BANANA_2.value: 14,
    ImageModel.NANO_BANANA_2_LITE.value: 10,
    ImageModel.NANO_BANANA_PRO.value: 8,
    ImageModel.QWEN_I2I.value: 1,
    ImageModel.QWEN_EDIT.value: 1,
    ImageModel.QWEN2_EDIT.value: 1,
    ImageModel.GPT_IMAGE_2_I2I.value: _MAX_GPT_IMAGE_2_REFERENCES,
}
_GROK_MAX_REFERENCE_BYTES = 10 * 1024 * 1024

MODEL_ASPECT_RATIOS: dict[ImageModel, list[str]] = {
    ImageModel.SEEDREAM_5_PRO_T2I: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2"],
    ImageModel.SEEDREAM_5_PRO_I2I: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2"],
    ImageModel.SEEDREAM_45: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.SEEDREAM_45_EDIT: ["1:1", "4:3", "3:4", "16:9", "9:16", "2:3", "3:2", "21:9"],
    ImageModel.GROK_T2I: ["1:1", "2:3", "3:2", "16:9", "9:16"],
    ImageModel.GROK_I2I: [],
    ImageModel.WAN_27: ["1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"],
    ImageModel.WAN_27_PRO: ["1:1", "16:9", "4:3", "21:9", "3:4", "9:16", "8:1", "1:8"],
    ImageModel.NANO_BANANA: ["auto", "1:1", "9:16", "16:9", "3:4", "4:3", "3:2", "2:3", "5:4", "4:5", "21:9"],
    ImageModel.NANO_BANANA_2: ["auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"],
    ImageModel.NANO_BANANA_2_LITE: ["auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"],
    ImageModel.NANO_BANANA_PRO: ["auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"],
    ImageModel.QWEN_T2I: ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.QWEN_I2I: [],
    ImageModel.QWEN_EDIT: ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.QWEN2_T2I: ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.QWEN2_EDIT: ["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9"],
    ImageModel.GPT_IMAGE_2_T2I: ["1:1", "9:16", "16:9", "4:3", "3:4"],
    ImageModel.GPT_IMAGE_2_I2I: ["1:1", "9:16", "16:9", "4:3", "3:4"],
}


@dataclass
class ImageResult:
    is_async: bool = False
    task_id: str | None = None
    url: str | None = None
    result_urls: list[str] = field(default_factory=list)
    image_bytes: bytes | None = None
    mime_type: str = "image/png"


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
    return [str(url) for url in image_url if url]


def _restore_reference_shape(
    original: str | list[str] | None,
    urls: list[str],
) -> str | list[str] | None:
    if not urls:
        return None
    if isinstance(original, str):
        return urls[0]
    return urls


def _effective_model_for_request(
    model: ImageModel,
    image_url: str | list[str] | None,
) -> ImageModel:
    if model == ImageModel.GPT_IMAGE_2_T2I and _reference_list(image_url):
        return ImageModel.GPT_IMAGE_2_I2I
    return model


def _validate_reference_count(
    model: ImageModel,
    image_url: str | list[str] | None,
) -> None:
    refs = _reference_list(image_url)
    effective_model = _effective_model_for_request(model, image_url)
    resolved_model = resolve_model_for_reference(effective_model.value) if refs else effective_model.value

    if effective_model == ImageModel.GPT_IMAGE_2_I2I and not refs:
        raise ValueError("GPT Image 2 Edit requires at least one reference image")

    limit = _REFERENCE_LIMITS.get(resolved_model)
    if limit is not None and len(refs) > limit:
        raise ValueError(f"{resolved_model} supports at most {limit} reference image(s)")

    spec = IMAGE_SPECS.get(resolved_model)
    if refs and spec and "image" not in spec.supported_modes:
        raise ValueError(f"{resolved_model} does not support reference images")


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


def _validate_local_reference(model_key: str, path: Path) -> None:
    content_type = _content_type_for_path(path)
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError(f"Unsupported reference image type for {model_key}: {content_type}")
    if model_key == ImageModel.GROK_I2I.value and path.stat().st_size > _GROK_MAX_REFERENCE_BYTES:
        raise ValueError("Grok Imagine reference image must not exceed 10 MB")


async def _upload_local_kie_reference(url: str, *, model_key: str) -> str | None:
    path = local_upload_path_from_url(url)
    if not path or not path.exists() or not path.is_file():
        return None
    _validate_local_reference(model_key, path)
    return await kieai_client.upload_file_stream(
        path.read_bytes(),
        filename=path.name,
        content_type=_content_type_for_path(path),
        upload_path="images/apix-refs",
    )


async def _prepare_reference_urls_for_model(
    model: ImageModel,
    image_url: str | list[str] | None,
) -> str | list[str] | None:
    urls = _reference_list(image_url)
    if not urls:
        return image_url

    effective_model = _effective_model_for_request(model, image_url)
    resolved_model = resolve_model_for_reference(effective_model.value)
    if resolved_model not in _KIE_UPLOAD_REFERENCE_MODELS:
        return image_url

    prepared: list[str] = []
    for url in urls:
        local_path = local_upload_path_from_url(url)
        if not local_path or not local_path.exists() or not local_path.is_file():
            prepared.append(url)
            continue
        try:
            uploaded_url = await _upload_local_kie_reference(url, model_key=resolved_model)
        except Exception as exc:
            if resolved_model in _STRICT_UPLOAD_MODELS:
                raise RuntimeError(
                    f"Failed to upload {resolved_model} reference to KIE storage: {local_path.name}"
                ) from exc
            logger.warning("Failed to upload local reference url=%s: %s", url, exc)
            prepared.append(url)
            continue
        if not uploaded_url:
            raise RuntimeError(
                f"KIE file upload returned no URL for {resolved_model}: {local_path.name}"
            )
        prepared.append(uploaded_url)

    return _restore_reference_shape(image_url, prepared)


def _validate_prompt(prompt: str) -> str:
    value = str(prompt or "").strip()
    if not value:
        raise ValueError("Image prompt is required")
    return value


async def generate_image(
    model: ImageModel,
    prompt: str,
    image_url: str | list[str] | None = None,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    aspect_ratio: str | None = None,
    size: str = "1K",
    n: int = 1,
    quality: str = "basic",
    callback_url: str | None = None,
    *,
    negative_prompt: str | None = None,
    num_inference_steps: int | None = None,
    guidance_scale: float | None = None,
    acceleration: str | None = None,
    strength: float | None = None,
    sync_mode: bool | None = None,
    enable_safety_checker: bool | None = None,
    output_format: str | None = None,
    seed: int | None = None,
    enable_sequential: bool | None = None,
    thinking_mode: bool | None = None,
    watermark: bool | None = None,
    bbox_list: list[list[Any]] | None = None,
) -> ImageResult:
    del image_bytes, image_mime, size

    prompt = _validate_prompt(prompt)
    _validate_reference_count(model, image_url)
    prepared_image_url = await _prepare_reference_urls_for_model(model, image_url)
    resolved_model, inp = _build_input(
        model,
        prompt,
        prepared_image_url,
        aspect_ratio,
        n,
        quality,
        negative_prompt=negative_prompt,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        acceleration=acceleration,
        strength=strength,
        sync_mode=sync_mode,
        enable_safety_checker=enable_safety_checker,
        output_format=output_format,
        seed=seed,
        enable_sequential=enable_sequential,
        thinking_mode=thinking_mode,
        watermark=watermark,
        bbox_list=bbox_list,
    )

    if model in _COMET_PRIMARY_IMAGE_MODELS:
        result = await comet_fallback.generate_image(
            model_key=resolved_model,
            prompt=str(inp.get("prompt") or prompt),
            reference_urls=prepared_image_url,
            aspect_ratio=str(inp.get("aspect_ratio") or "") or None,
            count=max(1, int(n or 1)),
            resolution=str(inp.get("resolution") or "") or None,
        )
        if not result.urls:
            raise RuntimeError(f"CometAPI image returned no result URLs for {resolved_model}")
        return ImageResult(
            is_async=False,
            task_id=result.task_id,
            url=result.urls[0],
            result_urls=result.urls,
        )

    try:
        resp = await kieai_client.create_task(
            {"model": resolved_model, "input": inp},
            callback_url=callback_url,
        )
        if not isinstance(resp, dict):
            raise RuntimeError(f"KIE.AI image: invalid createTask response for {resolved_model}: {resp!r}")
        code = resp.get("code")
        if code not in (None, 200, "200"):
            raise RuntimeError(
                f"KIE.AI image createTask failed for {resolved_model}: {code} {resp.get('msg')}"
            )
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
    except Exception as exc:
        raise RuntimeError(
            f"{resolved_model} generation failed via its configured provider; "
            f"cross-model fallback is disabled: {exc}"
        ) from exc


def _build_input(
    model: ImageModel,
    prompt: str,
    image_url: str | list[str] | None,
    aspect_ratio: str | None,
    n: int,
    quality: str,
    *,
    negative_prompt: str | None = None,
    num_inference_steps: int | None = None,
    guidance_scale: float | None = None,
    acceleration: str | None = None,
    strength: float | None = None,
    sync_mode: bool | None = None,
    enable_safety_checker: bool | None = None,
    output_format: str | None = None,
    seed: int | None = None,
    enable_sequential: bool | None = None,
    thinking_mode: bool | None = None,
    watermark: bool | None = None,
    bbox_list: list[list[Any]] | None = None,
) -> tuple[str, dict[str, Any]]:
    _validate_reference_count(model, image_url)
    effective_model = _effective_model_for_request(model, image_url)

    ratio_value = aspect_ratio
    if effective_model in _GPT_IMAGE_2_MODELS and ratio_value == "auto":
        ratio_value = None

    resolved_for_validation = (
        resolve_model_for_reference(effective_model.value) if image_url else effective_model.value
    )
    try:
        ratio_model = ImageModel(resolved_for_validation)
    except ValueError:
        ratio_model = effective_model
    allowed_ratios = MODEL_ASPECT_RATIOS.get(ratio_model, [])
    if ratio_value and allowed_ratios and ratio_value not in allowed_ratios:
        raise ValueError(f"Unsupported aspect ratio {ratio_value} for {effective_model.value}")

    quality_value = quality
    resolution_value: str | None = None
    if effective_model in {
        ImageModel.WAN_27,
        ImageModel.WAN_27_PRO,
        ImageModel.NANO_BANANA_2,
        ImageModel.NANO_BANANA_PRO,
        ImageModel.GPT_IMAGE_2_T2I,
        ImageModel.GPT_IMAGE_2_I2I,
    }:
        resolution_value = quality_value if quality_value in {"1K", "2K", "4K"} else None

    if effective_model in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO}:
        if quality_value not in {"1K", "2K", "4K"}:
            quality_value = "1K" if effective_model == ImageModel.NANO_BANANA_2 else "2K"
        resolution_value = quality_value
    elif effective_model == ImageModel.NANO_BANANA_2_LITE and quality_value not in {"1K", "2K"}:
        quality_value = "1K"
    elif effective_model not in {
        ImageModel.GPT_IMAGE_2_T2I,
        ImageModel.GPT_IMAGE_2_I2I,
        ImageModel.WAN_27,
        ImageModel.WAN_27_PRO,
    } and quality_value in {"1K", "2K", "4K"}:
        quality_value = "basic"

    normalized_quality = normalize_quality_for_aspect_ratio(
        effective_model,
        ratio_value,
        quality_value,
    )
    if normalized_quality != quality_value:
        quality_value = str(normalized_quality)
        resolution_value = quality_value if quality_value in {"1K", "2K", "4K"} else resolution_value

    prepared_reference_urls = image_url
    if effective_model in {ImageModel.NANO_BANANA_2, ImageModel.NANO_BANANA_PRO}:
        if isinstance(image_url, str):
            prepared_reference_urls = ensure_provider_safe_png_url(image_url) or image_url
        elif isinstance(image_url, list):
            prepared_reference_urls = [ensure_provider_safe_png_url(url) or url for url in image_url]

    params: dict[str, Any] = {
        "aspect_ratio": ratio_value,
        "image_size": ratio_value,
        "n": n,
        "quality": quality_value,
        "resolution": resolution_value,
        "negative_prompt": negative_prompt,
        "num_inference_steps": num_inference_steps,
        "guidance_scale": guidance_scale,
        "acceleration": acceleration,
        "strength": strength,
        "sync_mode": sync_mode,
        "enable_safety_checker": enable_safety_checker,
        "output_format": output_format,
        "seed": seed,
        "enable_sequential": enable_sequential,
        "thinking_mode": thinking_mode,
        "watermark": watermark,
        "bbox_list": bbox_list,
    }

    resolved_model, payload = build_kie_input(
        model=effective_model.value,
        prompt=prompt,
        reference_urls=prepared_reference_urls,
        params=params,
    )

    if effective_model in _GPT_IMAGE_2_MODELS:
        payload.pop("nsfw_checker", None)
    return resolved_model, payload


def _urls_from_value(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, dict):
        for key in (
            "resultUrls",
            "result_urls",
            "imageUrls",
            "image_urls",
            "urls",
        ):
            item = value.get(key)
            if isinstance(item, list):
                urls.extend(str(url) for url in item if url)
            elif isinstance(item, str) and item.startswith("http"):
                urls.append(item)
        for key in ("resultUrl", "result_url", "imageUrl", "image_url", "url"):
            item = value.get(key)
            if isinstance(item, str) and item.startswith("http"):
                urls.append(item)
        for nested in value.values():
            urls.extend(_urls_from_value(nested))
    elif isinstance(value, list):
        for item in value:
            urls.extend(_urls_from_value(item))
    elif isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("http"):
            urls.append(stripped)
        elif stripped.startswith("{") or stripped.startswith("["):
            try:
                urls.extend(_urls_from_value(json.loads(stripped)))
            except json.JSONDecodeError:
                pass
    return list(dict.fromkeys(urls))


async def poll_kieai_result_urls(task_id: str) -> list[str] | None:
    resp = await kieai_client.get_task_status(task_id)
    if not isinstance(resp, dict):
        raise RuntimeError(f"KIE.AI image: invalid status response for task {task_id}: {resp!r}")
    data = resp.get("data")
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        raise RuntimeError(f"KIE.AI image: invalid status data for task {task_id}: {data!r}")

    state = str(data.get("state", "")).lower()
    if state == "success":
        urls = _urls_from_value(data.get("resultJson"))
        if not urls:
            urls = _urls_from_value(data)
        if urls:
            return urls
        raise RuntimeError("KIE.AI image: success but no result URL")
    if state == "fail":
        raise RuntimeError(f"KIE.AI image failed: {data.get('failMsg', 'unknown error')}")
    return None


async def poll_kieai_status(task_id: str) -> str | None:
    urls = await poll_kieai_result_urls(task_id)
    return urls[0] if urls else None


poll_seedream_status = poll_kieai_status
poll_wan27pro_status = poll_kieai_status
