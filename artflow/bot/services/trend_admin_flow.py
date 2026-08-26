from __future__ import annotations

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


def _generation_type_value(item: Any) -> str:
    raw = getattr(item, "gen_type", None)
    return str(getattr(raw, "value", raw) or "").strip().lower()


def _active(item: Any) -> bool:
    return bool(getattr(item, "is_active", True))


def _model_key(item: Any) -> str:
    return str(getattr(item, "model_key", "") or "").strip()


def _available_models(costs: list[Any], kind: str) -> list[Any]:
    """Return active models for an image/video trend without trusting enum shape.

    Production rows may expose `gen_type` as either GenerationType or plain text.
    If legacy rows have an empty/misaligned type, the runtime capability catalog is
    the safe fallback for deciding whether the model belongs to image or video.
    """

    kind = "video" if str(kind).lower() == "video" else "image"
    active = [item for item in costs if _active(item)]
    exact = [item for item in active if _generation_type_value(item) == kind]
    if exact:
        return exact

    caps = VIDEO_CAPS if kind == "video" else IMAGE_CAPS
    return [item for item in active if _model_key(item) in caps]


def build_trend_admin_router(trends_module: Any) -> Router:
    """Install a resilient category→model step ahead of the legacy handler."""

    router = Router(name="trend_admin_guard")

    @router.callback_query(
        trends_module.TrendAdminFSM.category,
        F.data.startswith("trends:category:"),
        IsAdmin(),
    )
    async def trend_category_pick(
        call: CallbackQuery,
        state: FSMContext,
        session: AsyncSession,
    ) -> None:
        # Always stop Telegram's loading spinner before any DB work.
        await safe_answer_callback(call)

        category = call.data.split(":", 2)[2]  # type: ignore[union-attr]
        if category not in trends_module.TREND_CATEGORIES:
            await call.message.answer("Эта категория больше недоступна. Выбери другую.")
            return

        data = await state.get_data()
        kind = "video" if data.get("kind") == "video" else "image"
        costs = list(await repo.get_all_model_costs(session))
        models = _available_models(costs, kind)

        if not models:
            # Keep the wizard state intact: the admin can retry after pricing/model
            # settings are corrected instead of starting the whole trend again.
            await state.update_data(category=category)
            await call.message.answer(
                "Не нашёл доступную модель для этого тренда. "
                "Черновик сохранён — можно вернуться к выбору категории или проверить модели в админке.",
                reply_markup=trends_module._cancel_kb(),
            )
            return

        await state.update_data(category=category)
        await state.set_state(trends_module.TrendAdminFSM.model)
        builder = InlineKeyboardBuilder()
        for item in models:
            label = str(getattr(item, "display_name", None) or _model_key(item) or "Модель")
            builder.row(
                InlineKeyboardButton(
                    text=label[:50],
                    callback_data=f"trends:model:{_model_key(item)}",
                )
            )
        builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
        await call.message.answer("Выбери модель:", reply_markup=builder.as_markup())

    return router
