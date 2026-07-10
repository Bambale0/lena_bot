from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api.assistant_service import generate_prompt_moderation_decision
from api.image_service import ImageModel
from api.public_files import (
    ensure_public_image_url,
    local_upload_path_from_url,
    mirror_telegram_file,
)
from bot.filters.admin import IsAdmin
from bot.keyboards.main_menu import back_to_menu_kb
from bot.keyboards.prompts import (
    moderation_kb,
    my_prompt_detail_kb,
    my_prompts_kb,
    prompt_card_kb,
    prompt_collections_kb,
    prompt_confirm_kb,
    prompt_use_model_kb,
    prompt_use_reference_kb,
    prompts_home_kb,
)
from bot.states import PromptUseFSM
from bot.states.prompt import PromptModerateFSM, PromptUploadFSM
from bot.utils.deep_links import build_start_payload
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import PromptStatus, User, UserPrompt
from db.prompt_repository import (
    COLLECTION_TAGS,
    MAX_ACTIVE_PROMPTS_PER_USER,
    approve_prompt,
    count_active_prompts_by_author,
    create_prompt,
    deactivate_prompt,
    derive_description,
    derive_title,
    get_author_prompts,
    get_author_total_uses,
    get_pending_prompts,
    get_popular_prompts,
    get_prompt_by_id,
    get_prompts_by_tag,
    get_top_prompts,
    infer_category,
    infer_tags,
    like_prompt,
    reject_prompt,
    set_ai_moderation_result,
    use_prompt,
)

logger = logging.getLogger(__name__)
router = Router(name="marketplace")
DEFAULT_PROMPT_MODEL = ImageModel.NANO_BANANA_PRO
PROMPT_FALLBACK_IMAGE = Path(__file__).resolve().parents[1] / "assets" / "prompt_fallback.jpg"


def _prompt_library_text() -> str:
    return (
        "📚 <b>Библиотека промптов</b>\n\n"
        "🔥 Trending\n"
        "👑 Top today\n"
        "🧠 Best prompts\n"
        "🎭 Characters · 🌆 Cyberpunk · 📸 Realism\n"
        "🎬 Cinematic · 🔞 NSFW · 🎵 Music prompts"
    )


def _prompt_card_caption(prompt: UserPrompt, *, position: int | None = None, total: int | None = None) -> str:
    ranking = f"#{position} из {total}\n\n" if position and total else ""
    tags = "  ".join(f"#{t}" for t in (prompt.tags or []))
    tags_line = f"\n{tags}" if tags else ""
    return (
        f"{ranking}<b>{prompt.title}</b>\n\n"
        f"<i>{prompt.description}</i>{tags_line}\n\n"
        f"🔥 Использовали: <b>{prompt.uses_count}</b>  ❤️ <b>{prompt.likes}</b>"
    )


def _prompt_source_title(source: str) -> str:
    if source == "top":
        return "👑 Top today"
    if source == "trending":
        return "🔥 Trending"
    if source == "popular":
        return "⭐ Популярные"
    if source == "best":
        return "🧠 Best prompts"
    if source.startswith("tag-"):
        tag = source.removeprefix("tag-")
        return COLLECTION_TAGS.get(tag, f"📁 {tag}")
    return "📂 Промпты"


def _prompt_photo_source(preview_url: str | None):
    normalized_url = ensure_public_image_url(preview_url)
    local_path = local_upload_path_from_url(normalized_url)
    if local_path and local_path.exists():
        return FSInputFile(local_path)
    if normalized_url and not local_path:
        return normalized_url
    if PROMPT_FALLBACK_IMAGE.exists():
        return FSInputFile(PROMPT_FALLBACK_IMAGE)
    return None


async def _prompts_for_source(session: AsyncSession, source: str) -> list[UserPrompt]:
    if source == "top":
        return await get_top_prompts(session)
    if source == "trending":
        return await get_popular_prompts(session)
    if source == "popular":
        return await get_popular_prompts(session)
    if source == "best":
        prompts = await get_prompts_by_tag(session, "best")
        return prompts or await get_top_prompts(session)
    if source.startswith("tag-"):
        return await get_prompts_by_tag(session, source.removeprefix("tag-"))
    return []


