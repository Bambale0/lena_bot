"""Compatibility and canonical normalization guards for Mini App video requests.

The backend remains the source of truth for model capabilities. This module is
installed by :mod:`api.__init__` after ``api.miniapp_routes`` is imported and
wraps its request normalizer so stale browser state cannot leak invalid values
into provider payloads. Motion Control is handled explicitly because Kling
motion models consume *both* an image reference and a motion video while their
logical mode is ``motion``.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any


def _first_or_none(values: list[Any] | tuple[Any, ...] | None) -> Any | None:
    return values[0] if values else None


def _normalized_resolution(routes: Any, model_key: str, resolution: str | None) -> str | None:
    normalize = getattr(routes, "_normalize_video_resolution", None)
    if callable(normalize):
        return normalize(model_key, resolution)
    return resolution


def _sanitize_mode(kwargs: dict[str, Any], supported_modes: list[str]) -> None:
    requested_mode = str(kwargs.get("mode") or "").strip() or "text"
    if requested_mode in supported_modes:
        return

    has_image_reference = bool(kwargs.get("image_url") or kwargs.get("reference_urls"))
    has_video_reference = bool(kwargs.get("video_url"))

    # Stale state after switching away from a video-input model must not make a
    # perfectly valid text/image request fail with a generic 422.
    if requested_mode == "video" and "video" not in supported_modes:
        kwargs["video_url"] = None
        has_video_reference = False

    if has_video_reference and "video" in supported_modes:
        kwargs["mode"] = "video"
    elif has_image_reference and "image" in supported_modes:
        kwargs["mode"] = "image"
    elif "text" in supported_modes:
        kwargs["mode"] = "text"
    elif len(supported_modes) == 1:
        kwargs["mode"] = supported_modes[0]


def _sanitize_discrete_params(routes: Any, kwargs: dict[str, Any], caps: dict[str, Any]) -> None:
    durations = list(caps.get("duration_options") or [])
    if durations and kwargs.get("duration") not in durations:
        kwargs["duration"] = _first_or_none(durations)

    if caps.get("has_resolution"):
        resolutions = list(caps.get("resolutions") or [])
        normalized = _normalized_resolution(routes, str(kwargs.get("model_key") or ""), kwargs.get("resolution"))
        if resolutions and normalized not in resolutions:
            kwargs["resolution"] = _first_or_none(resolutions)

    ratios = list(caps.get("aspect_ratios") or [])
    if ratios and kwargs.get("aspect_ratio") not in ratios:
        kwargs["aspect_ratio"] = _first_or_none(ratios)

    mode_options = list(caps.get("mode_options") or [])
    if mode_options and kwargs.get("grok_mode") not in mode_options:
        kwargs["grok_mode"] = "normal" if "normal" in mode_options else _first_or_none(mode_options)


def _normalize_motion_request(routes: Any, kwargs: dict[str, Any], caps: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Kling Motion Control request without losing either media input.

    ``miniapp_routes._normalize_video_request`` historically retained image
    references only for ``mode=image`` and accepted ``video_url`` only for
    ``mode=video``. Kling Motion's provider contract is different: one image
    drives the character and one video drives the motion. The provider adapter
    already maps these to ``input_urls`` + ``video_urls``; this normalizer makes
    the public request contract match that provider contract.
    """

    normalize_urls = routes._normalize_public_urls
    image_urls = normalize_urls(kwargs.get("image_url"), *(kwargs.get("reference_urls") or []))
    max_refs = max(1, int(caps.get("max_refs", 1) or 1))
    if not image_urls:
        raise routes.HTTPException(status_code=422, detail="Motion Control requires an image reference")
    if len(image_urls) > max_refs:
        raise routes.HTTPException(status_code=422, detail=f"Model supports at most {max_refs} reference image(s)")

    raw_video = kwargs.get("video_url")
    video_urls = normalize_urls(raw_video) if raw_video else []
    if not video_urls:
        raise routes.HTTPException(status_code=422, detail="Motion Control requires a motion video")

    resolutions = list(caps.get("resolutions") or []) if caps.get("has_resolution") else []
    resolution = _normalized_resolution(routes, str(kwargs.get("model_key") or ""), kwargs.get("resolution"))
    if resolutions:
        resolution = routes._normalize_choice(
            resolution,
            resolutions,
            field_name="resolution",
            default=resolutions[0],
        )
    else:
        resolution = None

    duration = int(kwargs.get("duration") or 5)
    if duration <= 0:
        duration = 5

    image_value: str | list[str] = image_urls[0] if len(image_urls) == 1 else image_urls
    return {
        "mode": "motion",
        "duration": duration,
        "aspect_ratio": None,
        "resolution": resolution,
        "image_url": image_value,
        "reference_video_url": video_urls[0],
        "video_start": None,
        "video_end": None,
        "audio_ids": [],
        "character_ids": [],
        "seed": None,
        "grok_mode": "normal",
    }


def install_video_request_compat(routes: Any) -> None:
    """Patch Mini App video normalization with capability-aware compatibility."""
    if getattr(routes, "_video_request_compat_installed", False):
        return

    original: Callable[..., dict[str, Any]] = routes._normalize_video_request

    def compat_normalize_video_request(**kwargs: Any) -> dict[str, Any]:
        model_key = str(kwargs.get("model_key") or "")
        caps = dict(getattr(routes, "VIDEO_CAPS", {}).get(model_key, {}) or {})
        supported_modes = list(caps.get("modes") or ["text"])

        if "motion" in supported_modes and str(kwargs.get("mode") or "") == "motion":
            return _normalize_motion_request(routes, kwargs, caps)

        # Ignore stale video input for models that cannot consume video. True
        # video-to-video remains untouched for capability-declared models.
        if "video" not in supported_modes and kwargs.get("video_url"):
            kwargs["video_url"] = None

        _sanitize_mode(kwargs, supported_modes)
        _sanitize_discrete_params(routes, kwargs, caps)
        return original(**kwargs)

    routes._normalize_video_request = compat_normalize_video_request
    routes._video_request_compat_installed = True
