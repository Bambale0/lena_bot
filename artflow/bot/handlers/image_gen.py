from __future__ import annotations

import logging
from urllib.parse import urlencode

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api import image_service
from api.image_service import ImageModel
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    IMAGE_CAPS,
    image_aspect_ratio_kb,
    image_count_kb,
    image_mode_kb,
    image_models_kb,
    image_quality_kb,
    image_session_kb,
    image_session_settings_kb,
)
from bot.states import ImageGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db import repository as repo
from db.models import GenerationType, ImageGenerationAction, ImageSession, User

logger = logging.getLogger(__name__)
router = Router(name="image_gen")


def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}{query}"


async def _telegram_file_url(bot: Bot, file_id: str | None) -> str | None:
    if not file_id:
        return None
    file = await bot.get_file(file_id)
    return f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"


def _supports_img2img(model_key: str) -> bool:
    caps = IMAGE_CAPS.get(model_key, {})
    return "image" in caps.get("modes", [])


def _safe_image_model(model_key: str) -> ImageModel | None:
    try:
        return ImageModel(model_key)
    except ValueError:
        logger.warning("Unknown image model in session flow: %s", model_key)
        return None


async def _resolve_image_session(
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    gen_id: int | None = None,
) -> tuple[ImageSession | None, int | None]:
    data = await state.get_data()
    image_session_id = data.get("image_session_id")

    if image_session_id:
        image_session = await repo.get_image_session(session, image_session_id, db_user.id)
        if image_session:
            return image_session, gen_id

    if gen_id:
        gen = await repo.get_generation_by_id(session, gen_id)
        if gen and gen.user_id == db_user.id and gen.image_session_id:
            image_session = await repo.get_image_session(session, gen.image_session_id, db_user.id)
            if image_session:
                return image_session, gen.id

    image_session = await repo.get_active_image_session(session, db_user.id)
    return image_session, gen_id


async def _session_reference_url(
    bot: Bot,
    image_session: ImageSession,
    *,
    prefer_last_result: bool = False,
) -> str | None:
    """
    Для remix берём last_result_url.
    Для обычной серии берём reference_file_id.
    Для text-only моделей image_url не передаём.
    """
    if not _supports_img2img(image_session.model):
        return None

    if prefer_last_result and image_session.last_result_url:
        return image_session.last_result_url

    if image_session.reference_file_id:
        return await _telegram_file_url(bot, image_session.reference_file_id)

    return None


def _session_settings_text(image_session: ImageSession) -> str:
    quality_label = "4K" if image_session.quality == "high" else "2K"
    return (
        "⚙️ <b>Настройки активной серии</b>\n\n"
        f"Модель: <code>{image_session.model}</code>\n"
        f"Режим: <code>{image_session.mode}</code>\n"
        f"Формат: <b>{image_session.aspect_ratio or 'по умолчанию'}</b>\n"
        f"Качество: <b>{quality_label}</b>\n"
        f"Количество: <b>{image_session.count}</b>\n\n"
        "Можно менять параметры, не теряя активную серию."
    )


def _session_ratio_choices_kb(image_session: ImageSession) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ratios = IMAGE_CAPS.get(image_session.model, {}).get("aspect_ratios", [])
    buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if ratio == image_session.aspect_ratio else ''}{ratio}",
            callback_data=f"img_sset_ratio:set:{image_session.id}:{ratio}",
        )
        for ratio in ratios
    ]
    for i in range(0, len(buttons), 3):
        builder.row(*buttons[i:i + 3])
    builder.row(InlineKeyboardButton(text="← К настройкам", callback_data=f"img_sset:back:{image_session.id}"))
    return builder.as_markup()


def _session_quality_choices_kb(image_session: ImageSession) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for quality, label in (("basic", "🔷 2K"), ("high", "💎 4K")):
        builder.row(
            InlineKeyboardButton(
                text=f"{'✅ ' if image_session.quality == quality else ''}{label}",
                callback_data=f"img_sset_quality:set:{image_session.id}:{quality}",
            )
        )
    builder.row(InlineKeyboardButton(text="← К настройкам", callback_data=f"img_sset:back:{image_session.id}"))
    return builder.as_markup()


