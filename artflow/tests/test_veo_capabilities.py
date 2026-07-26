from __future__ import annotations

from api.video_service import VideoModel
from bot.keyboards.models import VIDEO_CAPS


def test_veo_quality_capabilities_match_generation_endpoint() -> None:
    caps = VIDEO_CAPS[VideoModel.VEO_3]

    assert caps["modes"] == ["text", "image"]
    assert caps["duration_options"] == []
    assert caps["has_resolution"] is False
    assert caps["resolutions"] == []
    assert caps["aspect_ratios"] == ["16:9", "9:16", "auto"]
    assert caps["max_refs"] == 2
    assert caps["supports_first_last_frames"] is True
    assert caps["supports_material_reference"] is False
    assert caps["billing_mode"] == "flat"


def test_veo_fast_and_lite_expose_material_reference_mode() -> None:
    for model in (VideoModel.VEO_3_FAST, VideoModel.VEO_3_LITE):
        caps = VIDEO_CAPS[model]
        assert caps["max_refs"] == 3
        assert caps["supports_material_reference"] is True
        assert caps["generation_types"] == [
            "TEXT_2_VIDEO",
            "FIRST_AND_LAST_FRAMES_2_VIDEO",
            "REFERENCE_2_VIDEO",
        ]
