from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import IsAdmin
from bot.keyboards.models import IMAGE_CAPS, VIDEO_CAPS
from bot.utils.telegram_ui import safe_answer_callback
from db import repository as repo

logger = logging.getLogger(__name__)

_MODEL_OPTIONS_KEY = "trend_model_options"


def _generation_type_value(item: Any) -> str:
    raw = getattr(item, "gen_type", None)
    return str(getattr(raw, "value", raw) or "").strip().lower()


def _active(item: Any) -> bool:
    return bool(getattr(item, "is_active", True))


def _model_key(item: Any) -> str:
    return str(getattr(item, "model_key", "") or "").strip()


def _available_models(costs: list[Any], kind: str) -> list[Any]:
    """Return active models for an image/video trend without trusting enum shape."""

    kind = "video" if str(kind).lower() == "video" else "image"
    active = [item for item in costs if _active(item)]
    exact = [item for item in active if _generation_type_value(item) == kind]
    if exact:
        return exact

    caps = VIDEO_CAPS if kind == "video" else IMAGE_CAPS
    return [item for item in active if _model_key(item) in caps]


def _parse_category_callback(value: str | None) -> tuple[str | None, str | None]:
    """Accept both old `trends:category:<category>` and kind-aware payloads."""

    parts = str(value or "").split(":")
    if len(parts) == 4 and parts[:2] == ["trends", "category"] and parts[2] in {"image", "video"}:
        return parts[2], parts[3]
    if len(parts) == 3 and parts[:2] == ["trends", "category"]:
        return None, parts[2]
    return None, None


def _restart_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Фото-тренд", callback_data="trends:add:image"),
        InlineKeyboardButton(text="🎬 Видео-тренд", callback_data="trends:add:video"),
    )
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    return builder.as_markup()


def _model_selector(models: list[Any]):
    """Build a Telegram-safe keyboard without putting provider model ids in callback_data."""

    builder = InlineKeyboardBuilder()
    options: dict[str, str] = {}
    for item in models:
        model_key = _model_key(item)
        if not model_key:
            continue
        token = str(len(options))
        options[token] = model_key
        label = str(getattr(item, "display_name", None) or model_key or "Модель")
        builder.row(
            InlineKeyboardButton(
                text=label[:50],
                callback_data=f"trends:model-option:{token}",
            )
        )
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    return options, builder.as_markup()


def build_trend_admin_router(trends_module: Any) -> Router:
    """Install a fail-visible trend category/model flow ahead of legacy handlers."""

    router = Router(name="trend_admin_guard")

    @router.callback_query(
        F.data.startswith("trends:category:"),
        IsAdmin(),
    )
    async def trend_category_pick(
        call: CallbackQuery,
        state: FSMContext,
        session: AsyncSession,
    ) -> None:
        # Acknowledge first so Telegram never leaves the button spinning.
        await safe_answer_callback(call)

        payload_kind, category = _parse_category_callback(call.data)
        if category not in trends_module.TREND_CATEGORIES:
            await call.message.answer("Эта категория больше недоступна. Выбери другую.")
            return

        data = await state.get_data()
        state_kind = data.get("kind") if data.get("kind") in {"image", "video"} else None
        kind = payload_kind or state_kind
        if kind is None:
            await call.message.answer(
                "Этот экран уже устарел. Выбери тип тренда ещё раз — дальше продолжим без потери шага.",
                reply_markup=_restart_kb(),
            )
            return

        # Make the next step visible before touching pricing/model storage. If an
        # unexpected production error happens later, the admin never gets a silent no-op.
        status = await call.message.answer("⏳ Подбираю доступные модели…")
        try:
            costs = list(await repo.get_all_model_costs(session))
            models = _available_models(costs, kind)
            if not models:
                await state.update_data(category=category, kind=kind)
                await status.edit_text(
                    "Не нашёл активных моделей для этого тренда. Черновик сохранён.",
                    reply_markup=trends_module._cancel_kb(),
                )
                return

            options, markup = _model_selector(models)
            if not options:
                await state.update_data(category=category, kind=kind)
                await status.edit_text(
                    "Не получилось собрать список моделей. Черновик сохранён — попробуй ещё раз.",
                    reply_markup=trends_module._cancel_kb(),
                )
                return

            await state.update_data(
                category=category,
                kind=kind,
                **{_MODEL_OPTIONS_KEY: options},
            )
            await state.set_state(trends_module.TrendAdminFSM.model)
            await status.edit_text("Выбери модель:", reply_markup=markup)
        except Exception:
            logger.exception("Trend admin category -> model failed kind=%s category=%s", kind, category)
            await state.update_data(category=category, kind=kind)
            try:
                await status.edit_text(
                    "Не получилось открыть модели. Черновик сохранён — нажми ещё раз или начни выбор типа заново.",
                    reply_markup=_restart_kb(),
                )
            except Exception:
                logger.exception("Trend admin could not render recovery message")

    @router.callback_query(
        F.data.startswith("trends:model-option:"),
        IsAdmin(),
    )
    async def trend_model_pick(call: CallbackQuery, state: FSMContext) -> None:
        await safe_answer_callback(call)

        token = str(call.data or "").rsplit(":", 1)[-1]
        data = await state.get_data()
        options = data.get(_MODEL_OPTIONS_KEY)
        model = options.get(token) if isinstance(options, dict) else None
        kind = data.get("kind") if data.get("kind") in {"image", "video"} else None
        if not model or kind is None:
            await call.message.answer(
                "Список моделей уже устарел. Выбери тип тренда ещё раз.",
                reply_markup=_restart_kb(),
            )
            return

        await state.update_data(model=model, **{_MODEL_OPTIONS_KEY: None})
        if kind == "video":
            await state.set_state(trends_module.TrendAdminFSM.scenario)
            builder = InlineKeyboardBuilder()
            builder.row(
                InlineKeyboardButton(text="Текст → видео", callback_data="trends:scenario:text"),
                InlineKeyboardButton(text="Фото → видео", callback_data="trends:scenario:image"),
            )
            await call.message.answer("Сценарий видео:", reply_markup=builder.as_markup())
            return

        await state.set_state(trends_module.TrendAdminFSM.preview)
        await call.message.answer("Пришли preview: JPEG, PNG или WEBP до 20 МБ.")

    return router
