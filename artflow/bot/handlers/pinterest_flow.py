# bot/handlers/pinterest_flow.py
"""Telegram Pinterest Flow — a text-only parity of the Mini App Pinterest Service.

Pinterest is a standalone Service domain. This flow never touches trends,
trend_id, UserPrompt or published prompt recipes; it reuses the exact same
backend pipeline as the Mini App (``create_image_generation`` + the Pinterest
service provider/persistence contract).
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import mirror_telegram_file
from api.trend_assets import sign_uploaded_asset
from bot.keyboards.main_menu import back_to_menu_kb
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="pinterest_flow")

HEIGHT_MIN_CM = 120
HEIGHT_MAX_CM = 230
WEIGHT_MIN_KG = 30
WEIGHT_MAX_KG = 250
MAX_EXTRA_IDENTITY_PHOTOS = 5


class PinterestFlow(StatesGroup):
    waiting_scene_reference = State()
    waiting_identity_reference = State()
    waiting_extra_references = State()
    waiting_height = State()
    waiting_weight = State()
    confirmation = State()


# ── Pure helpers (unit-testable) ─────────────────────────────────────────────

def _to_int(value: Any) -> int | None:
    try:
        return int(str(value or "").strip())
    except (TypeError, ValueError):
        return None


def parse_height(value: Any) -> int | None:
    parsed = _to_int(value)
    if parsed is None or not (HEIGHT_MIN_CM <= parsed <= HEIGHT_MAX_CM):
        return None
    return parsed


def parse_weight(value: Any) -> int | None:
    parsed = _to_int(value)
    if parsed is None or not (WEIGHT_MIN_KG <= parsed <= WEIGHT_MAX_KG):
        return None
    return parsed


def reference_asset_ids(
    scene_asset_id: str | None,
    identity_asset_id: str | None,
    extra_asset_ids: list[str] | None,
) -> list[str]:
    """Frontend contract order: SCENE, IDENTITY, extra IDENTITY_EVIDENCE."""
    result: list[str] = []
    for value in (scene_asset_id, identity_asset_id):
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    for value in extra_asset_ids or []:
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def flow_missing_fields(data: dict) -> set[str]:
    """Payload fields required before a Pinterest run is allowed."""
    missing: set[str] = set()
    if not str(data.get("scene_asset_id") or "").strip():
        missing.add("scene")
    if not str(data.get("identity_asset_id") or "").strip():
        missing.add("identity")
    if parse_height(data.get("height_cm")) is None:
        missing.add("height")
    if parse_weight(data.get("weight_kg")) is None:
        missing.add("weight")
    return missing


def confirmation_text(data: dict, price_credits: float | None) -> str:
    price = price_credits if price_credits is not None else 0
    return (
        "📌 <b>Pinterest</b>\n\n"
        "РЕФЕРЕНС ✅\n\n"
        "ТЫ ✅\n\n"
        f"Рост:\n{int(data.get('height_cm') or 0)} см\n\n"
        f"Вес:\n{int(data.get('weight_kg') or 0)} кг\n\n"
        f"Стоимость:\n{price:g} 💎\n\n"
        "Создать?"
    )


def confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✨ Создать", callback_data="pinterest:confirm"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="pinterest:cancel"))
    return builder.as_markup()


def _extra_prompt_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить фото", callback_data="pinterest:extra:add"))
    builder.row(InlineKeyboardButton(text="➡️ Продолжить", callback_data="pinterest:extra:done"))
    return builder.as_markup()


def _extra_prompt_text() -> str:
    return (
        "Можно добавить дополнительные фото.\n\n"
        "Они помогают сохранить лицо и пропорции.\n\n"
        f"До {MAX_EXTRA_IDENTITY_PHOTOS} дополнительных фото."
    )


# ── Backend helpers ──────────────────────────────────────────────────────────

async def _pinterest_price(session: AsyncSession) -> float | None:
    from api.pinterest_service_routes import _service_price_credits

    try:
        value = await _service_price_credits(session)
        return float(value or 0)
    except Exception:  # noqa: BLE001 — price availability must not crash the flow
        logger.warning("Pinterest price lookup failed", exc_info=True)
        return None


async def _run_pinterest_service(
    session: AsyncSession,
    user: User,
    data: dict,
    *,
    idempotency_key: str,
) -> dict[str, Any]:
    from api.pinterest_service_routes import launch_pinterest_service

    return await launch_pinterest_service(
        session,
        user,
        idempotency_key=idempotency_key,
        reference_asset_ids=reference_asset_ids(
            data.get("scene_asset_id"),
            data.get("identity_asset_id"),
            data.get("extra_asset_ids"),
        ),
        height_cm=int(data["height_cm"]),
        weight_kg=int(data["weight_kg"]),
    )


async def _photo_asset_id(
    bot: Bot,
    file_id: str,
    *,
    user_id: int,
    file_size: int | None = None,
) -> str | None:
    url = await mirror_telegram_file(bot, file_id)
    if not url:
        return None
    return sign_uploaded_asset(
        user_id=user_id,
        url=url,
        kind="image",
        filename=f"pinterest_{file_id}.jpg",
        content_type="image/jpeg",
        size=file_size or 0,
    )


async def _best_photo_asset_id(bot: Bot, message: Message, user_id: int) -> str | None:
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    return await _photo_asset_id(bot, best.file_id, user_id=user_id, file_size=best.file_size or 0)


# ── Entry ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:pinterest")
@router.message(Command("pinterest"))
async def open_pinterest_flow(
    event: Message | CallbackQuery,
    state: FSMContext,
) -> None:
    await state.clear()
    await state.set_state(PinterestFlow.waiting_scene_reference)
    await state.update_data(extra_asset_ids=[])
    holder = getattr(event, "message", None) or event
    await holder.answer(
        "📌 <b>Pinterest</b>\n\n"
        "Повторите фото в стиле Pinterest.\n\n"
        "Сначала отправьте изображение,\nкоторое хотите повторить.\n\n"
        "Это будет <b>РЕФЕРЕНС</b>:\n"
        "• сцена\n"
        "• поза\n"
        "• свет\n"
        "• композиция\n"
        "• одежда\n\n"
        "<i>Лицо человека с этого изображения не переносится.</i>"
    )
    if isinstance(event, CallbackQuery):
        await safe_answer_callback(event)


@router.message(PinterestFlow.waiting_scene_reference, F.photo)
async def scene_reference_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_user: User,
) -> None:
    asset_id = await _best_photo_asset_id(bot, message, db_user.id)
    if not asset_id:
        await message.answer("Не удалось сохранить фото. Попробуйте ещё раз.")
        return
    await state.update_data(scene_asset_id=asset_id)
    await state.set_state(PinterestFlow.waiting_identity_reference)
    await message.answer("✅ <b>РЕФЕРЕНС добавлен</b>")
    await message.answer(
        "Теперь отправьте <b>ваше фото</b>.\n\n"
        "Оно используется для:\n"
        "✅ лица\n"
        "✅ внешности\n"
        "✅ волос\n"
        "✅ ваших особенностей"
    )


@router.message(PinterestFlow.waiting_scene_reference)
async def scene_ask_photo(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте изображение (фото).")


@router.message(PinterestFlow.waiting_identity_reference, F.photo)
async def identity_reference_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_user: User,
) -> None:
    asset_id = await _best_photo_asset_id(bot, message, db_user.id)
    if not asset_id:
        await message.answer("Не удалось сохранить фото. Попробуйте ещё раз.")
        return
    await state.update_data(identity_asset_id=asset_id)
    await state.set_state(PinterestFlow.waiting_extra_references)
    await message.answer("✅ <b>ТЫ</b> добавлен(а)")
    await message.answer(_extra_prompt_text(), reply_markup=_extra_prompt_keyboard())


@router.message(PinterestFlow.waiting_identity_reference)
async def identity_ask_photo(message: Message) -> None:
    await message.answer("Пожалуйста, отправьте ваше фото.")

# ── Extra identity references ────────────────────────────────────────────────

def _dedupe_extras(values: Any) -> list[str]:
    result: list[str] = []
    for value in values or []:
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


@router.callback_query(F.data == "pinterest:extra:add")
async def extra_add_photo(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    extras = _dedupe_extras(data.get("extra_asset_ids"))
    if len(extras) >= MAX_EXTRA_IDENTITY_PHOTOS:
        await call.answer("Максимум 5 дополнительных фото.", show_alert=True)
        return
    await call.message.answer("Пришлите дополнительное фото:")
    await safe_answer_callback(call)


@router.callback_query(F.data == "pinterest:extra:done")
async def extra_done(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if flow_missing_fields(data) & {"scene", "identity"}:
        await call.answer("Сначала добавьте референс и ваше фото.", show_alert=True)
        return
    await state.set_state(PinterestFlow.waiting_height)
    await call.message.answer("Введите рост в сантиметрах:")
    await safe_answer_callback(call)


@router.message(PinterestFlow.waiting_extra_references, F.photo)
async def extra_photo(
    message: Message,
    state: FSMContext,
    bot: Bot,
    db_user: User,
) -> None:
    data = await state.get_data()
    extras = _dedupe_extras(data.get("extra_asset_ids"))
    if len(extras) >= MAX_EXTRA_IDENTITY_PHOTOS:
        await message.answer(
            "Максимум 5 дополнительных фото уже добавлено.",
            reply_markup=_extra_prompt_keyboard(),
        )
        return
    asset_id = await _best_photo_asset_id(bot, message, db_user.id)
    if not asset_id:
        await message.answer("Не удалось сохранить фото. Попробуйте ещё раз.")
        return
    if asset_id not in extras:
        extras.append(asset_id)
    await state.update_data(extra_asset_ids=extras)
    remaining = MAX_EXTRA_IDENTITY_PHOTOS - len(extras)
    await message.answer(
        f"Фото добавлено ✅ Можно добавить ещё {remaining}."
        if remaining
        else "Фото добавлено ✅",
        reply_markup=_extra_prompt_keyboard(),
    )


@router.message(PinterestFlow.waiting_extra_references)
async def extra_ask_photo(message: Message) -> None:
    await message.answer(_extra_prompt_text(), reply_markup=_extra_prompt_keyboard())


# ── Measurements ─────────────────────────────────────────────────────────────

@router.message(PinterestFlow.waiting_height, F.text)
async def height_input(message: Message, state: FSMContext) -> None:
    height = parse_height(message.text)
    if height is None:
        await message.answer("Введите рост числом от 120 до 230 см. Попробуйте ещё раз:")
        return
    await state.update_data(height_cm=height)
    await state.set_state(PinterestFlow.waiting_weight)
    await message.answer("Введите вес в килограммах:")


@router.message(PinterestFlow.waiting_weight, F.text)
async def weight_input(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    weight = parse_weight(message.text)
    if weight is None:
        await message.answer(
            "Вес должен быть числом от 30 до 250 кг. Попробуйте ещё раз:"
        )
        return
    await state.update_data(weight_kg=weight)

    price = await _pinterest_price(session)
    if price is None or price <= 0:
        # Do not silently mimic unavailability; keep the flow and let the user retry.
        await message.answer("Цена Pinterest AI временно недоступна. Попробуйте чуть позже.")
        await state.set_state(PinterestFlow.waiting_weight)
        return

    data = await state.get_data()
    await state.set_state(PinterestFlow.confirmation)
    await message.answer(confirmation_text(data, price), reply_markup=confirmation_keyboard())


# ── Confirmation / run / cancel ──────────────────────────────────────────────

@router.callback_query(PinterestFlow.confirmation, F.data == "pinterest:confirm")
async def confirm_and_run(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    data = await state.get_data()
    missing = flow_missing_fields(data)
    if missing:
        await call.answer("Сначала заполните все шаги.", show_alert=True)
        return

    await safe_edit_message(call.message, "⏳ <b>Запускаю генерацию…</b>", reply_markup=None)
    idempotency_key = f"pinterest-tg-{secrets.token_hex(16)}"
    try:
        await _run_pinterest_service(
            session,
            db_user,
            data,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # noqa: BLE001 — user-facing error surface
        logger.warning("Pinterest Telegram run failed user=%s err=%s", db_user.id, exc)
        await state.clear()
        await call.message.answer(
            "⚠️ Не удалось запустить генерацию. Кредиты возвращены при необходимости.",
            reply_markup=back_to_menu_kb(),
        )
        await safe_answer_callback(call)
        return

    await state.clear()
    await call.message.answer(
        "✅ <b>Генерация запущена!</b>\n\n"
        "Результат и исходное изображение придут в этот чат.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "pinterest:cancel")
async def cancel_pinterest(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit_message(call.message, "Pinterest flow отменён.", reply_markup=back_to_menu_kb())
    await safe_answer_callback(call)
