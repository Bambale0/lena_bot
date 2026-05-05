from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable


class KieMediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class KieReferenceType(StrEnum):
    NONE = "none"
    SINGLE = "single"
    LIST = "list"
    FIRST_LAST = "first_last"
    KLING_MOTION = "kling_motion"


ParamBuilder = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class KieModelSpec:
    model: str
    media_type: KieMediaType
    supported_modes: tuple[str, ...]
    reference_field: str | None = None
    reference_type: KieReferenceType = KieReferenceType.NONE
    defaults: dict[str, Any] = field(default_factory=dict)
    optional_params: dict[str, str] = field(default_factory=dict)
    param_builder: ParamBuilder | None = None
    remix_model: str | None = None


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value if v is not None and v != ""]
    return value


def _refs(reference_urls: str | list[str] | None) -> list[str]:
    if not reference_urls:
        return []
    if isinstance(reference_urls, str):
        return [reference_urls] if reference_urls else []
    return [url for url in reference_urls if url]


def _str_duration(params: dict[str, Any]) -> dict[str, Any]:
    duration = params.get("duration")
    return {"duration": str(duration)} if duration is not None else {}


def _wan_image_params(params: dict[str, Any]) -> dict[str, Any]:
    out = {
        "resolution": params.get("resolution") or "2K",
        "n": max(1, min(4, int(params.get("n") or 1))),
        "enable_sequential": bool(params.get("enable_sequential", False)),
        "thinking_mode": bool(params.get("thinking_mode", False)),
        "watermark": False,
        "seed": int(params.get("seed") or 0),
        "nsfw_checker": False,
    }
    if not params.get("has_reference"):
        out["aspect_ratio"] = params.get("aspect_ratio") or "1:1"
    return out


def _seedance_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolution": params.get("resolution") or "720p",
        "aspect_ratio": params.get("aspect_ratio") or "16:9",
        "duration": params.get("duration") or 5,
        "return_last_frame": bool(params.get("return_last_frame", False)),
        "generate_audio": bool(params.get("generate_audio", False)),
        "nsfw_checker": False,
    }


def _grok_i2v_params(params: dict[str, Any]) -> dict[str, Any]:
    out = {
        "mode": params.get("grok_mode") or "normal",
        "duration": str(params.get("duration") or 6),
        "resolution": params.get("resolution") or "480p",
        "nsfw_checker": False,
    }
    if params.get("aspect_ratio"):
        out["aspect_ratio"] = params["aspect_ratio"]
    return out


def _kling_30_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": params.get("mode_quality") or params.get("resolution") or "pro",
        "sound": False,
        "duration": str(params.get("duration") or 5),
        "aspect_ratio": params.get("aspect_ratio") or "16:9",
        "multi_shots": bool(params.get("multi_shots", False)),
        "multi_prompt": params.get("multi_prompt") or [],
    }


def _kling_motion_params(params: dict[str, Any]) -> dict[str, Any]:
    mode = params.get("resolution")
    if params.get("model") == "kling-3.0/motion-control":
        mode = "pro" if mode == "1080p" else "std"
    return {"mode": mode or "720p"}


