from __future__ import annotations

import html
import logging
from typing import Any, Callable

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api.photo_prompt_service import generate_prompt_from_photo
from bot.keyboards.models import IMAGE_CAPS
from bot.states import ImageGenFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import ImageGenerationAction, ImageSession, User

logger = logging.getLogger(__name__)
router = Router(name="photo_prompt")

_MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
_ALLOWED_DOCUMENT_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_PROMPT_MESSAGE_CHARS = 3200
_PHOTO_PROMPT_CALLBACK = "img:photo2prompt"


def _append_photo_prompt_button(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    rows = [list(row) for row in markup.inline_keyboard]
    if any(
        button.callback_data == _PHOTO_PROMPT_CALLBACK
        for row in rows
        for button in row
    ):
        return markup

    insert_at = len(rows)
    if rows and any(
        button.callback_data in {"menu:main", "menu:create"}
        for button in rows[-1]
    ):
        insert_at -= 1

    rows.insert(
        insert_at,
        [InlineKeyboardButton(text="📸 Фото → промпт", callback_data=_PHOTO_PROMPT_CALLBACK)],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _wrap_markup_builder(
    original: Callable[..., InlineKeyboardMarkup],
    *,
    image_only: bool = False,
) -> Callable[..., InlineKeyboardMarkup]:
    if getattr(original, "__photo_prompt_wrapped__", False):
        return original

    def wrapped(*args: Any, **kwargs: Any) -> InlineKeyboardMarkup:
        markup = original(*args, **kwargs)
        if image_only:
            gen_type = args[1] if len(args) > 1 else kwargs.get("gen_type")
            if str(gen_type or "").lower() != "image":
                return markup
        return _append_photo_prompt_button(markup)

    setattr(wrapped, "__photo_prompt_wrapped__", True)
    setattr(wrapped, "__wrapped__", original)
    return wrapped


def install_photo_prompt_keyboard_hooks(legacy_image_gen: Any) -> None:
    """Expose Photo → Prompt from active sessions and completed image results."""
    from bot.keyboards import models as model_keyboards
    from bot.ui import image_menu

    wrapped_session = _wrap_markup_builder(model_keyboards.image_session_kb)
    wrapped_active = _wrap_markup_builder(model_keyboards.image_active_kb)
    wrapped_after = _wrap_markup_builder(model_keyboards.after_generation_kb, image_only=True)

    model_keyboards.image_session_kb = wrapped_session
    model_keyboards.image_active_kb = wrapped_active
    model_keyboards.after_generation_kb = wrapped_after

    # These modules imported the builders directly, so update their local references too.
    legacy_image_gen.image_session_kb = wrapped_session
    image_menu.image_session_kb = wrapped_session
    image_menu.image_active_kb = wrapped_active


def _display_prompt(prompt: str) -> tuple[str, bool]:
    clean = str(prompt or "").strip()
    truncated = len(clean) > _MAX_PROMPT_MESSAGE_CHARS
    if truncated:
        clean = clean[:_MAX_PROMPT_MESSAGE_CHARS].rstrip() + "…"
    return html.escape(clean), truncated


def _result_text(
    prompt: str,
    *,
    active_session: ImageSession | None = None,
    selected_model_name: str | None = None,
) -> str:
    escaped_prompt, truncated = _display_prompt(prompt)
    context_lines: list[str] = []
    if active_session is not None:
        from bot.handlers.image_gen import get_image_model_label

        context_lines.append(
            f"🔥 Активная серия: <b>{html.escape(get_image_model_label(active_session.model))}</b>"
        )
    if selected_model_name:
        context_lines.append(f"🎨 Выбрана модель: <b>{html.escape(selected_model_name)}</b>")

    context = ("\n" + "\n".join(context_lines)) if context_lines else ""
    truncated_note = (
        "\n\n<i>Промпт очень длинный, поэтому в сообщении показана сокращённая версия. "
        "Для генерации сохранён полный текст.</i>"
        if truncated
        else ""
    )
    return (
        "✨ <b>Промпт готов!</b>\n\n"
        f"<code>{escaped_prompt}</code>"
        f"{truncated_note}{context}\n\n"
        "Нажми на текст, чтобы выделить и скопировать его, либо сразу запусти генерацию."
    )


def _result_keyboard(
    *,
    has_active_session: bool,
    selected_model_key: str | None = None,
    selected_model_name: str | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_active_session:
        rows.append(
            [InlineKeyboardButton(text="✅ Сгенерировать сейчас", callback_data="img:use_prompt")]
        )

    if selected_model_key:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"🎨 {selected_model_name or selected_model_key} ✅",
                    callback_data="p2p:model",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text="✨ Сгенерировать выбранной моделью",
                    callback_data="p2p:generate",
                )
            ]
        )
    else:
        rows.append(
            [InlineKeyboardButton(text="🎨 Выбрать модель", callback_data="p2p:model")]
        )

    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="img:cancel_prompt")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _resolve_active_session(
    session: AsyncSession,
    db_user: User,
    data: dict[str, Any],
) -> ImageSession | None:
    raw_session_id = data.get("photo_prompt_active_session_id")
    if raw_session_id:
        try:
            image_session = await repo.get_image_session(session, int(raw_session_id), db_user.id)
        except (TypeError, ValueError):
            image_session = None
        if image_session is not None:
            return image_session
    return await repo.get_active_image_session(session, db_user.id)


