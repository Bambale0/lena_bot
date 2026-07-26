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
from api.video_service import VideoModel
from bot.keyboards.models import (
    HIDDEN_IMAGE_MODELS,
    IMAGE_CAPS,
    IMAGE_MODEL_DESC,
    VIDEO_CAPS,
    VIDEO_MODEL_DESC,
)


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
_VEO_RATIOS = ["16:9", "9:16"]
_GROK_15_RATIOS = ["auto", "1:1", "16:9", "9:16", "3:2", "2:3"]
_GROK_15_DURATIONS = [4, 6, 8, 10, 12, 15]


def _configure_gpt_image_2() -> None:
    """Expose GPT Image 2 as one model with automatic text/edit routing."""
    MODEL_ASPECT_RATIOS[ImageModel.GPT_IMAGE_2_T2I][:] = _GPT_IMAGE_2_STABLE_RATIOS
    MODEL_ASPECT_RATIOS[ImageModel.GPT_IMAGE_2_I2I][:] = _GPT_IMAGE_2_STABLE_RATIOS

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

    HIDDEN_IMAGE_MODELS.add(ImageModel.GPT_IMAGE_2_I2I)
    IMAGE_MODEL_DESC[ImageModel.GPT_IMAGE_2_T2I] = (
        "🤖 GPT Image 2 · текст или до 16 фото-референсов · 1K/2K/4K"
    )


def _configure_veo_31() -> None:
    """Expose only controls accepted by the Veo 3.1 generation endpoint."""
    common = {
        "modes": ["text", "image"],
        "duration_options": [],
        "aspect_ratios": list(_VEO_RATIOS),
        "has_resolution": False,
        "resolutions": [],
        "billing_mode": "flat",
        "supports_first_last_frames": True,
        "generation_types": [
            "TEXT_2_VIDEO",
            "FIRST_AND_LAST_FRAMES_2_VIDEO",
        ],
    }

    VIDEO_CAPS[VideoModel.VEO_3].update(
        **common,
        max_refs=2,
        supports_material_reference=False,
    )
    reference_common = {
        **common,
        "generation_types": [
            "TEXT_2_VIDEO",
            "FIRST_AND_LAST_FRAMES_2_VIDEO",
            "REFERENCE_2_VIDEO",
        ],
    }
    VIDEO_CAPS[VideoModel.VEO_3_FAST].update(
        **reference_common,
        max_refs=3,
        supports_material_reference=True,
    )
    VIDEO_CAPS[VideoModel.VEO_3_LITE].update(
        **reference_common,
        max_refs=3,
        supports_material_reference=True,
    )

    VIDEO_MODEL_DESC[VideoModel.VEO_3] = (
        "🏆 Veo 3.1 Quality · текст, первый кадр или первый+последний"
    )
    VIDEO_MODEL_DESC[VideoModel.VEO_3_FAST] = (
        "🏆 Veo 3.1 Fast · кадры и material references · 1080P/4K после генерации"
    )
    VIDEO_MODEL_DESC[VideoModel.VEO_3_LITE] = (
        "🏆 Veo 3.1 Lite · кадры и material references · экономичный режим"
    )


def _configure_grok_15() -> None:
    """Expose the current Grok Imagine Video 1.5 Preview contract.

    Legacy internal model keys remain valid for saved sessions and pricing. The
    API bootstrap translates both keys to `grok-imagine-video-1-5-preview`.
    """
    common = {
        "modes": ["text", "image"],
        "duration_options": list(_GROK_15_DURATIONS),
        "aspect_ratios": list(_GROK_15_RATIOS),
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
        "max_refs": 7,
        "billing_mode": "per_second",
        "native_audio": True,
    }
    VIDEO_CAPS[VideoModel.GROK_T2V].update(**common, mode_options=[])
    VIDEO_CAPS[VideoModel.GROK_I2V].update(**common, mode_options=[])

    VIDEO_MODEL_DESC[VideoModel.GROK_T2V] = (
        "⚡ Grok Imagine Video 1.5 Preview · текст или до 7 фото · нативный звук"
    )
    VIDEO_MODEL_DESC[VideoModel.GROK_I2V] = (
        "⚡ Grok Imagine Video 1.5 Preview · фото в видео · нативный звук"
    )


_configure_gpt_image_2()
_configure_veo_31()
_configure_grok_15()
