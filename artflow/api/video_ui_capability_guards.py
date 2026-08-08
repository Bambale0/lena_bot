"""UI capability guards for provider-specific video controls.

`Audio ID` and `Character ID` are Gemini Omni resources. Other providers may
also accept audio references, but those are ordinary files/URLs and must not
trigger Gemini Omni ID controls.
"""
from __future__ import annotations

from typing import Any

from core.gemini_omni import GEMINI_OMNI_VIDEO_MODEL

SEEDANCE25_MODEL = "bytedance/seedance-2-5"


def _strip_model_omni_id_caps(caps_by_model: Any, model_key: str) -> None:
    if not isinstance(caps_by_model, dict):
        return
    caps = caps_by_model.get(model_key)
    if not isinstance(caps, dict):
        return
    caps.pop("max_audio_ids", None)
    caps.pop("max_character_ids", None)


def _scope_keyboard_omni_id_caps(caps_by_model: Any) -> None:
    if not isinstance(caps_by_model, dict):
        return
    for model_key, caps in caps_by_model.items():
        if model_key == GEMINI_OMNI_VIDEO_MODEL or not isinstance(caps, dict):
            continue
        caps.pop("max_audio_ids", None)
        caps.pop("max_character_ids", None)


def strip_seedance25_omni_id_controls(routes: Any | None = None) -> None:
    """Keep Omni IDs on Gemini Omni while preserving Seedance audio refs.

    Seedance 2.5 still supports `reference_audio_urls`; only the unrelated
    `Audio ID` / `Character ID` UI affordances are removed.
    """
    try:
        from api import seedance25_adapter

        raw_caps = getattr(seedance25_adapter, "VIDEO_CAPS", None)
        if isinstance(raw_caps, dict):
            raw_caps.pop("max_audio_ids", None)
            raw_caps.pop("max_character_ids", None)
    except Exception:
        pass

    try:
        from bot.keyboards import models as keyboard_models

        _scope_keyboard_omni_id_caps(getattr(keyboard_models, "VIDEO_CAPS", None))
    except Exception:
        pass

    if routes is not None:
        _strip_model_omni_id_caps(getattr(routes, "VIDEO_CAPS", None), SEEDANCE25_MODEL)
