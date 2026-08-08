"""Telegram presentation guard for KIE Veo 3.1.

KIE's current create endpoint does not expose a duration selector, while Veo
reference-image generation is an 8-second upstream scenario. Keep Telegram's
state/review aligned with the public capability registry instead of its legacy
5-second fallback.
"""
from __future__ import annotations

from typing import Any

VEO_MODEL_KEYS = ("veo3", "veo3_fast", "veo3_lite")


def install_veo_handler_presentation(video_gen: Any) -> None:
    if getattr(video_gen, "_apix_veo_presentation_installed", False):
        return
    for model_key in VEO_MODEL_KEYS:
        video_gen._DEFAULT_DURATION[model_key] = 8
        video_gen._DEFAULT_RES.pop(model_key, None)
    video_gen._apix_veo_presentation_installed = True
