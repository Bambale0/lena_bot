"""Runtime support for KIE Bytedance Seedance 2.5.

The rest of the media stack already uses the generic KIE Market createTask /
recordInfo contract. This module registers the new provider model in the shared
capability/spec/cost registries without exposing provider details to the Mini App
client.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

MODEL_KEY = "bytedance/seedance-2-5"
DISPLAY_NAME = "🌱 Seedance 2.5"

DURATIONS = [5, 10, 15, 30]
ASPECT_RATIOS = ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"]
RESOLUTIONS = ["480p", "720p", "1080p"]
CREDITS_PER_SECOND = {"480p": 7.0, "720p": 10.0, "1080p": 14.0}

VIDEO_CAPS: dict[str, Any] = {
    "modes": ["text", "image"],
    "duration_options": DURATIONS,
    "aspect_ratios": ASPECT_RATIOS,
    "has_resolution": True,
    "resolutions": RESOLUTIONS,
    "max_refs": 9,
    "billing_mode": "per_second",
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


def _model_cost(*, resolution: str | None = None):
    from db.models import GenerationType

    credits = CREDITS_PER_SECOND.get(str(resolution or "720p"), CREDITS_PER_SECOND["720p"])
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
        supported_modes=("text", "image"),
        reference_field="reference_image_urls",
        reference_type=kie_model_specs.KieReferenceType.LIST,
        param_builder=kie_model_specs._seedance_params,
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