async def _show_prompt_card(
    *,
    holder: Message,
    prompt: UserPrompt,
    source: str,
    index: int,
    total: int,
) -> None:
    caption = _prompt_card_caption(prompt, position=index + 1, total=total)
    reply_markup = prompt_card_kb(
        prompt.id,
        source=source,
        index=index,
        has_next=index + 1 < total,
    )

    photo_source = _prompt_photo_source(prompt.preview_url)
    if photo_source:
        if holder.photo:
            try:
                await holder.edit_media(
                    media=InputMediaPhoto(
                        media=photo_source,
                        caption=caption,
                        parse_mode="HTML",
                    ),
                    reply_markup=reply_markup,
                )
                return
            except Exception as e:
                logger.debug("Failed to edit prompt media prompt=%s: %s", prompt.id, e)
        try:
            await holder.answer_photo(photo_source, caption=caption, reply_markup=reply_markup)
            return
        except TelegramBadRequest as e:
            logger.warning(
                "Prompt photo fallback failed prompt=%s preview=%s error=%s",
                prompt.id,
                prompt.preview_url,
                e,
            )

    await safe_edit_message(holder, caption, reply_markup=reply_markup)


async def show_prompt_card_from_source(
    *,
    call: CallbackQuery,
    session: AsyncSession,
    source: str,
    index: int,
) -> None:
    prompts = await _prompts_for_source(session, source)
    if not prompts:
        await call.answer("Промпты пока не найдены", show_alert=True)
        return

    idx = max(0, min(index, len(prompts) - 1))
    await _show_prompt_card(
        holder=call.message,  # type: ignore[arg-type]
        prompt=prompts[idx],
        source=source,
        index=idx,
        total=len(prompts),
    )
    await call.answer(_prompt_source_title(source))


async def show_prompt_card_by_id(
    *,
    message: Message,
    session: AsyncSession,
    prompt_id: int,
) -> None:
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.status != PromptStatus.approved or not prompt.is_public:
        await message.answer("Промпт не найден или скрыт.", reply_markup=back_to_menu_kb())
        return
    await _show_prompt_card(holder=message, prompt=prompt, source="top", index=0, total=1)


def _default_quality_for_model(model_key: str) -> str:
    from bot.keyboards.models import IMAGE_CAPS

    caps = IMAGE_CAPS.get(model_key, {})
    options = caps.get("quality_options") or []
    return options[0][0] if options else "basic"


def _default_count_for_model(model_key: str) -> int:
    from bot.keyboards.models import IMAGE_CAPS

    counts = IMAGE_CAPS.get(model_key, {}).get("counts", [1])
    return counts[0] if counts else 1


async def _launch_prompt_generation(
    *,
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User,
    bot: Bot,
    prompt: UserPrompt,
    remix: bool,
) -> None:
    from bot.handlers.image_gen import _launch_session_generation, _supports_img2img
    from db.models import ImageGenerationAction

    model_key = prompt.model or DEFAULT_PROMPT_MODEL
    model_cost = await repo.resolve_image_model_cost(
        session,
        model_key,
        quality=_default_quality_for_model(model_key),
    )
    if not model_cost:
        await call.answer("Модель для этого промпта недоступна", show_alert=True)
        return
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋. Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    prompt, rewards = await use_prompt(
        session,
        prompt.id,
        db_user.id,
        credits_spent=model_cost.credits,
    )

    prompt_preview_url = ensure_public_image_url(prompt.preview_url)
    mode = "image" if remix and prompt_preview_url and _supports_img2img(model_key) else "text"
    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=model_key,
        mode=mode,
        aspect_ratio=None,
        quality=_default_quality_for_model(model_key),
        count=_default_count_for_model(model_key),
        base_prompt=prompt.prompt_text,
        reference_file_id=None,
        reference_url=prompt_preview_url if mode == "image" else None,
    )

    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt.prompt_text,
        action_type=ImageGenerationAction.remix if remix else ImageGenerationAction.initial,
        reference_url=prompt_preview_url if mode == "image" else None,
        parent_generation_id=None,
        launching_text="⏳ <b>Запускаю генерацию по промпту...</b>",
        queued_text="⏳ <b>Генерация запущена.</b> Результат придёт сюда автоматически.",
    )

    if rewards["author"] > 0:
        author = await repo.get_user_by_id(session, prompt.author_id)
        if author:
            try:
                parts = [f"+{rewards['author']} 💋 автору"]
                if rewards["l2"] > 0:
                    parts.append(f"+{rewards['l2']} 💋 lvl2")
                if rewards["l3"] > 0:
                    parts.append(f"+{rewards['l3']} 💋 lvl3")
                await bot.send_message(
                    author.tg_id,
                    f"💰 Промпт «<b>{prompt.title}</b>» использовали.\n" + " · ".join(parts),
                )
            except Exception as e:
                logger.warning("Failed to notify prompt author %s: %s", author.tg_id, e)