IMAGE_SPECS: dict[str, KieModelSpec] = {
    "seedream/4.5-text-to-image": KieModelSpec(
        model="seedream/4.5-text-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio", "quality": "quality"},
        defaults={"aspect_ratio": "1:1", "quality": "basic", "nsfw_checker": False},
        remix_model="seedream/4.5-edit",
    ),
    "seedream/4.5-edit": KieModelSpec(
        model="seedream/4.5-edit",
        media_type=KieMediaType.IMAGE,
        supported_modes=("image",),
        reference_field="image_urls",
        reference_type=KieReferenceType.LIST,
        optional_params={"aspect_ratio": "aspect_ratio", "quality": "quality"},
        defaults={"aspect_ratio": "1:1", "quality": "basic", "nsfw_checker": False},
    ),
    "grok-imagine/text-to-image": KieModelSpec(
        model="grok-imagine/text-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio"},
        defaults={"aspect_ratio": "1:1", "nsfw_checker": False, "enable_pro": False},
        remix_model="grok-imagine/image-to-image",
    ),
    "grok-imagine/image-to-image": KieModelSpec(
        model="grok-imagine/image-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("image",),
        reference_field="image_urls",
        reference_type=KieReferenceType.LIST,
        defaults={"nsfw_checker": False},
    ),
    "wan/2-7-image-pro": KieModelSpec(
        model="wan/2-7-image-pro",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text", "image"),
        reference_field="input_urls",
        reference_type=KieReferenceType.LIST,
        param_builder=_wan_image_params,
    ),
    "google/nano-banana": KieModelSpec(
        model="google/nano-banana",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "image_size"},
        defaults={"image_size": "auto", "output_format": "png"},
    ),
    "nano-banana-2": KieModelSpec(
        model="nano-banana-2",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text", "image"),
        reference_field="image_input",
        reference_type=KieReferenceType.LIST,
        optional_params={"aspect_ratio": "aspect_ratio", "quality": "resolution"},
        defaults={"aspect_ratio": "auto", "resolution": "1K", "output_format": "jpg"},
    ),
    "nano-banana-pro": KieModelSpec(
        model="nano-banana-pro",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text", "image"),
        reference_field="image_input",
        reference_type=KieReferenceType.LIST,
        optional_params={"aspect_ratio": "aspect_ratio", "quality": "resolution"},
        defaults={"aspect_ratio": "auto", "resolution": "1K", "output_format": "png"},
    ),
}


VIDEO_SPECS: dict[str, KieModelSpec] = {
    "kling-2.6/text-to-video": KieModelSpec(
        model="kling-2.6/text-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio"},
        defaults={"aspect_ratio": "16:9", "sound": False},
        param_builder=_str_duration,
        remix_model="kling-2.6/image-to-video",
    ),
    "kling-2.6/image-to-video": KieModelSpec(
        model="kling-2.6/image-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("image",),
        reference_field="image_urls",
        reference_type=KieReferenceType.LIST,
        defaults={"sound": False},
        param_builder=_str_duration,
    ),
    "kling-2.6/motion-control": KieModelSpec(
        model="kling-2.6/motion-control",
        media_type=KieMediaType.VIDEO,
        supported_modes=("motion",),
        reference_type=KieReferenceType.KLING_MOTION,
        defaults={"character_orientation": "video"},
        param_builder=_kling_motion_params,
    ),
    "kling-3.0/video": KieModelSpec(
        model="kling-3.0/video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image"),
        reference_field="image_urls",
        reference_type=KieReferenceType.FIRST_LAST,
        param_builder=_kling_30_params,
    ),
    "kling-3.0/motion-control": KieModelSpec(
        model="kling-3.0/motion-control",
        media_type=KieMediaType.VIDEO,
        supported_modes=("motion",),
        reference_type=KieReferenceType.KLING_MOTION,
        param_builder=_kling_motion_params,
    ),
    "wan/2-7-text-to-video": KieModelSpec(
        model="wan/2-7-text-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "ratio", "duration": "duration", "resolution": "resolution", "negative_prompt": "negative_prompt", "seed": "seed"},
        defaults={"ratio": "16:9", "duration": 5, "resolution": "1080p", "prompt_extend": True, "watermark": False},
        remix_model="wan/2-7-image-to-video",
    ),
    "wan/2-7-image-to-video": KieModelSpec(
        model="wan/2-7-image-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("image",),
        reference_field="first_frame_url",
        reference_type=KieReferenceType.FIRST_LAST,
        optional_params={"duration": "duration", "resolution": "resolution", "negative_prompt": "negative_prompt", "seed": "seed"},
        defaults={"duration": 5, "resolution": "1080p", "prompt_extend": True, "watermark": False},
    ),
    "bytedance/seedance-2": KieModelSpec(
        model="bytedance/seedance-2",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image"),
        reference_field="first_frame_url",
        reference_type=KieReferenceType.FIRST_LAST,
        param_builder=_seedance_params,
    ),
    "bytedance/seedance-2-fast": KieModelSpec(
        model="bytedance/seedance-2-fast",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image"),
        reference_field="first_frame_url",
        reference_type=KieReferenceType.FIRST_LAST,
        param_builder=_seedance_params,
    ),
    "grok-imagine/text-to-video": KieModelSpec(
        model="grok-imagine/text-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio", "duration": "duration", "resolution": "resolution", "grok_mode": "mode"},
        defaults={"aspect_ratio": "2:3", "duration": "6", "resolution": "480p", "mode": "normal", "nsfw_checker": False},
        remix_model="grok-imagine/image-to-video",
    ),
    "grok-imagine/image-to-video": KieModelSpec(
        model="grok-imagine/image-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("image",),
        reference_field="image_urls",
        reference_type=KieReferenceType.LIST,
        param_builder=_grok_i2v_params,
    ),
    "happyhorse/text-to-video": KieModelSpec(
        model="happyhorse/text-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio", "duration": "duration", "resolution": "resolution", "seed": "seed"},
        defaults={"aspect_ratio": "16:9", "duration": 5, "resolution": "1080p", "seed": 0},
        remix_model="happyhorse/image-to-video",
    ),
    "happyhorse/image-to-video": KieModelSpec(
        model="happyhorse/image-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("image",),
        reference_field="image_urls",
        reference_type=KieReferenceType.LIST,
        optional_params={"duration": "duration", "resolution": "resolution", "seed": "seed"},
        defaults={"duration": 5, "resolution": "1080p", "seed": 0},
    ),
}