def _session_count_choices_kb(image_session: ImageSession) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    counts = IMAGE_CAPS.get(image_session.model, {}).get("counts", [1])
    for count in counts:
        builder.row(
            InlineKeyboardButton(
                text=f"{'✅ ' if image_session.count == count else ''}{count} шт",
                callback_data=f"img_sset_count:set:{image_session.id}:{count}",
            )
        )
    builder.row(InlineKeyboardButton(text="← К настройкам", callback_data=f"img_sset:back:{image_session.id}"))
    return builder.as_markup()


async def _launch_session_generation(
    *,
    source_message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    image_session: ImageSession,
    prompt: str,
    action_type: ImageGenerationAction,
    reference_url: str | None,
    parent_generation_id: int | None,
    launching_text: str,
    queued_text: str,
) -> bool:
    model_cost = await repo.get_model_cost(session, image_session.model)
    credits = model_cost.credits if model_cost else 1

    model = _safe_image_model(image_session.model)
    if model is None:
        await source_message.answer(
            "❌ Модель серии больше не поддерживается.",
            reply_markup=main_menu_kb(),
        )
        return False

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await source_message.answer("❌ Недостаточно кредитов.", reply_markup=main_menu_kb())
        return False

    gen = await repo.create_generation(
        session,
        db_user.id,
        image_session.model,
        GenerationType.image,
        prompt,
        credits,
        image_session_id=image_session.id,
        parent_generation_id=parent_generation_id,
        action_type=action_type,
    )

    status_msg = await source_message.answer(launching_text)

    try:
        result = await image_service.generate_image(
            model,
            prompt,
            image_url=reference_url,
            aspect_ratio=image_session.aspect_ratio,
            n=image_session.count,
            quality=image_session.quality,
            callback_url=_kie_callback_url(),
        )
    except Exception as e:
        logger.error("Session image generation error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            "❌ Ошибка генерации. Кредиты возвращены.",
            reply_markup=image_session_kb(parent_generation_id),
        )
        return False

    await repo.update_generation_task(session, gen.id, result.task_id or "")
    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        model_key=image_session.model,
        credits=credits,
        aspect_ratio=image_session.aspect_ratio,
        count=image_session.count,
        quality=image_session.quality,
        image_file_id=image_session.reference_file_id,
        remix_mode=False,
        remix_parent_generation_id=None,
    )
    await status_msg.edit_text(queued_text, reply_markup=image_session_kb(gen.id))
    return True


# ── Model select ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:image")
async def cb_image_menu(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(ImageGenFSM.model_select)
    model_costs = await repo.get_all_model_costs(session)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎨 <b>Генерация изображений</b>\n\n"
        "Выбери AI-модель. Каждая имеет свои сильные стороны:\n\n"
        "• <b>Seedream</b> — максимум деталей и реализма\n"
        "• <b>Gemini Pro/Flash</b> — точное следование описанию, поддержка img2img\n"
        "• <b>WAN</b> — кино-стиль, персонажи, фэнтези\n"
        "• <b>GPT Image</b> — понимает сложные и длинные промпты\n\n"
        "👇 <b>Нажми на модель для выбора:</b>",
        reply_markup=image_models_kb(model_costs),
    )
    await safe_answer_callback(call)


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_model:"))
async def cb_model_selected(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    model_key = call.data.split(":")[1]  # type: ignore[union-attr]
    model_cost = await repo.get_model_cost(session, model_key)
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно кредитов! Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    await state.update_data(
        model_key=model_key,
        credits=model_cost.credits,
        aspect_ratio=None,
        count=1,
        image_file_id=None,
        quality="basic",
        remix_mode=False,
        remix_parent_generation_id=None,
    )

    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])

    if len(modes) > 1:
        await state.set_state(ImageGenFSM.mode_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{model_cost.display_name}</b> ({model_cost.credits} кр)\n\nВыбери режим:",
            reply_markup=image_mode_kb(model_key),
        )
    else:
        await state.update_data(mode=modes[0])
        await _go_to_next_step(call, state, session, model_key, model_cost.display_name)
    await call.answer()