@router.message(Command("prompts"))
@router.callback_query(F.data == "menu:prompts")
@router.callback_query(F.data == "prompts:open")
async def open_catalog(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if isinstance(event, CallbackQuery):
        await safe_edit_message(
            event.message,  # type: ignore[arg-type]
            _prompt_library_text(),
            reply_markup=prompts_home_kb(),
        )
        await safe_answer_callback(event)
    else:
        await event.answer(_prompt_library_text(), reply_markup=prompts_home_kb())


@router.callback_query(F.data == "prompts:top")
@router.callback_query(F.data == "prompts:top_today")
async def cb_top_prompts(call: CallbackQuery, session: AsyncSession) -> None:
    await show_prompt_card_from_source(call=call, session=session, source="top", index=0)


@router.callback_query(F.data == "prompts:popular")
@router.callback_query(F.data == "prompts:trending")
async def cb_popular_prompts(call: CallbackQuery, session: AsyncSession) -> None:
    source = "trending" if call.data == "prompts:trending" else "popular"
    await show_prompt_card_from_source(call=call, session=session, source=source, index=0)


@router.callback_query(F.data == "prompts:best")
async def cb_best_prompts(call: CallbackQuery, session: AsyncSession) -> None:
    await show_prompt_card_from_source(call=call, session=session, source="best", index=0)


@router.callback_query(F.data == "prompts:collections")
async def cb_collections(call: CallbackQuery) -> None:
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "📁 <b>Коллекции</b>\n\nВыбери визуальную подборку:",
        reply_markup=prompt_collections_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("prompts:collection:"))
async def cb_collection_prompts(call: CallbackQuery, session: AsyncSession) -> None:
    _, _, tag, index_raw = call.data.split(":", 3)  # type: ignore[union-attr]
    await show_prompt_card_from_source(call=call, session=session, source=f"tag-{tag}", index=int(index_raw))


@router.callback_query(F.data.startswith("prompt_next:"))
async def cb_prompt_next(call: CallbackQuery, session: AsyncSession) -> None:
    _, source, index_raw = call.data.split(":", 2)  # type: ignore[union-attr]
    await show_prompt_card_from_source(call=call, session=session, source=source, index=int(index_raw))


