from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import IsAdmin
from bot.handlers.trends import TREND_CATEGORIES, TrendAdminFSM
from bot.keyboards.models import IMAGE_CAPS, VIDEO_CAPS
from bot.utils.telegram_ui import safe_answer_callback
from db import repository as repo

logger = logging.getLogger(__name__)
router = Router(name="trend_admin_guard")


def _model_key(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "")


_IMAGE_MODEL_KEYS = {_model_key(key) for key in IMAGE_CAPS}
_VIDEO_MODEL_KEYS = {_model_key(key) for key in VIDEO_CAPS}


def _trend_model_kind(item: object) -> str | None:
    """Resolve model family from runtime capability first, DB metadata second."""
    key = _model_key(getattr(item, "model_key", ""))
    if key in _IMAGE_MODEL_KEYS:
        return "image"
    if key in _VIDEO_MODEL_KEYS:
        return "video"

    raw_type = getattr(item, "gen_type", None)
    normalized = _model_key(raw_type).lower().rsplit(".", 1)[-1]
    return normalized if normalized in {"image", "video"} else None


def _cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    return builder.as_markup()


@router.callback_query(TrendAdminFSM.category, F.data.startswith("trends:category:"), IsAdmin())
async def trend_category_pick(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    category = (call.data or "").split(":", 2)[2]
    if category not in TREND_CATEGORIES:
        await safe_answer_callback(call, "Категория не найдена", show_alert=True)
        return

    # Telegram keeps the button spinner alive until callback_query is answered.
    # A DB lookup must never make a healthy button look frozen.
    await safe_answer_callback(call)

    data = await state.get_data()
    kind = str(data.get("kind") or "image")
    try:
        all_models = await repo.get_all_model_costs(session)
    except Exception:
        logger.exception("Failed to load model costs for trend admin kind=%s category=%s", kind, category)
        await call.message.answer(
            "Не получилось загрузить модели. Попробуй нажать категорию ещё раз — введённые данные сохранены.",
            reply_markup=_cancel_kb(),
        )
        return

    models = [
        item
        for item in all_models
        if getattr(item, "is_active", True) and _trend_model_kind(item) == kind
    ]
    if not models:
        await call.message.answer(
            "Не нашёл доступных моделей для этого типа тренда. Выбери категорию ещё раз чуть позже — мастер не сброшен.",
            reply_markup=_cancel_kb(),
        )
        return

    await state.update_data(category=category)
    await state.set_state(TrendAdminFSM.model)

    builder = InlineKeyboardBuilder()
    for item in models:
        model_key = _model_key(getattr(item, "model_key", ""))
        display_name = str(getattr(item, "display_name", None) or model_key or "Модель")
        builder.row(
            InlineKeyboardButton(
                text=display_name[:50],
                callback_data=f"trends:model:{model_key}",
            )
        )
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    await call.message.answer("Выбери модель:", reply_markup=builder.as_markup())
