from __future__ import annotations

import asyncio
import html
import logging
import secrets
from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.pinterest_contract import pinterest_provider_context
from api.public_files import public_url_is_available
from api.repeat_runtime import repeat_launch_context
from bot.handlers import image_gen
from bot.keyboards.models import IMAGE_CAPS
from bot.utils.telegram_ui import safe_answer_callback
from core.config import settings
from db import repository as repo
from db.models import GenerationStatus, GenerationType, ImageGenerationAction, User
from db.repeat_lookup import (
    find_repeat_by_confirm_key as _find_repeat_by_confirm_key,
    get_repeat_task_by_any_id,
    parse_input_params,
)

logger = logging.getLogger(__name__)
router = Router(name="safe_image_repeat")


class SafeRepeatFSM(StatesGroup):
    confirming = State()
    editing_prompt = State()
    collecting_refs = State()


_confirm_locks: dict[tuple[int, str], asyncio.Lock] = {}


def _unique_urls(values: Any) -> list[str]:
    if isinstance(values, str):
        source = [values]
    elif isinstance(values, (list, tuple)):
        source = list(values)
    else:
        source = []
    result: list[str] = []
    for value in source:
        clean = str(value or "").strip()
        if clean and clean not in result:
            result.append(clean)
    return result


def available_reference_images(reference_images: list[str]) -> tuple[list[str], list[str]]:
    available: list[str] = []
    missing: list[str] = []
    for url in _unique_urls(reference_images):
        (available if public_url_is_available(url) else missing).append(url)
    return available, missing


def pinterest_repeat_contract(snapshot: dict[str, Any]) -> dict[str, Any]:
    scene = str(snapshot.get("scene_reference") or "").strip()
    identity = str(snapshot.get("identity_reference") or "").strip()
    evidence = _unique_urls(snapshot.get("identity_evidence"))

    logical: list[str] = []
    roles: list[str] = []
    if scene:
        logical.append(scene)
        roles.append("scene")
    if identity:
        logical.append(identity)
        roles.append("identity")
    for item in evidence:
        if item not in logical:
            logical.append(item)
            roles.append("identity_evidence")

    provider_refs = [item for item in (identity, scene) if item]
    return {
        "flow": "pinterest",
        "scene_reference": scene or None,
        "identity_reference": identity or None,
        "identity_evidence": evidence,
        "reference_images": logical,
        "reference_roles": roles,
        "provider_reference_images": provider_refs,
        "trend_id": snapshot.get("trend_id"),
        "pinterest_source_url": snapshot.get("pinterest_source_url") or scene or None,
    }


async def find_repeat_by_confirm_key(
    session: AsyncSession,
    *,
    user_id: int,
    confirm_key: str | None,
):
    return await _find_repeat_by_confirm_key(session, user_id=user_id, confirm_key=confirm_key)


def _is_image(generation: Any) -> bool:
    return str(getattr(getattr(generation, "gen_type", None), "value", getattr(generation, "gen_type", ""))) == GenerationType.image.value


def _is_failed(generation: Any) -> bool:
    return str(getattr(getattr(generation, "status", None), "value", getattr(generation, "status", ""))) == GenerationStatus.failed.value


def _is_admin(user: User | Any) -> bool:
    return bool(getattr(user, "tg_id", None) in settings.ADMIN_IDS)


def _raw_repeat_id(data: str | None, prefix: str) -> str:
    return str(data or "").removeprefix(prefix).strip()


def _max_refs(model_key: str) -> int:
    return max(1, int(IMAGE_CAPS.get(model_key, {}).get("max_refs", 1) or 1))


def _confirmation_keyboard(data: dict[str, Any]) -> InlineKeyboardMarkup:
    raw = str(data.get("repeat_raw_task_id") or data.get("repeat_source_generation_id") or "")
    cost = float(data.get("repeat_cost") or 0)
    builder = InlineKeyboardBuilder()
    label = "✅ Запустить бесплатно" if cost <= 0 else f"✅ Запустить за {cost:g} 💋"
    builder.row(InlineKeyboardButton(text=label, callback_data=f"repeat_run_confirm_{raw}"))
    if not data.get("repeat_is_pinterest"):
        builder.row(InlineKeyboardButton(text="✏️ Изменить промпт", callback_data=f"repeat_edit_prompt_{raw}"))
    if bool(data.get("repeat_supports_refs")):
        builder.row(InlineKeyboardButton(text="📎 Добавить референсы", callback_data=f"repeat_add_refs_{raw}"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"repeat_run_cancel_{raw}"))
    return builder.as_markup()


