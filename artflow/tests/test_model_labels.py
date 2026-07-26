from api.image_service import ImageModel
from api.video_service import VideoModel
from bot.ui.model_labels import (
    all_known_model_keys,
    canonical_model_key,
    is_internal_variant,
    model_display_name,
)


def test_seedream_5_pro_is_one_hot_public_model():
    text = model_display_name("seedream/5-pro-text-to-image")
    edit = model_display_name("seedream/5-pro-image-to-image")
    assert text == "🔥 HOT · Seedream 5 Pro"
    assert edit == text
    assert canonical_model_key("seedream/5-pro-image-to-image") == "seedream/5-pro-text-to-image"


def test_grok_video_15_is_one_new_public_model():
    text = model_display_name("grok-imagine/text-to-video")
    image = model_display_name("grok-imagine/image-to-video")
    assert text == "🆕 NEW · Grok Imagine Video 1.5"
    assert image == text
    assert canonical_model_key("grok-imagine/image-to-video") == "grok-imagine/text-to-video"


def test_all_text_and_reference_route_pairs_share_public_name():
    pairs = [
        ("seedream/4.5-text-to-image", "seedream/4.5-edit"),
        ("grok-imagine/text-to-image", "grok-imagine/image-to-image"),
        ("qwen/text-to-image", "qwen/image-to-image"),
        ("qwen2/text-to-image", "qwen2/image-edit"),
        ("gpt-image-2-text-to-image", "gpt-image-2-image-to-image"),
        ("kling-2.6/text-to-video", "kling-2.6/image-to-video"),
        ("kling/v3-turbo-text-to-video", "kling/v3-turbo-image-to-video"),
        ("wan/2-7-text-to-video", "wan/2-7-image-to-video"),
        ("happyhorse/text-to-video", "happyhorse/image-to-video"),
    ]
    for canonical, variant in pairs:
        assert model_display_name(canonical) == model_display_name(variant)
        assert canonical_model_key(variant) == canonical
        assert is_internal_variant(variant)
        assert not is_internal_variant(canonical)


def test_every_runtime_image_and_video_model_has_explicit_public_label():
    known = all_known_model_keys()
    missing_images = {item.value for item in ImageModel} - known
    missing_videos = {item.value for item in VideoModel} - known
    assert missing_images == set()
    assert missing_videos == set()


def test_every_runtime_model_label_starts_with_emoji_or_badge():
    for key in all_known_model_keys():
        label = model_display_name(key)
        assert label
        assert label[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


def test_motion_and_quality_variants_remain_distinct_products():
    assert model_display_name("kling-2.6/motion-control") != model_display_name("kling-2.6/text-to-video")
    assert model_display_name("kling-3.0/motion-control") != model_display_name("kling-3.0/video")
    assert model_display_name("wan/2-7-image-pro") != model_display_name("wan/2-7-image")
    assert model_display_name("veo3_fast") != model_display_name("veo3")
