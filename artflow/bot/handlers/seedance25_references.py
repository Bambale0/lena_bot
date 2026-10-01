from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import mirror_telegram_file, save_public_file
from api.seedance25_adapter import (
    DISPLAY_NAME,
    MAX_REFERENCE_AUDIOS,
    MAX_REFERENCE_IMAGES,
    MAX_REFERENCE_VIDEOS,
    MODEL_KEY,
    route_for_inputs,
    validate_reference_video_metadata,
)
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db import repository as repo
from db.models import User
from payments import tribute

router = Router(name="seedance25_references")


def _fmt_amount(value: float) -> str:
    return f"{float(value):.2f}".rstrip("0").rstrip(".")


def _recommended_checkout_plan(plans: list[object], deficit: float):
    active = [
        plan
        for plan in plans
        if bool(getattr(plan, "is_active", True))
        and float(getattr(plan, "credits", 0) or 0) > 0
        and float(getattr(plan, "price_rub", 0) or 0) > 0
    ]
    if not active:
        return None
    covering = [
        plan
        for plan in active
        if float(getattr(plan, "credits", 0) or 0) >= float(deficit)
    ]
    if covering:
        return min(
            covering,
            key=lambda plan: (
                float(getattr(plan, "credits", 0) or 0),
                float(getattr(plan, "price_rub", 0) or 0),
                int(getattr(plan, "sort_order", 0) or 0),
            ),
        )
    return max(
        active,
        key=lambda plan: (
            float(getattr(plan, "credits", 0) or 0),
            -float(getattr(plan, "price_rub", 0) or 0),
        ),
    )


def _checkout_kb(plan) -> object:
    builder = InlineKeyboardBuilder()
    key = str(plan.key)
    if settings.TBANK_TERMINAL_KEY and settings.TBANK_PASSWORD:
        builder.row(
            InlineKeyboardButton(
                text=f"💳 Карта | СБП · {_fmt_amount(plan.price_rub)} ₽",
                callback_data=f"topup:rub:{key}",
            )
        )
    if settings.TRIBUTE_API_KEY and tribute.digital_product_for_plan(key) is not None:
        price = tribute.digital_product_price_text(key)
        builder.row(
            InlineKeyboardButton(
                text=f"💵 USD{f' · {price}' if price else ''}",
                callback_data=f"topup:tribute_plan:{key}",
            )
        )
    if settings.CRYPTOBOT_TOKEN:
        builder.row(
            InlineKeyboardButton(
                text="🪙 CryptoBot",
                callback_data=f"topup:crypto_plan:{key}",
            )
        )
    if settings.lava_is_enabled() and settings.lava_offer_id_for_plan(key):
        builder.row(
            InlineKeyboardButton(
                text="💸 Lava",
                callback_data=f"topup:lava_plan:{key}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="✅ Оплатил — продолжить",
            callback_data="s25pay:continue",
        )
    )
    builder.row(
        InlineKeyboardButton(text="← К моделям", callback_data="vid_nav:back"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    )
    return builder.as_markup()


async def _show_checkout(
    call: CallbackQuery,
    state: FSMContext,
    *,
    balance: float,
    minimum: float,
    plan,
) -> None:
    deficit = max(0.0, minimum - balance)
    await state.update_data(
        payment_return_callback="s25pay:continue",
        payment_return_label="🎬 Продолжить Seedance 2.5",
        payment_required_credits=minimum,
        payment_context="seedance25",
    )
    if plan is None:
        text = (
            "💋 <b>Недостаточно для Seedance 2.5</b>\n\n"
            f"Нужно для 5 сек: <b>{minimum:g} 💋</b>\n"
            f"Баланс: <b>{balance:g} 💋</b>\n"
            f"Не хватает: <b>{deficit:g} 💋</b>\n\n"
            "Сейчас нет активного пакета пополнения. Открой баланс позже или вернись к моделям."
        )
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="← К моделям", callback_data="vid_nav:back"))
        builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
        markup = builder.as_markup()
    else:
        text = (
            "💋 <b>Не хватает баланса</b>\n\n"
            f"Нужно для 5 сек: <b>{minimum:g} 💋</b>\n"
            f"Баланс: <b>{balance:g} 💋</b>\n"
            f"Не хватает: <b>{deficit:g} 💋</b>\n\n"
            f"Подойдёт пакет: <b>{_fmt_amount(plan.credits)} 💋</b> "
            f"за <b>{_fmt_amount(plan.price_rub)} ₽</b>.\n"
            "Оплати прямо здесь и нажми «Оплатил — продолжить»."
        )
        markup = _checkout_kb(plan)
    await safe_edit_message(call.message, text, reply_markup=markup)
    await safe_answer_callback(call)


def _as_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value if item]


def _counts(data: dict) -> tuple[int, int, int]:
    return (
        len([item for item in (data.get("ref_file_ids") or []) if item]),
        len(_as_list(data.get("reference_video_url"))),
        len([item for item in (data.get("audio_ids") or []) if item]),
    )


