"""Provider contract corrections derived from current official specifications.

This module is intentionally imported by :mod:`api` before service modules load.
It replaces stale registry entries without duplicating request-building logic in
Telegram, Mini App and public API handlers.
"""
from __future__ import annotations

from typing import Any

from api.kie_model_specs import (
    IMAGE_SPECS,
    KieMediaType,
    KieModelSpec,
    KieReferenceType,
)

_APPLIED = False

_QWEN_LEGACY_SIZES = {
    "1:1": "square_hd",
    "3:4": "portrait_4_3",
    "2:3": "portrait_4_3",
    "9:16": "portrait_16_9",
    "4:3": "landscape_4_3",
    "3:2": "landscape_4_3",
    "16:9": "landscape_16_9",
    "21:9": "landscape_16_9",
    "square": "square",
    "square_hd": "square_hd",
    "portrait_4_3": "portrait_4_3",
    "portrait_16_9": "portrait_16_9",
    "landscape_4_3": "landscape_4_3",
    "landscape_16_9": "landscape_16_9",
}
_QWEN2_SIZES = {"1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2", "21:9"}


def _bool(params: dict[str, Any], key: str, default: bool) -> bool:
    value = params.get(key)
    return default if value is None else bool(value)


def _int(params: dict[str, Any], key: str, default: int) -> int:
    value = params.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _float(params: dict[str, Any], key: str, default: float) -> float:
    value = params.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a number") from exc


def _output_format(params: dict[str, Any], default: str = "png") -> str:
    value = str(params.get("output_format") or default).lower().strip()
    if value not in {"png", "jpeg", "jpg", "webp"}:
        raise ValueError("output_format must be png, jpeg, jpg or webp")
    return value


def _qwen_size(params: dict[str, Any], *, default: str) -> str:
    value = str(params.get("image_size") or params.get("aspect_ratio") or default)
    return _QWEN_LEGACY_SIZES.get(value, value)


def _qwen_common(
    params: dict[str, Any],
    *,
    default_size: str,
    default_steps: int,
    default_guidance: float,
) -> dict[str, Any]:
    return {
        "image_size": _qwen_size(params, default=default_size),
        "num_inference_steps": _int(params, "num_inference_steps", default_steps),
        "guidance_scale": _float(params, "guidance_scale", default_guidance),
        "enable_safety_checker": _bool(params, "enable_safety_checker", True),
        "output_format": _output_format(params),
        "negative_prompt": str(params.get("negative_prompt") or ""),
        "acceleration": str(params.get("acceleration") or "none"),
    }


def _qwen_t2i_params(params: dict[str, Any]) -> dict[str, Any]:
    return _qwen_common(
        params,
        default_size="square_hd",
        default_steps=30,
        default_guidance=2.5,
    )


def _qwen_i2i_params(params: dict[str, Any]) -> dict[str, Any]:
    out = _qwen_common(
        params,
        default_size="square_hd",
        default_steps=30,
        default_guidance=2.5,
    )
    out.pop("image_size", None)  # not part of the official qwen/image-to-image example contract
    out["strength"] = _float(params, "strength", 0.8)
    return out


def _qwen_edit_params(params: dict[str, Any]) -> dict[str, Any]:
    out = _qwen_common(
        params,
        default_size="landscape_4_3",
        default_steps=25,
        default_guidance=4.0,
    )
    out["sync_mode"] = _bool(params, "sync_mode", False)
    return out


def _qwen2_params(params: dict[str, Any], *, default_size: str = "16:9") -> dict[str, Any]:
    size = str(params.get("image_size") or params.get("aspect_ratio") or default_size)
    if size not in _QWEN2_SIZES:
        raise ValueError(f"Unsupported Qwen2 image_size: {size}")
    return {
        "image_size": size,
        "seed": _int(params, "seed", 0),
        "output_format": _output_format(params),
    }


def _qwen2_t2i_params(params: dict[str, Any]) -> dict[str, Any]:
    return _qwen2_params(params)


def _qwen2_edit_params(params: dict[str, Any]) -> dict[str, Any]:
    return _qwen2_params(params)


