"""Runtime support for KIE Bytedance Seedance 2.5.

Seedance 2.5 uses the same KIE Market createTask / recordInfo flow as the
existing video models, but its input contract is richer than the older
Seedance 2.x variants.  The model supports three mutually exclusive scenarios:

* text-to-video;
* image-to-video with first frame or first+last frames;
* multimodal reference-to-video with image/video/audio references.

This module registers the model and its full request builder without exposing
provider secrets or ADMIN_IDS to the Mini App client.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

MODEL_KEY = "bytedance/seedance-2-5"
DISPLAY_NAME = "🌱 Seedance 2.5"

DURATION_AUTO = -1
DURATIONS = [DURATION_AUTO, *range(4, 31)]
ASPECT_RATIOS = ["adaptive", "16:9", "9:16", "1:1", "4:3", "3:4", "21:9"]
RESOLUTIONS = ["480p", "720p"]
OUTPUT_FORMATS = ["mp4", "mov"]
CREDITS_PER_SECOND = {"480p": 7.0, "720p": 10.0}
AUTO_DURATION_BILLING_SECONDS = 30

VIDEO_CAPS: dict[str, Any] = {
    "modes": ["text", "image", "first_last", "reference", "multimodal"],
    "duration_options": DURATIONS,
    "aspect_ratios": ASPECT_RATIOS,
    "has_resolution": True,
    "resolutions": RESOLUTIONS,
    "max_refs": 30,
    "max_reference_images": 30,
    "max_reference_videos": 10,
    "max_reference_audios": 10,
    "supports_video_input": True,
    "supports_audio_references": True,
    "supports_audio_generation": True,
    "supports_return_last_frame": True,
    "supports_output_format": True,
    "supports_web_search": True,
    "output_formats": OUTPUT_FORMATS,
    "billing_mode": "per_second",
    "auto_duration_billing_seconds": AUTO_DURATION_BILLING_SECONDS,
}


def _install_enum_value(enum_cls: Any, name: str, value: str) -> Any:
    """Register a runtime enum value so existing `VideoModel(value)` code works."""
    if value in getattr(enum_cls, "_value2member_map_", {}):
        return enum_cls(value)

    member = str.__new__(enum_cls, value)
    member._name_ = name
    member._value_ = value
    enum_cls._member_names_.append(name)
    enum_cls._member_map_[name] = member
    enum_cls._value2member_map_[value] = member
    return member


def _list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value] if value else []
    return [str(item) for item in value if item]


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _choice(value: Any, allowed: list[str], default: str) -> str:
    selected = str(value or default)
    return selected if selected in allowed else default


def _duration(value: Any) -> int:
    if value in {"auto", "AUTO", DURATION_AUTO, str(DURATION_AUTO)}:
        return DURATION_AUTO
    try:
        duration = int(value or 5)
    except (TypeError, ValueError):
        duration = 5
    return max(4, min(30, duration))


def _seedance25_params(params: dict[str, Any]) -> dict[str, Any]:
    """Build the official Seedance 2.5 `input` payload.

    The provider explicitly forbids mixing first/last-frame inputs with
    multimodal reference inputs.  The Mini App/backend normalizer passes a
    `mode` so this builder can choose exactly one scenario deterministically.
    """
    mode = str(params.get("mode") or "text").lower()
    image_refs = _list(params.get("reference_image_urls") or params.get("reference_urls"))[:30]
    video_refs = _list(params.get("reference_video_urls") or params.get("reference_video_url"))[:10]
    audio_refs = _list(params.get("reference_audio_urls") or params.get("reference_audio_url"))[:10]

    first_frame = str(params.get("first_frame_url") or "").strip()
    last_frame = str(params.get("last_frame_url") or "").strip()

    out: dict[str, Any] = {
        "resolution": _choice(params.get("resolution"), RESOLUTIONS, "720p"),
        "aspect_ratio": _choice(params.get("aspect_ratio"), ASPECT_RATIOS, "adaptive"),
        "duration": _duration(params.get("duration")),
        "output_format": _choice(params.get("output_format"), OUTPUT_FORMATS, "mp4"),
        "return_last_frame": _bool(params.get("return_last_frame"), False),
        "generate_audio": _bool(params.get("generate_audio"), True),
    }

    if params.get("web_search") is not None:
        out["web_search"] = _bool(params.get("web_search"), False)

    # Keep APIX moderation/safety policy centralized.  Do not expose a public
    # switch that lets the browser disable provider-side checks.
    if params.get("nsfw_checker") is not None:
        out["nsfw_checker"] = _bool(params.get("nsfw_checker"), False)

    wants_multimodal = mode in {"reference", "multimodal", "video", "audio"} or bool(video_refs or audio_refs)
    if wants_multimodal:
        if image_refs:
            out["reference_image_urls"] = image_refs
        if video_refs:
            out["reference_video_urls"] = video_refs
        if audio_refs:
            out["reference_audio_urls"] = audio_refs
        return out

    # Image mode means strict first-frame / first+last-frame.  For backward
    # compatibility old Mini App payloads may only provide `reference_urls`.
    if not first_frame and image_refs:
        first_frame = image_refs[0]
    if not last_frame and len(image_refs) >= 2:
        last_frame = image_refs[1]

    if first_frame:
        out["first_frame_url"] = first_frame
    if last_frame:
        out["last_frame_url"] = last_frame
    return out


def _model_cost(*, resolution: str | None = None):
    from db.models import GenerationType

    selected_resolution = resolution if resolution in CREDITS_PER_SECOND else "720p"
    credits = CREDITS_PER_SECOND[selected_resolution]
    return SimpleNamespace(
        model_key=MODEL_KEY,
        display_name=DISPLAY_NAME,
        gen_type=GenerationType.video,
        credits=float(credits),
        is_active=True,
    )


def install_seedance25_provider_support() -> None:
    """Install model enum/spec/repository support used by backend generation."""
    from api import kie_model_specs, video_service
    from db import repository

    if getattr(video_service, "_seedance25_adapter_installed", False):
        return

    _install_enum_value(video_service.VideoModel, "SEEDANCE_25", MODEL_KEY)
    kie_model_specs.VIDEO_SPECS[MODEL_KEY] = kie_model_specs.KieModelSpec(
        model=MODEL_KEY,
        media_type=kie_model_specs.KieMediaType.VIDEO,
        supported_modes=("text", "image", "first_last", "reference", "multimodal"),
        reference_type=kie_model_specs.KieReferenceType.NONE,
        param_builder=_seedance25_params,
    )
    kie_model_specs.MODEL_SPECS[MODEL_KEY] = kie_model_specs.VIDEO_SPECS[MODEL_KEY]

    if not getattr(repository, "_seedance25_adapter_installed", False):
        original_get_all = repository.get_all_model_costs
        original_get_one = repository.get_model_cost
        original_resolve_video = repository.resolve_video_model_cost

        async def get_all_model_costs(session, *args, **kwargs):
            rows = list(await original_get_all(session, *args, **kwargs))
            if not any(getattr(row, "model_key", None) == MODEL_KEY for row in rows):
                rows.append(_model_cost())
            return rows

        async def get_model_cost(session, model_key: str, *args, **kwargs):
            row = await original_get_one(session, model_key, *args, **kwargs)
            if row is None and model_key == MODEL_KEY:
                return _model_cost()
            return row

        async def resolve_video_model_cost(session, model_key: str, *args, **kwargs):
            row = await original_resolve_video(session, model_key, *args, **kwargs)
            if row is None and model_key == MODEL_KEY:
                return _model_cost(resolution=kwargs.get("resolution"))
            return row

        repository.get_all_model_costs = get_all_model_costs
        repository.get_model_cost = get_model_cost
        repository.resolve_video_model_cost = resolve_video_model_cost
        repository._seedance25_adapter_installed = True

    video_service._seedance25_adapter_installed = True


def install_seedance25_miniapp(routes: Any) -> None:
    """Expose model capabilities in Mini App routes after miniapp_routes loads."""
    install_seedance25_provider_support()

    routes.VIDEO_CAPS[MODEL_KEY] = dict(VIDEO_CAPS)
    order = getattr(routes, "_VIDEO_MODEL_ORDER", [])
    if MODEL_KEY not in order:
        try:
            insert_at = order.index("bytedance/seedance-2")
        except ValueError:
            insert_at = len(order)
        order.insert(insert_at, MODEL_KEY)


def install_seedance25_keyboard_support() -> None:
    """Keep Telegram bot keyboard capability registry in sync when imported."""
    try:
        from bot.keyboards import models as keyboard_models
    except Exception:
        return
    keyboard_models.VIDEO_CAPS[MODEL_KEY] = dict(VIDEO_CAPS)
