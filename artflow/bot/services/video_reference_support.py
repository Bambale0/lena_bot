from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from api.kie_model_specs import VIDEO_SPECS
from api.video_service import VideoModel
from bot.keyboards.models import VIDEO_CAPS, VIDEO_MODEL_DESC


SEEDANCE_VIDEO_REFERENCE_MODELS = {
    VideoModel.SEEDANCE_2.value,
    VideoModel.SEEDANCE_2_FAST.value,
    VideoModel.SEEDANCE_2_MINI.value,
}

VIDEO_REFERENCE_LIMITS: dict[str, dict[str, int]] = {
    VideoModel.SEEDANCE_2.value: {"min_duration": 2, "max_duration": 15, "max_refs": 3},
    VideoModel.SEEDANCE_2_FAST.value: {"min_duration": 2, "max_duration": 15, "max_refs": 3},
    VideoModel.SEEDANCE_2_MINI.value: {"min_duration": 2, "max_duration": 15, "max_refs": 3},
}


def _reference_video_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return []


def _wrap_seedance_builder(builder: Callable[[dict[str, Any]], dict[str, Any]] | None):
    def wrapped(params: dict[str, Any]) -> dict[str, Any]:
        out = dict(builder(params) if builder else {})
        refs = _reference_video_list(
            params.get("reference_video_urls") or params.get("reference_video_url")
        )
        if refs:
            out["reference_video_urls"] = refs[:3]
        return out

    return wrapped


def install_video_reference_support() -> None:
    """Expose provider-documented video reference modes without changing model keys."""
    for model_key in SEEDANCE_VIDEO_REFERENCE_MODELS:
        caps = VIDEO_CAPS.setdefault(model_key, {})
        modes = list(caps.get("modes") or [])
        if "video" not in modes:
            modes.append("video")
        caps.update(
            modes=modes,
            supports_video_input=True,
            max_video_refs=VIDEO_REFERENCE_LIMITS[model_key]["max_refs"],
            video_ref_min_duration=VIDEO_REFERENCE_LIMITS[model_key]["min_duration"],
            video_ref_max_duration=VIDEO_REFERENCE_LIMITS[model_key]["max_duration"],
            video_ref_formats=("mp4", "mov"),
        )

        spec = VIDEO_SPECS.get(model_key)
        if spec is not None:
            supported_modes = tuple(dict.fromkeys((*spec.supported_modes, "video")))
            VIDEO_SPECS[model_key] = replace(
                spec,
                supported_modes=supported_modes,
                param_builder=_wrap_seedance_builder(spec.param_builder),
            )

    VIDEO_MODEL_DESC[VideoModel.SEEDANCE_2] = (
        "🌱 Seedance 2 · текст, фото или видео-референсы · до 3 видео"
    )
    VIDEO_MODEL_DESC[VideoModel.SEEDANCE_2_FAST] = (
        "⚡ Seedance 2 Fast · текст, фото или видео-референсы · до 3 видео"
    )
    VIDEO_MODEL_DESC[VideoModel.SEEDANCE_2_MINI] = (
        "🚀 Seedance 2 Mini · текст, фото или видео-референсы · до 3 видео"
    )


def supports_video_reference(model_key: str) -> bool:
    return bool(VIDEO_CAPS.get(str(model_key), {}).get("supports_video_input"))


def video_reference_limits(model_key: str) -> dict[str, int]:
    return dict(VIDEO_REFERENCE_LIMITS.get(str(model_key), {}))
