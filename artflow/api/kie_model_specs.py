from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass
from typing import Any, Callable

from core.gemini_omni import (
    GEMINI_OMNI_MAX_AUDIO_IDS,
    GEMINI_OMNI_MAX_CHARACTER_IDS,
    GEMINI_OMNI_VIDEO_MODEL,
    normalize_gemini_omni_aspect_ratio,
    normalize_gemini_omni_duration,
    normalize_gemini_omni_ids,
    normalize_gemini_omni_resolution,
    normalize_gemini_omni_seed,
    validate_gemini_omni_media_slots,
)


class KieMediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class KieReferenceType(StrEnum):
    NONE = "none"
    SINGLE = "single"
    LIST = "list"
    FIRST_LAST = "first_last"
    KLING_MOTION = "kling_motion"
    GEMINI_OMNI = "gemini_omni"


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


def _singular_reference_field(field: str) -> str | None:
    # Only expose aliases that we know are accepted and useful.
    # Wan and several other models document list-only fields such as
    # `input_urls` / `reference_image_urls`; sending a made-up singular key can
    # cause the provider to prefer the first image or ignore the full list.
    if field == "image_urls":
        return "image_url"
    return None


def _refs(reference_urls: str | list[str] | None) -> list[str]:
    if not reference_urls:
        return []
    if isinstance(reference_urls, str):
        return [reference_urls] if reference_urls else []
    return [url for url in reference_urls if url]


def _str_duration(params: dict[str, Any]) -> dict[str, Any]:
    duration = params.get("duration")
    return {"duration": str(duration)} if duration is not None else {}


def _qwen_legacy_size(value: str | None, *, default: str) -> str:
    mapping = {
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
    if not value:
        return default
    return mapping.get(str(value), default)


def _qwen_image_size_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "image_size": _qwen_legacy_size(params.get("aspect_ratio"), default="square_hd"),
        "output_format": "png",
        "nsfw_checker": False,
    }


def _qwen_edit_size_params(params: dict[str, Any]) -> dict[str, Any]:
    out = {
        "image_size": _qwen_legacy_size(params.get("aspect_ratio"), default="landscape_4_3"),
        "output_format": "png",
        "nsfw_checker": False,
    }
    if params.get("n") is not None:
        out["num_images"] = str(max(1, min(4, int(params.get("n") or 1))))
    return out


def _qwen2_size_params(params: dict[str, Any], *, default: str = "16:9") -> dict[str, Any]:
    allowed = {"1:1", "3:4", "4:3", "9:16", "16:9", "2:3", "3:2", "21:9"}
    value = str(params.get("aspect_ratio") or default)
    if value not in allowed:
        value = default
    return {
        "image_size": value,
        "output_format": "png",
        "nsfw_checker": False,
    }


def _qwen2_text_params(params: dict[str, Any]) -> dict[str, Any]:
    allowed = {"1:1", "3:4", "4:3", "9:16", "16:9"}
    value = str(params.get("aspect_ratio") or "16:9")
    if value not in allowed:
        if value == "2:3":
            value = "3:4"
        elif value in {"3:2", "21:9"}:
            value = "16:9"
        else:
            value = "16:9"
    return {
        "image_size": value,
        "output_format": "png",
        "nsfw_checker": False,
    }


def _wan_image_params(params: dict[str, Any]) -> dict[str, Any]:
    has_reference = bool(params.get("has_reference"))
    enable_sequential = bool(params.get("enable_sequential", False))
    resolution = params.get("resolution") or "2K"
    if resolution == "4K" and (has_reference or enable_sequential):
        resolution = "2K"
    max_images = 12 if enable_sequential else 4
    out = {
        "resolution": resolution,
        "n": max(1, min(max_images, int(params.get("n") or 1))),
        "enable_sequential": enable_sequential,
        "thinking_mode": bool(params.get("thinking_mode", False)),
        "watermark": False,
        "seed": int(params.get("seed") or 0),
        "nsfw_checker": False,
    }
    if not has_reference:
        out["aspect_ratio"] = params.get("aspect_ratio") or "1:1"
    return out