async def _download_telegram_file(bot: Bot, file_id: str) -> bytes:
    telegram_file = await bot.get_file(file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    return downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)


async def _analyse_photo(
    *,
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    file_id: str,
    mime_type: str,
) -> None:
    wait_msg = await message.answer("⏳ Анализирую фотографию…")
    try:
        raw = await _download_telegram_file(bot, file_id)
        prompt = await generate_prompt_from_photo(raw, mime_type)
    except Exception as exc:
        logger.exception("photo_to_prompt failed for user=%s: %s", db_user.id, exc)
        await wait_msg.edit_text(
            "❌ Не удалось проанализировать фото. Отправь другое изображение или попробуй ещё раз.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="img:cancel_prompt")]
                ]
            ),
        )
        return

    await state.update_data(
        generated_prompt=prompt,
        photo_prompt_source_file_id=file_id,
    )
    data = await state.get_data()
    active_session = await _resolve_active_session(session, db_user, data)

    await wait_msg.delete()
    await message.answer(
        _result_text(
            prompt,
            active_session=active_session,
            selected_model_name=data.get("p2p_model_name"),
        ),
        reply_markup=_result_keyboard(
            has_active_session=active_session is not None,
            selected_model_key=data.get("p2p_model_key"),
            selected_model_name=data.get("p2p_model_name"),
        ),
    )


@router.callback_query(F.data == _PHOTO_PROMPT_CALLBACK)
async def cb_photo_to_prompt(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    active_session = await repo.get_active_image_session(session, db_user.id)
    previous_state = await state.get_state()
    await state.set_state(ImageGenFSM.photo_to_prompt)
    await state.update_data(
        generated_prompt=None,
        photo_prompt_source_file_id=None,
        photo_prompt_previous_state=previous_state,
        photo_prompt_active_session_id=getattr(active_session, "id", None),
        p2p_model_key=None,
        p2p_model_name=None,
    )
    await safe_edit_message(
        call.message,
        "📸 <b>Фото → Промпт</b>\n\n"
        "Отправь фотографию. Я разберу объект, стиль, композицию, свет, палитру, "
        "настроение, текстуры и ракурс, а затем подготовлю подробный промпт на английском.\n\n"
        "Анализ бесплатный — кредиты не списываются.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="img:cancel_prompt")]
            ]
        ),
    )
    await safe_answer_callback(call)


@router.message(ImageGenFSM.photo_to_prompt, F.photo)
async def handle_photo_to_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    best = max(message.photo, key=lambda photo: photo.file_size or 0)
    await _analyse_photo(
        message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        file_id=best.file_id,
        mime_type="image/jpeg",
    )


@router.message(ImageGenFSM.photo_to_prompt, F.document)
async def handle_document_to_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    document = message.document
    mime_type = str(document.mime_type or "").lower()
    if mime_type not in _ALLOWED_DOCUMENT_MIME_TYPES:
        await message.answer(
            "Пришли изображение JPG, PNG, WEBP или GIF.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="img:cancel_prompt")]
                ]
            ),
        )
        return
    if document.file_size and document.file_size > _MAX_DOCUMENT_BYTES:
        await message.answer("Файл слишком большой. Максимальный размер — 20 МБ.")
        return

    await _analyse_photo(
        message=message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        file_id=document.file_id,
        mime_type=mime_type,
    )


@router.message(ImageGenFSM.photo_to_prompt)
async def handle_invalid_photo_prompt_input(message: Message) -> None:
    await message.answer(
        "Нужно отправить фотографию или файл изображения JPG, PNG, WEBP либо GIF.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="img:cancel_prompt")]
            ]
        ),
    )