def _kb(*, require_image_reference: bool = False) -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Референсы готовы", callback_data="s25ref:done"))
    if not require_image_reference:
        builder.row(InlineKeyboardButton(text="➡️ Без референсов", callback_data="s25ref:none"))
    builder.row(InlineKeyboardButton(text="🗑 Очистить", callback_data="s25ref:clear"))
    builder.row(InlineKeyboardButton(text="← Назад", callback_data="vid_nav:back"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _kb_for_data(data: dict) -> object:
    return _kb(require_image_reference=bool(data.get("feed_force_reference")))


def _text(data: dict) -> str:
    images, videos, audios = _counts(data)
    feed_requirement = (
        "\n\n🔒 Для повтора тренда добавь хотя бы одно своё фото."
        if data.get("feed_force_reference")
        else ""
    )
    return (
        "🌱 <b>Seedance 2.5</b>\n\n"
        "Просто пришли нужные референсы — режим выбирать не надо:\n"
        "• без референсов → текст в видео\n"
        "• любое фото, видео или аудио → мультимодальные референсы\n\n"
        f"🖼 Фото: <b>{images}/{MAX_REFERENCE_IMAGES}</b>\n"
        f"🎬 Видео: <b>{videos}/{MAX_REFERENCE_VIDEOS}</b>\n"
        f"🎵 Аудио: <b>{audios}/{MAX_REFERENCE_AUDIOS}</b>\n\n"
        "Можно смешивать фото, видео и аудио в одной генерации."
        + feed_requirement
    )


async def _go_params(call: CallbackQuery, state: FSMContext) -> None:
    from bot.handlers import video_gen as legacy

    data = await state.get_data()
    images, videos, audios = _counts(data)
    if data.get("feed_force_reference") and images < 1:
        await safe_answer_callback(
            call,
            "Для повтора тренда нужен хотя бы один фото-референс.",
            show_alert=True,
        )
        return
    route = route_for_inputs(
        images=[str(item) for item in (data.get("ref_file_ids") or []) if item],
        videos=_as_list(data.get("reference_video_url")),
        audios=[str(item) for item in (data.get("audio_ids") or []) if item],
    )
    await state.update_data(
        mode=route,
        aspect_ratio=data.get("aspect_ratio"),
    )
    updated = await state.get_data()
    await state.set_state(VideoGenFSM.params_select)
    await safe_edit_message(
        call.message,
        f"⚙️ <b>Параметры</b> · {DISPLAY_NAME}\n\n"
        f"Референсы: фото {images}, видео {videos}, аудио {audios}.\n"
        "Seedance сам выберет внутренний сценарий по этим материалам.",
        reply_markup=legacy._video_params_reply_markup(MODEL_KEY, updated),
    )
    await safe_answer_callback(call)


async def _enter_seedance25_flow(
    call: CallbackQuery,
    state: FSMContext,
    *,
    model_cost,
) -> None:
    old = await state.get_data()
    await state.set_state(VideoGenFSM.seedance25_reference_upload)
    await state.update_data(
        model_key=MODEL_KEY,
        credits=float(model_cost.credits),
        duration=5,
        aspect_ratio="adaptive",
        resolution="720p",
        mode="text",
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        character_ids=[],
        grok_mode=None,
        payment_return_callback=None,
        payment_return_label=None,
        payment_required_credits=None,
        payment_context=None,
        wizard_review_enabled=bool(old.get("wizard_review_enabled", True)),
        wizard_scenario=old.get("wizard_scenario", "advanced"),
    )
    updated = await state.get_data()
    await safe_edit_message(
        call.message,
        _text(updated),
        reply_markup=_kb_for_data(updated),
    )
    await safe_answer_callback(call)


async def _seedance25_cost(session: AsyncSession):
    return await repo.resolve_video_model_cost(
        session,
        MODEL_KEY,
        duration=5,
        resolution="720p",
    )


@router.callback_query(VideoGenFSM.model_select, F.data == f"vid_model:{MODEL_KEY}")
async def choose_seedance25(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    model_cost = await _seedance25_cost(session)
    if not model_cost:
        await safe_answer_callback(call, "Модель временно недоступна", show_alert=True)
        return
    minimum = float(model_cost.credits) * 5
    balance = float(db_user.credits)
    if balance < minimum:
        plan = _recommended_checkout_plan(
            await repo.get_active_price_plans(session),
            minimum - balance,
        )
        await _show_checkout(
            call,
            state,
            balance=balance,
            minimum=minimum,
            plan=plan,
        )
        return

    await _enter_seedance25_flow(call, state, model_cost=model_cost)


@router.callback_query(VideoGenFSM.model_select, F.data == "s25pay:continue")
async def continue_seedance25_after_payment(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    model_cost = await _seedance25_cost(session)
    if not model_cost:
        await safe_answer_callback(call, "Модель временно недоступна", show_alert=True)
        return
    minimum = float(model_cost.credits) * 5
    balance = float(db_user.credits)
    if balance < minimum:
        plan = _recommended_checkout_plan(
            await repo.get_active_price_plans(session),
            minimum - balance,
        )
        await _show_checkout(
            call,
            state,
            balance=balance,
            minimum=minimum,
            plan=plan,
        )
        return
    await _enter_seedance25_flow(call, state, model_cost=model_cost)


@router.callback_query(VideoGenFSM.seedance25_reference_upload, F.data == "s25ref:none")
async def no_seedance25_refs(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if data.get("feed_force_reference"):
        await safe_answer_callback(
            call,
            "Для повтора тренда сначала загрузи своё фото/референс.",
            show_alert=True,
        )
        return
    await state.update_data(
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
        mode="text",
    )
    await _go_params(call, state)


@router.callback_query(VideoGenFSM.seedance25_reference_upload, F.data == "s25ref:clear")
async def clear_seedance25_refs(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(
        image_url=None,
        image_file_id=None,
        ref_file_ids=[],
        reference_video_url=None,
        audio_ids=[],
    )
    updated = await state.get_data()
    await safe_edit_message(call.message, _text(updated), reply_markup=_kb_for_data(updated))
    await safe_answer_callback(call, "Очищено")


@router.message(VideoGenFSM.seedance25_reference_upload, F.photo)
async def add_seedance25_photo(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("ref_file_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_IMAGES:
        await message.answer(f"Лимит фото — {MAX_REFERENCE_IMAGES}.", reply_markup=_kb_for_data(data))
        return
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    if best.file_id not in refs:
        refs.append(best.file_id)
    await state.update_data(ref_file_ids=refs, image_file_id=refs[0], image_url=None)
    updated = await state.get_data()
    await message.answer(_text(updated), reply_markup=_kb_for_data(updated))


@router.message(VideoGenFSM.seedance25_reference_upload, F.video)
async def add_seedance25_video(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = _as_list(data.get("reference_video_url"))
    if len(refs) >= MAX_REFERENCE_VIDEOS:
        await message.answer(f"Лимит видео — {MAX_REFERENCE_VIDEOS}.", reply_markup=_kb_for_data(data))
        return

    video = message.video
    validation_error = validate_reference_video_metadata(
        width=getattr(video, "width", None),
        height=getattr(video, "height", None),
        duration_seconds=getattr(video, "duration", None),
    )
    if validation_error:
        await message.answer(f"❌ {validation_error}", reply_markup=_kb_for_data(data))
        return

    url = await mirror_telegram_file(bot, video.file_id, is_video=True)  # type: ignore[union-attr]
    if url not in refs:
        refs.append(url)
    await state.update_data(reference_video_url=refs)
    updated = await state.get_data()
    await message.answer(_text(updated), reply_markup=_kb_for_data(updated))


async def _save_audio(message: Message, bot: Bot) -> str | None:
    media = message.audio or message.voice or message.document
    if media is None:
        return None
    mime_type = str(getattr(media, "mime_type", "") or "").lower()
    if message.document and not mime_type.startswith("audio/"):
        return None
    telegram_file = await bot.get_file(media.file_id)
    downloaded = await bot.download_file(telegram_file.file_path)
    raw = downloaded.read() if hasattr(downloaded, "read") else bytes(downloaded)
    return save_public_file(raw, mime_type or "audio/ogg", subdir="seedance25/audio")


@router.message(VideoGenFSM.seedance25_reference_upload, F.audio | F.voice | F.document)
async def add_seedance25_audio(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    refs = [str(item) for item in (data.get("audio_ids") or []) if item]
    if len(refs) >= MAX_REFERENCE_AUDIOS:
        await message.answer(f"Лимит аудио — {MAX_REFERENCE_AUDIOS}.", reply_markup=_kb_for_data(data))
        return
    url = await _save_audio(message, bot)
    if not url:
        await message.answer("Пришли аудиофайл или voice-сообщение.", reply_markup=_kb_for_data(data))
        return
    if url not in refs:
        refs.append(url)
    await state.update_data(audio_ids=refs)
    updated = await state.get_data()
    await message.answer(_text(updated), reply_markup=_kb_for_data(updated))


@router.callback_query(VideoGenFSM.seedance25_reference_upload, F.data == "s25ref:done")
async def finish_seedance25_refs(call: CallbackQuery, state: FSMContext) -> None:
    await _go_params(call, state)


@router.message(VideoGenFSM.seedance25_reference_upload)
async def invalid_seedance25_ref(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    text = (
        "Для повтора тренда сначала пришли своё фото-референс."
        if data.get("feed_force_reference")
        else "Здесь можно отправить фото, видео, аудио/voice или нажать «Без референсов»."
    )
    await message.answer(text, reply_markup=_kb_for_data(data))
