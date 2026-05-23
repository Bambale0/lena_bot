from __future__ import annotations

import json

from bot.keyboards.models import (
    IMAGE_SCENARIOS,
    image_active_kb,
    image_models_kb,
    image_scenarios_kb,
)
from bot.ui.common import ScreenRender
from db.models import ImageSession, ModelCost

_IMAGE_MODEL_LABELS = {
    "grok-imagine/text-to-image": "Grok Imagine",
    "grok-imagine/image-to-image": "Grok Imagine Edit",
    "qwen/text-to-image": "Qwen",
    "qwen/image-to-image": "Qwen Edit",
    "qwen/image-edit": "Qwen Edit Pro",
    "qwen2/text-to-image": "Qwen2",
    "qwen2/image-edit": "Qwen2 Edit",
    "seedream/4.5-text-to-image": "Seedream 4.5",
    "seedream/4.5-edit": "Seedream 4.5 Edit",
    "wan/2-7-image": "WAN 2.7",
    "wan/2-7-image-pro": "WAN 2.7 Pro",
    "gpt-image-2-text-to-image": "GPT Image 2",
    "gpt-image-2-image-to-image": "GPT Image 2 Edit",
    "google/nano-banana": "Nano Banana",
    "nano-banana-pro": "Nano Banana Pro",
    "nano-banana-2": "Nano Banana 2",
}


def _pretty_image_model(model_key: str) -> str:
    return _IMAGE_MODEL_LABELS.get(model_key, model_key.replace('-', ' ').replace('/', ' · ').title())


def _pretty_ratio(value: str | None) -> str:
    if not value or value in {"default", "auto"}:
        return "Авто"
    return value


def _pretty_quality(value: str | None) -> str:
    if not value or value == "basic":
        return "Стандарт"
    if value == "high":
        return "Высокое"
    return value.upper() if value.lower() in {"1k", "2k", "4k"} else value


def render_image_scenarios() -> ScreenRender:
    scenario_lines = "\n".join(
        f"{scenario['title']} — {scenario['description']}"
        for scenario in (
            IMAGE_SCENARIOS["fast"],
            IMAGE_SCENARIOS["edit"],
        )
    )

    text = (
        "🎨 <b>Изображения</b>\n\n"
        "Выбери сценарий. Полный ручной контроль — во вкладке <b>Все нейросети</b>.\n\n"
        f"{scenario_lines}"
    )
    return ScreenRender(text=text, reply_markup=image_scenarios_kb())


def render_image_advanced_menu(model_costs: list[ModelCost]) -> ScreenRender:
    text = (
        "🧠 <b>Все нейросети изображений</b>\n\n"
        "Ручной режим: модель, формат, качество, количество и референсы.\n"
        "Доступные кнопки зависят от возможностей выбранной модели."
    )
    return ScreenRender(text=text, reply_markup=image_models_kb(model_costs))


def render_active_image_session(image_session: ImageSession) -> ScreenRender:
    ratio = _pretty_ratio(image_session.aspect_ratio)
    count = image_session.count or 1

    reference_count = 0
    if image_session.reference_file_ids:
        try:
            reference_count = len([item for item in json.loads(image_session.reference_file_ids) if item])
        except (TypeError, ValueError):
            reference_count = 0

    if reference_count == 0 and (image_session.reference_url or image_session.reference_file_id):
        reference_count = 1

    reference_label = f"{reference_count} шт" if reference_count else "нет"
    model_label = _pretty_image_model(image_session.model)
    quality_label = _pretty_quality(image_session.quality)
    count_label = f"{count} фото" if count > 1 else "1 фото"

    text = (
        "🎨 <b>Активная серия</b>\n\n"
        f"🍌 <b>{model_label}</b>\n"
        f"📐 {ratio} · {quality_label} · {count_label}\n"
        f"📎 Референс: <b>{reference_label}</b>\n\n"
        "Отправь новый текст или фото — я продолжу серию в том же стиле."
    )
    return ScreenRender(
        text=text,
        reply_markup=image_active_kb(),
    )
