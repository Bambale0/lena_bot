"""Compatibility guard for stale Mini App video draft payloads.

The Mini App may keep a previous mode/duration/resolution in local React state
while the user switches to another video model. Backend validation should still
protect provider contracts, but a stale client-only value should not turn a
valid text/video generation form into a generic 422.
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

    # Common stale-state case from the Mini App: user previously selected a
    # video-input model, then switched to Seedance/Grok/etc. The hidden draft
    # still says mode="video", while the selected model only accepts text/image.
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


def install_video_request_compat(routes: Any) -> None:
    """Patch Mini App video normalization to tolerate stale UI draft values."""
    if getattr(routes, "_video_request_compat_installed", False):
        return

    original: Callable[..., dict[str, Any]] = routes._normalize_video_request

    def compat_normalize_video_request(**kwargs: Any) -> dict[str, Any]:
        model_key = str(kwargs.get("model_key") or "")
        caps = dict(getattr(routes, "VIDEO_CAPS", {}).get(model_key, {}) or {})
        supported_modes = list(caps.get("modes") or ["text"])

        # Ignore stale video input for models that cannot consume video. The
        # user can still use true video-to-video on models with mode="video".
        if "video" not in supported_modes and kwargs.get("video_url"):
            kwargs["video_url"] = None

        _sanitize_mode(kwargs, supported_modes)
        _sanitize_discrete_params(routes, kwargs, caps)
        return original(**kwargs)

    routes._normalize_video_request = compat_normalize_video_request
    routes._video_request_compat_installed = True
