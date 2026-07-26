"""Keyboard capability initialization.

Keep provider-specific compatibility overrides close to the UI capability
registry without duplicating them across Telegram and Mini App handlers.
"""
from __future__ import annotations

from api.image_service import ImageModel
from bot.keyboards.models import HIDDEN_IMAGE_MODELS, IMAGE_CAPS, IMAGE_MODEL_DESC


def _configure_gpt_image_2() -> None:
    """Expose GPT Image 2 as one model with automatic text/edit routing."""
    base = IMAGE_CAPS[ImageModel.GPT_IMAGE_2_T2I]
    base.update(
        modes=["text", "image"],
        aspect_ratio_modes=["text", "image"],
        max_refs=16,
    )

    edit = IMAGE_CAPS[ImageModel.GPT_IMAGE_2_I2I]
    edit.update(
        modes=["image"],
        aspect_ratio_modes=["image"],
        max_refs=16,
    )

    # The text model now auto-routes to the edit endpoint when references are
    # present. Keep the legacy edit key working for saved sessions/API clients,
    # but avoid showing two near-identical buttons to new users.
    HIDDEN_IMAGE_MODELS.add(ImageModel.GPT_IMAGE_2_I2I)
    IMAGE_MODEL_DESC[ImageModel.GPT_IMAGE_2_T2I] = (
        "🤖 GPT Image 2 · текст или до 16 фото-референсов · точные правки"
    )


_configure_gpt_image_2()