@router.callback_query(F.data.startswith("prompt_like:"))
async def cb_prompt_like(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    _, prompt_id_raw, source, index_raw = call.data.split(":", 3)  # type: ignore[union-attr]
    prompt, like_status = await like_prompt(session, int(prompt_id_raw), db_user.id)
    if like_status == "duplicate":
        await call.answer("Ты уже лайкал этот промпт")
        return
    if like_status == "missing":
        await call.answer("Промпт не найден", show_alert=True)
        return
    if like_status == "unavailable":
        await call.answer("Лайки временно недоступны", show_alert=True)
        return
    if not prompt:
        await call.answer()
        return
    prompts = await _prompts_for_source(session, source)
    await _show_prompt_card(
        holder=call.message,  # type: ignore[arg-type]
        prompt=prompt,
        source=source,
        index=int(index_raw),
        total=max(len(prompts), 1),
    )
    await call.answer("Лайк сохранён ❤️")


@router.callback_query(F.data.startswith("prompt_share:"))
async def cb_prompt_share(call: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot) -> None:
    prompt_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return
    bot_info = await bot.get_me()
    share_payload = build_start_payload(ref_code=db_user.referral_code, target_kind="prompt", target_id=prompt.id)
    share_link = f"https://t.me/{bot_info.username}?start={share_payload}"
    await call.message.answer(
        f"📤 Поделись промптом «<b>{prompt.title}</b>»:\n{share_link}\n\n"
        f"Твоя партнёрская ссылка: https://t.me/{bot_info.username}?start={db_user.referral_code}",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer("Ссылка готова")


@router.callback_query(F.data.startswith("prompt_use:"))
async def cb_prompt_use(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    prompt_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return

    model_costs = await repo.get_all_model_costs(session)
    await state.set_state(PromptUseFSM.model_select)
    await state.update_data(use_prompt_id=prompt_id)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🎨 <b>{prompt.title}</b>\n\n"
        "<i>Выбери модель для генерации:</i>",
        reply_markup=prompt_use_model_kb(prompt_id, model_costs),
    )
    await call.answer()


@router.callback_query(PromptUseFSM.model_select, F.data.startswith("prompt_pick_model:"))
async def cb_prompt_pick_model(
    call: CallbackQuery,
    state: FSMContext,
) -> None:
    _, id_raw, model_key = call.data.split(":", 2)  # type: ignore[union-attr]
    data = await state.get_data()
    is_feed_use = data.get("feed_use_prompt") is not None
    await state.update_data(use_model_key=model_key)
    await state.set_state(PromptUseFSM.reference_upload)
    if is_feed_use:
        text = (
            "🖼 <b>Твой референс</b>\n\n"
            "Отправь фото, по которому нужно повторить пост из ленты.\n"
            "Промпт автора применю скрыто, а лицо/объект возьму из твоего фото."
        )
    else:
        text = (
            "🖼 <b>Референс (необязательно)</b>\n\n"
            "Отправь фото-референс, чтобы задать стиль,\n"
            "или нажми <b>«Без референса»</b> для запуска прямо сейчас."
        )
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        text,
        reply_markup=prompt_use_reference_kb(int(id_raw), allow_skip=not is_feed_use),
    )
    await call.answer()


@router.callback_query(PromptUseFSM.reference_upload, F.data.startswith("prompt_skip_ref:"))
async def cb_prompt_skip_ref(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    from bot.handlers.image_gen import _launch_session_generation
    from db.models import ImageGenerationAction

    data = await state.get_data()
    model_key: str = data.get("use_model_key") or DEFAULT_PROMPT_MODEL

    # Feed use flow: prompt comes from state directly
    if data.get("feed_use_prompt") is not None:
        await call.answer("Для повтора из ленты сначала загрузи своё фото.", show_alert=True)
        return

    # Prompt library flow
    prompt_id = data.get("use_prompt_id") or int(call.data.split(":")[1])  # type: ignore[union-attr]
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        await state.clear()
        return

    model_cost = await repo.resolve_image_model_cost(
        session,
        model_key,
        quality=_default_quality_for_model(model_key),
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        await state.clear()
        return
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋. Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        await state.clear()
        return

    prompt, rewards = await use_prompt(session, prompt.id, db_user.id, credits_spent=model_cost.credits)
    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=model_key,
        mode="text",
        aspect_ratio=None,
        quality=_default_quality_for_model(model_key),
        count=_default_count_for_model(model_key),
        base_prompt=prompt.prompt_text,
        reference_file_id=None,
        reference_url=None,
    )
    await state.clear()
    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt.prompt_text,
        action_type=ImageGenerationAction.initial,
        reference_url=None,
        parent_generation_id=None,
        launching_text="⏳ <b>Запускаю генерацию по промпту...</b>",
        queued_text="⏳ <b>Генерация запущена.</b> Результат придёт сюда автоматически.",
    )
    if rewards["author"] > 0:
        author = await repo.get_user_by_id(session, prompt.author_id)
        if author:
            try:
                parts = [f"+{rewards['author']} 💋 автору"]
                if rewards["l2"] > 0:
                    parts.append(f"+{rewards['l2']} 💋 lvl2")
                if rewards["l3"] > 0:
                    parts.append(f"+{rewards['l3']} 💋 lvl3")
                await bot.send_message(
                    author.tg_id,
                    f"💰 Промпт «<b>{prompt.title}</b>» использовали.\n" + " · ".join(parts),
                )
            except Exception as e:
                logger.warning("Failed to notify prompt author %s: %s", author.tg_id, e)
    await call.answer()


@router.message(PromptUseFSM.reference_upload, F.photo)
async def fsm_prompt_use_reference(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    from api.public_files import mirror_telegram_file
    from bot.handlers.image_gen import _launch_session_generation, _supports_img2img
    from db.models import ImageGenerationAction

    data = await state.get_data()
    model_key: str = data.get("use_model_key") or DEFAULT_PROMPT_MODEL

    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    reference_url = await mirror_telegram_file(bot, best[0].file_id)

    # Feed use flow
    if data.get("feed_use_prompt") is not None:
        prompt_text: str = data["feed_use_prompt"]
        source_feed_gen_id = data.get("feed_use_gen_id")
        mode = "image" if reference_url and _supports_img2img(model_key) else "text"
        model_cost = await repo.resolve_image_model_cost(
            session, model_key, quality=_default_quality_for_model(model_key),
        )
        if not model_cost:
            await message.answer("Модель недоступна.", reply_markup=back_to_menu_kb())
            await state.clear()
            return
        if db_user.credits < model_cost.credits:
            await message.answer(
                f"Недостаточно 💋. Нужно {model_cost.credits}, у тебя {db_user.credits}.",
                reply_markup=back_to_menu_kb(),
            )
            await state.clear()
            return
        image_session = await repo.create_image_session(
            session=session,
            user_id=db_user.id,
            model=model_key,
            mode=mode,
            aspect_ratio=None,
            quality=_default_quality_for_model(model_key),
            count=_default_count_for_model(model_key),
            base_prompt=prompt_text,
            reference_file_id=None,
            reference_url=reference_url if mode == "image" else None,
        )
        await state.clear()
        await _launch_session_generation(
            source_message=message,
            state=state,
            session=session,
            db_user=db_user,
            image_session=image_session,
            prompt=prompt_text,
            action_type=ImageGenerationAction.repeat,
            reference_url=reference_url if mode == "image" else None,
            parent_generation_id=source_feed_gen_id,
            source_feed_gen_id=source_feed_gen_id,
            launching_text="⏳ <b>Запускаю повтор из ленты...</b>",
            queued_text="⏳ <b>Повтор из ленты запущен.</b> Результат придёт сюда автоматически.",
        )
        return

    # Prompt library flow
    prompt_id = data.get("use_prompt_id")
    if not prompt_id:
        await state.clear()
        return

    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt:
        await message.answer("Промпт не найден.", reply_markup=back_to_menu_kb())
        await state.clear()
        return

    if model_key and model_key != DEFAULT_PROMPT_MODEL:
        prompt.model = model_key

    effective_model = model_key or prompt.model or DEFAULT_PROMPT_MODEL
    mode = "image" if reference_url and _supports_img2img(effective_model) else "text"
    model_cost = await repo.resolve_image_model_cost(
        session,
        effective_model,
        quality=_default_quality_for_model(effective_model),
    )
    if not model_cost:
        await message.answer("Модель недоступна.", reply_markup=back_to_menu_kb())
        await state.clear()
        return
    if db_user.credits < model_cost.credits:
        await message.answer(
            f"Недостаточно 💋. Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    prompt, rewards = await use_prompt(session, prompt.id, db_user.id, credits_spent=model_cost.credits)
    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=effective_model,
        mode=mode,
        aspect_ratio=None,
        quality=_default_quality_for_model(effective_model),
        count=_default_count_for_model(effective_model),
        base_prompt=prompt.prompt_text,
        reference_file_id=None,
        reference_url=reference_url if mode == "image" else None,
    )
    await state.clear()
    await _launch_session_generation(
        source_message=message,
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt.prompt_text,
        action_type=ImageGenerationAction.initial,
        reference_url=reference_url if mode == "image" else None,
        parent_generation_id=None,
        launching_text="⏳ <b>Запускаю генерацию по промпту...</b>",
        queued_text="⏳ <b>Генерация запущена.</b> Результат придёт сюда автоматически.",
    )
    if rewards["author"] > 0:
        author = await repo.get_user_by_id(session, prompt.author_id)
        if author:
            try:
                parts = [f"+{rewards['author']} 💋 автору"]
                if rewards["l2"] > 0:
                    parts.append(f"+{rewards['l2']} 💋 lvl2")
                if rewards["l3"] > 0:
                    parts.append(f"+{rewards['l3']} 💋 lvl3")
                await bot.send_message(
                    author.tg_id,
                    f"💰 Промпт «<b>{prompt.title}</b>» использовали.\n" + " · ".join(parts),
                )
            except Exception as e:
                logger.warning("Failed to notify prompt author %s: %s", author.tg_id, e)


@router.callback_query(F.data.startswith("prompt_remix:"))
async def cb_prompt_remix(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    prompt_id = int(call.data.split(":")[1])  # type: ignore[union-attr]
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return
    await _launch_prompt_generation(call=call, session=session, state=state, db_user=db_user, bot=bot, prompt=prompt, remix=True)
    await call.answer()


@router.callback_query(F.data == "prompts:add")
async def cb_add_prompt(call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    active = await count_active_prompts_by_author(session, db_user.id)
    if active >= MAX_ACTIVE_PROMPTS_PER_USER:
        await call.answer(
            f"Максимум {MAX_ACTIVE_PROMPTS_PER_USER} активных промптов. Деактивируй старый, чтобы добавить новый.",
            show_alert=True,
        )
        return
    await state.set_state(PromptUploadFSM.upload_image)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "➕ <b>Добавить свой промпт</b>\n\n"
        "<b>Шаг 1/2</b> — Отправь картинку-превью.\n\n"
        "Это будет обложка карточки в витрине.",
    )
    await call.answer()


@router.message(PromptUploadFSM.upload_image, F.photo)
async def fsm_upload_image(message: Message, state: FSMContext, bot: Bot) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size or 0, reverse=True)  # type: ignore[union-attr]
    preview_url = await mirror_telegram_file(bot, best[0].file_id)
    await state.update_data(preview_url=preview_url)
    await state.set_state(PromptUploadFSM.prompt_text)
    await message.answer(
        "<b>Шаг 2/2</b> — Отправь сам промпт.\n\n"
        "Теги я постараюсь определить автоматически по содержанию.",
        reply_markup=back_to_menu_kb(),
    )


@router.message(PromptUploadFSM.prompt_text, F.text)
async def fsm_prompt_text(message: Message, state: FSMContext) -> None:
    prompt_text = message.text.strip()
    tags = infer_tags(prompt_text)
    title = derive_title(prompt_text)
    description = derive_description(prompt_text)
    category = infer_category(prompt_text, tags)
    await state.update_data(
        prompt_text=prompt_text,
        title=title,
        description=description,
        category=category.value,
        tags=tags,
        model=DEFAULT_PROMPT_MODEL,
    )
    await state.set_state(PromptUploadFSM.confirm)
    await message.answer(
        "📋 <b>Предпросмотр промпта</b>\n\n"
        f"<b>Название:</b> {title}\n"
        f"<b>Категория:</b> {category.label()}\n"
        f"<b>Теги:</b> {' '.join('#' + tag for tag in tags)}\n\n"
        f"<blockquote>{prompt_text[:500]}</blockquote>",
        reply_markup=prompt_confirm_kb(),
    )


@router.callback_query(PromptUploadFSM.confirm, F.data == "prompt_confirm:yes")
async def fsm_confirm(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    await state.clear()
    prompt = await create_prompt(
        session,
        author_id=db_user.id,
        title=data["title"],
        description=data["description"],
        category=infer_category(data["prompt_text"], data["tags"]),
        prompt_text=data["prompt_text"],
        preview_url=data["preview_url"],
        model=data["model"],
        tags=data["tags"],
    )

    moderation_decision = None
    try:
        moderation_decision = await generate_prompt_moderation_decision(
            prompt_id=prompt.id,
            title=prompt.title,
            description=prompt.description,
            prompt_text=prompt.prompt_text,
            tags=list(prompt.tags or []),
            model=prompt.model,
        )
        prompt = await set_ai_moderation_result(
            session,
            prompt.id,
            decision=moderation_decision.decision,
            risk=moderation_decision.risk,
            reason=moderation_decision.reason,
            recommendation=moderation_decision.recommendation,
            raw=moderation_decision.raw,
        ) or prompt
    except Exception as e:
        logger.warning("Prompt auto moderation failed %s: %s", prompt.id, e)

    if moderation_decision and moderation_decision.decision == "approve":
        prompt = await approve_prompt(session, prompt.id) or prompt
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ Промпт «<b>{prompt.title}</b>» автоматически одобрен и опубликован в витрине.",
            reply_markup=prompts_home_kb(),
        )
        await call.answer("Одобрено автоматически ✓")
        return

    if moderation_decision and moderation_decision.decision == "reject":
        prompt = await reject_prompt(session, prompt.id, moderation_decision.reason[:500]) or prompt
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"❌ Промпт «<b>{prompt.title}</b>» автоматически отклонён.\n\nПричина: {prompt.reject_reason or moderation_decision.reason}",
            reply_markup=prompts_home_kb(),
        )
        await call.answer("Отклонено автоматически")
        return

    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ Промпт «<b>{prompt.title}</b>» отправлен на модерацию.\n\n"
        "ИИ не смог уверенно принять решение, поэтому промпт ушёл на ручную проверку.",
        reply_markup=prompts_home_kb(),
    )
    await call.answer()

    from core.config import settings

    for admin_id in settings.ADMIN_IDS:
        try:
            admin_photo = _prompt_photo_source(prompt.preview_url)
            ai_note = ""
            if moderation_decision:
                ai_note = (
                    f"\nAI verdict: manual_review\n"
                    f"AI risk: {moderation_decision.risk}\n"
                    f"AI reason: {moderation_decision.reason[:220]}\n"
                    f"AI recommendation: {moderation_decision.recommendation[:220]}\n"
                )
            if admin_photo:
                await bot.send_photo(
                    admin_id,
                    photo=admin_photo,
                    caption=(
                        f"📬 <b>Спорный промпт на модерацию</b>\n\n"
                        f"ID: {prompt.id}\n"
                        f"Название: {prompt.title}\n"
                        f"Теги: {' '.join('#' + tag for tag in prompt.tags)}\n"
                        f"Автор: {db_user.tg_id} (@{db_user.username or '—'}){ai_note}\n"
                        f"<blockquote>{prompt.prompt_text[:400]}</blockquote>"
                    ),
                    reply_markup=moderation_kb(prompt.id),
                )
            else:
                await bot.send_message(
                    admin_id,
                    f"📬 <b>Спорный промпт на модерацию</b>\n\n"
                    f"ID: {prompt.id}\n"
                    f"Название: {prompt.title}\n"
                    f"Автор: {db_user.tg_id} (@{db_user.username or '—'}){ai_note}\n\n"
                    f"<blockquote>{prompt.prompt_text[:400]}</blockquote>",
                    reply_markup=moderation_kb(prompt.id),
                )
        except Exception as e:
            logger.warning("Failed to notify admin %s: %s", admin_id, e)


