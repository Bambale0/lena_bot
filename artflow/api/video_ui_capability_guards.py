"""UI capability guards for provider-specific video controls.

`Audio ID` and `Character ID` are Gemini Omni resources. Seedance 2.5 supports
ordinary audio references by URL, so its capability metadata must not trigger
the generic Omni ID controls in Telegram or the React Mini App.
"""
from __future__ import annotations

from typing import Any

SEEDANCE25_MODEL = "bytedance/seedance-2-5"


def _strip_omni_id_caps(caps_by_model: Any) -> None:
    if not isinstance(caps_by_model, dict):
        return
    caps = caps_by_model.get(SEEDANCE25_MODEL)
    if not isinstance(caps, dict):
        return
    caps.pop("max_audio_ids", None)
    caps.pop("max_character_ids", None)


def strip_seedance25_omni_id_controls(routes: Any | None = None) -> None:
    """Remove Gemini Omni ID affordances from Seedance 2.5 UI metadata.

    Seedance's real `reference_audio_urls` support stays intact; only the
    provider-specific ID controls are removed.
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

        _strip_omni_id_caps(getattr(keyboard_models, "VIDEO_CAPS", None))
    except Exception:
        pass

    if routes is not None:
        _strip_omni_id_caps(getattr(routes, "VIDEO_CAPS", None))