def _confirmation_text(data: dict[str, Any]) -> str:
    refs = _unique_urls(data.get("repeat_reference_images"))
    missing = _unique_urls(data.get("repeat_missing_references"))
    cost = float(data.get("repeat_cost") or 0)
    prompt = str(data.get("repeat_prompt") or "").strip()
    prompt_line = "🔒 Скрытый трендовый промпт" if data.get("repeat_prompt_hidden") else html.escape(prompt)
    price_label = "бесплатно" if cost <= 0 else f"{cost:g} 💋"
    lines = [
        "🔁 <b>Повторить эту генерацию?</b>",
        "",
        f"• Модель: <b>{html.escape(image_gen.get_image_model_label(str(data.get('repeat_model_key') or '')))}</b>",
        f"• Формат: <b>{html.escape(str(data.get('repeat_aspect_ratio') or 'авто'))}</b>",
        f"• Качество: <b>{html.escape(str(data.get('repeat_quality') or 'по умолчанию'))}</b>",
        f"• Референсы: <b>{len(refs)}</b>",
        f"• Цена: <b>{price_label}</b>",
        "",
        f"📝 {prompt_line}",
        "",
        "💋 Списание произойдёт только после подтверждения запуска.",
    ]
    if missing:
        lines.extend(["", "⚠️ Часть старых фото уже очищена. Добавьте фото заново."])
    if data.get("repeat_reference_required") and not refs:
        lines.extend(["", "⚠️ Для этой модели сначала отправьте фото."])
    if data.get("repeat_is_pinterest"):
        lines.extend(["", "📌 Pinterest: сцена и личность сохраняются как разные роли."])
    return "\n".join(lines)


async def _source_session_snapshot(
    session: AsyncSession,
    bot: Bot,
    generation: Any,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], Any | None]:
    source_session = None
    if getattr(generation, "image_session_id", None):
        source_session = await repo.get_image_session(session, generation.image_session_id, generation.user_id)

    model_key = str(payload.get("img_service") or payload.get("model") or generation.model)
    prompt = str(payload.get("prompt") or generation.prompt or "")
    ratio = payload.get("img_ratio") or getattr(source_session, "aspect_ratio", None)
    quality = str(payload.get("img_quality") or getattr(source_session, "quality", None) or "basic")
    count = int(payload.get("img_count") or getattr(source_session, "count", 1) or 1)
    refs = _unique_urls(payload.get("reference_images"))
    if not refs and source_session is not None:
        resolved = await image_gen._session_reference_url(bot, source_session, prefer_last_result=False, state=None)
        refs = _unique_urls(resolved)

    if payload.get("flow") == "pinterest":
        pinterest = pinterest_repeat_contract(payload)
        refs = pinterest["reference_images"] or refs
    else:
        pinterest = {}

    return (
        {
            **payload,
            **pinterest,
            "model_key": model_key,
            "prompt": prompt,
            "aspect_ratio": ratio,
            "quality": quality,
            "count": count,
            "reference_images": refs,
        },
        source_session,
    )