async def _go_to_next_step(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    model_key: str,
    display_name: str,
) -> None:
    caps = IMAGE_CAPS.get(model_key, {})
    data = await state.get_data()
    mode = data.get("mode", "text")

    if mode == "image" and not data.get("image_file_id"):
        await state.set_state(ImageGenFSM.image_upload)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            "🖼️ Загрузи референс-изображение:",
            reply_markup=back_to_menu_kb(),
        )
        return

    if caps.get("aspect_ratios") and mode == "text":
        await state.set_state(ImageGenFSM.aspect_ratio_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b>\n\n📐 Соотношение сторон:",
            reply_markup=image_aspect_ratio_kb(model_key),
        )
        return

    if caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b>\n\n💎 Качество изображения:",
            reply_markup=image_quality_kb(),
        )
        return

    if len(caps.get("counts", [1])) > 1:
        await state.set_state(ImageGenFSM.count_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b>\n\n🔢 Количество изображений:",
            reply_markup=image_count_kb(),
        )
        return

    await state.set_state(ImageGenFSM.prompt_input)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ <b>{display_name}</b>\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )


# ── Mode select ───────────────────────────────────────────────────────────────

@router.callback_query(ImageGenFSM.mode_select, F.data.startswith("img_mode:"))
async def cb_image_mode(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    mode, model_key = parts[1], parts[2]
    await state.update_data(mode=mode)
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await _go_to_next_step(call, state, session, model_key, display_name)
    await call.answer()


# ── Aspect ratio ──────────────────────────────────────────────────────────────

@router.callback_query(ImageGenFSM.aspect_ratio_select, F.data.startswith("img_ratio:"))
async def cb_image_ratio(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    ratio = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(aspect_ratio=ratio)
    data = await state.get_data()
    model_key = data["model_key"]
    caps = IMAGE_CAPS.get(model_key, {})
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    if caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · {ratio}\n\n💎 Качество:",
            reply_markup=image_quality_kb(),
        )
    elif len(caps.get("counts", [1])) > 1:
        await state.set_state(ImageGenFSM.count_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · {ratio}\n\n🔢 Количество изображений:",
            reply_markup=image_count_kb(),
        )
    else:
        await state.set_state(ImageGenFSM.prompt_input)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · {ratio}\n\n✍️ Введи промпт:",
            reply_markup=back_to_menu_kb(),
        )
    await call.answer(ratio)


@router.callback_query(ImageGenFSM.aspect_ratio_select, F.data.startswith("img_back:mode:"))
async def cb_image_back_to_mode(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":")[-1]  # type: ignore[union-attr]
    await state.set_state(ImageGenFSM.mode_select)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "Выбери режим:",
        reply_markup=image_mode_kb(model_key),
    )
    await call.answer()


# ── Quality / Count ───────────────────────────────────────────────────────────

