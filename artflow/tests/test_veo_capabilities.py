from __future__ import annotations

from api.video_service import VideoModel
from bot.keyboards.models import VIDEO_CAPS


def test_veo_quality_capabilities_match_generation_endpoint() -> None:
    caps = VIDEO_CAPS[VideoModel.VEO_3]
    assert caps["modes"] == ["text", "image"]
    assert caps["duration_options"] == [8]
    assert caps["provider_managed_duration"] is True
    assert caps["has_resolution"] is False and caps["resolutions"] == []
    assert caps["aspect_ratios"] == ["16:9", "9:16"]
    assert caps["max_refs"] == 2
    assert not caps.get("supports_material_references", False)
    assert caps["billing_mode"] == "per_second"


def test_veo_fast_and_lite_expose_material_reference_mode() -> None:
    for model in (VideoModel.VEO_3_FAST, VideoModel.VEO_3_LITE):
        caps = VIDEO_CAPS[model]
        assert caps["max_refs"] == 3
        assert caps["supports_material_references"] is True
        assert caps["duration_options"] == [8]