@router.callback_query(PromptUploadFSM.confirm, F.data == "prompt_confirm:edit")
async def fsm_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PromptUploadFSM.upload_image)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "✏️ Начнём заново.\n\n<b>Шаг 1/2</b> — Отправь картинку-превью.",
    )
    await call.answer()


@router.callback_query(F.data == "prompts:my")
async def cb_my_prompts(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prompts = await get_author_prompts(session, db_user.id)
    total_uses = await get_author_total_uses(session, db_user.id)
    if not prompts:
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            "📊 <b>Мои промпты</b>\n\nУ тебя ещё нет промптов.",
            reply_markup=prompts_home_kb(),
        )
        await call.answer()
        return
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"📊 <b>Мои промпты</b>\n\nВсего: {len(prompts)}\nИспользований: {total_uses}",
        reply_markup=my_prompts_kb(prompts),
    )
    await call.answer()


@router.callback_query(F.data.startswith("prompts:my_view:"))
async def cb_my_prompt_view(call: CallbackQuery, session: AsyncSession) -> None:
    prompt_id = int(call.data.split(":")[2])
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt:
        await call.answer("Не найден", show_alert=True)
        return
    status_labels = {
        "pending": "⏳ На модерации",
        "approved": "✅ Опубликован",
        "rejected": "❌ Отклонён",
        "deactivated": "🔴 Деактивирован",
    }
    text = (
        f"📝 <b>{prompt.title}</b>\n"
        f"Статус: {status_labels.get(prompt.status.value, prompt.status.value)}\n"
        f"Использований: {prompt.uses_count}\n"
        f"Лайков: {prompt.likes}\n"
        f"Теги: {' '.join('#' + tag for tag in prompt.tags)}\n\n"
        f"<blockquote>{prompt.prompt_text[:500]}</blockquote>"
    )
    if prompt.reject_reason:
        text += f"\n\n❌ Причина отказа: {prompt.reject_reason}"
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        text,
        reply_markup=my_prompt_detail_kb(prompt_id, prompt.status.value),
    )
    await call.answer()


