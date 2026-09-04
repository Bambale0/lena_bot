from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import mirror_telegram_file
from bot.keyboards.main_menu import back_to_menu_kb
from bot.services.video_reference_support import (
    SEEDANCE_VIDEO_REFERENCE_MODELS,
    video_reference_limits,
)
from bot.states import VideoGenFSM
from bot.ui.model_labels import model_display_name
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo

router = Router(name="video_references_v2")
_VIDEO_REFERENCE_CALLBACKS = {
    f"vid_mode:video:{model_key}" for model_key in SEEDANCE_VIDEO_REFERENCE_MODELS
}


def _done_kb(count: int, max_refs: int):
    builder = InlineKeyboardBuilder()
    if count < max_refs:
        builder.row(InlineKeyboardButton(text="➕ Добавить ещё видео", callback_data="vid_vrefs:wait"))
    builder.row(InlineKeyboardButton(text="✅ Готово", callback_data="vid_vrefs:done"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


@router.callback_query(VideoGenFSM.mode_select, F.data.in_(_VIDEO_REFERENCE_CALLBACKS))
async def choose_video_reference_mode(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    model_key = (call.data or "").split(":", 2)[-1]
    await state.update_data(
        model_key=model_key,
        mode="video",
        reference_video_url=None,
        reference_video_urls=[],
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
    )
    await state.set_state(VideoGenFSM.video_upload)
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_display_name(model_key, getattr(model_cost, "display_name", None))
    limits = video_reference_limits(model_key)
    await safe_edit_message(
        call.message,
        f"🎞 <b>{display_name}</b> · видео-референсы\n\n"
        f"Отправь до <b>{limits.get('max_refs', 1)}</b> видео подряд. "
        f"Каждый ролик: <b>{limits.get('min_duration', 2)}–{limits.get('max_duration', 15)} сек</b>, MP4 или MOV.\n\n"
        "APIX использует движение, персонажей, композицию и стиль из референсов. "
        "После загрузки нажми <b>Готово</b>.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.video_upload, F.data == "vid_vrefs:wait")
async def wait_for_more_video_refs(call: CallbackQuery) -> None:
    await safe_answer_callback(call, "Отправь следующее видео")


@router.message(VideoGenFSM.video_upload, F.video)
async def upload_video_reference(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    model_key = str(data.get("model_key") or "")
    if model_key not in SEEDANCE_VIDEO_REFERENCE_MODELS:
        return

    limits = video_reference_limits(model_key)
    duration = int(message.video.duration or 0)  # type: ignore[union-attr]
    if duration < limits.get("min_duration", 2) or duration > limits.get("max_duration", 15):
        await message.answer(
            f"❌ Длина видео должна быть от {limits.get('min_duration', 2)} до {limits.get('max_duration', 15)} секунд.",
            reply_markup=back_to_menu_kb(),
        )
        return

    refs = [str(item) for item in (data.get("reference_video_urls") or []) if item]
    max_refs = limits.get("max_refs", 1)
    if len(refs) >= max_refs:
        await message.answer(
            "Лимит видео-референсов уже достигнут.",
            reply_markup=_done_kb(len(refs), max_refs),
        )
        return

    url = await mirror_telegram_file(bot, message.video.file_id, is_video=True)  # type: ignore[union-attr]
    refs.append(url)
    await state.update_data(reference_video_urls=refs, reference_video_url=refs)
    total_duration = int(data.get("reference_video_total_duration") or 0) + duration
    await state.update_data(reference_video_total_duration=total_duration)

    await message.answer(
        f"✅ Видео добавлено: <b>{len(refs)}/{max_refs}</b>\n"
        f"Общая длительность референсов: <b>{total_duration} сек</b>.",
        reply_markup=_done_kb(len(refs), max_refs),
    )


@router.callback_query(VideoGenFSM.video_upload, F.data == "vid_vrefs:done")
async def finish_video_references(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    from bot.handlers import video_gen as legacy

    data = await state.get_data()
    refs = [str(item) for item in (data.get("reference_video_urls") or []) if item]
    if not refs:
        await safe_answer_callback(call, "Сначала загрузи хотя бы одно видео", show_alert=True)
        return

    model_key = str(data["model_key"])
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_display_name(model_key, getattr(model_cost, "display_name", None))
    await state.set_state(VideoGenFSM.params_select)
    updated = await state.get_data()
    await safe_edit_message(
        call.message,
        f"✅ Загружено видео-референсов: <b>{len(refs)}</b>\n\n"
        f"⚙️ <b>Параметры</b> · {display_name}\n"
        "Настрой формат, длительность и качество, затем переходи к промпту.",
        reply_markup=legacy._video_params_reply_markup(model_key, updated),
    )
    await safe_answer_callback(call)
