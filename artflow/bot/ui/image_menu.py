from __future__ import annotations

from db.models import ImageSession, ModelCost

from bot.keyboards.models import IMAGE_SCENARIOS, image_active_kb, image_models_kb, image_scenarios_kb
from bot.ui.common import ScreenRender


def render_image_scenarios() -> ScreenRender:
    scenario_lines = "\n".join(
        f"{scenario['title']} — {scenario['description']}"
        for scenario in (
            IMAGE_SCENARIOS["fast"],
            IMAGE_SCENARIOS["quality"],
            IMAGE_SCENARIOS["hot_wan"],
            IMAGE_SCENARIOS["hot_seedream"],
            IMAGE_SCENARIOS["edit"],
            IMAGE_SCENARIOS["cinematic"],
        )
    )
    text = (
        "🎨 <b>Изображения</b>\n\n"
        "Сначала выбери сценарий. Я подберу модель и сразу проведу к генерации.\n\n"
        f"{scenario_lines}\n\n"
        "Если хочешь полный ручной контроль, открой <b>Все модели</b>."
    )
    return ScreenRender(text=text, reply_markup=image_scenarios_kb())


def render_image_advanced_menu(model_costs: list[ModelCost]) -> ScreenRender:
    text = (
        "🧠 <b>Все модели изображений</b>\n\n"
        "Полный ручной режим: сам выбираешь модель, затем режим и параметры.\n\n"
        "Подходит, если ты уже знаешь разницу между Seedream, Nano Banana, WAN и Grok."
    )
    return ScreenRender(text=text, reply_markup=image_models_kb(model_costs))


def render_active_image_session(image_session: ImageSession) -> ScreenRender:
    ratio = image_session.aspect_ratio or "auto"
    count = image_session.count or 1
    reference_count = 0
    if image_session.reference_file_ids:
        import json

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
        f"📐 {ratio} · {count_label}\n\n"
        f"📎 Референс: <b>{reference_label}</b>\n\n"
        "────────────\n\n"
        "✍️ Отправь текст или фото\n"
        "Бот продолжит генерацию\n\n"
        "────────────"
    )
    return ScreenRender(
        text=text,
        reply_markup=image_active_kb(),
    )
