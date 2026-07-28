from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.image_service import ImageModel
from bot.keyboards.models import IMAGE_CAPS
from bot.states import ImageGenFSM
from bot.ui.image_menu import render_image_scenarios
from bot.ui.model_labels import model_display_name
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import ImageSession
from db.models import User

router = Router(name="image_wizard_v2")

_DEFAULT_MODEL = ImageModel.SEEDREAM_5_PRO_T2I.value
_DEFAULT_ASPECT_RATIO = "1:1"
_DEFAULT_QUALITY = "basic"


def _public_model_title(model_key: str) -> str:
    return model_display_name(model_key).replace("🔥 HOT · ", "")


def _quality_label(model_key: str, quality: str | None) -> str:
    labels = {
        value: label.replace("🔷 ", "").replace("💎 ", "").replace(" (стандарт)", "").replace(" (высокое)", "")
        for value, label in IMAGE_CAPS.get(model_key, {}).get("quality_options", [])
    }
    if quality in labels:
        return labels[quality]
    if not quality or quality == _DEFAULT_QUALITY:
        return "Авто"
    return quality


def _reference_count_from_state(data: dict) -> int:
    refs = [item for item in list(data.get("ref_file_ids", []) or []) if item]
    image_file_id = data.get("image_file_id")
    if image_file_id and image_file_id not in refs:
        refs.insert(0, image_file_id)
    return len(refs)


def _default_quality_for_model(model_key: str) -> str:
    options = IMAGE_CAPS.get(model_key, {}).get("quality_options") or []
    if IMAGE_CAPS.get(model_key, {}).get("has_quality") and options:
        return str(options[0][0])
    return _DEFAULT_QUALITY


def _default_aspect_ratio_for_model(model_key: str, mode: str | None) -> str:
    caps = IMAGE_CAPS.get(model_key, {})
    ratio_modes = caps.get("aspect_ratio_modes", caps.get("modes", ["text"]))
    ratios = [str(item) for item in caps.get("aspect_ratios", []) if item]
    if mode and ratio_modes and mode not in ratio_modes:
        return "Авто"
    if _DEFAULT_ASPECT_RATIO in ratios:
        return _DEFAULT_ASPECT_RATIO
    return ratios[0] if ratios else "Авто"


def _reference_payload_from_state(data: dict, *, max_refs: int, supports_refs: bool) -> dict[str, object]:
    if not supports_refs:
        return {
            "image_file_id": None,
            "ref_file_ids": [],
            "remix_reference_url": None,
        }

    refs = [str(item) for item in list(data.get("carryover_ref_file_ids") or data.get("ref_file_ids") or []) if item]
    image_file_id = data.get("carryover_image_file_id") or data.get("image_file_id")
    if image_file_id and image_file_id not in refs:
        refs.insert(0, str(image_file_id))
    refs = refs[:max_refs]

    return {
        "image_file_id": refs[0] if refs else None,
        "ref_file_ids": refs,
        "remix_reference_url": data.get("carryover_reference_url") or data.get("remix_reference_url"),
    }


def _default_mode_for_model(model_key: str, data: dict, reference_payload: dict[str, object]) -> str:
    caps = IMAGE_CAPS.get(model_key, {})
    modes = list(caps.get("modes") or ["text"])
    carryover_mode = data.get("carryover_mode")
    has_reference = bool(
        reference_payload.get("ref_file_ids")
        or reference_payload.get("image_file_id")
        or reference_payload.get("remix_reference_url")
    )
    if carryover_mode in modes:
        return str(carryover_mode)
    if has_reference and "image" in modes:
        return "image"
    if "text" in modes:
        return "text"
    return str(modes[0])


def _sync_active_session_state(image_session: ImageSession) -> dict:
    return {
        "image_session_id": image_session.id,
        "model_key": image_session.model,
        "image_model": image_session.model,
        "mode": image_session.mode,
        "image_mode": image_session.mode,
        "aspect_ratio": image_session.aspect_ratio,
        "image_aspect_ratio": image_session.aspect_ratio,
        "quality": image_session.quality,
        "image_quality": image_session.quality,
        "count": image_session.count,
        "image_count": image_session.count,
        "image_file_id": image_session.reference_file_id,
    }