@router.callback_query(F.data.startswith("prompts:deactivate:"))
async def cb_deactivate(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prompt_id = int(call.data.split(":")[2])
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt or prompt.author_id != db_user.id:
        await call.answer("Нет доступа", show_alert=True)
        return
    await deactivate_prompt(session, prompt_id)
    await call.answer("Промпт деактивирован ✓", show_alert=True)
    await cb_my_prompts(call, session, db_user)


mod_router = Router(name="marketplace_mod")
mod_router.callback_query.filter(IsAdmin())


@mod_router.callback_query(F.data.startswith("mod:approve:"))
async def cb_mod_approve(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    prompt_id = int(call.data.split(":")[2])
    prompt = await approve_prompt(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ Промпт <b>#{prompt_id}</b> «{prompt.title}» — одобрен."
    )
    await call.answer("Одобрено ✓")
    author = await repo.get_user_by_id(session, prompt.author_id)
    if author:
        try:
            await bot.send_message(
                author.tg_id,
                f"🎉 Ваш промпт «<b>{prompt.title}</b>» опубликован в витрине.\n"
                "Теперь пользователи могут запускать генерацию прямо из карточки.",
            )
        except Exception as e:
            logger.warning("notify author error: %s", e)


@mod_router.callback_query(F.data.startswith("mod:reject:"))
async def cb_mod_reject_start(call: CallbackQuery, state: FSMContext) -> None:
    prompt_id = int(call.data.split(":")[2])
    await state.set_state(PromptModerateFSM.reject_reason)
    await state.update_data(reject_prompt_id=prompt_id)
    await call.message.answer(f"Введи причину отклонения промпта #{prompt_id}:")
    await call.answer()


@mod_router.message(PromptModerateFSM.reject_reason, F.text)
async def cb_mod_reject_reason(message: Message, state: FSMContext, session: AsyncSession, bot: Bot) -> None:
    data = await state.get_data()
    prompt_id = data["reject_prompt_id"]
    reason = message.text.strip()
    await state.clear()
    prompt = await reject_prompt(session, prompt_id, reason)
    if not prompt:
        await message.answer("Промпт не найден")
        return
    await message.answer(f"❌ Промпт #{prompt_id} «{prompt.title}» — отклонён.\nПричина: {reason}")
    author = await repo.get_user_by_id(session, prompt.author_id)
    if author:
        try:
            await bot.send_message(
                author.tg_id,
                f"❌ Промпт «<b>{prompt.title}</b>» отклонён.\nПричина: {reason}",
            )
        except Exception as e:
            logger.warning("notify author error: %s", e)


@mod_router.callback_query(F.data.startswith("mod:deactivate:"))
async def cb_mod_deactivate(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    prompt_id = int(call.data.split(":")[2])
    prompt = await deactivate_prompt(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🔴 Промпт #{prompt_id} «{prompt.title}» — деактивирован."
    )
    await call.answer("Деактивировано ✓")
    author = await repo.get_user_by_id(session, prompt.author_id)
    if author:
        try:
            await bot.send_message(author.tg_id, f"⚠️ Ваш промпт «<b>{prompt.title}</b>» скрыт администратором.")
        except Exception:
            pass


@mod_router.callback_query(F.data == "adm:prompts")
async def cb_adm_prompts(call: CallbackQuery, session: AsyncSession) -> None:
    pending = await get_pending_prompts(session)
    if not pending:
        await call.answer("Нет промптов на модерации ✓", show_alert=True)
        return
    for p in pending[:10]:
        author = await repo.get_user_by_id(session, p.author_id)
        author_str = f"@{author.username}" if author and author.username else str(p.author_id)
        pending_photo = _prompt_photo_source(p.preview_url)
        if pending_photo:
            await call.message.answer_photo(
                pending_photo,
                caption=(
                    f"📬 <b>#{p.id}</b> — {p.title}\n"
                    f"Автор: {author_str}\n"
                    f"Теги: {' '.join('#' + tag for tag in p.tags)}\n\n"
                    f"<blockquote>{p.prompt_text[:300]}</blockquote>"
                ),
                reply_markup=moderation_kb(p.id),
            )
        else:
            await call.message.answer(
                f"📬 <b>#{p.id}</b> — {p.title}\n"
                f"Автор: {author_str}\n\n"
                f"<blockquote>{p.prompt_text[:300]}</blockquote>",
                reply_markup=moderation_kb(p.id),
            )
    await call.answer()