def _wan_image_params(params: dict[str, Any]) -> dict[str, Any]:
    has_reference = bool(params.get("has_reference"))
    enable_sequential = _bool(params, "enable_sequential", False)
    requested_resolution = str(params.get("resolution") or "2K")
    if requested_resolution not in {"1K", "2K", "4K"}:
        raise ValueError("WAN image resolution must be 1K, 2K or 4K")
    if requested_resolution == "4K" and (has_reference or enable_sequential):
        raise ValueError("WAN 4K is unavailable with references or sequential generation")

    max_images = 12 if enable_sequential else 4
    count = _int(params, "n", 1)
    if count < 1 or count > max_images:
        raise ValueError(f"WAN image count must be between 1 and {max_images}")

    bbox_list = params.get("bbox_list")
    if bbox_list is None and has_reference:
        refs_count = max(1, int(params.get("refs_count") or 1))
        bbox_list = [[] for _ in range(refs_count)]

    out: dict[str, Any] = {
        "n": count,
        "enable_sequential": enable_sequential,
        "resolution": requested_resolution,
        "thinking_mode": _bool(params, "thinking_mode", False),
        "watermark": _bool(params, "watermark", False),
        "seed": _int(params, "seed", 0),
    }
    if bbox_list is not None:
        out["bbox_list"] = bbox_list
    if not has_reference:
        out["aspect_ratio"] = str(params.get("aspect_ratio") or "1:1")
    return out


def apply_provider_spec_overrides() -> None:
    """Replace known stale model specs once per process."""
    global _APPLIED
    if _APPLIED:
        return

    IMAGE_SPECS.update(
        {
            "grok-imagine/text-to-image": KieModelSpec(
                model="grok-imagine/text-to-image",
                media_type=KieMediaType.IMAGE,
                supported_modes=("text",),
                optional_params={"aspect_ratio": "aspect_ratio"},
                defaults={"aspect_ratio": "1:1"},
                remix_model="grok-imagine/image-to-image",
            ),
            "grok-imagine/image-to-image": KieModelSpec(
                model="grok-imagine/image-to-image",
                media_type=KieMediaType.IMAGE,
                supported_modes=("image",),
                reference_field="image_urls",
                reference_type=KieReferenceType.LIST,
            ),
            "google/nano-banana": KieModelSpec(
                model="google/nano-banana",
                media_type=KieMediaType.IMAGE,
                supported_modes=("text",),
                optional_params={
                    "aspect_ratio": "aspect_ratio",
                    "output_format": "output_format",
                },
                defaults={"aspect_ratio": "1:1", "output_format": "png"},
            ),
            "qwen/text-to-image": KieModelSpec(
                model="qwen/text-to-image",
                media_type=KieMediaType.IMAGE,
                supported_modes=("text",),
                param_builder=_qwen_t2i_params,
                remix_model="qwen/image-to-image",
            ),
            "qwen/image-to-image": KieModelSpec(
                model="qwen/image-to-image",
                media_type=KieMediaType.IMAGE,
                supported_modes=("image",),
                reference_field="image_url",
                reference_type=KieReferenceType.SINGLE,
                param_builder=_qwen_i2i_params,
            ),
            "qwen/image-edit": KieModelSpec(
                model="qwen/image-edit",
                media_type=KieMediaType.IMAGE,
                supported_modes=("image",),
                reference_field="image_url",
                reference_type=KieReferenceType.SINGLE,
                param_builder=_qwen_edit_params,
            ),
            "qwen2/text-to-image": KieModelSpec(
                model="qwen2/text-to-image",
                media_type=KieMediaType.IMAGE,
                supported_modes=("text",),
                param_builder=_qwen2_t2i_params,
                remix_model="qwen2/image-edit",
            ),
            "qwen2/image-edit": KieModelSpec(
                model="qwen2/image-edit",
                media_type=KieMediaType.IMAGE,
                supported_modes=("image",),
                reference_field="image_url",
                reference_type=KieReferenceType.SINGLE,
                param_builder=_qwen2_edit_params,
            ),
            "wan/2-7-image": KieModelSpec(
                model="wan/2-7-image",
                media_type=KieMediaType.IMAGE,
                supported_modes=("text", "image"),
                reference_field="input_urls",
                reference_type=KieReferenceType.LIST,
                param_builder=_wan_image_params,
            ),
            "wan/2-7-image-pro": KieModelSpec(
                model="wan/2-7-image-pro",
                media_type=KieMediaType.IMAGE,
                supported_modes=("text", "image"),
                reference_field="input_urls",
                reference_type=KieReferenceType.LIST,
                param_builder=_wan_image_params,
            ),
        }
    )
    _APPLIED = True
