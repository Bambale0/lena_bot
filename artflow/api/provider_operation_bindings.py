"""Bind catalog contracts to the fullest typed implementation available."""
from __future__ import annotations

from dataclasses import replace

from api import advanced_video_service, kling_grok_service
from api.provider_operation_registry import OPERATION_SPECS, PollKind


def _bind(
    contract_id: str,
    executor,
    *,
    fixed: dict | None = None,
    price_alias: str | None = None,
    poll_kind: PollKind = PollKind.KIE,
) -> None:
    current = OPERATION_SPECS[contract_id]
    OPERATION_SPECS[contract_id] = replace(
        current,
        executor=executor,
        fixed_params=tuple((fixed or {}).items()),
        price_alias=price_alias if price_alias is not None else current.price_alias,
        poll_kind=poll_kind,
    )


def apply_full_provider_bindings() -> None:
    _bind("video.kling26.t2v", kling_grok_service.create_kling_26_text_to_video)
    _bind("video.kling26.i2v", kling_grok_service.create_kling_26_image_to_video)
    _bind(
        "video.kling26.motion",
        kling_grok_service.create_kling_motion_control,
        fixed={"version": "2.6"},
    )
    _bind("video.kling30", kling_grok_service.create_kling_30_video)
    _bind(
        "video.kling30.motion",
        kling_grok_service.create_kling_motion_control,
        fixed={"version": "3.0"},
    )
    _bind("video.klingv3.turbo.t2v", kling_grok_service.create_kling_v3_turbo_text)
    _bind("video.klingv3.turbo.i2v", kling_grok_service.create_kling_v3_turbo_image)

    _bind("video.wan27.t2v", advanced_video_service.create_wan_text_to_video)
    _bind("video.wan27.i2v", advanced_video_service.create_wan_image_to_video)

    _bind(
        "video.seedance2",
        advanced_video_service.create_seedance_task,
        fixed={"model": advanced_video_service.SeedanceModel.QUALITY},
    )
    _bind(
        "video.seedance2.fast",
        advanced_video_service.create_seedance_task,
        fixed={"model": advanced_video_service.SeedanceModel.FAST},
    )
    _bind(
        "video.seedance2.mini",
        advanced_video_service.create_seedance_task,
        fixed={"model": advanced_video_service.SeedanceModel.MINI},
    )

    _bind(
        "video.happyhorse.t2v",
        advanced_video_service.create_happyhorse_text_to_video,
        fixed={"version_11": False},
    )
    _bind(
        "video.happyhorse.i2v",
        advanced_video_service.create_happyhorse_image_to_video,
        fixed={"version_11": False},
    )


apply_full_provider_bindings()