MODEL_SPECS: dict[str, KieModelSpec] = {**IMAGE_SPECS, **VIDEO_SPECS}


def resolve_model_for_reference(model: str) -> str:
    spec = MODEL_SPECS.get(model)
    return spec.remix_model if spec and spec.remix_model else model


def build_kie_input(
    *,
    model: str,
    prompt: str,
    reference_urls: str | list[str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    urls = _refs(reference_urls)
    resolved_model = resolve_model_for_reference(model) if urls else model
    spec = MODEL_SPECS.get(resolved_model)
    if not spec:
        raise ValueError(f"Unknown KIE model: {resolved_model}")

    p = dict(params or {})
    p["has_reference"] = bool(urls)
    p["model"] = resolved_model

    inp: dict[str, Any] = {"prompt": prompt}
    inp.update(spec.defaults)

    for source_key, target_key in spec.optional_params.items():
        value = p.get(source_key)
        if value is not None:
            inp[target_key] = value

    if spec.param_builder:
        inp.update(spec.param_builder(p))

    if spec.reference_type == KieReferenceType.SINGLE and spec.reference_field:
        if urls:
            inp[spec.reference_field] = urls[0]
    elif spec.reference_type == KieReferenceType.LIST and spec.reference_field:
        if urls:
            inp[spec.reference_field] = urls
    elif spec.reference_type == KieReferenceType.FIRST_LAST:
        if spec.reference_field == "image_urls":
            image_urls = list(urls)
            if p.get("last_frame_url"):
                image_urls.append(p["last_frame_url"])
            if image_urls:
                inp["image_urls"] = image_urls
        else:
            if urls:
                inp[spec.reference_field or "first_frame_url"] = urls[0]
            if p.get("last_frame_url"):
                inp["last_frame_url"] = p["last_frame_url"]
    elif spec.reference_type == KieReferenceType.KLING_MOTION:
        inp["input_urls"] = urls
        inp["video_urls"] = [p["reference_video_url"]] if p.get("reference_video_url") else []

    return resolved_model, _clean(inp)
