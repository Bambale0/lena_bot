from __future__ import annotations

import json

from db.models import ImageSession, ModelCost

from bot.keyboards.models import (
    IMAGE_SCENARIOS,
    image_active_kb,
    image_models_kb,
    image_scenarios_kb,
)
from bot.ui.common import ScreenRender


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
        "Выбери сценарий. Полный ручной контроль — во вкладке <b>Все модели</b>.\n\n"
        f"{scenario_lines}"
    )
    return ScreenRender(text=text, reply_markup=image_scenarios_kb())


def render_image_advanced_menu(model_costs: list[ModelCost]) -> ScreenRender:
    text = (
        "🧠 <b>Все модели изображений</b>\n\n"
        "Ручной режим: модель, формат, качество, количество и референсы.\n"
        "Доступные кнопки зависят от возможностей выбранной модели."
    )
    return ScreenRender(text=text, reply_markup=image_models_kb(model_costs))


def render_active_image_session(image_session: ImageSession) -> ScreenRender:
    ratio = image_session.aspect_ratio or "auto"
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
    model_label = image_session.model.replace("-", " ").title()
    count_label = f"{count} фото" if count > 1 else "1 фото"

    text = (
        "🎨 <b>Активная серия</b>\n\n"
        f"🍌 <b>{model_label}</b>\n"
        f"📐 {ratio} · {count_label}\n"
        f"📎 Референс: <b>{reference_label}</b>\n\n"
        "Отправь текст или фото — бот продолжит генерацию."
    )
    return ScreenRender(
        text=text,
        reply_markup=image_active_kb(),
    )
