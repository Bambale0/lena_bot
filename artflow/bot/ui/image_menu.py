from __future__ import annotations

import json

from bot.keyboards.models import (
    IMAGE_SCENARIOS,
    image_active_kb,
    image_models_kb,
    image_scenarios_kb,
    image_session_kb,
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
    "seedream/5-pro-text-to-image": "Seedream 5.0 Pro",
    "seedream/5-pro-image-to-image": "Seedream 5.0 Pro Edit",
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
    return _IMAGE_MODEL_LABELS.get(model_key, model_key.replace("-", " ").replace("/", " · ").title())


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
    text = (
        "🎨 <b>Что нужно сделать с изображением?</b>\n\n"
        "Не нужно разбираться в названиях нейросетей. Сначала выбери задачу — APIX сам предложит подходящий путь.\n\n"
        "⚡ <b>Создать быстро</b>\n"
        "Опиши идею обычными словами. Подходит для артов, рекламы, карточек товара, персонажей и постов.\n\n"
        "🪄 <b>Изменить готовое фото</b>\n"
        "Пришли один или несколько референсов и напиши, что поменять: фон, одежду, стиль, объект или детали.\n\n"
        "📸 <b>Получить промпт из фото</b>\n"
        "APIX разберёт изображение и подготовит описание, которое можно использовать для новой генерации.\n\n"
        "🧠 <b>Все нейросети</b>\n"
        "Экспертный режим. Открывай его только когда действительно нужна конкретная модель или тонкая настройка.\n\n"
        "👇 Выбери ближайший к твоей задаче вариант:"
    )
    return ScreenRender(text=text, reply_markup=image_scenarios_kb())


def render_image_advanced_menu(model_costs: list[ModelCost]) -> ScreenRender:
    text = (
        "🧠 <b>Экспертный выбор модели</b>\n\n"
        "Здесь можно выбрать конкретную нейросеть вручную. Для большинства задач быстрее вернуться назад и использовать готовый сценарий.\n\n"
        "<b>Как ориентироваться:</b>\n"
        "• нужна универсальная генерация или редактирование — выбирай Nano Banana или GPT Image;\n"
        "• важны детали, текст и коммерческие изображения — GPT Image или Seedream;\n"
        "• нужна скорость и эксперименты — Grok или Qwen;\n"
        "• несколько референсов и сложная композиция — модель с поддержкой нескольких фото.\n\n"
        "Цена указана прямо на кнопке. После выбора APIX покажет только те параметры, которые поддерживает эта модель."
    )
    return ScreenRender(text=text, reply_markup=image_models_kb(model_costs))


def render_active_image_session(
    image_session: ImageSession,
    active_generation=None,
    *,
    prompt_actions_allowed: bool | None = None,
) -> ScreenRender:
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

    gen_id = getattr(active_generation, "id", None) or getattr(image_session, "last_generation_id", None)
    prompt = getattr(active_generation, "prompt", None)
    action_type = getattr(active_generation, "action_type", None)
    action_value = str(getattr(action_type, "value", action_type) or "")
    is_repeat = action_value == "repeat" or action_value.endswith(".repeat")
    if prompt_actions_allowed is None:
        prompt_actions_allowed = not bool(getattr(active_generation, "source_feed_gen_id", None))
    reply_markup = (
        image_session_kb(
            gen_id,
            prompt=None if is_repeat else prompt,
            allow_publish=prompt_actions_allowed,
            allow_copy_prompt=prompt_actions_allowed and not is_repeat,
        )
        if gen_id
        else image_active_kb()
    )

    text = (
        "🎨 <b>Текущая работа</b>\n\n"
        f"🤖 Модель: <b>{model_label}</b>\n"
        f"📐 Формат: <b>{ratio}</b>\n"
        f"💎 Качество: <b>{quality_label}</b>\n"
        f"🔢 Результатов за запуск: <b>{count_label}</b>\n"
        f"📎 Референсы: <b>{reference_label}</b>\n\n"
        "<b>Что можно сделать дальше:</b>\n"
        "• отправить новый текст — изменить идею, сохранив текущие настройки;\n"
        "• отправить фото — добавить или заменить визуальный референс;\n"
        "• нажать «Ещё вариант» — повторить текущий запрос;\n"
        "• открыть «Настройки» — сменить модель, формат или качество."
    )
    return ScreenRender(text=text, reply_markup=reply_markup)
