from __future__ import annotations

import json

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards.models import image_active_kb, image_models_kb, image_session_kb
from bot.ui.common import ScreenRender
from bot.ui.model_labels import model_display_name
from db.models import ImageSession, ModelCost


def _pretty_image_model(model_key: str) -> str:
    return model_display_name(model_key)


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


def _image_start_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✨ Создать с нуля", callback_data="img_v2:text"),
        InlineKeyboardButton(text="🪄 Изменить фото", callback_data="img_v2:edit"),
    )
    builder.row(
        InlineKeyboardButton(text="📸 Фото → промпт", callback_data="img:photo2prompt"),
        InlineKeyboardButton(text="🧠 Выбрать модель", callback_data="img_menu:advanced"),
    )
    builder.row(InlineKeyboardButton(text="🏠 На главную", callback_data="menu:main"))
    return builder.as_markup()


def render_image_scenarios() -> ScreenRender:
    text = (
        "🎨 <b>Создание изображений</b>\n\n"
        "Выбери только результат. Модель, режим и базовые параметры APIX подберёт автоматически.\n\n"
        "✨ <b>Создать с нуля</b>\n"
        "Напиши идею обычными словами — реклама, персонаж, карточка товара, пост или иллюстрация.\n\n"
        "🪄 <b>Изменить фото</b>\n"
        "Сначала отправь изображение, затем напиши, что изменить: фон, одежду, объект, стиль или детали.\n\n"
        "📸 <b>Фото → промпт</b>\n"
        "Получи подробное описание загруженной фотографии.\n\n"
        "🧠 <b>Выбрать модель</b>\n"
        "Экспертный режим со всеми моделями и ручными настройками.\n\n"
        "Обычно достаточно первых двух кнопок 👇"
    )
    return ScreenRender(text=text, reply_markup=_image_start_kb())


def render_image_advanced_menu(model_costs: list[ModelCost]) -> ScreenRender:
    text = (
        "🧠 <b>Экспертный выбор модели</b>\n\n"
        "Выбирай конкретную нейросеть только когда это действительно важно. "
        "APIX сам переключит генерацию на редактирование, если ты добавишь фото.\n\n"
        "🔥 <b>Seedream 5 Pro</b> — коммерческий фотореализм и детали.\n"
        "🍌 <b>Nano Banana</b> — универсальная работа с идеями и референсами.\n"
        "🤖 <b>GPT Image 2</b> — точное следование сложному запросу.\n"
        "⚡ <b>Grok</b> и 🟣 <b>Qwen</b> — быстрые альтернативные варианты.\n\n"
        "Цена указана на кнопке. После выбора откроются только поддерживаемые настройки."
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
        "Отправь текст — сделаю новый вариант с текущими настройками.\n"
        "Отправь фото — использую его как референс и автоматически включу редактирование.\n\n"
        f"🤖 <b>{model_label}</b>\n"
        f"📐 {ratio} · 💎 {quality_label} · 🔢 {count_label}\n"
        f"📎 Референсы: {reference_label}\n\n"
        "Тонкие параметры доступны в кнопке «Настройки»."
    )
    return ScreenRender(text=text, reply_markup=reply_markup)