def _composer_screen(data: dict | None = None):
    payload = data or {}
    model_key = str(payload.get("model_key") or _DEFAULT_MODEL)
    max_refs = int(IMAGE_CAPS.get(model_key, {}).get("max_refs") or 10)
    return render_image_scenarios(
        model_title=_public_model_title(model_key),
        reference_count=_reference_count_from_state(payload),
        max_refs=max_refs,
        aspect_ratio=str(payload.get("aspect_ratio") or _DEFAULT_ASPECT_RATIO),
        quality=_quality_label(model_key, str(payload.get("quality") or _DEFAULT_QUALITY)),
        show_continue=bool(payload.get("image_params_changed")),
    )


def _ratio_choice_kb(model_key: str, current: str | None):
    builder = InlineKeyboardBuilder()
    ratios = [str(item) for item in IMAGE_CAPS.get(model_key, {}).get("aspect_ratios", []) if item]
    if not ratios:
        ratios = ["auto"]
    selected = str(current or _DEFAULT_ASPECT_RATIO)
    for ratio in ratios:
        label = "Авто" if ratio == "auto" else ratio
        prefix = "✅ " if ratio == selected else ""
        builder.button(text=f"{prefix}{label}", callback_data=f"img_v2:ratio:set:{ratio}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="img_v2:back"))
    return builder.as_markup()


def _quality_choice_kb(model_key: str, current: str | None):
    builder = InlineKeyboardBuilder()
    options = IMAGE_CAPS.get(model_key, {}).get("quality_options") or [(_DEFAULT_QUALITY, "Авто")]
    selected = str(current or options[0][0])
    for value, label in options:
        clean_label = label.replace("🔷 ", "").replace("💎 ", "").replace(" (стандарт)", "").replace(" (высокое)", "")
        prefix = "✅ " if value == selected else ""
        builder.button(text=f"{prefix}{clean_label}", callback_data=f"img_v2:quality:set:{value}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="img_v2:back"))
    return builder.as_markup()


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
        quality=_DEFAULT_QUALITY,
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
        aspect_ratio=_DEFAULT_ASPECT_RATIO,
        image_aspect_ratio=_DEFAULT_ASPECT_RATIO,
        count=1,
        image_count=1,
        quality=_DEFAULT_QUALITY,
        image_quality=_DEFAULT_QUALITY,
        image_file_id=None,
        ref_file_ids=[],
        remix_mode=False,
        remix_parent_generation_id=None,
        remix_reference_url=None,
        source_feed_gen_id=None,
        image_prompt_enhance=True,
    )
    return True


async def open_model_composer_for_selection(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    model_key: str,
    forced_mode: str | None = None,
) -> bool:
    quality = _default_quality_for_model(model_key)
    model_cost = await repo.resolve_image_model_cost(session, model_key, quality=quality)
    if model_cost is None:
        await call.answer("Модель временно недоступна", show_alert=True)
        return False

    data = await state.get_data()
    caps = IMAGE_CAPS.get(model_key, {})
    modes = list(caps.get("modes") or ["text"])
    max_refs = int(caps.get("max_refs") or 10)
    supports_refs = "image" in modes
    reference_payload = _reference_payload_from_state(data, max_refs=max_refs, supports_refs=supports_refs)
    mode = forced_mode if forced_mode in modes else _default_mode_for_model(model_key, data, reference_payload)
    aspect_ratio = _default_aspect_ratio_for_model(model_key, mode)

    updates = {
        "image_session_id": None,
        "model_key": model_key,
        "image_model": model_key,
        "mode": mode,
        "image_mode": mode,
        "credits": model_cost.credits,
        "aspect_ratio": aspect_ratio,
        "image_aspect_ratio": aspect_ratio,
        "count": 1,
        "image_count": 1,
        "quality": quality,
        "image_quality": quality,
        "source_feed_gen_id": None,
        "image_prompt_enhance": True,
        "image_params_changed": False,
        **reference_payload,
    }
    await state.update_data(**updates)
    await state.set_state(ImageGenFSM.prompt_input)

    screen = _composer_screen({**data, **updates})
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await safe_answer_callback(call)
    return True


@router.callback_query(F.data == "menu:image")
async def open_image_composer(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    image_session = await repo.get_active_image_session(session, db_user.id)
    if image_session:
        await state.clear()
        await state.update_data(**_sync_active_session_state(image_session))
        await state.set_state(ImageGenFSM.session_active)
        from bot.ui.router import render_screen

        screen = await render_screen(
            screen="image_active",
            session=session,
            db_user=db_user,
            extra={"image_session": image_session},
        )
        await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
        await safe_answer_callback(call)
        return

    if not await _prepare_default_flow(
        call=call,
        state=state,
        session=session,
        db_user=db_user,
        mode="text",
    ):
        return
    await state.set_state(ImageGenFSM.prompt_input)
    screen = _composer_screen(await state.get_data())
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.prompt_input, F.data == "img_v2:refs")
async def explain_references(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    model_key = str(data.get("model_key") or _DEFAULT_MODEL)
    max_refs = int(IMAGE_CAPS.get(model_key, {}).get("max_refs") or 10)
    await call.answer(
        f"Отправь фото сообщением сюда. Сейчас {_reference_count_from_state(data)}/{max_refs}.",
        show_alert=True,
    )


@router.callback_query(ImageGenFSM.prompt_input, F.data == "img_v2:ratio")
async def choose_default_ratio(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    model_key = str(data.get("model_key") or _DEFAULT_MODEL)
    current = str(data.get("aspect_ratio") or _DEFAULT_ASPECT_RATIO)
    await safe_edit_message(
        call.message,
        f"📐 <b>Выбери формат</b>\n\nТекущий: <b>{current}</b>",
        reply_markup=_ratio_choice_kb(model_key, current),
    )
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.prompt_input, F.data.startswith("img_v2:ratio:set:"))
async def set_default_ratio(call: CallbackQuery, state: FSMContext) -> None:
    next_ratio = call.data.split(":", 3)[3]  # type: ignore[union-attr]
    data = await state.get_data()
    await state.update_data(
        aspect_ratio=next_ratio,
        image_aspect_ratio=next_ratio,
        image_params_changed=True,
    )
    screen = _composer_screen({**data, "aspect_ratio": next_ratio, "image_aspect_ratio": next_ratio, "image_params_changed": True})
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await call.answer(f"Формат: {next_ratio}")


@router.callback_query(ImageGenFSM.prompt_input, F.data == "img_v2:quality")
async def choose_default_quality(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    model_key = str(data.get("model_key") or _DEFAULT_MODEL)
    options = IMAGE_CAPS.get(model_key, {}).get("quality_options") or [(_DEFAULT_QUALITY, "1K")]
    current = str(data.get("quality") or options[0][0])
    await safe_edit_message(
        call.message,
        f"💎 <b>Выбери качество</b>\n\nТекущее: <b>{_quality_label(model_key, current)}</b>",
        reply_markup=_quality_choice_kb(model_key, current),
    )
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.prompt_input, F.data.startswith("img_v2:quality:set:"))
async def set_default_quality(call: CallbackQuery, state: FSMContext) -> None:
    next_quality = call.data.split(":", 3)[3]  # type: ignore[union-attr]
    data = await state.get_data()
    model_key = str(data.get("model_key") or _DEFAULT_MODEL)
    await state.update_data(
        quality=next_quality,
        image_quality=next_quality,
        image_params_changed=True,
    )
    screen = _composer_screen({**data, "quality": next_quality, "image_quality": next_quality, "image_params_changed": True})
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await call.answer(f"Качество: {_quality_label(model_key, next_quality)}")


@router.callback_query(ImageGenFSM.prompt_input, F.data == "img_v2:back")
async def back_to_default_composer(call: CallbackQuery, state: FSMContext) -> None:
    screen = _composer_screen(await state.get_data())
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.prompt_input, F.data == "img_v2:continue")
async def continue_default_composer(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(image_params_changed=False)
    screen = _composer_screen(await state.get_data())
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await call.answer()


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
    if not await _prepare_default_flow(
        call=call,
        state=state,
        session=session,
        db_user=db_user,
        mode="text",
    ):
        return
    await state.set_state(ImageGenFSM.prompt_input)
    screen = await render_screen(screen="image_entry", session=session, db_user=db_user)
    await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await safe_answer_callback(call)