def _seedance_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "resolution": params.get("resolution") or "720p",
        "aspect_ratio": params.get("aspect_ratio") or "16:9",
        "duration": params.get("duration") or 5,
        "return_last_frame": bool(params.get("return_last_frame", False)),
        "generate_audio": bool(params.get("generate_audio", True)),
        "nsfw_checker": False,
    }


def _grok_duration(value: Any, *, default: int = 6) -> str:
    try:
        duration = int(value)
    except (TypeError, ValueError):
        duration = default
    duration = max(6, min(30, duration))
    return str(duration)


def _grok_mode(value: Any, *, allow_spicy: bool) -> str:
    mode = str(value or "normal")
    allowed = {"fun", "normal", "spicy" if allow_spicy else "normal"}
    if mode not in allowed:
        return "normal"
    if mode == "spicy" and not allow_spicy:
        return "normal"
    return mode


def _grok_t2v_params(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "duration": _grok_duration(params.get("duration"), default=6),
        "mode": _grok_mode(params.get("grok_mode"), allow_spicy=True),
    }


def _grok_i2v_params(params: dict[str, Any]) -> dict[str, Any]:
    refs_count = int(params.get("refs_count") or 0)
    out = {
        "mode": _grok_mode(params.get("grok_mode"), allow_spicy=False),
        "duration": _grok_duration(params.get("duration"), default=6),
        "resolution": params.get("resolution") or "480p",
        "nsfw_checker": False,
    }
    if params.get("aspect_ratio") and refs_count > 1:
        out["aspect_ratio"] = params["aspect_ratio"]
    return out


def _kling_30_params(params: dict[str, Any]) -> dict[str, Any]:
    _RES_MAP = {"2K": "pro", "4K": "4K", "std": "std", "pro": "pro"}
    raw_res = params.get("mode_quality") or params.get("resolution") or "pro"
    return {
        "mode": _RES_MAP.get(raw_res, raw_res),
        "sound": bool(params.get("sound", True)),
        "duration": str(params.get("duration") or 5),
        "aspect_ratio": params.get("aspect_ratio") or "16:9",
        "multi_shots": bool(params.get("multi_shots", False)),
        "multi_prompt": params.get("multi_prompt") or [],
    }


def _kling_motion_params(params: dict[str, Any]) -> dict[str, Any]:
    raw_mode = str(params.get("resolution") or params.get("mode_quality") or "").strip()
    model = str(params.get("model") or "")

    if model == "kling-2.6/motion-control":
        mode_map = {
            "720p": "720p",
            "1080p": "1080p",
            # Backward-compatible aliases if old UI/state still sends them.
            "std": "720p",
            "pro": "1080p",
        }
        return {"mode": mode_map.get(raw_mode or "720p", raw_mode or "720p")}

    if model == "kling-3.0/motion-control":
        mode_map = {
            "720p": "720p",
            "1080p": "1080p",
            "4K": "4K",
            # Accept legacy/internal aliases and normalize to current provider values.
            "std": "720p",
            "pro": "1080p",
            "2K": "1080p",
        }
        return {"mode": mode_map.get(raw_mode or "720p", raw_mode or "720p")}

    return {"mode": raw_mode or "720p"}


