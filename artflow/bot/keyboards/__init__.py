"""Keyboard capability initialization.

Keep provider-specific compatibility overrides close to the UI capability
registry without duplicating them across Telegram and Mini App handlers.
"""
from __future__ import annotations

from api.image_service import (
    MODEL_ASPECT_RATIOS,
    ImageModel,
    _SQUARE_4K_UNSUPPORTED_MODELS,
)
from bot.keyboards.models import HIDDEN_IMAGE_MODELS, IMAGE_CAPS, IMAGE_MODEL_DESC


_GPT_IMAGE_2_STABLE_RATIOS = [
    "auto",
    "1:1",
    "3:2",
    "2:3",
    "4:3",
    "3:4",
    "16:9",
    "9:16",
    "2:1",
    "1:2",
    "21:9",
]
_GPT_IMAGE_2_QUALITY_OPTIONS = [
    ("2K", "🔷 2K (стандарт)"),
    ("4K", "💎 4K (высокое)"),
    ("1K", "⚡ 1K (быстро)"),
]


def _configure_gpt_image_2() -> None:
    """Expose GPT Image 2 as one model with automatic text/edit routing."""
    # Mutate the existing lists in place: IMAGE_CAPS keeps references to these
    # same list objects when bot.keyboards.models is initialized.
    MODEL_ASPECT_RATIOS[ImageModel.GPT_IMAGE_2_T2I][:] = _GPT_IMAGE_2_STABLE_RATIOS
    MODEL_ASPECT_RATIOS[ImageModel.GPT_IMAGE_2_I2I][:] = _GPT_IMAGE_2_STABLE_RATIOS

    # Current KIE capabilities allow square 4K for GPT Image 2. Preserve the
    # downgrade only for providers where that limitation still applies.
    _SQUARE_4K_UNSUPPORTED_MODELS.discard(ImageModel.GPT_IMAGE_2_T2I)
    _SQUARE_4K_UNSUPPORTED_MODELS.discard(ImageModel.GPT_IMAGE_2_I2I)

    base = IMAGE_CAPS[ImageModel.GPT_IMAGE_2_T2I]
    base.update(
        modes=["text", "image"],
        aspect_ratio_modes=["text", "image"],
        max_refs=16,
        quality_options=list(_GPT_IMAGE_2_QUALITY_OPTIONS),
        has_quality=True,
    )

    edit = IMAGE_CAPS[ImageModel.GPT_IMAGE_2_I2I]
    edit.update(
        modes=["image"],
        aspect_ratio_modes=["image"],
        max_refs=16,
        quality_options=list(_GPT_IMAGE_2_QUALITY_OPTIONS),
        has_quality=True,
    )

    # The text model now auto-routes to the edit endpoint when references are
    # present. Keep the legacy edit key working for saved sessions/API clients,
    # but avoid showing two near-identical buttons to new users.
    HIDDEN_IMAGE_MODELS.add(ImageModel.GPT_IMAGE_2_I2I)
    IMAGE_MODEL_DESC[ImageModel.GPT_IMAGE_2_T2I] = (
        "🤖 GPT Image 2 · текст или до 16 фото-референсов · 1K/2K/4K"
    )


_configure_gpt_image_2()
