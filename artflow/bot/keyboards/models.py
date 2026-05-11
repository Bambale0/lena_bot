# bot/keyboards/models.py
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from api.image_service import MODEL_ASPECT_RATIOS, ImageModel
from api.video_service import MotionDirection, VideoModel
from db.models import ModelCost

# ── Video capabilities ────────────────────────────────────────────────────────

DEFAULT_MOTION_CONTROLS = ["auto", "pan_left", "pan_right", "zoom_in", "zoom_out", "orbit", "dolly_in", "dolly_out", "handheld", "cinematic"]

VIDEO_CAPS: dict[str, dict] = {
    "kling-2.6/text-to-video": {
        "modes": ["text"],
        "duration_options": [5, 10],
        "aspect_ratios": ["1:1", "16:9", "9:16"],
        "has_resolution": False,
        "billing_mode": "per_second",
    },
    "kling-2.6/image-to-video": {
        "modes": ["image"],
        "duration_options": [5, 10],
        "aspect_ratios": [],
        "has_resolution": False,
        "billing_mode": "per_second",
    },
    "kling-2.6/motion-control": {
        "modes": ["motion"],
        "duration_options": [],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
        "billing_mode": "per_second",
    },
    "kling-3.0/video": {
        "modes": ["text", "image"],
        "duration_options": [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "has_resolution": True,
        "resolutions": ["std", "pro", "4K"],
        "resolution_labels": {"std": "std · 720p", "pro": "pro · 1080p", "4K": "4K · 2160p"},
        "billing_mode": "per_second",
    },
    "kling-3.0/motion-control": {
        "modes": ["motion"],
        "duration_options": [],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["std", "pro", "4K"],
        "resolution_labels": {"std": "std · 720p", "pro": "pro · 1080p", "4K": "4K · 2160p"},
        "billing_mode": "per_second",
    },
    "wan/2-7-text-to-video": {
        "modes": ["text"],
        "duration_options": [2, 3, 5, 8, 10, 12, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    "wan/2-7-image-to-video": {
        "modes": ["image"],
        "duration_options": [2, 3, 5, 8, 10, 12, 15],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    "bytedance/seedance-2": {
        "modes": ["text", "image"],
        "duration_options": [3, 5, 8, 10, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"],
        "has_resolution": True,
        "resolutions": ["480p", "720p", "1080p"],
    },
    "bytedance/seedance-2-fast": {
        "modes": ["text", "image"],
        "duration_options": [3, 5, 8, 10, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"],
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
    },
    "grok-imagine/text-to-video": {
        "modes": ["text"],
        "duration_options": [6, 10, 15, 20, 30],
        "aspect_ratios": ["2:3", "3:2", "1:1", "16:9", "9:16"],
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
        "mode_options": ["fun", "normal", "spicy"],
    },
    "grok-imagine/image-to-video": {
        "modes": ["image"],
        "duration_options": [6, 10, 15, 20, 30],
        "aspect_ratios": ["2:3", "3:2", "1:1", "16:9", "9:16"],
        "has_resolution": True,
        "resolutions": ["480p", "720p"],
        "mode_options": ["fun", "normal"],
    },
    "happyhorse/text-to-video": {
        "modes": ["text"],
        "duration_options": [3, 5, 8, 10, 12, 15],
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    "happyhorse/image-to-video": {
        "modes": ["image"],
        "duration_options": [3, 5, 8, 10, 12, 15],
        "aspect_ratios": [],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    "veo3_fast": {
        "modes": ["text", "image"],
        "duration_options": [5, 10, 15],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    "veo3": {
        "modes": ["text", "image"],
        "duration_options": [5, 10, 15],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
    "veo3_lite": {
        "modes": ["text", "image"],
        "duration_options": [5, 10, 15],
        "aspect_ratios": ["16:9", "9:16"],
        "has_resolution": True,
        "resolutions": ["720p", "1080p"],
    },
}

# ── Image capabilities ────────────────────────────────────────────────────────

IMAGE_CAPS: dict[str, dict] = {
    ImageModel.SEEDREAM_45: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.SEEDREAM_45, []),
        "aspect_ratio_modes": ["text"],
        "counts": [1],
        "has_quality": True,
        "quality_options": [("basic", "🔷 2K"), ("high", "💎 4K")],
    },
    ImageModel.SEEDREAM_45_EDIT: {
        "modes": ["image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.SEEDREAM_45_EDIT, []),
        "aspect_ratio_modes": ["image"],
        "counts": [1],
        "has_quality": True,
        "quality_options": [("basic", "🔷 2K"), ("high", "💎 4K")],
        "max_refs": 3,
    },
    ImageModel.GROK_T2I: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.GROK_T2I, []),
        "aspect_ratio_modes": ["text"],
        "counts": [1],
    },
    ImageModel.GROK_I2I: {
        "modes": ["image"],
        "aspect_ratios": [],
        "aspect_ratio_modes": [],
        "counts": [1],
        "max_refs": 1,
    },
    ImageModel.WAN_27_PRO: {
        "modes": ["text", "image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.WAN_27_PRO, []),
        "aspect_ratio_modes": ["text"],
        "counts": [1, 2, 4, 6],
        "has_quality": True,
        "quality_options": [("1K", "1K"), ("2K", "2K"), ("4K", "4K")],
        "max_refs": 4,
    },
    ImageModel.NANO_BANANA: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA, []),
        "aspect_ratio_modes": ["text"],
        "counts": [1],
    },
    ImageModel.NANO_BANANA_2: {
        "modes": ["text", "image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA_2, []),
        "aspect_ratio_modes": ["text", "image"],
        "counts": [1],
        "has_quality": True,
        "quality_options": [("2K", "2K"), ("4K", "4K")],
        "max_refs": 4,
    },
    ImageModel.NANO_BANANA_PRO: {
        "modes": ["text", "image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.NANO_BANANA_PRO, []),
        "aspect_ratio_modes": ["text", "image"],
        "counts": [1],
        "has_quality": True,
        "quality_options": [("2K", "2K"), ("4K", "4K")],
        "max_refs": 4,
    },
    ImageModel.QWEN_T2I: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.QWEN_T2I, []),
        "aspect_ratio_modes": ["text"],
        "counts": [1],
    },
    ImageModel.QWEN_I2I: {
        "modes": ["image"],
        "aspect_ratios": [],
        "aspect_ratio_modes": [],
        "counts": [1],
        "max_refs": 1,
    },
    ImageModel.QWEN_EDIT: {
        "modes": ["image"],
        "aspect_ratios": [],
        "aspect_ratio_modes": [],
        "counts": [1],
        "max_refs": 1,
    },
    ImageModel.QWEN2_T2I: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.QWEN2_T2I, []),
        "aspect_ratio_modes": ["text"],
        "counts": [1],
    },
    ImageModel.QWEN2_EDIT: {
        "modes": ["image"],
        "aspect_ratios": [],
        "aspect_ratio_modes": [],
        "counts": [1],
        "max_refs": 1,
    },
    ImageModel.GPT_IMAGE_2_T2I: {
        "modes": ["text"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.GPT_IMAGE_2_T2I, []),
        "aspect_ratio_modes": ["text"],
        "counts": [1],
        "quality_options": [("2K", "🔷 2K (стандарт)"), ("4K", "💎 4K (высокое)")],
        "has_quality": True,
    },
    ImageModel.GPT_IMAGE_2_I2I: {
        "modes": ["image"],
        "aspect_ratios": MODEL_ASPECT_RATIOS.get(ImageModel.GPT_IMAGE_2_I2I, []),
        "aspect_ratio_modes": ["image"],
        "counts": [1],
        "max_refs": 1,
        "quality_options": [("2K", "🔷 2K (стандарт)"), ("4K", "💎 4K (высокое)")],
        "has_quality": True,
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
    "openrouter/free": "🆓 OpenRouter Free · универсальная модель",
    ImageModel.QWEN_T2I:  "🟣 Qwen T2I · реалистично · детали · текст→изображение",
    ImageModel.QWEN_I2I:  "🟣 Qwen I2I · трансформация по референсу",
    ImageModel.QWEN_EDIT: "🟣 Qwen Edit · редактирование по референсу",
    ImageModel.QWEN2_T2I: "🟣 Qwen2 T2I · улучшенная генерация · v2",
    ImageModel.QWEN2_EDIT:"🟣 Qwen2 Edit · продвинутое редактирование · v2",
    ImageModel.GPT_IMAGE_2_T2I:  "🤖 GPT Image 2 · T2I · высокое качество",
    ImageModel.GPT_IMAGE_2_I2I:  "🤖 GPT Image 2 · I2I · трансформация по референсу",
}

HIDDEN_IMAGE_MODELS = {
    ImageModel.NANO_BANANA,
}

IMAGE_SCENARIOS: dict[str, dict[str, str]] = {
    "fast": {
        "title": "⚡ Быстрый старт",
        "description": "Текст → изображение. Быстро создать картинку по описанию",
        "model": ImageModel.NANO_BANANA_PRO,
        "mode": "text",
    },
    "edit": {
        "title": "🖼️ Из фото в новую версию",
        "description": "Фото → изображение. Ремикс, правки, стилизация по референсу",
        "model": ImageModel.NANO_BANANA_2,
        "mode": "image",
    },
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
    """Put the preferred aspect ratio first without dropping the rest."""
    return ([preferred] if preferred in ratios else []) + [r for r in ratios if r != preferred]


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
    # Kling 3.0 and Veo are listed above but also appear in i2v group
]

_VIDEO_GROUPS: list[tuple[str, list[str]]] = [
    (
        "fast",
        [
            VideoModel.KLING_30,
            VideoModel.VEO_3_LITE,
            VideoModel.SEEDANCE_2_FAST,
            VideoModel.HAPPYHORSE_T2V,
            VideoModel.VEO_3,
            VideoModel.VEO_3_FAST,
            VideoModel.SEEDANCE_2,
            VideoModel.WAN_27_T2V,
            VideoModel.GROK_T2V,
            VideoModel.KLING_26_T2V,
        ],
    ),
    (
        "i2v",
        [
            VideoModel.KLING_30,
            VideoModel.VEO_3,
            VideoModel.VEO_3_FAST,
            VideoModel.VEO_3_LITE,
            VideoModel.KLING_26_I2V,
            VideoModel.WAN_27_I2V,
            VideoModel.GROK_I2V,
            VideoModel.HAPPYHORSE_I2V,
            VideoModel.SEEDANCE_2,
            VideoModel.SEEDANCE_2_FAST,
        ],
    ),
    (
        "motion",
        [
            VideoModel.KLING_26_MOTION,
            VideoModel.KLING_30_MOTION,
        ],
    ),
]

VIDEO_GROUP_TITLES: dict[str, str] = {
    "fast": "⚡ Быстрый старт",
    "i2v": "🖼️ Из изображения в видео",
    "motion": "🕺 Управление камерой",
}


# Per-second rates for Kling models (cheapest resolution first)
_KLING_PER_SEC: dict[str, dict[str, int]] = {
    "kling-2.6/text-to-video":    {"720p": 5, "1080p": 7},
    "kling-2.6/image-to-video":    {"720p": 6, "1080p": 8},
    "kling-2.6/motion-control": {"720p": 7, "1080p": 9},
    "kling-3.0/video":        {"2K": 8, "4K": 10},
    "kling-3.0/motion-control": {"2K": 9, "4K": 11},
}
_KLING_BASE_RATE: dict[str, int] = {k: min(v.values()) for k, v in _KLING_PER_SEC.items()}


def _model_button(mc: ModelCost, prefix: str) -> InlineKeyboardButton:
    base_rate = _KLING_BASE_RATE.get(mc.model_key)
    price_txt = f"от {base_rate} 💋/сек" if base_rate else f"{mc.credits} 💋"
    return InlineKeyboardButton(
        text=f"{mc.display_name} · {price_txt}",
        callback_data=f"{prefix}:{mc.model_key}",
    )


def _sorted_models(model_costs: list[ModelCost], allowed_keys: list[str]) -> list[ModelCost]:
    order = {key: idx for idx, key in enumerate(allowed_keys)}
    filtered = [mc for mc in model_costs if mc.model_key in order]
    return sorted(filtered, key=lambda mc: order[mc.model_key])


# ── Image keyboards ───────────────────────────────────────────────────────────

def image_models_kb(model_costs: list[ModelCost]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mc in model_costs:
        if (
            mc.gen_type.value == "image"
            and mc.model_key in IMAGE_CAPS
            and mc.model_key not in HIDDEN_IMAGE_MODELS
        ):
            label = f"{mc.display_name} · {mc.credits} 💋"
            builder.row(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"img_model:{mc.model_key}",
                )
            )
    builder.row(InlineKeyboardButton(text="← К сценариям", callback_data="menu:image"))
    return builder.as_markup()


def image_scenarios_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for scenario_key in ("fast", "edit"):
        scenario = IMAGE_SCENARIOS[scenario_key]
        builder.row(
            InlineKeyboardButton(
                text=scenario["title"],
                callback_data=f"img_scn:{scenario_key}",
            )
        )
    builder.row(InlineKeyboardButton(text="🧠 Все модели", callback_data="img_menu:advanced"))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


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


def image_count_kb(model_key: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    counts = IMAGE_CAPS.get(model_key, {}).get("counts", [1, 2, 4]) if model_key else [1, 2, 4]
    buttons = [
        InlineKeyboardButton(text=f"{count} изображение" if count == 1 else f"{count} изображения", callback_data=f"img_count:{count}")
        for count in counts
    ]
    for i in range(0, len(buttons), 2):
        builder.row(*buttons[i:i + 2])
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="img_back:ratio"))
    return builder.as_markup()


def image_quality_kb(model_key: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    options = IMAGE_CAPS.get(model_key, {}).get(
        "quality_options",
        [("basic", "🔷 2K (стандарт)"), ("high", "💎 4K (высокое)")],
    )
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"img_quality:{value}")
        for value, label in options
    ]
    for i in range(0, len(buttons), 2):
        builder.row(*buttons[i:i + 2])
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="img_back:ratio"))
    return builder.as_markup()


def image_active_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✨ Ремикс", callback_data="img_remix"),
        InlineKeyboardButton(text="🔁 Ещё вариант", callback_data="img_variation"),
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="img_settings"),
    )
    builder.row(
        InlineKeyboardButton(text="🆕 Новая серия", callback_data="img_new"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def image_session_kb(gen_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    remix_cb = f"img_session:remix:{gen_id}" if gen_id else "img_remix"
    repeat_cb = f"img_session:repeat:{gen_id}" if gen_id else "img_variation"
    builder.row(
        InlineKeyboardButton(text="✨ Ремикс", callback_data=remix_cb),
        InlineKeyboardButton(text="🔁 Ещё вариант", callback_data=repeat_cb),
    )
    if gen_id:
        builder.row(
            InlineKeyboardButton(text="🎬 Оживить", callback_data=f"img_session:animate:{gen_id}"),
        )
        builder.row(
            InlineKeyboardButton(text="📤 В ленту", callback_data=f"gen:share:{gen_id}"),
            InlineKeyboardButton(text="📚 В библиотеку", callback_data=f"gen:library:{gen_id}"),
        )
    builder.row(
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="img_settings"),
    )
    builder.row(
        InlineKeyboardButton(text="🆕 Новая серия", callback_data="img_new"),
    )
    builder.row(
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def image_session_settings_kb(
    image_session_id: int,
    model_key: str | None = None,
    mode: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    caps = IMAGE_CAPS.get(model_key, {}) if model_key else {}
    modes_with_ratio = caps.get("aspect_ratio_modes", caps.get("modes", []))
    has_ratio = bool(caps.get("aspect_ratios")) and (not mode or mode in modes_with_ratio)
    has_quality = bool(caps.get("has_quality")) if model_key else True
    has_count = len(caps.get("counts", [1])) > 1 if model_key else True

    setting_buttons: list[InlineKeyboardButton] = []
    if has_ratio:
        setting_buttons.append(
            InlineKeyboardButton(text="📐 Формат", callback_data=f"img_sset:ratio:{image_session_id}")
        )
    if has_quality:
        setting_buttons.append(
            InlineKeyboardButton(text="💎 Качество", callback_data=f"img_sset:quality:{image_session_id}")
        )
    if has_count:
        setting_buttons.append(
            InlineKeyboardButton(text="🔢 Количество", callback_data=f"img_sset:count:{image_session_id}")
        )

    for i in range(0, len(setting_buttons), 2):
        builder.row(*setting_buttons[i:i + 2])
    builder.row(InlineKeyboardButton(text="🔁 Сменить модель", callback_data=f"img_sset:model:{image_session_id}"))
    builder.row(
        InlineKeyboardButton(text="← К серии", callback_data=f"img_sset:back:{image_session_id}")
    )
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


def video_models_kb(
    model_costs: list[ModelCost],
    group_key: str | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    supported_video_keys = set(VIDEO_CAPS.keys())
    if group_key:
        keys = dict(_VIDEO_GROUPS).get(group_key, [])
        for mc in _sorted_models([mc for mc in model_costs if mc.model_key in supported_video_keys], keys):
            builder.row(_model_button(mc, "vid_model"))
        builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:video"))
        return builder.as_markup()

    ordered = _sorted_models(
        [mc for mc in model_costs if mc.gen_type.value == "video" and mc.model_key in supported_video_keys],
        _VIDEO_MODEL_ORDER,
    )
    remaining = [
        mc
        for mc in model_costs
        if mc.gen_type.value == "video"
        and mc.model_key in supported_video_keys
        and mc.model_key not in {m.model_key for m in ordered}
    ]
    for mc in ordered + remaining:
        builder.row(_model_button(mc, "vid_model"))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="menu:main"))
    return builder.as_markup()


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
    mode: str | None = None,
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

    mode_options = caps.get("mode_options", [])
    if mode_options:
        mode_buttons = [
            InlineKeyboardButton(
                text=f"{'✅ ' if mode == opt else ''}{opt}",
                callback_data=f"vpar_mode:{opt}",
            )
            for opt in mode_options
        ]
        builder.row(*mode_buttons)

    kling_rates = _KLING_PER_SEC.get(model_key, {})
    if kling_rates and dur and res and res in kling_rates:
        rate = kling_rates[res]
        next_text = f"▶️ Далее · {dur} сек × {rate} = {dur * rate} 💋"
    elif kling_rates and dur:
        rate = min(kling_rates.values())
        next_text = f"▶️ Далее · {dur} сек × от {rate} = от {dur * rate} 💋"
    else:
        next_text = "▶️ Далее: Промпт"

    builder.row(InlineKeyboardButton(text=next_text, callback_data="vpar_next"))
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


def reference_upload_kb(
    back_cb: str = "menu:main",
    *,
    allow_skip: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if allow_skip:
        builder.row(InlineKeyboardButton(text="⏭ Пропустить (без референса)", callback_data="ref:skip"))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data=back_cb))
    return builder.as_markup()


def multi_ref_kb(
    uploaded: int,
    max_refs: int,
    *,
    allow_skip: bool = False,
) -> InlineKeyboardMarkup:
    """Shown after each reference upload when model supports multiple refs."""
    builder = InlineKeyboardBuilder()
    if uploaded < max_refs:
        builder.row(InlineKeyboardButton(
            text=f"📸 Добавить ещё ({uploaded}/{max_refs})",
            callback_data="ref:add_more",
        ))
    builder.row(InlineKeyboardButton(
        text=f"✅ Готово ({uploaded} фото)",
        callback_data="ref:done_multi",
    ))
    if allow_skip and uploaded == 0:
        builder.row(InlineKeyboardButton(text="⏭ Без референса", callback_data="ref:skip"))
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
    builder.row(
        InlineKeyboardButton(text="📤 В ленту", callback_data=f"gen:share:{gen_id}"),
        InlineKeyboardButton(text="📚 В библиотеку", callback_data=f"gen:library:{gen_id}"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


# ── Dynamic model settings keyboards ──────────────────────────────────────────

def get_image_capabilities(model_key: str) -> dict:
    caps = dict(IMAGE_CAPS.get(model_key, {}))
    caps.setdefault("modes", ["text"])
    caps.setdefault("aspect_ratios", [])
    caps.setdefault("aspect_ratio_modes", caps.get("modes", []))
    caps.setdefault("quality_options", [])
    caps.setdefault("counts", [1])
    caps.setdefault("has_quality", bool(caps.get("quality_options")))
    caps.setdefault("supports_reference", "image" in caps.get("modes", []) or bool(caps.get("max_refs")))
    caps.setdefault("supports_prompt_enhance", True)
    return caps


def image_available_settings(model_key: str, mode: str | None = None) -> list[str]:
    caps = get_image_capabilities(model_key)
    settings: list[str] = []

    modes = caps.get("modes") or ["text"]
    selected_mode = mode or modes[0]
    ratio_modes = caps.get("aspect_ratio_modes") or modes

    if len(modes) > 1:
        settings.append("mode")

    if caps.get("supports_reference") and selected_mode == "image":
        settings.append("reference")

    if caps.get("aspect_ratios") and selected_mode in ratio_modes:
        settings.append("aspect_ratio")

    if caps.get("has_quality") and caps.get("quality_options"):
        settings.append("quality")

    if len(caps.get("counts") or [1]) > 1:
        settings.append("count")

    if caps.get("supports_prompt_enhance", True):
        settings.append("prompt_enhance")

    return settings


def image_dynamic_settings_kb(model_key: str, mode: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    settings = image_available_settings(model_key, mode)

    if "mode" in settings:
        builder.button(text="🔀 Режим", callback_data=f"img_dyn:mode:{model_key}")

    if "reference" in settings:
        builder.button(text="🖼 Референс", callback_data=f"img_dyn:reference:{model_key}")

    if "aspect_ratio" in settings:
        builder.button(text="📐 Формат", callback_data=f"img_dyn:ratio:{model_key}")

    if "quality" in settings:
        builder.button(text="💎 Качество", callback_data=f"img_dyn:quality:{model_key}")

    if "count" in settings:
        builder.button(text="🔢 Количество", callback_data=f"img_dyn:count:{model_key}")

    if "prompt_enhance" in settings:
        builder.button(text="✨ Улучшить промпт", callback_data=f"img_dyn:enhance:{model_key}")

    builder.button(text="✅ Продолжить", callback_data=f"img_dyn:continue:{model_key}")
    builder.button(text="← Назад", callback_data="img_menu:advanced")
    builder.adjust(2, 2, 2, 1, 1)
    return builder.as_markup()