@router.callback_query(F.data == "p2p:model")
async def cb_photo_prompt_model(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    await state.set_state(ImageGenFSM.photo_to_prompt_model)
    model_costs = await repo.get_all_model_costs(session)
    screen = await render_screen(
        screen="image_advanced",
        session=session,
        db_user=db_user,
        extra={"model_costs": model_costs},
    )
    await safe_edit_message(
        call.message,
        "🎨 <b>Выбери модель для генерации</b>\n\n" + screen.text.split("\n\n", 1)[-1],
        reply_markup=screen.reply_markup,
    )
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.photo_to_prompt_model, F.data.startswith("img_model:"))
async def cb_photo_prompt_model_selected(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    model_key = str(call.data or "").removeprefix("img_model:")
    model_cost = await repo.get_model_cost(session, model_key)
    if model_cost is None:
        await call.answer("Модель временно недоступна", show_alert=True)
        return

    modes = list(IMAGE_CAPS.get(model_key, {}).get("modes") or ["text"])
    if "text" not in modes:
        await call.answer("Эта модель работает только с референсом. Выбери text-to-image модель.", show_alert=True)
        return

    await state.set_state(ImageGenFSM.photo_to_prompt)
    await state.update_data(
        p2p_model_key=model_key,
        p2p_model_name=model_cost.display_name,
    )
    data = await state.get_data()
    prompt = str(data.get("generated_prompt") or "").strip()
    active_session = await _resolve_active_session(session, db_user, data)
    await safe_edit_message(
        call.message,
        _result_text(
            prompt,
            active_session=active_session,
            selected_model_name=model_cost.display_name,
        ),
        reply_markup=_result_keyboard(
            has_active_session=active_session is not None,
            selected_model_key=model_key,
            selected_model_name=model_cost.display_name,
        ),
    )
    await safe_answer_callback(call)


async def _launch_in_session(
    *,
    source_message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    image_session: ImageSession,
    prompt: str,
) -> None:
    from bot.handlers import image_gen as legacy_image_gen

    data = await state.get_data()
    reference_url = await legacy_image_gen._session_reference_url(
        bot,
        image_session,
        prefer_last_result=False,
        state=state,
    )
    current_mode = str(getattr(image_session, "mode", None) or "text")
    current_mode = await legacy_image_gen._promote_reference_mode_if_needed(
        session=session,
        state=state,
        image_session=image_session,
        data=data,
        current_mode=current_mode,
        reference_url=reference_url,
    )
    if current_mode != "image" or not legacy_image_gen._supports_img2img(image_session.model):
        reference_url = None

    await state.set_state(ImageGenFSM.session_active)
    await legacy_image_gen._launch_session_generation(
        source_message=source_message,
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt,
        action_type=ImageGenerationAction.initial,
        reference_url=reference_url,
        parent_generation_id=image_session.last_generation_id,
        source_feed_gen_id=None,
        launching_text="📸 <b>Генерирую по промпту из фото...</b>",
        queued_text="⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
    )


@router.callback_query(F.data == "img:use_prompt")
async def cb_use_generated_prompt(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    prompt = str(data.get("generated_prompt") or "").strip()
    if not prompt:
        await call.answer("Промпт не найден. Отправь фото ещё раз.", show_alert=True)
        return

    image_session = await _resolve_active_session(session, db_user, data)
    if image_session is None:
        await call.answer("Активной серии нет. Сначала выбери модель.", show_alert=True)
        return

    await safe_answer_callback(call)
    await _launch_in_session(
        source_message=call.message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        image_session=image_session,
        prompt=prompt,
    )


@router.callback_query(F.data == "p2p:generate")
async def cb_generate_selected_model(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    prompt = str(data.get("generated_prompt") or "").strip()
    model_key = str(data.get("p2p_model_key") or "").strip()
    if not prompt:
        await call.answer("Промпт не найден. Отправь фото ещё раз.", show_alert=True)
        return
    if not model_key:
        await call.answer("Сначала выбери модель", show_alert=True)
        return

    caps = IMAGE_CAPS.get(model_key, {})
    modes = list(caps.get("modes") or ["text"])
    if "text" not in modes:
        await call.answer("Эта модель требует референс", show_alert=True)
        return

    quality_options = list(caps.get("quality_options") or [])
    quality = str(quality_options[0][0]) if quality_options else "basic"
    ratio_modes = list(caps.get("aspect_ratio_modes") or modes)
    ratios = list(caps.get("aspect_ratios") or [])
    aspect_ratio = str(ratios[0]) if "text" in ratio_modes and ratios else None

    model_cost = await repo.resolve_image_model_cost(session, model_key, quality=quality)
    if model_cost is None:
        await call.answer("Модель временно недоступна", show_alert=True)
        return
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋. Нужно {model_cost.credits:g}, у тебя {db_user.credits:g}.",
            show_alert=True,
        )
        return

    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=model_key,
        mode="text",
        aspect_ratio=aspect_ratio,
        quality=quality,
        count=1,
        base_prompt=None,
    )
    await safe_answer_callback(call)
    await _launch_in_session(
        source_message=call.message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        image_session=image_session,
        prompt=prompt,
    )


@router.callback_query(F.data == "img:cancel_prompt")
async def cb_cancel_prompt(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    active_session = await _resolve_active_session(session, db_user, data)
    if active_session is not None:
        from bot.handlers import image_gen as legacy_image_gen

        await legacy_image_gen._show_active_image_session_callback(
            call,
            state,
            session,
            db_user,
            active_session,
        )
    else:
        await state.clear()
        screen = await render_screen(screen="image_entry", session=session, db_user=db_user)
        await safe_edit_message(call.message, screen.text, reply_markup=screen.reply_markup)
    await safe_answer_callback(call)
