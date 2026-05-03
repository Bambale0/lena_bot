# bot/keyboards/models.py
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.image_service import ImageModel
from api.video_service import MotionDirection, VideoModel
from db.models import ModelCost

# ── Capabilities registry ────────────────────────────────────────────────────

VIDEO_CAPS: dict[str, dict] = {
    VideoModel.KLING_30: {
        "label": "Kling 3.0", "emoji": "🌊",
        "modes": ["text", "image"],
        "duration_options": [5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "has_resolution": False,
    },
    VideoModel.KLING_26_MOTION: {
        "label": "Kling 2.6 Motion", "emoji": "🌊",
        "modes": ["text", "image"],
        "duration_options": [5],
        "aspect_ratios": ["16:9"],
        "has_resolution": False,
        "has_motion": True,
    },
    VideoModel.GROK_IMAGINE: {
        "label": "Grok Imagine Video", "emoji": "⚡",
        "modes": ["text"],
        "duration_options": [5, 10, 15],
        "aspect_ratios": ["16:9"],
        "has_resolution": False,
    },
    VideoModel.GROK_VIDEO: {
        "label": "Grok Video", "emoji": "⚡",
        "modes": ["text"],
        "duration_options": [],
        "aspect_ratios": [],
        "has_resolution": False,
    },
    VideoModel.SEEDANCE_20: {
        "label": "Seedance 2.0", "emoji": "🌸",
        "modes": ["text", "image"],
        "duration_options": [3, 5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "has_resolution": False,
    },
    VideoModel.VEO_31_PRO: {
        "label": "Veo 3.1 Pro", "emoji": "🌿",
        "modes": ["text", "image"],
        "duration_options": [],
        "aspect_ratios": ["16:9"],
        "has_resolution": False,
    },
    VideoModel.HAPPYHORSE_T2V: {
        "label": "HappyHorse T2V", "emoji": "🎠",
        "modes": ["text"],
        "duration_options": [3, 5, 8, 10, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    VideoModel.HAPPYHORSE_I2V: {
        "label": "HappyHorse I2V", "emoji": "🎠",
        "modes": ["image"],
        "duration_options": [3, 5, 8, 10, 15],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
}

IMAGE_CAPS: dict[str, dict] = {
    ImageModel.WAN_27_PRO: {
        "modes": ["text", "image"],
        "aspect_ratios": ["1:1", "16:9", "9:16", "4:3", "3:4"],
        "counts": [1, 2, 4],
        "resolutions": ["2K"],
    },
    ImageModel.SEEDREAM_3: {
        "modes": ["text", "image"],
        "aspect_ratios": [],
        "counts": [1],
    },
}


# ── Image keyboards ───────────────────────────────────────────────────────────

def image_models_kb(model_costs: list[ModelCost]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mc in model_costs:
        if mc.gen_type.value == "image":
            builder.row(
                InlineKeyboardButton(
                    text=f"{mc.display_name} — {mc.credits} кр",
                    callback_data=f"img_model:{mc.model_key}",
                )
            )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


def image_mode_kb(model_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✍️ Текст → Изображение", callback_data=f"img_mode:text:{model_key}"),
    )
    caps = IMAGE_CAPS.get(model_key, {})
    if "image" in caps.get("modes", []):
        builder.row(
            InlineKeyboardButton(text="🖼️ Референс → Изображение", callback_data=f"img_mode:image:{model_key}"),
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:image"))
    return builder.as_markup()


def image_aspect_ratio_kb(model_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    caps = IMAGE_CAPS.get(model_key, {})
    ratios = caps.get("aspect_ratios", [])
    if ratios:
        buttons = [
            InlineKeyboardButton(text=r, callback_data=f"img_ratio:{r}")
            for r in ratios
        ]
        builder.row(*buttons[:3])
        if len(buttons) > 3:
            builder.row(*buttons[3:])
    builder.row(InlineKeyboardButton(text="← Назад", callback_data=f"img_back:mode:{model_key}"))
    return builder.as_markup()


def image_count_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 изображение", callback_data="img_count:1"),
        InlineKeyboardButton(text="2 изображения", callback_data="img_count:2"),
    )
    builder.row(
        InlineKeyboardButton(text="4 изображения", callback_data="img_count:4"),
    )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="img_back:ratio"))
    return builder.as_markup()


# ── Video keyboards ───────────────────────────────────────────────────────────

def video_models_kb(model_costs: list[ModelCost]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mc in model_costs:
        if mc.gen_type.value == "video":
            builder.row(
                InlineKeyboardButton(
                    text=f"{mc.display_name} — {mc.credits} кр",
                    callback_data=f"vid_model:{mc.model_key}",
                )
            )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


def video_mode_kb(model_key: str) -> InlineKeyboardMarkup:
    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    builder = InlineKeyboardBuilder()
    if "text" in modes:
        builder.row(
            InlineKeyboardButton(text="✍️ Текст → Видео", callback_data=f"vid_mode:text:{model_key}"),
        )
    if "image" in modes:
        builder.row(
            InlineKeyboardButton(text="🖼️ Фото → Видео", callback_data=f"vid_mode:image:{model_key}"),
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:video"))
    return builder.as_markup()


def video_params_kb(model_key: str, dur: int | None, ratio: str | None, res: str | None) -> InlineKeyboardMarkup:
    """Dynamic params keyboard for a specific model."""
    caps = VIDEO_CAPS.get(model_key, {})
    builder = InlineKeyboardBuilder()

    duration_options = caps.get("duration_options", [])
    if duration_options:
        dur_buttons = []
        for d in duration_options:
            mark = "✅ " if dur == d else ""
            dur_buttons.append(
                InlineKeyboardButton(text=f"{mark}{d} сек", callback_data=f"vpar_dur:{d}")
            )
        builder.row(*dur_buttons[:4])
        if len(dur_buttons) > 4:
            builder.row(*dur_buttons[4:])

    aspect_ratios = caps.get("aspect_ratios", [])
    if aspect_ratios:
        ratio_buttons = []
        for r in aspect_ratios:
            mark = "✅ " if ratio == r else ""
            ratio_buttons.append(
                InlineKeyboardButton(text=f"{mark}{r}", callback_data=f"vpar_ratio:{r}")
            )
        builder.row(*ratio_buttons[:3])
        if len(ratio_buttons) > 3:
            builder.row(*ratio_buttons[3:])

    resolutions = caps.get("resolutions", [])
    if resolutions:
        res_buttons = [
            InlineKeyboardButton(
                text=f"{'✅ ' if res == r else ''}{r}",
                callback_data=f"vpar_res:{r}"
            )
            for r in resolutions
        ]
        builder.row(*res_buttons)

    builder.row(
        InlineKeyboardButton(text="▶️ Далее: Промпт", callback_data="vpar_next"),
    )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="vpar_back"))
    return builder.as_markup()


def motion_control_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for direction in MotionDirection:
        builder.button(
            text=direction.label(),
            callback_data=f"motion:{direction.value}",
        )
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:video"))
    return builder.as_markup()


def after_generation_kb(gen_id: int, gen_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"regen:{gen_type}:{gen_id}"),
        InlineKeyboardButton(text="✏️ Изменить промпт", callback_data=f"reprompt:{gen_type}:{gen_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data=f"reparams:{gen_type}:{gen_id}"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()
