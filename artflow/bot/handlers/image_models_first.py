from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.models import image_models_kb
from bot.states import ImageGenFSM
from bot.ui.model_labels import public_model_items
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import User

router = Router(name="image_models_first")

_MODEL_LIST_VISIBLE = "image_models_first_visible"


def _model_list_text(balance: float) -> str:
    return (
        "🖼 <b>Создание фото</b>\n"
        f"💋 Баланс: <b>{balance:g}</b>\n\n"
        "<b>Шаг 1. Выбери модель</b>\n"
        "Сначала выбери нейросеть. После этого откроется экран задачи с промптом, "
        "референсами, форматом, качеством и стоимостью."
    )


@router.callback_query(F.data == "menu:image")
async def open_image_models_first(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    current_state = await state.get_state()
    data = await state.get_data()

    # The existing model keyboard uses menu:image as its Back callback. When the
    # list is already open, keep that Back action useful instead of reopening
    # the exact same list in a loop.
    if current_state == ImageGenFSM.model_select.state and data.get(_MODEL_LIST_VISIBLE):
        await state.clear()
        screen = await render_screen(screen="image_entry", session=session, db_user=db_user)
        await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
        await safe_answer_callback(call)
        return

    await state.clear()
    model_costs = public_model_items(await repo.get_all_model_costs(session))
    await state.set_state(ImageGenFSM.model_select)
    await state.update_data(**{_MODEL_LIST_VISIBLE: True})

    await safe_edit_message(
        call.message,
        _model_list_text(float(db_user.credits or 0)),
        reply_markup=image_models_kb(model_costs),
    )
    await safe_answer_callback(call)
