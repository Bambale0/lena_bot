"""Multi-reference preparation flow for repeated image generations.

The legacy repeat buttons launched immediately. This module intercepts repeat
callbacks for models that support multiple references, preserves the original
prompt/model/settings/references and lets the user append several new photos
before the credit-consuming provider request starts.
"""
from __future__ import annotations

import json
from typing import Any

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import public_url_is_available

# Import the existing routers and handlers first. New handlers are then inserted
# at the beginning of their observer lists, so the old one-click repeat remains
# the fallback for single-reference/text-only models.
from bot.handlers import feed, image_gen
from bot.keyboards.models import IMAGE_CAPS
from bot.utils.telegram_ui import safe_answer_callback
from db import repository as repo
from db.models import GenerationType, ImageGenerationAction, User


class RepeatReferenceFSM(StatesGroup):
    collect = State()


def _url_list(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        values = []
    return list(dict.fromkeys(str(item).strip() for item in values if str(item or "").strip()))


def _generation_type_value(generation: Any) -> str:
    gen_type = getattr(generation, "gen_type", None)
    return str(getattr(gen_type, "value", gen_type) or "")


def _repeat_max_refs(model_key: str) -> int:
    caps = IMAGE_CAPS.get(model_key, {})
    direct = int(caps.get("max_refs", 0) or 0)
    if direct > 0:
        return direct

    spec = image_gen.IMAGE_SPECS.get(model_key)
    remix_model = getattr(spec, "remix_model", None) if spec else None
    if remix_model:
        return int(IMAGE_CAPS.get(str(remix_model), {}).get("max_refs", 1) or 1)
    return 1


def _prompt_user_reference_limit(model_key: str, data: dict[str, Any]) -> int:
    """Public image repeats reserve one provider slot for the source post."""
    reserved = 1 if data.get("feed_use_prompt") is not None else 0
    return max(0, _repeat_max_refs(model_key) - reserved)


def _repeat_ratio_options(model_key: str) -> list[str]:
    caps = IMAGE_CAPS.get(model_key, {})
    ratios = list(caps.get("aspect_ratios") or [])
    if not ratios:
        spec = image_gen.IMAGE_SPECS.get(model_key)
        remix_model = getattr(spec, "remix_model", None) if spec else None
        ratios = list(IMAGE_CAPS.get(str(remix_model), {}).get("aspect_ratios") or [])
    ratios = list(dict.fromkeys(str(ratio) for ratio in ratios if ratio))
    if "9:16" not in ratios:
        ratios.insert(0, "9:16")
    else:
        ratios.insert(0, ratios.pop(ratios.index("9:16")))
    return ratios


def _supports_repeat_reference_collection(model_key: str) -> bool:
    return image_gen._supports_img2img(model_key) and _repeat_max_refs(model_key) > 1


def _source_reference_file_ids(image_session: Any | None) -> list[str]:
    if image_session is None:
        return []
    refs = image_gen._stored_reference_file_ids(image_session)
    single = getattr(image_session, "reference_file_id", None)
    if single and single not in refs:
        refs.insert(0, single)
    return refs


def _repeat_refs_keyboard(
    *,
    total: int,
    added: int,
    max_refs: int,
    required: bool,
    selected_ratio: str = "9:16",
    ratio_options: list[str] | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ratio_buttons = [
        InlineKeyboardButton(
            text=f"{'✅ ' if ratio == selected_ratio else ''}{ratio}",
            callback_data=f"repeat_refs:ratio:{ratio}",
        )
        for ratio in (ratio_options or ["9:16"])
    ]
    for offset in range(0, len(ratio_buttons), 3):
        builder.row(*ratio_buttons[offset : offset + 3])
    if total <= max_refs and (total > 0 or not required):
        builder.row(
            InlineKeyboardButton(
                text=f"▶️ Запустить повтор · {total} фото" if total else "▶️ Запустить без фото",
                callback_data="repeat_refs:run",
            )
        )
    if total < max_refs:
        builder.row(
            InlineKeyboardButton(
                text=f"📸 Можно добавить ещё · {total}/{max_refs}",
                callback_data="repeat_refs:hint",
            )
        )
    if total or added:
        builder.row(
            InlineKeyboardButton(text="🧹 Очистить референсы", callback_data="repeat_refs:clear")
        )
    builder.row(InlineKeyboardButton(text="✖️ Отменить", callback_data="repeat_refs:cancel"))
    return builder.as_markup()


def _repeat_keyboard_from_data(data: dict[str, Any], *, total: int, added: int) -> InlineKeyboardMarkup:
    return _repeat_refs_keyboard(
        total=total,
        added=added,
        max_refs=int(data.get("repeat_max_refs") or 1),
        required=bool(data.get("repeat_reference_required")),
        selected_ratio=str(data.get("repeat_aspect_ratio") or "9:16"),
        ratio_options=list(data.get("repeat_ratio_options") or ["9:16"]),
    )


def _repeat_refs_text(data: dict[str, Any]) -> str:
    base_count = len(_url_list(data.get("repeat_base_reference_urls")))
    added_count = len(list(data.get("repeat_new_reference_file_ids") or []))
    total = int(data.get("repeat_reference_count", base_count + added_count))
    max_refs = int(data.get("repeat_max_refs") or 1)
    model_key = str(data.get("repeat_model_key") or "")
    required = bool(data.get("repeat_reference_required"))
    requirement = (
        "Для этой модели нужен хотя бы один референс."
        if required and total == 0
        else "Можно сразу запустить или добавить новые фото."
    )
    if total > max_refs:
        requirement = "Сохранённых фото больше лимита модели. Очисти референсы и добавь нужные заново."
    return (
        "🔁 <b>Повтор генерации</b>\n\n"
        f"Модель: <b>{image_gen.get_image_model_label(model_key)}</b>\n"
        f"Референсы: <b>{total}/{max_refs}</b> "
        f"(исходных {base_count}, новых {added_count})\n\n"
        f"Формат: <b>{data.get('repeat_aspect_ratio') or '9:16'}</b>\n\n"
        "Промпт, модель, формат, качество и количество вариантов сохранены.\n"
        "Отправляй фото сюда по одному или альбомом — я соберу их в один повтор.\n\n"
        f"{requirement}"
    )


async def _resolve_base_reference_urls(bot: Bot, image_session: Any | None) -> list[str]:
    if image_session is None:
        return []
    value = await image_gen._session_reference_url(
        bot,
        image_session,
        prefer_last_result=False,
        state=None,
    )
    return _url_list(value)


async def _repeat_provider_reference_urls(
    *, session: AsyncSession, db_user: User, source_feed_gen_id: int | None,
    reference_urls: list[str], retain_user_references: bool = True,
) -> list[str] | None:
    """Count the same public source used at launch, failing closed if it is gone."""
    external_source_id = await image_gen._external_source_feed_id(
        session=session, db_user=db_user, source_feed_gen_id=source_feed_gen_id,
    )
    if not external_source_id:
        return reference_urls if retain_user_references else []
    source = await repo.get_public_feed_generation(session, external_source_id)
    if _generation_type_value(source) != GenerationType.image.value:
        return None
    source_url = image_gen.selected_feed_source_url(source, reference_urls)
    if not source_url or not public_url_is_available(source_url):
        return None
    return image_gen.order_feed_image_references(
        source_url, image_gen.feed_identity_references(source, reference_urls) if retain_user_references else [],
    )


async def _begin_repeat_collection(
    *,
    call: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    db_user: User,
    generation: Any,
    source_session: Any | None,
    reuse_session: bool,
    source_feed_gen_id: int | None,
) -> bool:
    model_key = str(getattr(generation, "model", "") or "")
    if not _supports_repeat_reference_collection(model_key):
        return False
    if not getattr(generation, "prompt", None):
        await call.answer("У генерации нет промпта для повтора", show_alert=True)
        return True

    max_refs = _repeat_max_refs(model_key)
    try:
        base_urls = await _resolve_base_reference_urls(bot, source_session)
    except image_gen.ImageReferenceUnavailable:
        await safe_answer_callback(call, "Не удалось подготовить сохранённые фото. Попробуй ещё раз.", show_alert=True)
        return True
    provider_refs = await _repeat_provider_reference_urls(
        session=session, db_user=db_user, source_feed_gen_id=source_feed_gen_id,
        reference_urls=base_urls,
    )
    if provider_refs is None:
        await safe_answer_callback(call, "Исходное фото из ленты недоступно. Выбери другую публикацию.", show_alert=True)
        return True
    total = len(provider_refs)
    source_file_ids = _source_reference_file_ids(source_session)

    await state.clear()
    await state.set_state(RepeatReferenceFSM.collect)
    await state.update_data(
        repeat_generation_id=int(generation.id),
        repeat_parent_generation_id=int(generation.id),
        repeat_prompt=str(generation.prompt),
        repeat_model_key=model_key,
        repeat_max_refs=max_refs,
        repeat_reference_required=image_gen._requires_reference_image(model_key),
        repeat_base_reference_urls=base_urls,
        repeat_reference_count=total,
        repeat_new_reference_file_ids=[],
        repeat_source_reference_file_ids=source_file_ids,
        repeat_source_reference_url=(
            str(getattr(source_session, "reference_url", "") or "") or None
            if source_session is not None
            else None
        ),
        repeat_source_feed_gen_id=source_feed_gen_id,
        repeat_reuse_session_id=(int(source_session.id) if reuse_session and source_session else None),
        repeat_source_session_id=(int(source_session.id) if source_session else None),
        repeat_mode=(str(getattr(source_session, "mode", "text") or "text") if source_session else "text"),
        repeat_aspect_ratio="9:16",
        repeat_ratio_options=_repeat_ratio_options(model_key),
        repeat_quality=(
            str(getattr(source_session, "quality", "") or "")
            if source_session
            else feed._default_quality_for_model(model_key)
        ),
        repeat_count=(
            int(getattr(source_session, "count", 1) or 1)
            if source_session
            else feed._default_count_for_model(model_key, 1)
        ),
    )
    data = await state.get_data()
    await call.message.answer(  # type: ignore[union-attr]
        _repeat_refs_text(data),
        reply_markup=_repeat_keyboard_from_data(data, total=total, added=0),
    )
    await safe_answer_callback(call, "Можно добавить несколько фото")
    return True


async def _session_repeat_interceptor(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    gen_id: int | None = None
    if call.data and call.data.startswith("img_session:repeat:"):
        raw = call.data.rsplit(":", 1)[-1]
        gen_id = int(raw) if raw.isdigit() and int(raw) > 0 else None

    image_session, resolved_parent_id = await image_gen._resolve_image_session(
        session,
        db_user,
        state,
        gen_id,
    )
    if not image_session:
        await image_gen.cb_image_session_repeat(call, session, state, db_user, bot)
        return

    target_generation = None
    target_id = resolved_parent_id or gen_id
    if target_id:
        target_generation = await repo.get_generation_by_id(session, target_id)
    if not target_generation or getattr(target_generation, "user_id", None) != db_user.id:
        target_generation = await repo.get_last_session_generation(session, image_session.id)
    if not target_generation:
        await call.answer("Нечего повторять", show_alert=True)
        return

    handled = await _begin_repeat_collection(
        call=call,
        state=state,
        bot=bot,
        session=session,
        db_user=db_user,
        generation=target_generation,
        source_session=image_session,
        reuse_session=True,
        source_feed_gen_id=getattr(target_generation, "source_feed_gen_id", None),
    )
    if not handled:
        await image_gen.cb_image_session_repeat(call, session, state, db_user, bot)


async def _regen_repeat_interceptor(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    raw = (call.data or "").rsplit(":", 1)[-1]
    generation = await repo.get_generation_by_id(session, int(raw)) if raw.isdigit() else None
    if (
        not generation
        or getattr(generation, "user_id", None) != db_user.id
        or _generation_type_value(generation) != GenerationType.image.value
    ):
        await call.answer("Генерация не найдена", show_alert=True)
        return

    source_session = None
    if getattr(generation, "image_session_id", None):
        source_session = await repo.get_image_session(session, generation.image_session_id, db_user.id)

    handled = await _begin_repeat_collection(
        call=call,
        state=state,
        bot=bot,
        session=session,
        db_user=db_user,
        generation=generation,
        source_session=source_session,
        reuse_session=False,
        source_feed_gen_id=getattr(generation, "source_feed_gen_id", None),
    )
    if not handled:
        await image_gen.cb_regen_image(call, session, state, db_user, bot)


async def _feed_again_interceptor(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    raw = (call.data or "").rsplit(":", 1)[-1]
    generation = await repo.get_generation_by_id(session, int(raw)) if raw.isdigit() else None
    if not generation or getattr(generation, "user_id", None) != db_user.id:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    source_session = None
    if getattr(generation, "image_session_id", None):
        source_session = await repo.get_image_session(session, generation.image_session_id, db_user.id)

    source_feed_gen_id = getattr(generation, "source_feed_gen_id", None) or (
        int(generation.id) if bool(getattr(generation, "is_public_feed", False)) else None
    )
    handled = await _begin_repeat_collection(
        call=call,
        state=state,
        bot=bot,
        session=session,
        db_user=db_user,
        generation=generation,
        source_session=source_session,
        reuse_session=False,
        source_feed_gen_id=source_feed_gen_id,
    )
    if not handled:
        await feed.cb_feed_again(call, session, db_user, state, bot)


async def _collect_repeat_reference(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    model_key = str(data.get("repeat_model_key") or "")
    max_refs = _repeat_max_refs(model_key) if model_key else int(data.get("repeat_max_refs") or 1)
    base_urls = _url_list(data.get("repeat_base_reference_urls"))
    new_file_ids = list(data.get("repeat_new_reference_file_ids") or [])

    best = sorted(message.photo, key=lambda item: item.file_size or 0, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id
    if file_id not in new_file_ids:
        new_file_ids.append(file_id)
    candidate_urls = list(base_urls)
    try:
        for candidate_file_id in new_file_ids:
            url = str(await image_gen._telegram_file_url(bot, candidate_file_id) or "").strip()
            if not url:
                raise image_gen.ImageReferenceUnavailable()
            if url not in candidate_urls:
                candidate_urls.append(url)
    except Exception:
        await message.answer("Не удалось проверить фото. Попробуй ещё раз.")
        return
    source_feed_gen_id = data.get("repeat_source_feed_gen_id")
    generation_id = int(data.get("repeat_generation_id") or 0)
    if generation_id:
        generation = await repo.get_generation_by_id(session, generation_id)
        if not generation or getattr(generation, "user_id", None) != db_user.id:
            await message.answer("Генерация не найдена")
            return
        # Do not let stale collection state remove protected source lineage.
        source_feed_gen_id = getattr(generation, "source_feed_gen_id", None) or source_feed_gen_id
    candidate_urls = await _repeat_provider_reference_urls(
        session=session, db_user=db_user, source_feed_gen_id=source_feed_gen_id,
        reference_urls=candidate_urls,
    )
    if candidate_urls is None:
        await message.answer("Исходное фото из ленты недоступно. Выбери другую публикацию.")
        return
    total = await image_gen._accept_reference_candidate(
        message, bot, {"reference_urls": candidate_urls}, max_refs,
    )
    if total is None:
        return
    await state.update_data(
        repeat_new_reference_file_ids=new_file_ids, repeat_reference_count=total, repeat_max_refs=max_refs,
    )

    data = await state.get_data()
    await message.answer(
        _repeat_refs_text(data),
        reply_markup=_repeat_keyboard_from_data(data, total=total, added=len(new_file_ids)),
    )


async def _repeat_refs_hint(call: CallbackQuery) -> None:
    await call.answer("Отправь следующее фото обычным сообщением", show_alert=True)


async def _repeat_refs_ratio(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    ratio = (call.data or "").removeprefix("repeat_refs:ratio:")
    options = list(data.get("repeat_ratio_options") or ["9:16"])
    if ratio not in options:
        await call.answer("Этот формат недоступен для выбранной модели", show_alert=True)
        return
    await state.update_data(repeat_aspect_ratio=ratio)
    data = await state.get_data()
    total = int(data.get(
        "repeat_reference_count",
        len(_url_list(data.get("repeat_base_reference_urls"))) + len(data.get("repeat_new_reference_file_ids") or []),
    ))
    await call.message.answer(  # type: ignore[union-attr]
        _repeat_refs_text(data),
        reply_markup=_repeat_keyboard_from_data(
            data,
            total=total,
            added=len(list(data.get("repeat_new_reference_file_ids") or [])),
        ),
    )
    await safe_answer_callback(call, f"Формат: {ratio}")


async def _repeat_refs_clear(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User,
) -> None:
    data = await state.get_data()
    generation = await repo.get_generation_by_id(session, int(data.get("repeat_generation_id") or 0))
    if not generation or getattr(generation, "user_id", None) != db_user.id:
        await safe_answer_callback(call, "Генерация не найдена", show_alert=True)
        return
    source_feed_gen_id = getattr(generation, "source_feed_gen_id", None) or data.get("repeat_source_feed_gen_id")
    # Clearing removes user identity photos, never the required public scene.
    provider_refs = await _repeat_provider_reference_urls(
        session=session, db_user=db_user, source_feed_gen_id=source_feed_gen_id,
        reference_urls=_url_list(data.get("repeat_base_reference_urls")),
        retain_user_references=False,
    )
    if provider_refs is None:
        await safe_answer_callback(call, "Исходное фото из ленты недоступно. Выбери другую публикацию.", show_alert=True)
        return
    total = len(provider_refs)
    await state.update_data(
        repeat_base_reference_urls=provider_refs,
        repeat_reference_count=total,
        repeat_new_reference_file_ids=[],
        repeat_source_reference_file_ids=[],
        repeat_source_reference_url=None,
    )
    data = await state.get_data()
    await call.message.answer(  # type: ignore[union-attr]
        _repeat_refs_text(data),
        reply_markup=_repeat_keyboard_from_data(data, total=total, added=0),
    )
    await safe_answer_callback(call, "Референсы очищены")


async def _repeat_refs_cancel(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    parent_id = data.get("repeat_parent_generation_id")
    await state.clear()
    await call.message.answer(  # type: ignore[union-attr]
        "✖️ Повтор отменён.",
        reply_markup=image_gen.image_session_kb(parent_id),
    )
    await safe_answer_callback(call)


async def _repeat_refs_run(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    generation_id = int(data.get("repeat_generation_id") or 0)
    generation = await repo.get_generation_by_id(session, generation_id)
    if not generation or getattr(generation, "user_id", None) != db_user.id:
        await call.answer("Генерация не найдена", show_alert=True)
        await state.clear()
        return

    # Durable lineage takes precedence over missing or stale collection state.
    protected_source_id = getattr(generation, "source_feed_gen_id", None)
    source_feed_gen_id = protected_source_id or data.get("repeat_source_feed_gen_id")
    if source_feed_gen_id == generation.id and not protected_source_id:
        source_feed_gen_id = None
    prompt = str(data.get("repeat_prompt") or generation.prompt or "")
    prompt_is_user_supplied = (
        not source_feed_gen_id
        and feed._owned_generation_prompt_is_visible(generation, db_user.id)
        and prompt == generation.prompt
    )

    model_key = str(data.get("repeat_model_key") or generation.model)
    max_refs = _repeat_max_refs(model_key)
    references = _url_list(data.get("repeat_base_reference_urls"))
    new_file_ids = list(data.get("repeat_new_reference_file_ids") or [])
    for file_id in new_file_ids:
        try:
            url = str(await image_gen._telegram_file_url(bot, file_id) or "").strip()
        except Exception:
            url = ""
        if not url:
            await call.answer("Не удалось подготовить референсы. Отправь фото ещё раз.", show_alert=True)
            return
        if url not in references:
            references.append(url)
    candidate_refs = await _repeat_provider_reference_urls(
        session=session, db_user=db_user, source_feed_gen_id=source_feed_gen_id,
        reference_urls=references,
    )
    if candidate_refs is None:
        await safe_answer_callback(call, "Исходное фото из ленты недоступно. Выбери другую публикацию.", show_alert=True)
        return
    if await image_gen._accept_reference_candidate(
        call, bot, {"reference_urls": candidate_refs}, max_refs,
    ) is None:
        return

    if image_gen._requires_reference_image(model_key) and not candidate_refs:
        await call.answer("Для этой модели нужен хотя бы один референс", show_alert=True)
        return

    image_session = None
    reuse_session_id = data.get("repeat_reuse_session_id")
    if reuse_session_id:
        image_session = await repo.get_image_session(session, int(reuse_session_id), db_user.id)

    combined_file_ids = list(data.get("repeat_source_reference_file_ids") or [])
    for file_id in new_file_ids:
        if file_id not in combined_file_ids:
            combined_file_ids.append(file_id)
    # Public and mixed URL/file sets must remain complete on later repeats.
    # Mirrored Telegram URLs are durable; use one ordered URL set for mixed input
    # so the file-ID resolver cannot shadow the original public references.
    persist_as_urls = bool(data.get("repeat_source_reference_url")) or (
        len(_url_list(data.get("repeat_base_reference_urls")))
        > len(data.get("repeat_source_reference_file_ids") or [])
    ) or not combined_file_ids or candidate_refs != references
    stored_file_ids = [] if persist_as_urls else combined_file_ids
    stored_urls = candidate_refs if persist_as_urls else []

    target_mode = "image" if candidate_refs else str(data.get("repeat_mode") or "text")
    aspect_ratio = str(data.get("repeat_aspect_ratio") or "9:16")
    quality = image_gen._normalize_session_quality(
        str(data.get("repeat_model_key") or generation.model),
        aspect_ratio,
        str(data.get("repeat_quality") or "basic"),
    )
    if image_session is None:
        image_session = await repo.create_image_session(
            session=session,
            user_id=db_user.id,
            model=str(data.get("repeat_model_key") or generation.model),
            mode=target_mode,
            aspect_ratio=aspect_ratio,
            quality=quality,
            count=int(data.get("repeat_count") or 1),
            base_prompt=prompt if prompt_is_user_supplied else None,
            prompt_provenance="user_supplied" if prompt_is_user_supplied else None,
            reference_file_id=stored_file_ids[0] if stored_file_ids else None,
            reference_file_ids=stored_file_ids or None,
            reference_url=stored_urls[0] if stored_urls else None,
            reference_urls=stored_urls,
        )
    else:
        if source_feed_gen_id:
            image_session.base_prompt = None
            image_session.last_prompt = None
            image_session.prompt_provenance = None
        image_session.mode = target_mode
        image_session.aspect_ratio = aspect_ratio
        image_session.quality = quality
        image_session.reference_file_id = stored_file_ids[0] if stored_file_ids else None
        image_session.reference_file_ids = json.dumps(stored_file_ids) if stored_file_ids else None
        image_session.reference_url = stored_urls[0] if stored_urls else None
        image_session.reference_urls = json.dumps(stored_urls) if stored_urls else None
        await session.commit()

    await state.set_state(image_gen.ImageGenFSM.session_active)
    launched = await image_gen._launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt,
        action_type=ImageGenerationAction.repeat,
        reference_url=candidate_refs or None,
        parent_generation_id=int(data.get("repeat_parent_generation_id") or generation.id),
        source_feed_gen_id=source_feed_gen_id,
        launching_text="🔁 <b>Повторяю генерацию с референсами...</b>",
        queued_text="⏳ <b>Повтор запущен.</b> Результат придёт сюда автоматически.",
    )
    if launched:
        await safe_answer_callback(call, f"Запущено · референсов {len(candidate_refs)}")


def _register_front(observer: Any, callback: Any, *filters: Any) -> None:
    observer.register(callback, *filters)
    observer.handlers.insert(0, observer.handlers.pop())


# Existing result/session repeat buttons.
_register_front(image_gen.router.callback_query, _session_repeat_interceptor, F.data == "img_variation")
_register_front(image_gen.router.callback_query, _session_repeat_interceptor, F.data.startswith("img_session:repeat:"))
_register_front(image_gen.router.callback_query, _regen_repeat_interceptor, F.data.startswith("regen:image:"))

# Repeat from the user's own feed/history card. feed.router is registered before
# image_gen.router, so this handler must be inserted directly into feed.router.
_register_front(feed.router.callback_query, _feed_again_interceptor, F.data.startswith("feed:again:"))

# Unique FSM handlers do not conflict with the legacy image-session upload flow.
image_gen.router.message.register(_collect_repeat_reference, RepeatReferenceFSM.collect, F.photo)
image_gen.router.callback_query.register(_repeat_refs_hint, RepeatReferenceFSM.collect, F.data == "repeat_refs:hint")
image_gen.router.callback_query.register(_repeat_refs_ratio, RepeatReferenceFSM.collect, F.data.startswith("repeat_refs:ratio:"))
image_gen.router.callback_query.register(_repeat_refs_clear, RepeatReferenceFSM.collect, F.data == "repeat_refs:clear")
image_gen.router.callback_query.register(_repeat_refs_cancel, RepeatReferenceFSM.collect, F.data == "repeat_refs:cancel")
image_gen.router.callback_query.register(_repeat_refs_run, RepeatReferenceFSM.collect, F.data == "repeat_refs:run")
