from core.model_pricing import image_pricing_keys, pricing_variant_key, video_pricing_keys


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