@router.callback_query(ImageGenFSM.count_select, F.data.startswith("img_quality:"))
async def cb_image_quality(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    quality = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(quality=quality)
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    ratio = data.get("aspect_ratio", "1:1")
    q_label = "4K" if quality == "high" else "2K"

    await state.set_state(ImageGenFSM.prompt_input)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ <b>{display_name}</b> · {ratio} · {q_label}\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer(q_label)


@router.callback_query(ImageGenFSM.count_select, F.data.startswith("img_count:"))
async def cb_image_count(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    count = int(call.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(count=count)
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    ratio = data.get("aspect_ratio", "1:1")

    await state.set_state(ImageGenFSM.prompt_input)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ <b>{display_name}</b> · {ratio} · {count} изображ.\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer(f"{count} шт")


@router.callback_query(ImageGenFSM.count_select, F.data == "img_back:ratio")
async def cb_count_back(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await state.set_state(ImageGenFSM.aspect_ratio_select)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ <b>{display_name}</b>\n\n📐 Соотношение сторон:",
        reply_markup=image_aspect_ratio_kb(model_key),
    )
    await call.answer()


# ── Image upload (img2img референс) ───────────────────────────────────────────

@router.message(ImageGenFSM.image_upload, F.photo)
async def handle_reference_upload(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    await state.update_data(image_file_id=best[0].file_id)
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    caps = IMAGE_CAPS.get(model_key, {})
    if caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await message.answer(
            f"✅ Референс загружен!\n\n💎 Качество · <b>{display_name}</b>:",
            reply_markup=image_quality_kb(),
        )
    else:
        await state.set_state(ImageGenFSM.prompt_input)
        await message.answer(
            "✅ Референс загружен!\n\n✍️ Введи промпт:",
            reply_markup=back_to_menu_kb(),
        )


# ── First prompt starts a session ─────────────────────────────────────────────

@router.message(ImageGenFSM.prompt_input, F.text)
async def handle_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    model_key: str = data["model_key"]
    aspect_ratio: str | None = data.get("aspect_ratio")
    count: int = data.get("count", 1)
    quality: str = data.get("quality", "basic")
    image_file_id: str | None = data.get("image_file_id")
    prompt = message.text.strip()  # type: ignore[union-attr]

    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=model_key,
        mode=data.get("mode", "text"),
        aspect_ratio=aspect_ratio,
        quality=quality,
        count=count,
        base_prompt=prompt,
        reference_file_id=image_file_id,
    )
    await state.update_data(image_session_id=image_session.id)

    reference_url = await _telegram_file_url(bot, image_file_id)
    if not _supports_img2img(model_key):
        reference_url = None

    await _launch_session_generation(
        source_message=message,
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt,
        action_type=ImageGenerationAction.initial,
        reference_url=reference_url,
        parent_generation_id=None,
        launching_text=f"⏳ <b>Запускаю генерацию...</b>\n<code>{model_key}</code>",
        queued_text="⏳ <b>Задача запущена.</b> Пришлю результат, когда генерация будет готова.",
    )


# ── Active image session ──────────────────────────────────────────────────────

@router.message(ImageGenFSM.session_active, F.text)
async def handle_session_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    image_session, _ = await _resolve_image_session(session, db_user, state)

    if not image_session:
        await message.answer("Серия не найдена. Начни новую генерацию.", reply_markup=main_menu_kb())
        await state.clear()
        return

    prompt = message.text.strip()
    is_remix = bool(data.get("remix_mode"))
    parent_id = data.get("remix_parent_generation_id") or image_session.last_generation_id

    reference_url = await _session_reference_url(
        bot,
        image_session,
        prefer_last_result=is_remix,
    )

    await _launch_session_generation(
        source_message=message,
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt,
        action_type=ImageGenerationAction.remix if is_remix else ImageGenerationAction.initial,
        reference_url=reference_url,
        parent_generation_id=parent_id,
        launching_text=f"⏳ <b>Генерирую в активной серии...</b>\n<code>{image_session.model}</code>",
        queued_text="⏳ <b>Задача запущена.</b> Результат придёт сюда автоматически.",
    )


@router.message(ImageGenFSM.session_active, F.photo)
async def handle_session_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)

    if not image_session:
        await message.answer("Серия не найдена. Начни новую генерацию.", reply_markup=main_menu_kb())
        await state.clear()
        return

    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    await repo.update_image_session_reference(session, image_session.id, best[0].file_id)
    await state.update_data(image_file_id=best[0].file_id, image_session_id=image_session.id)

    await message.answer(
        "✅ Новый референс сохранён для активной серии. Теперь напиши, что изменить.",
        reply_markup=image_session_kb(image_session.last_generation_id),
    )


# ── Session callbacks ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("img_session:remix:"))
async def cb_image_session_remix(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    gen_id_raw = call.data.split(":")[-1]  # type: ignore[union-attr]
    gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None

    image_session, parent_id = await _resolve_image_session(session, db_user, state, gen_id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        remix_mode=True,
        remix_parent_generation_id=parent_id or image_session.last_generation_id,
    )
    await call.message.answer(  # type: ignore[union-attr]
        "✨ Напиши, что изменить в текущей картинке.\n"
        "Например: <i>поменяй позу, добавь дождь, сделай другой свет</i>"
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_session:repeat:"))
async def cb_image_session_repeat(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    gen_id_raw = call.data.split(":")[-1]  # type: ignore[union-attr]
    gen_id = int(gen_id_raw) if gen_id_raw.isdigit() and int(gen_id_raw) > 0 else None

    image_session, parent_id = await _resolve_image_session(session, db_user, state, gen_id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    last_gen = await repo.get_last_session_generation(session, image_session.id)
    if not last_gen:
        await call.answer("Нечего повторять", show_alert=True)
        return

    reference_url = await _session_reference_url(bot, image_session, prefer_last_result=False)

    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=last_gen.prompt,
        action_type=ImageGenerationAction.repeat,
        reference_url=reference_url,
        parent_generation_id=parent_id or last_gen.id,
        launching_text="🔁 <b>Повторяю последнюю генерацию...</b>",
        queued_text="⏳ <b>Повтор запущен.</b> Результат придёт сюда автоматически.",
    )
    await call.answer()


@router.callback_query(F.data == "img_session:settings")
async def cb_image_session_settings(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(image_session_id=image_session.id)

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset:back:"))
async def cb_image_settings_back(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)

    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    await state.set_state(ImageGenFSM.session_active)

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎨 <b>Серия активна.</b>\n\n"
        "Отправь новый текст или фото. Настройки сохраняются.",
        reply_markup=image_session_kb(image_session.last_generation_id),
    )
    await call.answer()


@router.callback_query(F.data == "img_session:new")
async def cb_image_session_new(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    await repo.archive_active_image_sessions(session, db_user.id)
    await state.clear()
    await cb_image_menu(call, session, state)


@router.callback_query(F.data.startswith("img_session:animate:"))
async def cb_image_session_animate(call: CallbackQuery) -> None:
    await call.answer("Оживление подключим следующим шагом через image-to-video.", show_alert=True)


# ── Session settings actions ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("img_sset:ratio:"))
async def cb_image_settings_ratio(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    ratios = IMAGE_CAPS.get(image_session.model, {}).get("aspect_ratios", [])
    if not ratios:
        await call.answer("У модели нет выбора формата", show_alert=True)
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📐 <b>Выбери формат для активной серии</b>",
        reply_markup=_session_ratio_choices_kb(image_session),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset_ratio:set:"))
async def cb_image_settings_ratio_set(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    _, _, session_id_raw, ratio = call.data.split(":", 3)  # type: ignore[union-attr]
    image_session = await repo.get_image_session(session, int(session_id_raw), db_user.id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    image_session.aspect_ratio = ratio
    await session.commit()
    await state.update_data(image_session_id=image_session.id, aspect_ratio=ratio)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id),
    )
    await call.answer("Формат обновлён")


@router.callback_query(F.data.startswith("img_sset:quality:"))
async def cb_image_settings_quality(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    if not IMAGE_CAPS.get(image_session.model, {}).get("has_quality"):
        await call.answer("У модели нет настройки качества", show_alert=True)
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "💎 <b>Выбери качество для активной серии</b>",
        reply_markup=_session_quality_choices_kb(image_session),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset_quality:set:"))
async def cb_image_settings_quality_set(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    _, _, session_id_raw, quality = call.data.split(":", 3)  # type: ignore[union-attr]
    image_session = await repo.get_image_session(session, int(session_id_raw), db_user.id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    image_session.quality = quality
    await session.commit()
    await state.update_data(image_session_id=image_session.id, quality=quality)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id),
    )
    await call.answer("Качество обновлено")


@router.callback_query(F.data.startswith("img_sset:count:"))
async def cb_image_settings_count(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    image_session, _ = await _resolve_image_session(session, db_user, state)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    counts = IMAGE_CAPS.get(image_session.model, {}).get("counts", [1])
    if len(counts) <= 1:
        await call.answer("У модели фиксированное количество изображений", show_alert=True)
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🔢 <b>Выбери количество изображений для серии</b>",
        reply_markup=_session_count_choices_kb(image_session),
    )
    await call.answer()


@router.callback_query(F.data.startswith("img_sset_count:set:"))
async def cb_image_settings_count_set(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    _, _, session_id_raw, count_raw = call.data.split(":", 3)  # type: ignore[union-attr]
    image_session = await repo.get_image_session(session, int(session_id_raw), db_user.id)
    if not image_session:
        await call.answer("Активная серия не найдена", show_alert=True)
        return

    count = int(count_raw)
    image_session.count = count
    await session.commit()
    await state.update_data(image_session_id=image_session.id, count=count)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        _session_settings_text(image_session),
        reply_markup=image_session_settings_kb(image_session.id),
    )
    await call.answer("Количество обновлено")


@router.callback_query(F.data.startswith("img_sset:model:"))
async def cb_image_settings_model(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
) -> None:
    await repo.archive_active_image_sessions(session, db_user.id)
    await state.clear()
    await cb_image_menu(call, session, state)


# ── Regen ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("regen:image:"))
async def cb_regen_image(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    prev = await repo.get_generation_by_id(session, gen_id)
    if not prev:
        await call.answer("Генерация не найдена", show_alert=True)
        return
    await state.update_data(model_key=prev.model, credits=prev.credits_spent)
    await state.set_state(ImageGenFSM.prompt_input)
    await call.message.answer(prev.prompt)  # type: ignore[union-attr]
    await call.answer()