async def _prepare_repeat(
    *,
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
    raw_task_id: str,
) -> None:
    generation = await get_repeat_task_by_any_id(session, raw_task_id)
    logger.info(
        "Repeat open requested: telegram_id=%s raw_task_id=%s resolved_task_id=%s",
        getattr(call.from_user, "id", None),
        raw_task_id,
        getattr(generation, "task_id", None) if generation else None,
    )
    if not generation or not _is_image(generation):
        await safe_answer_callback(call, "Не удалось найти данные для повтора.", show_alert=True)
        return
    if getattr(generation, "user_id", None) != db_user.id:
        await safe_answer_callback(call, "Эту генерацию нельзя повторить из приватного результата.", show_alert=True)
        return

    payload = parse_input_params(getattr(generation, "input_params", None))
    snapshot, _ = await _source_session_snapshot(session, bot, generation, payload)
    model_key = str(snapshot["model_key"])
    available_refs, missing_refs = available_reference_images(_unique_urls(snapshot.get("reference_images")))

    model_cost = await repo.resolve_image_model_cost(session, model_key, quality=str(snapshot.get("quality") or "basic"))
    if not model_cost:
        await safe_answer_callback(call, "Модель исходной генерации сейчас недоступна.", show_alert=True)
        return
    cost = 0.0 if _is_admin(db_user) else float(model_cost.credits or 0)
    public_id = str(payload.get("public_task_id") or raw_task_id or generation.id)
    confirm_key = f"repeat-{generation.id}-{db_user.id}-{secrets.token_urlsafe(8)}"
    is_pinterest = snapshot.get("flow") == "pinterest"

    await state.clear()
    await state.set_state(SafeRepeatFSM.confirming)
    await state.update_data(
        repeat_source_generation_id=int(generation.id),
        repeat_raw_task_id=public_id,
        repeat_model_key=model_key,
        repeat_prompt=str(snapshot.get("prompt") or generation.prompt or ""),
        repeat_prompt_hidden=bool(snapshot.get("hidden_prompt")) or is_pinterest,
        repeat_aspect_ratio=snapshot.get("aspect_ratio"),
        repeat_quality=str(snapshot.get("quality") or "basic"),
        repeat_count=max(1, int(snapshot.get("count") or 1)),
        repeat_reference_images=available_refs,
        repeat_missing_references=missing_refs,
        repeat_reference_required=image_gen._requires_reference_image(model_key),
        repeat_supports_refs=image_gen._supports_img2img(model_key),
        repeat_max_refs=_max_refs(model_key),
        repeat_source_feed_gen_id=getattr(generation, "source_feed_gen_id", None),
        repeat_confirm_key=confirm_key,
        repeat_cost=cost,
        repeat_is_admin=_is_admin(db_user),
        repeat_is_pinterest=is_pinterest,
        repeat_scene_reference=snapshot.get("scene_reference"),
        repeat_identity_reference=snapshot.get("identity_reference"),
        repeat_identity_evidence=_unique_urls(snapshot.get("identity_evidence")),
        repeat_trend_id=snapshot.get("trend_id"),
        repeat_pinterest_source_url=snapshot.get("pinterest_source_url"),
    )
    data = await state.get_data()
    await call.message.answer(_confirmation_text(data), reply_markup=_confirmation_keyboard(data))  # type: ignore[union-attr]
    await safe_answer_callback(call, "Проверь параметры повтора")