def _gemini_omni_video_params(params: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "duration": str(normalize_gemini_omni_duration(params.get("duration"))),
        "aspect_ratio": normalize_gemini_omni_aspect_ratio(params.get("aspect_ratio")),
        "resolution": normalize_gemini_omni_resolution(params.get("resolution")),
    }
    audio_ids = normalize_gemini_omni_ids(
        params.get("audio_ids"),
        max_items=GEMINI_OMNI_MAX_AUDIO_IDS,
        field_name="audio_ids",
    )
    character_ids = normalize_gemini_omni_ids(
        params.get("character_ids"),
        max_items=GEMINI_OMNI_MAX_CHARACTER_IDS,
        field_name="character_ids",
    )
    if audio_ids:
        out["audio_ids"] = audio_ids
    if character_ids:
        out["character_ids"] = character_ids
    seed = normalize_gemini_omni_seed(params.get("seed"))
    if seed is not None:
        out["seed"] = seed
    return out


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
        defaults={"aspect_ratio": "auto", "resolution": "2K", "output_format": "jpg"},
    ),
    "nano-banana-pro": KieModelSpec(
        model="nano-banana-pro",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text", "image"),
        reference_field="image_input",
        reference_type=KieReferenceType.LIST,
        optional_params={"aspect_ratio": "aspect_ratio", "quality": "resolution"},
        defaults={"aspect_ratio": "auto", "resolution": "2K", "output_format": "png"},
    ),
    "qwen/text-to-image": KieModelSpec(
        model="qwen/text-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text",),
        param_builder=_qwen_image_size_params,
        remix_model="qwen/image-to-image",
    ),
    "qwen/image-to-image": KieModelSpec(
        model="qwen/image-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("image",),
        reference_field="image_url",
        reference_type=KieReferenceType.SINGLE,
        param_builder=_qwen_image_size_params,
    ),
    "qwen/image-edit": KieModelSpec(
        model="qwen/image-edit",
        media_type=KieMediaType.IMAGE,
        supported_modes=("image",),
        reference_field="image_url",
        reference_type=KieReferenceType.SINGLE,
        param_builder=_qwen_edit_size_params,
    ),
    "qwen2/text-to-image": KieModelSpec(
        model="qwen2/text-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text",),
        param_builder=_qwen2_text_params,
        remix_model="qwen2/image-edit",
    ),
    "qwen2/image-edit": KieModelSpec(
        model="qwen2/image-edit",
        media_type=KieMediaType.IMAGE,
        supported_modes=("image",),
        reference_field="image_url",
        reference_type=KieReferenceType.SINGLE,
        param_builder=_qwen2_size_params,
    ),
    "openrouter/free": KieModelSpec(
        model="openrouter/free",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio"},
        defaults={"aspect_ratio": "1:1", "nsfw_checker": False},
    ),
    # GPT Image 2
    "gpt-image-2-text-to-image": KieModelSpec(
        model="gpt-image-2-text-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio", "resolution": "resolution"},
        defaults={"nsfw_checker": False},
    ),
    "gpt-image-2-image-to-image": KieModelSpec(
        model="gpt-image-2-image-to-image",
        media_type=KieMediaType.IMAGE,
        supported_modes=("image",),
        reference_field="input_urls",
        reference_type=KieReferenceType.LIST,
        optional_params={"aspect_ratio": "aspect_ratio", "resolution": "resolution"},
        defaults={"nsfw_checker": False},
    ),
}


