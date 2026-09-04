from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.models import image_models_kb
from bot.states import ImageGenFSM
from bot.ui.model_labels import public_model_items
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import User

router = Router(name="image_models_first")


def _model_list_text(balance: float) -> str:
    return (
        "🖼 <b>Создание фото</b>\n"
        f"💋 Баланс: <b>{balance:g}</b>\n\n"
        "<b>Шаг 1. Выбери модель</b>\n"
        "Сначала выбери нейросеть. После этого откроется экран задачи с промптом, "
        "референсами, форматом, качеством и стоимостью."
    )


def _model_list_kb(model_costs: list, *, back_text: str, back_callback: str) -> InlineKeyboardMarkup:
    markup = image_models_kb(model_costs)
    rows = [list(row) for row in markup.inline_keyboard]
    if rows:
        rows[-1] = [InlineKeyboardButton(text=back_text, callback_data=back_callback)]
    else:
        rows = [[InlineKeyboardButton(text=back_text, callback_data=back_callback)]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _public_image_model_costs(session: AsyncSession) -> list:
    return public_model_items(await repo.get_all_model_costs(session))


@router.callback_query(F.data == "img_session:continue")
async def resume_active_image_session(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    image_session = await repo.get_active_image_session(session, db_user.id)
    if not image_session:
        await safe_answer_callback(call, "Активная серия не найдена", show_alert=True)
        return

    # Keep the saved model, mode and every stored reference. The model-first
    # entrypoint is only for a new image task, not for resuming an existing one.
    from bot.handlers.image_gen import _show_active_image_session_callback

    await _show_active_image_session_callback(call, state, session, db_user, image_session)
    await safe_answer_callback(call)


@router.callback_query(F.data == "menu:image")
async def open_image_models_first(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    await state.clear()
    await state.set_state(ImageGenFSM.model_select)
    model_costs = await _public_image_model_costs(session)

    await safe_edit_message(
        call.message,
        _model_list_text(float(db_user.credits or 0)),
        reply_markup=_model_list_kb(
            model_costs,
            back_text="🏠 Главное меню",
            back_callback="menu:main",
        ),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "img_menu:advanced")
async def reopen_image_model_picker(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    model_costs = await _public_image_model_costs(session)
    current_state = await state.get_state()
    back_callback = "img_v2:back" if current_state == ImageGenFSM.prompt_input.state else "menu:image"
    back_text = "← К задаче" if back_callback == "img_v2:back" else "← Назад"

    await safe_edit_message(
        call.message,
        _model_list_text(float(db_user.credits or 0)),
        reply_markup=_model_list_kb(
            model_costs,
            back_text=back_text,
            back_callback=back_callback,
        ),
    )
    await safe_answer_callback(call)
