from core.model_pricing import image_pricing_keys, pricing_variant_key, video_pricing_keys
from db.seed import DEFAULT_MODEL_COSTS, LEGACY_MODEL_ALIASES_TO_DISABLE


def test_image_pricing_keys_prioritize_quality_variant() -> None:
    assert image_pricing_keys("nano-banana-pro", "4K") == [
        "nano-banana-pro__quality=4K",
        "nano-banana-pro",
    ]


def test_video_pricing_keys_prioritize_full_match_then_fallbacks() -> None:
    assert video_pricing_keys("kling-3.0/video", duration=10, resolution="pro") == [
        pricing_variant_key("kling-3.0/video", duration=10, resolution="pro"),
        pricing_variant_key("kling-3.0/video", resolution="pro"),
        pricing_variant_key("kling-3.0/video", duration=10),
        "kling-3.0/video",
    ]


def test_default_video_pricing_has_resolution_rates_and_per_second_base_rates() -> None:
    by_key = {item["model_key"]: item for item in DEFAULT_MODEL_COSTS}

    assert by_key["kling-2.6/text-to-video"]["credits"] == 5
    assert by_key["kling-2.6/text-to-video__resolution=1080p"]["credits"] == 7
    assert by_key["kling-3.0/video"]["credits"] == 6
    assert by_key["kling-3.0/video__resolution=pro"]["credits"] == 8
    assert by_key["bytedance/seedance-2"]["credits"] == 5
    assert by_key["bytedance/seedance-2__resolution=480p"]["credits"] == 5
    assert by_key["bytedance/seedance-2__resolution=720p"]["credits"] == 7
    assert by_key["grok-imagine/text-to-video__resolution=720p"]["credits"] == 45
    assert by_key["veo3"]["credits"] == 55


def test_active_video_resolution_variants_are_not_legacy_disabled() -> None:
    active_variant_keys = {
        "kling-3.0/video__resolution=std",
        "kling-3.0/video__resolution=pro",
        "kling-3.0/motion-control__resolution=1080p",
        "bytedance/seedance-2__resolution=480p",
        "grok-imagine/text-to-video__resolution=720p",
    }

    assert active_variant_keys.isdisjoint(LEGACY_MODEL_ALIASES_TO_DISABLE)
