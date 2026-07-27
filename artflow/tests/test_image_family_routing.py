from api.image_service import ImageModel
from bot.keyboards.models import IMAGE_CAPS
from bot.services.image_family_routing import (
    IMAGE_FAMILY_ROUTES,
    image_route_for_input,
    install_image_family_routing,
)


def test_all_split_image_families_route_to_edit_endpoint_with_reference():
    expected = {
        ImageModel.SEEDREAM_5_PRO_T2I: ImageModel.SEEDREAM_5_PRO_I2I,
        ImageModel.SEEDREAM_45: ImageModel.SEEDREAM_45_EDIT,
        ImageModel.GROK_T2I: ImageModel.GROK_I2I,
        ImageModel.QWEN_T2I: ImageModel.QWEN_I2I,
        ImageModel.QWEN2_T2I: ImageModel.QWEN2_EDIT,
        ImageModel.GPT_IMAGE_2_T2I: ImageModel.GPT_IMAGE_2_I2I,
    }
    assert IMAGE_FAMILY_ROUTES == expected
    for text_model, image_model in expected.items():
        assert image_route_for_input(text_model, has_reference=False) == text_model
        assert image_route_for_input(text_model, has_reference=True) == image_model


def test_public_family_entries_expose_text_and_image_modes():
    install_image_family_routing()
    for text_model, image_model in IMAGE_FAMILY_ROUTES.items():
        caps = IMAGE_CAPS[text_model]
        assert caps["modes"] == ["text", "image"]
        assert caps["img2img_model"] == image_model.value
        assert caps["max_refs"] == IMAGE_CAPS[image_model].get("max_refs", 1)


def test_native_multimodal_models_remain_img2img_enabled():
    install_image_family_routing()
    for model in (
        ImageModel.WAN_27,
        ImageModel.WAN_27_PRO,
        ImageModel.NANO_BANANA_2,
        ImageModel.NANO_BANANA_2_LITE,
        ImageModel.NANO_BANANA_PRO,
    ):
        assert "image" in IMAGE_CAPS[model]["modes"]


def test_truly_text_only_legacy_nano_banana_is_not_falsely_advertised():
    install_image_family_routing()
    assert IMAGE_CAPS[ImageModel.NANO_BANANA]["modes"] == ["text"]
