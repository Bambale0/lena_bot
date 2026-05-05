# bot/keyboards/models.py
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.image_service import ImageModel, MODEL_ASPECT_RATIOS, _SUPPORTS_IMG2IMG
from api.video_service import MotionDirection, VideoModel
from db.models import ModelCost

# ── Video capabilities ────────────────────────────────────────────────────────

VIDEO_CAPS: dict[str, dict] = {
    VideoModel.KLING_26_T2V: {
        "modes": ["text"],
        "duration_options": [5, 10],
        "aspect_ratios": ["1:1", "16:9", "9:16"],
        "has_resolution": False,
    },
    VideoModel.KLING_26_I2V: {
        "modes": ["image"],
        "duration_options": [5, 10],
        "aspect_ratios": [],
        "has_resolution": False,
    },
    VideoModel.KLING_26_MOTION: {
        "modes": ["motion"],
        "duration_options": [],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    VideoModel.KLING_30: {
        "modes": ["text", "image"],
        "duration_options": [5, 10],
        "aspect_ratios": [],
        "has_resolution": False,
    },
    VideoModel.KLING_30_MOTION: {
        "modes": ["motion"],
        "duration_options": [],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    VideoModel.WAN_27_T2V: {
        "modes": ["text"],
        "duration_options": [3, 5, 10, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    VideoModel.WAN_27_I2V: {
        "modes": ["image"],
        "duration_options": [3, 5, 10, 15],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    VideoModel.SEEDANCE_2: {
        "modes": ["text", "image"],
        "duration_options": [3, 5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "has_resolution": True,
        "resolutions": ["480p", "720p", "1080p"],
    },
    VideoModel.SEEDANCE_2_FAST: {
        "modes": ["text", "image"],
        "duration_options": [3, 5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
    },
    VideoModel.GROK_T2V: {
        "modes": ["text"],
        "duration_options": [6, 10],
        "aspect_ratios": ["16:9", "1:1", "9:16"],
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
    },
    VideoModel.GROK_I2V: {
        "modes": ["image"],
        "duration_options": [],
        "aspect_ratios": ["16:9", "1:1", "9:16"],
        "has_resolution": False,
    },
    VideoModel.HAPPYHORSE_T2V: {
        "modes": ["text"],
        "duration_options": [3, 5, 8, 10, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    VideoModel.HAPPYHORSE_I2V: {
        "modes": ["image"],
        "duration_options": [3, 5, 8, 10, 15],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    VideoModel.VEO_3_FAST: {
        "modes": ["text", "image"],
        "duration_options": [],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": False,
    },
    VideoModel.VEO_3: {
        "modes": ["text", "image"],
        "duration_options": [],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": False,
    },
    VideoModel.VEO_3_LITE: {
        "modes": ["text", "image"],
        "duration_options": [],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": False,
    },
}

# ── Image capabilities ────────────────────────────────────────────────────────

IMAGE_CAPS: dict[str, dict] = {
    ImageModel.SEEDREAM_45: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.SEEDREAM_45, []),
        "counts": [1],
        "has_quality": True,
    },
    ImageModel.SEEDREAM_45_EDIT: {
        "modes": ["image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.SEEDREAM_45_EDIT, []),
        "counts": [1],
        "has_quality": True,
    },
    ImageModel.GROK_T2I: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.GROK_T2I, []),
        "counts": [1],
    },
    ImageModel.GROK_I2I: {
        "modes": ["image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.GROK_I2I, []),
        "counts": [1],
    },
    ImageModel.WAN_27_PRO: {
        "modes": ["text", "image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.WAN_27_PRO, []),
        "counts": [1, 2, 4],
    },
    ImageModel.NANO_BANANA: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA, []),
        "counts": [1],
    },
    ImageModel.NANO_BANANA_2: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA_2, []),
        "counts": [1],
    },
    ImageModel.NANO_BANANA_PRO: {
        "modes": ["text", "image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA_PRO, []),
        "counts": [1],
    },
}

# ── Model descriptions ────────────────────────────────────────────────────────

IMAGE_MODEL_DESC: dict[str, str] = {
    "seedream-4.5":    "🌟 Топ качество · реализм · детали · медленнее",
    "nano-banano-pro": "⚡ Gemini Pro · точное следование промпту · img2img",
    "nano-banano-2":   "🚀 Gemini Flash · быстро · стиль · иллюстрации",
    "wan-2.7":         "🎭 WAN · кино-стиль · персонажи · фэнтези",
    "wan-2.7-pro":     "💎 WAN Pro · kie.ai · высокое разрешение · async",
    "gpt-image-1":     "🤖 GPT Image · понимает сложные описания · творчество",
}

VIDEO_MODEL_DESC: dict[str, str] = {
    "kling-3.0":               "🎬 Kling 3.0 · плавное движение · text & img2video",
    "kling-2.6-motion":        "🎥 Kling Motion · управление камерой (pan/zoom/tilt)",
    "grok-video":              "⚡ Grok · быстрая генерация · реализм",
    "grok-imagine-video":      "✨ Grok Imagine · творческие сцены",
    "doubao-seedance-2-0":     "🌊 Seedance 2.0 · плавная анимация · текст→видео",
    "veo3.1-pro":              "🏆 Veo 3.1 Pro · Google · высшее качество · img2video",
    "happyhorse-1.0-text-to-video":  "🐎 HappyHorse · text2video · быстро",
    "happyhorse-1.0-image-to-video": "🐎 HappyHorse · img2video · анимация фото",
}



def _prioritize_ratio(ratios: list[str], preferred: str = "9:16") -> list[str]:
    """Put the most important aspect ratio first without dropping options."""
    return ([preferred] if preferred in ratios else []) + [r for r in ratios if r != preferred]


_IMAGE_MODEL_ORDER: list[str] = [
    ImageModel.NANO_BANANA_2,
    ImageModel.NANO_BANANA_PRO,
    ImageModel.NANO_BANANA,
    ImageModel.SEEDREAM_45,
    ImageModel.SEEDREAM_45_EDIT,
    ImageModel.WAN_27_PRO,
    ImageModel.GROK_T2I,
    ImageModel.GROK_I2I,
]

_VIDEO_MODEL_ORDER: list[str] = [
    VideoModel.KLING_30,
    VideoModel.VEO_3_LITE,
    VideoModel.SEEDANCE_2_FAST,
    VideoModel.HAPPYHORSE_T2V,
    VideoModel.VEO_3,
    VideoModel.VEO_3_FAST,
    VideoModel.SEEDANCE_2,
    VideoModel.WAN_27_T2V,
    VideoModel.GROK_T2V,
    VideoModel.KLING_26_I2V,
    VideoModel.WAN_27_I2V,
    VideoModel.GROK_I2V,
    VideoModel.HAPPYHORSE_I2V,
    VideoModel.KLING_26_MOTION,
    VideoModel.KLING_30_MOTION,
    VideoModel.KLING_26_T2V,
]

_IMAGE_GROUPS: list[tuple[str, list[str]]] = [
    ("fast", [
        ImageModel.NANO_BANANA_2,
        ImageModel.NANO_BANANA,
        ImageModel.GROK_T2I,
        ImageModel.SEEDREAM_45,
    ]),
    ("edit", [
        ImageModel.NANO_BANANA_PRO,
        ImageModel.SEEDREAM_45_EDIT,
        ImageModel.GROK_I2I,
        ImageModel.WAN_27_PRO,
    ]),
]

_VIDEO_GROUPS: list[tuple[str, list[str]]] = [
    ("fast", [
        VideoModel.KLING_30,
        VideoModel.VEO_3_LITE,
        VideoModel.SEEDANCE_2_FAST,
        VideoModel.HAPPYHORSE_T2V,
    ]),
    ("quality", [
        VideoModel.VEO_3,
        VideoModel.VEO_3_FAST,
        VideoModel.SEEDANCE_2,
        VideoModel.WAN_27_T2V,
        VideoModel.GROK_T2V,
        VideoModel.KLING_26_T2V,
    ]),
    ("i2v", [
        VideoModel.KLING_26_I2V,
        VideoModel.WAN_27_I2V,
        VideoModel.GROK_I2V,
        VideoModel.HAPPYHORSE_I2V,
    ]),
    ("motion", [
        VideoModel.KLING_26_MOTION,
        VideoModel.KLING_30_MOTION,
    ]),
]

IMAGE_GROUP_TITLES: dict[str, str] = {
    "fast": "⚡ Быстрый старт",
    "edit": "🎯 Референс и редактирование",
}

VIDEO_GROUP_TITLES: dict[str, str] = {
    "fast": "⚡ Быстрый старт",
    "quality": "🎬 Кино и качество",
    "i2v": "🖼️ Из изображения в видео",
    "motion": "🕺 Управление камерой",
}


def _model_button(mc: ModelCost, prefix: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=f"{mc.display_name} · {mc.credits} кр",
        callback_data=f"{prefix}:{mc.model_key}",
    )


def _sorted_models(model_costs: list[ModelCost], allowed_keys: list[str]) -> list[ModelCost]:
    order = {key: idx for idx, key in enumerate(allowed_keys)}
    filtered = [mc for mc in model_costs if mc.model_key in order]
    return sorted(filtered, key=lambda mc: order[mc.model_key])


def _build_model_list_kb(
    model_costs: list[ModelCost],
    keys: list[str],
    callback_prefix: str,
    back_callback: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mc in _sorted_models(model_costs, keys):
        builder.row(_model_button(mc, callback_prefix))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data=back_callback))
    return builder.as_markup()

# ── Image keyboards ───────────────────────────────────────────────────────────

def image_model_groups_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group_key, _ in _IMAGE_GROUPS:
        builder.row(
            InlineKeyboardButton(
                text=IMAGE_GROUP_TITLES[group_key],
                callback_data=f"img_group:{group_key}",
            )
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


def image_models_kb(model_costs: list[ModelCost], group_key: str) -> InlineKeyboardMarkup:
    keys = dict(_IMAGE_GROUPS).get(group_key, [])
    return _build_model_list_kb(
        model_costs=model_costs,
        keys=keys,
        callback_prefix="img_model",
        back_callback="menu:image",
    )


def image_model_info(model_key: str) -> str:
    """Returns description text for a model to show in the screen body."""
    return IMAGE_MODEL_DESC.get(model_key, "")


def image_mode_kb(model_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    if "text" in modes:
        builder.row(
            InlineKeyboardButton(text="✍️ Текст → Изображение", callback_data=f"img_mode:text:{model_key}"),
        )
    if "image" in modes:
        builder.row(
            InlineKeyboardButton(text="🖼️ Референс → Изображение", callback_data=f"img_mode:image:{model_key}"),
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:image"))
    return builder.as_markup()


def image_aspect_ratio_kb(model_key: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    caps = IMAGE_CAPS.get(model_key, {})
    ratios = _prioritize_ratio(caps.get("aspect_ratios", []))
    buttons = [
        InlineKeyboardButton(text=r, callback_data=f"img_ratio:{r}")
        for r in ratios
    ]
    for i in range(0, len(buttons), 3):
        builder.row(*buttons[i:i+3])
    builder.row(InlineKeyboardButton(text="← Назад", callback_data=f"img_back:mode:{model_key}"))
    return builder.as_markup()


def image_count_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 изображение", callback_data="img_count:1"),
        InlineKeyboardButton(text="2 изображения", callback_data="img_count:2"),
    )
    builder.row(InlineKeyboardButton(text="4 изображения", callback_data="img_count:4"))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="img_back:ratio"))
    return builder.as_markup()


def image_quality_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔷 2K (стандарт)", callback_data="img_quality:basic"),
        InlineKeyboardButton(text="💎 4K (высокое)", callback_data="img_quality:high"),
    )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="img_back:ratio"))
    return builder.as_markup()


# ── Video keyboards ───────────────────────────────────────────────────────────


def video_model_groups_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group_key, _ in _VIDEO_GROUPS:
        builder.row(
            InlineKeyboardButton(
                text=VIDEO_GROUP_TITLES[group_key],
                callback_data=f"vid_group:{group_key}",
            )
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


def video_models_kb(model_costs: list[ModelCost], group_key: str) -> InlineKeyboardMarkup:
    keys = dict(_VIDEO_GROUPS).get(group_key, [])
    return _build_model_list_kb(
        model_costs=model_costs,
        keys=keys,
        callback_prefix="vid_model",
        back_callback="menu:video",
    )


def video_model_info(model_key: str) -> str:
    return VIDEO_MODEL_DESC.get(model_key, "")


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
    if "motion" in modes:
        builder.row(
            InlineKeyboardButton(text="🕺 Motion Control", callback_data=f"vid_mode:motion:{model_key}"),
        )
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:video"))
    return builder.as_markup()


def video_params_kb(
    model_key: str,
    dur: int | None,
    ratio: str | None,
    res: str | None,
) -> InlineKeyboardMarkup:
    caps = VIDEO_CAPS.get(model_key, {})
    builder = InlineKeyboardBuilder()

    duration_options = caps.get("duration_options", [])
    if duration_options:
        dur_buttons = [
            InlineKeyboardButton(
                text=f"{'✅ ' if dur == d else ''}{d} сек",
                callback_data=f"vpar_dur:{d}",
            )
            for d in duration_options
        ]
        for i in range(0, len(dur_buttons), 4):
            builder.row(*dur_buttons[i:i+4])

    aspect_ratios = caps.get("aspect_ratios", [])
    if aspect_ratios:
        ratio_buttons = [
            InlineKeyboardButton(
                text=f"{'✅ ' if ratio == r else ''}{r}",
                callback_data=f"vpar_ratio:{r}",
            )
            for r in aspect_ratios
        ]
        for i in range(0, len(ratio_buttons), 3):
            builder.row(*ratio_buttons[i:i+3])

    resolutions = caps.get("resolutions", []) if caps.get("has_resolution") else []
    if resolutions:
        res_buttons = [
            InlineKeyboardButton(
                text=f"{'✅ ' if res == r else ''}{r}",
                callback_data=f"vpar_res:{r}",
            )
            for r in resolutions
        ]
        builder.row(*res_buttons)

    builder.row(InlineKeyboardButton(text="▶️ Далее: Промпт", callback_data="vpar_next"))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="vpar_back"))
    return builder.as_markup()


def motion_control_kb() -> InlineKeyboardMarkup:
    """Камера-управление для Kling 2.6 (legacy, не используется в motion-control flow)."""
    builder = InlineKeyboardBuilder()
    for direction in MotionDirection:
        builder.button(text=direction.label(), callback_data=f"motion:{direction.value}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:video"))
    return builder.as_markup()


def reference_upload_kb(back_cb: str = "menu:main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⏭ Пропустить (без референса)", callback_data="ref:skip"))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data=back_cb))
    return builder.as_markup()


def after_generation_kb(gen_id: int, gen_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"regen:{gen_type}:{gen_id}"),
        InlineKeyboardButton(text="✏️ Новый промпт", callback_data=f"reprompt:{gen_type}:{gen_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data=f"reparams:{gen_type}:{gen_id}"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()



def image_session_kb(gen_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    suffix = str(gen_id or 0)
    builder.row(
        InlineKeyboardButton(text="✨ Ремикс", callback_data=f"img_session:remix:{suffix}"),
        InlineKeyboardButton(text="🔁 Повторить", callback_data=f"img_session:repeat:{suffix}"),
    )
    builder.row(
        InlineKeyboardButton(text="🎬 Оживить", callback_data=f"img_session:animate:{suffix}"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="img_session:settings"),
    )
    builder.row(
        InlineKeyboardButton(text="🆕 Новая серия", callback_data="img_session:new"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu:main"),
    )
    return builder.as_markup()
