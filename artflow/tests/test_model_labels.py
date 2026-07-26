from bot.ui.model_labels import model_display_name, model_family_key, resolve_model_variant


def test_seedream_5_pro_is_one_public_hot_model():
    assert model_display_name("seedream/5-pro-text-to-image") == "🔥 HOT · Seedream 5 Pro"
    assert model_display_name("seedream/5-pro-image-to-image") == "🔥 HOT · Seedream 5 Pro"
    assert model_family_key("seedream/5-pro-text-to-image") == "seedream-5-pro"
    assert model_family_key("seedream/5-pro-image-to-image") == "seedream-5-pro"


def test_grok_video_15_is_one_public_new_model():
    assert model_display_name("grok-imagine/text-to-video") == "🆕 NEW · Grok Imagine Video 1.5"
    assert model_display_name("grok-imagine/image-to-video") == "🆕 NEW · Grok Imagine Video 1.5"
    assert model_family_key("grok-imagine/text-to-video") == "grok-video-1.5"
    assert model_family_key("grok-imagine/image-to-video") == "grok-video-1.5"


def test_provider_variant_is_selected_from_input_materials():
    assert resolve_model_variant("seedream-5-pro", has_image=False) == "seedream/5-pro-text-to-image"
    assert resolve_model_variant("seedream-5-pro", has_image=True) == "seedream/5-pro-image-to-image"
    assert resolve_model_variant("grok-video-1.5", has_image=False) == "grok-imagine/text-to-video"
    assert resolve_model_variant("grok-video-1.5", has_image=True) == "grok-imagine/image-to-video"


def test_every_known_family_has_an_emoji_prefix():
    keys = [
        "nano-banana-pro",
        "gpt-image-2-text-to-image",
        "kling-3.0/video",
        "bytedance/seedance-2-fast",
        "gemini-omni-video",
        "veo3",
        "suno/v5.5",
        "midjourney-imagine",
    ]
    for key in keys:
        label = model_display_name(key)
        assert label[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