VIDEO_SPECS: dict[str, KieModelSpec] = {
    "kling-2.6/text-to-video": KieModelSpec(
        model="kling-2.6/text-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio"},
        defaults={"aspect_ratio": "16:9", "sound": True},
        param_builder=_str_duration,
        remix_model="kling-2.6/image-to-video",
    ),
    "kling-2.6/image-to-video": KieModelSpec(
        model="kling-2.6/image-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("image",),
        reference_field="image_urls",
        reference_type=KieReferenceType.LIST,
        defaults={"sound": True},
        param_builder=_str_duration,
    ),
    "kling-2.6/motion-control": KieModelSpec(
        model="kling-2.6/motion-control",
        media_type=KieMediaType.VIDEO,
        supported_modes=("motion",),
        reference_type=KieReferenceType.KLING_MOTION,
        defaults={"character_orientation": "image"},
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
        defaults={"character_orientation": "image", "background_source": "input_video"},
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
        reference_field="reference_image_urls",
        reference_type=KieReferenceType.LIST,
        param_builder=_seedance_params,
    ),
    "bytedance/seedance-2-fast": KieModelSpec(
        model="bytedance/seedance-2-fast",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image"),
        reference_field="reference_image_urls",
        reference_type=KieReferenceType.LIST,
        param_builder=_seedance_params,
    ),
    "grok-imagine/text-to-video": KieModelSpec(
        model="grok-imagine/text-to-video",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text",),
        optional_params={"aspect_ratio": "aspect_ratio", "resolution": "resolution"},
        defaults={"aspect_ratio": "2:3", "duration": "6", "resolution": "480p", "mode": "normal", "nsfw_checker": False},
        param_builder=_grok_t2v_params,
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
    GEMINI_OMNI_VIDEO_MODEL: KieModelSpec(
        model=GEMINI_OMNI_VIDEO_MODEL,
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image", "video"),
        reference_field="image_urls",
        reference_type=KieReferenceType.GEMINI_OMNI,
        param_builder=_gemini_omni_video_params,
    ),

    # ── Veo 3 ────────────────────────────────────────────────────────────────
    "veo3": KieModelSpec(
        model="veo3",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image"),
        reference_type=KieReferenceType.SINGLE,
        reference_field="first_frame_url",
        optional_params={
            "aspect_ratio": "aspect_ratio",
            "duration": "duration",
            "resolution": "resolution",
        },
        defaults={
            "aspect_ratio": "16:9",
            "duration": 5,
            "nsfw_checker": False,
            "enableTranslation": True,
            "enableFallback": False,
        },
        param_builder=_str_duration,
    ),
    "veo3_fast": KieModelSpec(
        model="veo3_fast",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image"),
        reference_type=KieReferenceType.SINGLE,
        reference_field="first_frame_url",
        optional_params={
            "aspect_ratio": "aspect_ratio",
            "duration": "duration",
            "resolution": "resolution",
        },
        defaults={
            "aspect_ratio": "16:9",
            "duration": 5,
            "nsfw_checker": False,
            "enableTranslation": True,
            "enableFallback": False,
        },
        param_builder=_str_duration,
    ),
    "veo3_lite": KieModelSpec(
        model="veo3_lite",
        media_type=KieMediaType.VIDEO,
        supported_modes=("text", "image"),
        reference_type=KieReferenceType.SINGLE,
        reference_field="first_frame_url",
        optional_params={
            "aspect_ratio": "aspect_ratio",
            "duration": "duration",
            "resolution": "resolution",
        },
        defaults={
            "aspect_ratio": "16:9",
            "duration": 5,
            "nsfw_checker": False,
            "enableTranslation": True,
            "enableFallback": False,
        },
        param_builder=_str_duration,
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
    p["refs_count"] = len(urls)
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
    elif spec.reference_type == KieReferenceType.GEMINI_OMNI:
        video_url = p.get("reference_video_url")
        character_ids = inp.get("character_ids") if isinstance(inp.get("character_ids"), list) else []
        validate_gemini_omni_media_slots(
            image_count=len(urls),
            video_count=1 if video_url else 0,
            character_count=len(character_ids),
        )
        if urls:
            inp["image_urls"] = urls
        if video_url:
            raw_start = p.get("video_start", 0)
            raw_end = p.get("video_end", p.get("video_ends", p.get("duration", 10)))
            try:
                start = float(raw_start or 0)
            except (TypeError, ValueError):
                start = 0.0
            try:
                end = float(raw_end or 10)
            except (TypeError, ValueError):
                end = 10.0
            if end <= start:
                end = start + 1
            if end - start > 10:
                end = start + 10
            inp["video_list"] = [{"url": video_url, "start": start, "ends": end}]

    if spec.reference_field in {"image_urls"} and spec.reference_type != KieReferenceType.GEMINI_OMNI:
        urls_value = inp.get(spec.reference_field)
        if isinstance(urls_value, list) and urls_value:
            singular_field = _singular_reference_field(spec.reference_field)
            if singular_field:
                inp.setdefault(singular_field, urls_value[0])

    return resolved_model, _clean(inp)
