from api.image_service import ImageModel, _effective_model_for_request
from api.kie_model_specs import build_kie_input


def test_image_families_route_to_edit_endpoint_when_reference_is_present():
    pairs = [
        ("seedream/5-pro-text-to-image", "seedream/5-pro-image-to-image"),
        ("seedream/4.5-text-to-image", "seedream/4.5-edit"),
        ("grok-imagine/text-to-image", "grok-imagine/image-to-image"),
        ("qwen/text-to-image", "qwen/image-to-image"),
        ("qwen2/text-to-image", "qwen2/image-edit"),
    ]
    for public_key, provider_edit_key in pairs:
        resolved, payload = build_kie_input(
            model=public_key,
            prompt="edit the image",
            reference_urls="https://example.com/reference.png",
        )
        assert resolved == provider_edit_key
        assert payload["prompt"] == "edit the image"


def test_gpt_image_2_routes_to_i2i_when_reference_is_present():
    assert _effective_model_for_request(
        ImageModel.GPT_IMAGE_2_T2I,
        "https://example.com/reference.png",
    ) == ImageModel.GPT_IMAGE_2_I2I
    assert _effective_model_for_request(ImageModel.GPT_IMAGE_2_T2I, None) == ImageModel.GPT_IMAGE_2_T2I


def test_video_families_route_to_i2v_endpoint_when_reference_is_present():
    pairs = [
        ("kling-2.6/text-to-video", "kling-2.6/image-to-video"),
        ("wan/2-7-text-to-video", "wan/2-7-image-to-video"),
        ("grok-imagine/text-to-video", "grok-imagine/image-to-video"),
        ("happyhorse/text-to-video", "happyhorse/image-to-video"),
    ]
    for public_key, provider_image_key in pairs:
        resolved, payload = build_kie_input(
            model=public_key,
            prompt="animate this image",
            reference_urls="https://example.com/reference.png",
            params={"duration": 5, "resolution": "720p"},
        )
        assert resolved == provider_image_key
        assert payload["prompt"] == "animate this image"


def test_native_multimodal_models_keep_one_provider_key():
    keys = [
        "wan/2-7-image",
        "wan/2-7-image-pro",
        "nano-banana-2",
        "nano-banana-2-lite",
        "nano-banana-pro",
        "kling-3.0/video",
        "bytedance/seedance-2",
        "bytedance/seedance-2-fast",
        "bytedance/seedance-2-mini",
        "gemini-omni-video",
        "veo3_fast",
        "veo3_lite",
    ]
    for key in keys:
        resolved, _ = build_kie_input(
            model=key,
            prompt="use reference",
            reference_urls="https://example.com/reference.png",
            params={"duration": 5, "resolution": "720p"},
        )
        assert resolved == key
