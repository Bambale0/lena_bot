from __future__ import annotations

from types import SimpleNamespace

from api.video_ui_capability_guards import (
    SEEDANCE25_MODEL,
    strip_seedance25_omni_id_controls,
)
from bot.keyboards import models as keyboard_models
from core.gemini_omni import GEMINI_OMNI_VIDEO_MODEL


def test_seedance25_does_not_expose_omni_id_controls() -> None:
    strip_seedance25_omni_id_controls()

    seedance_caps = keyboard_models.VIDEO_CAPS[SEEDANCE25_MODEL]
    assert "max_audio_ids" not in seedance_caps
    assert "max_character_ids" not in seedance_caps
    assert seedance_caps.get("supports_audio_references") is True

    omni_caps = keyboard_models.VIDEO_CAPS[GEMINI_OMNI_VIDEO_MODEL]
    assert int(omni_caps.get("max_audio_ids") or 0) > 0
    assert int(omni_caps.get("max_character_ids") or 0) > 0


def test_seedance25_miniapp_caps_strip_only_omni_ids() -> None:
    routes = SimpleNamespace(
        VIDEO_CAPS={
            SEEDANCE25_MODEL: {
                "max_audio_ids": 10,
                "max_character_ids": 10,
                "supports_audio_references": True,
                "max_reference_audios": 10,
            },
            GEMINI_OMNI_VIDEO_MODEL: {
                "max_audio_ids": 3,
                "max_character_ids": 3,
            },
        }
    )

    strip_seedance25_omni_id_controls(routes)

    seedance_caps = routes.VIDEO_CAPS[SEEDANCE25_MODEL]
    assert "max_audio_ids" not in seedance_caps
    assert "max_character_ids" not in seedance_caps
    assert seedance_caps["supports_audio_references"] is True
    assert seedance_caps["max_reference_audios"] == 10

    assert routes.VIDEO_CAPS[GEMINI_OMNI_VIDEO_MODEL]["max_audio_ids"] == 3
    assert routes.VIDEO_CAPS[GEMINI_OMNI_VIDEO_MODEL]["max_character_ids"] == 3
