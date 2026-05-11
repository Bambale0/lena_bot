from __future__ import annotations

from api.image_service import ImageModel, _build_input, normalize_quality_for_aspect_ratio


def test_normalize_quality_for_aspect_ratio_downgrades_square_4k() -> None:
    assert normalize_quality_for_aspect_ratio(ImageModel.GPT_IMAGE_2_I2I, "1:1", "4K") == "2K"
    assert normalize_quality_for_aspect_ratio("nano-banana-pro", "1:1", "4K") == "2K"


def test_normalize_quality_for_aspect_ratio_keeps_supported_combo() -> None:
    assert normalize_quality_for_aspect_ratio(ImageModel.GPT_IMAGE_2_I2I, "16:9", "4K") == "4K"
    assert normalize_quality_for_aspect_ratio(ImageModel.SEEDREAM_45, "1:1", "high") == "high"


def test_build_input_uses_2k_for_square_4k_request() -> None:
    _resolved_model, payload = _build_input(
        ImageModel.GPT_IMAGE_2_T2I,
        prompt="portrait",
        image_url=None,
        aspect_ratio="1:1",
        n=1,
        quality="4K",
    )

    assert payload["resolution"] == "2K"
