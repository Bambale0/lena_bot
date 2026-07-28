from __future__ import annotations

from api import image_service
from api.image_service import ImageModel
from bot.keyboards.models import IMAGE_CAPS


IMAGE_FAMILY_ROUTES: dict[ImageModel, ImageModel] = {
    ImageModel.SEEDREAM_5_PRO_T2I: ImageModel.SEEDREAM_5_PRO_I2I,
    ImageModel.SEEDREAM_45: ImageModel.SEEDREAM_45_EDIT,
    ImageModel.GROK_T2I: ImageModel.GROK_I2I,
    ImageModel.QWEN_T2I: ImageModel.QWEN_I2I,
    ImageModel.QWEN2_T2I: ImageModel.QWEN2_EDIT,
    ImageModel.GPT_IMAGE_2_T2I: ImageModel.GPT_IMAGE_2_I2I,
}


def image_route_for_input(model: ImageModel | str, *, has_reference: bool) -> ImageModel:
    selected = model if isinstance(model, ImageModel) else ImageModel(str(model))
    if has_reference:
        return IMAGE_FAMILY_ROUTES.get(selected, selected)
    return selected


def install_image_family_routing() -> None:
    """Expose one public model family while selecting T2I/I2I internally.

    Models with a provider-specific edit endpoint gain both user-facing modes on
    their canonical entry. Models with a native multimodal endpoint keep their
    existing capabilities. Truly text-only models are left untouched.
    """
    for text_model, image_model in IMAGE_FAMILY_ROUTES.items():
        text_key = text_model.value
        image_key = image_model.value
        text_caps = IMAGE_CAPS.setdefault(text_key, {})
        image_caps = IMAGE_CAPS.get(image_key, {})

        text_caps["modes"] = ["text", "image"]
        text_caps["img2img_model"] = image_key
        text_caps["max_refs"] = int(image_caps.get("max_refs") or 1)

        text_ratio_modes = list(text_caps.get("aspect_ratio_modes") or [])
        image_ratio_modes = list(image_caps.get("aspect_ratio_modes") or [])
        if image_ratio_modes and "image" not in text_ratio_modes:
            text_ratio_modes.append("image")
        text_caps["aspect_ratio_modes"] = text_ratio_modes

    original = image_service._effective_model_for_request
    if getattr(original, "__apix_family_routing__", False):
        return

    def _effective_model_for_request(
        model: ImageModel,
        image_url: str | list[str] | None,
    ) -> ImageModel:
        refs = image_service._reference_list(image_url)
        return image_route_for_input(model, has_reference=bool(refs))

    _effective_model_for_request.__apix_family_routing__ = True  # type: ignore[attr-defined]
    image_service._effective_model_for_request = _effective_model_for_request
    image_service._SUPPORTS_IMG2IMG.update(IMAGE_FAMILY_ROUTES)
    image_service._SUPPORTS_IMG2IMG.update(IMAGE_FAMILY_ROUTES.values())
