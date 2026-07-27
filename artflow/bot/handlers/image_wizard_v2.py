from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.image_service import ImageModel
from bot.states import ImageGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import User

router = Router(name="image_wizard_v2")

_DEFAULT_MODEL = ImageModel.NANO_BANANA_PRO.value


def _quick_flow_kb(*, edit: bool):
    builder = InlineKeyboardBuilder()
    if edit:
        builder.row(InlineKeyboardButton(text="🧠 Другая модель", callback_data="img_menu:advanced"))
    else:
        builder.row(
            InlineKeyboardButton(text="📎 Добавить фото", callback_data="img_v2:add_reference"),
            InlineKeyboardButton(text="🧠 Другая модель", callback_data="img_menu:advanced"),
        )
    builder.row(InlineKeyboardButton(text="← К изображениям", callback_data="img_v2:home"))
    return builder.as_markup()


async def _prepare_default_flow(
    *,
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    mode: str,
) -> bool:
    model_cost = await repo.resolve_image_model_cost(
        session,
        _DEFAULT_MODEL,
        quality="2K",
    )
    if model_cost is None:
        await call.answer("Модель временно недоступна", show_alert=True)
        return False
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋. Нужно {model_cost.credits:g}, у тебя {db_user.credits:g}.",
            show_alert=True,
        )
        return False

    await state.clear()
    await state.update_data(
        image_session_id=None,
        model_key=_DEFAULT_MODEL,
        image_model=_DEFAULT_MODEL,
        mode=mode,
        image_mode=mode,
        credits=model_cost.credits,
        aspect_ratio="auto",
        image_aspect_ratio="auto",
        count=1,
        image_count=1,
        quality="2K",
        image_quality="2K",
        image_file_id=None,
        ref_file_ids=[],
        remix_mode=False,
        remix_parent_generation_id=None,
        remix_reference_url=None,
        source_feed_gen_id=None,
        image_prompt_enhance=True,
    )
    return True


@router.callback_query(F.data == "img_v2:text")
async def start_text_image(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    if not await _prepare_default_flow(
        call=call,
        state=state,
        session=session,
        db_user=db_user,
        mode="text",
    ):
        return
    await state.set_state(ImageGenFSM.prompt_input)
    await safe_edit_message(
        call.message,
        "✨ <b>Создание изображения</b>\n\n"
        "Напиши, что хочешь получить, обычными словами.\n\n"
        "Например:\n"
        "<i>Рекламное фото белых кроссовок на мокром асфальте, ночной город, неоновый свет.</i>\n\n"
        "APIX улучшит запрос, подберёт внутренний режим и перед запуском покажет стоимость.\n\n"
        "Фото можно добавить кнопкой ниже — тогда задача автоматически станет редактированием.",
        reply_markup=_quick_flow_kb(edit=False),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "img_v2:edit")
async def start_edit_image(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    if not await _prepare_default_flow(
        call=call,
        state=state,
        session=session,
        db_user=db_user,
        mode="image",
    ):
        return
    await state.set_state(ImageGenFSM.image_upload)
    await safe_edit_message(
        call.message,
        "🪄 <b>Изменение фотографии</b>\n\n"
        "Отправь одно или несколько фото прямо в чат.\n"
        "После загрузки напиши, что нужно изменить.\n\n"
        "Например:\n"
        "<i>Убери фон, сохрани человека без изменений и сделай студийное освещение.</i>\n\n"
        "APIX сам выберет img2img-маршрут. Отдельную модель Edit искать не нужно.",
        reply_markup=_quick_flow_kb(edit=True),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "img_v2:add_reference")
async def add_reference(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(mode="image", image_mode="image")
    await state.set_state(ImageGenFSM.image_upload)
    await safe_edit_message(
        call.message,
        "📎 <b>Добавь фото-референс</b>\n\n"
        "Отправь фото сюда. После загрузки напиши, что создать или изменить.\n"
        "Текущая модель переключится на img2img автоматически.",
        reply_markup=_quick_flow_kb(edit=True),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "img_v2:home")
async def image_home(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    from bot.ui.router import render_screen

    await state.clear()
    screen = await render_screen(screen="image_entry", session=session, db_user=db_user)
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await safe_answer_callback(call)