@router.callback_query(F.data.startswith("repeat_run_confirm_"))
async def confirm_repeat(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    await safe_answer_callback(call, "Повтор запускаю")
    data = await state.get_data()
    source_id = int(data.get("repeat_source_generation_id") or 0)
    confirm_key = str(data.get("repeat_confirm_key") or "")
    if not source_id or not confirm_key:
        await call.message.answer("Сессия подтверждения устарела. Нажмите «Повторить генерацию» ещё раз.")  # type: ignore[union-attr]
        return

    lock_key = (db_user.id, confirm_key)
    lock = _confirm_locks.setdefault(lock_key, asyncio.Lock())
    async with lock:
        existing = await find_repeat_by_confirm_key(session, user_id=db_user.id, confirm_key=confirm_key)
        if existing is not None and not _is_failed(existing):
            await call.message.answer(f"✅ Повтор уже поставлен в очередь. ID: img_{existing.id}")  # type: ignore[union-attr]
            return

        source = await repo.get_generation_by_id(session, source_id)
        if not source or source.user_id != db_user.id or not _is_image(source):
            await call.message.answer("❌ Исходная генерация больше недоступна.")  # type: ignore[union-attr]
            return

        references, missing = available_reference_images(_unique_urls(data.get("repeat_reference_images")))
        if missing:
            await state.update_data(repeat_reference_images=references, repeat_missing_references=missing)
        if data.get("repeat_reference_required") and not references:
            await call.message.answer("❌ Для этой модели сначала отправьте фото.")  # type: ignore[union-attr]
            return

        model_key = str(data.get("repeat_model_key") or source.model)
        prompt = str(data.get("repeat_prompt") or source.prompt or "").strip()
        if not prompt:
            await call.message.answer("❌ Промпт исходной генерации недоступен.")  # type: ignore[union-attr]
            return

        logical_refs = list(references)
        provider_refs = list(references)
        provider_contract: dict[str, Any] | None = None
        metadata: dict[str, Any] = {
            "repeat_source_task_id": str(data.get("repeat_raw_task_id") or source_id),
            "repeat_source_generation_id": source_id,
            "repeat_confirm_key": confirm_key,
            "action_type": "repeat",
            "parent_generation_id": source_id,
            "source_feed_gen_id": data.get("repeat_source_feed_gen_id"),
            "prompt": prompt,
            "img_service": model_key,
            "img_ratio": data.get("repeat_aspect_ratio"),
            "img_quality": data.get("repeat_quality"),
            "img_count": int(data.get("repeat_count") or 1),
        }

        if data.get("repeat_is_pinterest"):
            provider_contract = pinterest_repeat_contract(
                {
                    "flow": "pinterest",
                    "scene_reference": data.get("repeat_scene_reference"),
                    "identity_reference": data.get("repeat_identity_reference"),
                    "identity_evidence": data.get("repeat_identity_evidence"),
                    "trend_id": data.get("repeat_trend_id"),
                    "pinterest_source_url": data.get("repeat_pinterest_source_url"),
                }
            )
            logical_refs = provider_contract["reference_images"]
            provider_refs, provider_missing = available_reference_images(provider_contract["provider_reference_images"])
            if provider_missing or len(provider_refs) < 2:
                await call.message.answer(  # type: ignore[union-attr]
                    "❌ Для Pinterest-повтора нужны доступные фото сцены и личности. Добавьте фото заново."
                )
                return
            metadata.update(provider_contract)
        else:
            metadata["reference_images"] = logical_refs

        image_session = await repo.create_image_session(
            session=session,
            user_id=db_user.id,
            model=model_key,
            mode="image" if provider_refs else "text",
            aspect_ratio=data.get("repeat_aspect_ratio"),
            quality=str(data.get("repeat_quality") or "basic"),
            count=max(1, int(data.get("repeat_count") or 1)),
            base_prompt=prompt,
            reference_file_id=None,
            reference_file_ids=None,
            reference_url=logical_refs[0] if logical_refs else None,
            reference_urls=logical_refs or None,
        )

        logger.info(
            "Repeat launch: telegram_id=%s source_task=%s model=%s refs=%s cost=%s",
            getattr(call.from_user, "id", None),
            data.get("repeat_raw_task_id"),
            model_key,
            len(provider_refs),
            data.get("repeat_cost"),
        )
        try:
            with repeat_launch_context(
                input_params_extra=metadata,
                credits_override=0.0 if data.get("repeat_is_admin") else None,
            ), pinterest_provider_context(provider_contract):
                launched = await image_gen._launch_session_generation(
                    source_message=call.message,  # type: ignore[arg-type]
                    state=state,
                    session=session,
                    db_user=db_user,
                    image_session=image_session,
                    prompt=prompt,
                    action_type=ImageGenerationAction.repeat,
                    reference_url=provider_refs or None,
                    parent_generation_id=source_id,
                    source_feed_gen_id=data.get("repeat_source_feed_gen_id"),
                    launching_text="🔁 <b>Повторяю генерацию...</b>",
                    queued_text="⏳ <b>Повтор запущен.</b> Результат придёт сюда автоматически.",
                )
        except Exception:
            logger.exception(
                "Repeat image generation failed: telegram_id=%s task_id=%s",
                getattr(call.from_user, "id", None),
                data.get("repeat_raw_task_id"),
            )
            raise

        if launched:
            await state.clear()
            spent = "0 💋" if data.get("repeat_is_admin") else f"{float(data.get('repeat_cost') or 0):g} 💋"
            await call.message.answer(  # type: ignore[union-attr]
                "🚀 <b>Повторная генерация запущена</b>\n"
                f"• Модель: {html.escape(image_gen.get_image_model_label(model_key))}\n"
                f"• Формат: {html.escape(str(data.get('repeat_aspect_ratio') or 'авто'))}\n"
                f"• Списано: {spent}\n\n"
                "Результат придёт в этот чат."
            )


@router.callback_query(F.data.startswith("repeat_run_cancel_"))
async def cancel_repeat(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("✖️ Повтор отменён.")  # type: ignore[union-attr]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("repeat_edit_prompt_"))
async def edit_repeat_prompt(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("repeat_source_generation_id"):
        await safe_answer_callback(call, "Сессия повтора устарела", show_alert=True)
        return
    if data.get("repeat_is_pinterest"):
        await safe_answer_callback(call, "В Pinterest-сценарии скрытый prompt сохраняется без изменений", show_alert=True)
        return
    await state.set_state(SafeRepeatFSM.editing_prompt)
    await call.message.answer("✏️ Отправьте новый prompt одним сообщением.")  # type: ignore[union-attr]
    await safe_answer_callback(call)


@router.message(SafeRepeatFSM.editing_prompt, F.text)
async def save_repeat_prompt(message: Message, state: FSMContext) -> None:
    prompt = str(message.text or "").strip()
    if not prompt:
        await message.answer("Prompt не может быть пустым.")
        return
    if len(prompt) > 4000:
        await message.answer("Prompt слишком длинный — максимум 4000 символов.")
        return
    await state.update_data(repeat_prompt=prompt)
    await state.set_state(SafeRepeatFSM.confirming)
    data = await state.get_data()
    await message.answer(_confirmation_text(data), reply_markup=_confirmation_keyboard(data))


@router.callback_query(F.data.startswith("repeat_add_refs_"))
async def add_repeat_refs(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("repeat_supports_refs"):
        await safe_answer_callback(call, "Эта модель не принимает референсы", show_alert=True)
        return
    await state.set_state(SafeRepeatFSM.collecting_refs)
    await call.message.answer(  # type: ignore[union-attr]
        f"📎 Отправьте фото. Можно добавить до {int(data.get('repeat_max_refs') or 1)} референсов."
    )
    await safe_answer_callback(call)


@router.message(SafeRepeatFSM.collecting_refs, F.photo)
async def collect_repeat_ref(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    references = _unique_urls(data.get("repeat_reference_images"))
    max_refs = int(data.get("repeat_max_refs") or 1)
    if len(references) >= max_refs:
        await message.answer("Лимит референсов для этой модели уже достигнут.", reply_markup=_confirmation_keyboard(data))
        return
    best = max(message.photo, key=lambda item: item.file_size or 0)  # type: ignore[arg-type]
    url = await image_gen._telegram_file_url(bot, best.file_id)
    if not url:
        await message.answer("Не удалось сохранить фото. Отправьте его ещё раз.")
        return
    if url not in references:
        references.append(url)

    update: dict[str, Any] = {"repeat_reference_images": references, "repeat_missing_references": []}
    if data.get("repeat_is_pinterest"):
        evidence = _unique_urls(data.get("repeat_identity_evidence"))
        if url not in evidence:
            evidence.append(url)
        update["repeat_identity_evidence"] = evidence
    await state.update_data(**update)
    await state.set_state(SafeRepeatFSM.confirming)
    data = await state.get_data()
    await message.answer(_confirmation_text(data), reply_markup=_confirmation_keyboard(data))


# Exact confirm/cancel handlers are deliberately registered before compatibility
# open handlers. There is no broad repeat_run_ handler in this router.
@router.callback_query(F.data.startswith("repeat_image_"))
@router.callback_query(F.data.startswith("repeat_result_"))
async def open_repeat(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    data = str(call.data or "")
    prefix = "repeat_image_" if data.startswith("repeat_image_") else "repeat_result_"
    raw_task_id = _raw_repeat_id(data, prefix)
    if not raw_task_id:
        await safe_answer_callback(call, "Некорректный ID генерации", show_alert=True)
        return
    await _prepare_repeat(
        call=call,
        session=session,
        state=state,
        db_user=db_user,
        bot=bot,
        raw_task_id=raw_task_id,
    )
