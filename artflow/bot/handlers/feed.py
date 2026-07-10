from __future__ import annotations

import html
import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.feed import empty_feed_kb, feed_card_kb
from bot.keyboards.main_menu import back_to_menu_kb
from bot.keyboards.models import IMAGE_CAPS, video_models_kb
from bot.keyboards.prompts import prompt_use_model_kb
from bot.states import ImageGenFSM, PromptUseFSM, VideoGenFSM
from bot.utils.deep_links import build_start_payload
from bot.utils.telegram_images import (
    TELEGRAM_PHOTO_TARGET_BYTES,
    fallback_document_caption,
    prepare_photo_upload,
    send_image_to_message,
)
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from api.public_files import public_url_is_available
from db import repository as repo
from db.models import GenerationType, User
from db.repository import FeedGenerationCard

logger = logging.getLogger(__name__)
router = Router(name="feed")


def _model_label(model_key: str) -> str:
    labels = {
        "grok-imagine/text-to-image": "Grok Imagine",
        "grok-imagine/image-to-image": "Grok Imagine Edit",
        "qwen/text-to-image": "Qwen",
        "qwen/image-to-image": "Qwen Edit",
        "qwen/image-edit": "Qwen Edit Pro",
        "qwen2/text-to-image": "Qwen 2",
        "qwen2/image-edit": "Qwen 2 Edit",
        "google/nano-banana": "Nano Banana",
        "nano-banana-pro": "Nano Banana Pro",
        "nano-banana-2": "Nano Banana 2",
        "seedream/4.5-text-to-image": "Seedream 4.5",
        "seedream/4.5-edit": "Seedream 4.5 Edit",
        "wan/2-7-image": "WAN",
        "wan/2-7-image-pro": "WAN Pro",
        "gpt-image-2-text-to-image": "GPT Image 2",
        "gpt-image-2-image-to-image": "GPT Image 2 Edit",
        "bytedance/seedance-2": "Seedance 2",
        "bytedance/seedance-2-fast": "Seedance 2 Fast",
        "grok-imagine/text-to-video": "Grok Video",
        "grok-imagine/image-to-video": "Grok Animate",
        "veo3": "Veo",
        "veo3_fast": "Veo Fast",
        "veo3_lite": "Veo Lite",
    }
    if model_key in labels:
        return labels[model_key]
    clean = model_key.split("/")[-1].replace("-", " ").replace("_", " ")
    clean = re.sub(r"\b(?:text to image|image to image|text to video|image to video|t2i|i2i|t2v|i2v)\b", "", clean, flags=re.I)
    clean = re.sub(r"\s{2,}", " ", clean).strip()
    return clean.title().strip()


def _default_quality_for_model(model_key: str, fallback: str | None = None) -> str:
    if fallback:
        return fallback
    options = IMAGE_CAPS.get(model_key, {}).get("quality_options") or []
    return options[0][0] if options else "basic"


def _default_count_for_model(model_key: str, fallback: int | None = None) -> int:
    if fallback:
        return fallback
    counts = IMAGE_CAPS.get(model_key, {}).get("counts", [1])
    return counts[0] if counts else 1


def _author_label(card: FeedGenerationCard) -> str:
    if card.username:
        return f"@{card.username}"
    if card.full_name:
        return html.escape(card.full_name)
    return "anon"


def _feed_caption(card: FeedGenerationCard, *, position: int | None = None) -> str:
    gen = card.generation
    prefix = f"👑 <b>#{position}</b>\n\n" if position else ""
    ratio = f"\n📐 {html.escape(card.aspect_ratio)}" if card.aspect_ratio else ""
    return (
        f"{prefix}👤 <b>{_author_label(card)}</b>\n"
        f"🎨 <b>{html.escape(_model_label(gen.model))}</b>{ratio}\n\n"
        f"❤️ <b>{gen.likes_count}</b>\n"
        f"📤 <b>{gen.shares_count}</b>\n"
        f"────────────"
    )


def _feed_fallback_text(card: FeedGenerationCard, caption: str, *, result_url: str | None = None) -> str:
    url = result_url or card.generation.result_url
    escaped_url = html.escape(url or "")
    if escaped_url and public_url_is_available(url):
        link = f'\n\n🔗 <a href="{escaped_url}">Открыть результат</a>'
        note = "⚠️ Telegram не смог открыть превью как фото, но пост доступен по ссылке."
    else:
        link = ""
        note = "⚠️ Файл превью недоступен после восстановления, но пост и скрытый промпт доступны для повтора."
    return f"{caption}\n\n{note}{link}"


def _prepare_feed_photo_upload(*, data: bytes, result_url: str, generation_id: int) -> object:
    return prepare_photo_upload(
        data=data,
        result_url=result_url,
        generation_id=generation_id,
        target_bytes=TELEGRAM_PHOTO_TARGET_BYTES,
    )



async def _cards_for_source(session: AsyncSession, source: str) -> list[FeedGenerationCard]:
    if source == "top":
        return await repo.get_top_day_generations(session, limit=10000)
    return await repo.get_feed_generations(session, limit=10000)


async def _show_feed_empty(holder: Message, *, top_day: bool = False) -> None:
    title = "👑 <b>Топ дня</b>" if top_day else "🔥 <b>Лента</b>"
    await safe_edit_message(
        holder,
        f"{title}\n\nПока нет готовых публичных изображений. Самое время создать первый пост.",
        reply_markup=empty_feed_kb(),
    )


async def _show_feed_card(
    *,
    holder: Message,
    card: FeedGenerationCard,
    source: str,
    index: int,
    total: int,
    viewer_user_id: int | None = None,
    session: AsyncSession | None = None,
) -> None:
    caption = _feed_caption(card, position=index + 1 if source == "top" else None)
    reply_markup = feed_card_kb(
        card.generation.id,
        index=index,
        source=source,
        has_next=total > 1,
        can_delete=bool(viewer_user_id and card.generation.user_id == viewer_user_id),
    )
    result_url = card.generation.result_url
    is_video = getattr(card.generation, "gen_type", None) == GenerationType.video

    # Attempt to mirror broken URLs on-the-fly
    if result_url and not public_url_is_available(result_url):
        logger.info("Feed card gen=%s url=%s unavailable, attempting mirror...", card.generation.id, result_url)
        try:
            from api.public_files import mirror_url

            mirrored = await mirror_url(result_url, subdir="feed")
            if mirrored and mirrored != result_url:
                logger.info("Feed card gen=%s mirrored from %s -> %s", card.generation.id, result_url, mirrored)
                result_url = mirrored
                # Persist the mirrored URL so it stays fixed
                if session:
                    from sqlalchemy import update
                    from db.models import Generation

                    await session.execute(
                        update(Generation)
                        .where(Generation.id == card.generation.id)
                        .values(result_url=mirrored)
                    )
                    await session.commit()
        except Exception as exc:
            logger.warning("Feed card mirror attempt gen=%s failed: %s", card.generation.id, exc)

    if result_url and not public_url_is_available(result_url):
        await holder.answer(_feed_fallback_text(card, caption, result_url=result_url), reply_markup=reply_markup)
        return

    if result_url and not is_video and holder.photo:
        try:
            await holder.edit_media(
                media=InputMediaPhoto(
                    media=result_url,
                    caption=caption,
                    parse_mode="HTML",
                ),
                reply_markup=reply_markup,
            )
            return
        except Exception as e:
            logger.debug("Failed to edit feed media gen=%s: %s", card.generation.id, e)

    if result_url and is_video and getattr(holder, "video", None):
        try:
            await holder.edit_media(
                media=InputMediaVideo(
                    media=result_url,
                    caption=caption,
                    parse_mode="HTML",
                ),
                reply_markup=reply_markup,
            )
            return
        except Exception as e:
            logger.debug("Failed to edit feed video gen=%s: %s", card.generation.id, e)

    if result_url and is_video:
        try:
            await holder.answer_video(result_url, caption=caption, reply_markup=reply_markup)
            return
        except TelegramBadRequest as e:
            logger.warning(
                "Feed video fallback gen=%s url=%s error=%s",
                card.generation.id,
                result_url,
                e,
            )
            await holder.answer(
                _feed_fallback_text(card, caption),
                reply_markup=reply_markup,
            )
            return
        except Exception as e:
            logger.warning(
                "Feed video unexpected fallback gen=%s url=%s error=%s",
                card.generation.id,
                result_url,
                e,
            )
            await holder.answer(
                _feed_fallback_text(card, caption),
                reply_markup=reply_markup,
            )
            return

    if result_url:
        delivery = await send_image_to_message(
            message=holder,
            result_url=result_url,
            generation_id=card.generation.id,
            caption=caption,
            reply_markup=reply_markup,
            log_prefix="feed-photo",
        )
        if delivery.delivered:
            return
        await holder.answer(
            _feed_fallback_text(card, fallback_document_caption(caption)),
            reply_markup=reply_markup,
        )
        return

    await safe_edit_message(holder, caption, reply_markup=reply_markup)


async def show_feed_from_source(
    *,
    holder: Message,
    session: AsyncSession,
    source: str,
    index: int = 0,
    viewer_user_id: int | None = None,
) -> None:
    cards = await _cards_for_source(session, source)
    if not cards:
        await _show_feed_empty(holder, top_day=source == "top")
        return
    idx = index % len(cards)
    await _show_feed_card(
        holder=holder,
        session=session,
        card=cards[idx],
        source=source,
        index=idx,
        total=len(cards),
        viewer_user_id=viewer_user_id,
    )


async def show_feed_card_by_id(
    *,
    message: Message,
    session: AsyncSession,
    gen_id: int,
    viewer_user_id: int | None = None,
) -> None:
    card = await repo.get_feed_generation_card(session, gen_id, require_media=False)
    if not card:
        await message.answer("Пост не найден или уже скрыт.", reply_markup=empty_feed_kb())
        return
    await _show_feed_card(holder=message, session=session, card=card, source="feed", index=0, total=1, viewer_user_id=viewer_user_id)


@router.message(Command("feed"))
@router.callback_query(F.data == "menu:feed")
async def open_feed(
    event: Message | CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User | None = None,
) -> None:
    await state.clear()
    holder = event.message if isinstance(event, CallbackQuery) else event
    await show_feed_from_source(
        holder=holder,
        session=session,
        source="feed",
        index=0,
        viewer_user_id=db_user.id if db_user else None,
    )  # type: ignore[arg-type]
    if isinstance(event, CallbackQuery):
        await safe_answer_callback(event)


@router.callback_query(F.data == "menu:top_day")
@router.callback_query(F.data == "feed:top")
async def open_top_day(
    call: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
    db_user: User | None = None,
) -> None:
    await state.clear()
    await show_feed_from_source(
        holder=call.message,
        session=session,
        source="top",
        index=0,
        viewer_user_id=db_user.id if db_user else None,
    )  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("feed:next:"))
async def cb_feed_next(call: CallbackQuery, session: AsyncSession, db_user: User | None = None) -> None:
    _, _, source, index_raw = call.data.split(":", 3)  # type: ignore[union-attr]
    await show_feed_from_source(
        holder=call.message,  # type: ignore[arg-type]
        session=session,
        source=source,
        index=int(index_raw),
        viewer_user_id=db_user.id if db_user else None,
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("feed:like:"))
async def cb_feed_like(call: CallbackQuery, session: AsyncSession, db_user: User | None = None) -> None:
    _, _, gen_id_raw, source, index_raw = call.data.split(":", 4)  # type: ignore[union-attr]
    await repo.like_feed_generation(session, int(gen_id_raw))
    await show_feed_from_source(
        holder=call.message,  # type: ignore[arg-type]
        session=session,
        source=source,
        index=int(index_raw),
        viewer_user_id=db_user.id if db_user else None,
    )
    await safe_answer_callback(call, "Лайк сохранён ❤️")


@router.callback_query(F.data.startswith("feed:share:"))
async def cb_feed_share(call: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot) -> None:
    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    gen = await repo.increment_feed_share(session, gen_id)
    if not gen:
        await call.answer("Пост не найден", show_alert=True)
        return

    bot_info = await bot.get_me()
    share_payload = build_start_payload(ref_code=db_user.referral_code, target_kind="feed", target_id=gen.id)
    share_link = f"https://t.me/{bot_info.username}?start={share_payload}"
    await call.message.answer(
        f"📤 <b>Ссылка на пост</b>\n{share_link}\n\n"
        f"👥 Твоя партнёрская ссылка:\nhttps://t.me/{bot_info.username}?start={db_user.referral_code}",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call, "Ссылка готова")


@router.callback_query(F.data.startswith("feed:use:"))
async def cb_feed_use(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    gen_id = int(call.data.split(":")[2])
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or not gen.prompt:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    model_costs = await repo.get_all_model_costs(session)
    if getattr(gen, "gen_type", None) == GenerationType.video:
        await state.set_state(VideoGenFSM.model_select)
        await state.update_data(
            feed_use_gen_id=gen_id,
            feed_use_prompt=gen.prompt,
            feed_use_model=gen.model,
            feed_use_gen_type="video",
            source_feed_gen_id=gen_id,
            feed_force_reference=True,
        )
        await call.message.answer(  # type: ignore[union-attr]
            "🎬 <b>Повторить видео</b>\n\n"
            "Выбери видео-модель. Следующим шагом загрузи своё фото/референс — "
            "по нему повторим ролик с промптом из ленты.",
            reply_markup=video_models_kb(model_costs, "i2v"),
        )
        await safe_answer_callback(call)
        return

    await state.set_state(PromptUseFSM.model_select)
    await state.update_data(
        feed_use_gen_id=gen_id,
        feed_use_prompt=gen.prompt,
        feed_use_model=gen.model,
        feed_use_gen_type="image",
    )
    await call.message.answer(  # type: ignore[union-attr]
        "🎨 <b>Повторить изображение</b>\n\n"
        "Выбери модель для работы по фото. Потом загрузи свой референс — "
        "промпт автора применю скрыто.",
        reply_markup=prompt_use_model_kb(gen_id, model_costs, reference_only=True),
    )
    await safe_answer_callback(call)



@router.callback_query(F.data.startswith("feed:again:"))
async def cb_feed_again(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    import json

    from bot.handlers.image_gen import _launch_session_generation, _session_reference_url
    from db.models import ImageGenerationAction

    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != db_user.id or not gen.prompt:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    source_session = None
    if gen.image_session_id:
        source_session = await repo.get_image_session(session, gen.image_session_id, db_user.id)

    mode = source_session.mode if source_session else "text"
    aspect_ratio = source_session.aspect_ratio if source_session else getattr(gen, "aspect_ratio", None)
    quality = source_session.quality if source_session else _default_quality_for_model(gen.model)
    count = source_session.count if source_session else _default_count_for_model(gen.model, 1)
    reference_file_id = source_session.reference_file_id if source_session else None
    reference_file_ids: list[str] = []
    if source_session and source_session.reference_file_ids:
        try:
            reference_file_ids = [item for item in json.loads(source_session.reference_file_ids) if isinstance(item, str) and item]
        except (TypeError, ValueError):
            reference_file_ids = []
    reference_url = source_session.reference_url if source_session else None
    effective_reference_url = None
    if source_session and mode == "image":
        effective_reference_url = await _session_reference_url(bot, source_session, prefer_last_result=False)
        if isinstance(effective_reference_url, str) and effective_reference_url:
            reference_url = effective_reference_url

    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=gen.model,
        mode=mode,
        aspect_ratio=aspect_ratio,
        quality=quality,
        count=count,
        base_prompt=gen.prompt,
        reference_file_id=reference_file_id,
        reference_file_ids=reference_file_ids,
        reference_url=reference_url if isinstance(reference_url, str) else None,
    )

    source_feed_gen_id = gen.id if gen.is_public_feed else getattr(gen, "source_feed_gen_id", None)

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        model_key=image_session.model,
        mode=mode,
        image_mode=mode,
        aspect_ratio=image_session.aspect_ratio,
        quality=image_session.quality,
        count=image_session.count,
        image_file_id=reference_file_id,
        ref_file_ids=reference_file_ids,
        remix_mode=False,
        remix_parent_generation_id=None,
        remix_reference_url=None,
        source_feed_gen_id=source_feed_gen_id,
    )

    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=gen.prompt,
        action_type=ImageGenerationAction.repeat,
        reference_url=effective_reference_url,
        parent_generation_id=gen.id,
        source_feed_gen_id=source_feed_gen_id,
        launching_text="🔁 <b>Готовлю ещё вариант...</b>",
        queued_text="⏳ <b>Ещё вариант запущен.</b> Результат придёт сюда автоматически.",
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("feed:remix:"))
async def cb_feed_remix(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    from bot.handlers.image_gen import _supports_img2img
    from bot.keyboards.models import image_session_kb

    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or not gen.result_url:
        await call.answer("Результат для ремикса не найден", show_alert=True)
        return

    if not _supports_img2img(gen.model):
        await call.answer("Эта модель не поддерживает ремикс по изображению", show_alert=True)
        return

    await repo.archive_active_image_sessions(session, db_user.id)
    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=gen.model,
        mode="image",
        aspect_ratio=getattr(gen, "aspect_ratio", None),
        quality=_default_quality_for_model(gen.model),
        count=_default_count_for_model(gen.model, 1),
        base_prompt=gen.prompt,
        reference_file_id=None,
        reference_url=gen.result_url,
    )

    await state.set_state(ImageGenFSM.session_active)
    await state.update_data(
        image_session_id=image_session.id,
        model_key=image_session.model,
        mode="image",
        image_mode="image",
        aspect_ratio=image_session.aspect_ratio,
        quality=image_session.quality,
        count=image_session.count,
        image_file_id=None,
        ref_file_ids=[],
        remix_mode=True,
        remix_parent_generation_id=gen.id,
        source_feed_gen_id=gen.id,
    )

    await call.message.answer(  # type: ignore[union-attr]
        "✨ <b>Ремикс готов</b>\n\n"
        "Референс из выбранной генерации сохранён.\n"
        "Теперь напиши, что изменить.",
        reply_markup=image_session_kb(gen.id, allow_publish=False),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("feed:publish:"))
async def cb_publish_generation(call: CallbackQuery, session: AsyncSession, db_user: User, bot: Bot | None = None) -> None:
    from api.public_files import mirror_url
    import json

    generation_id = int(call.data.split(":")[-1])
    gen = await repo.get_generation_by_id(session, generation_id)

    if not gen:
        await call.answer("Генерация не найдена", show_alert=True)
        return
    if gen.user_id != db_user.id or getattr(gen, "source_feed_gen_id", None):
        await call.answer("Этот результат нельзя добавить в библиотеку", show_alert=True)
        return

    # Mirror external URLs to local storage before publishing to feed
    current_result_url = getattr(gen, "result_url", None)
    current_result_urls = getattr(gen, "result_urls", None)
    original_urls = [current_result_url] if current_result_url else []
    if current_result_urls:
        try:
            parsed = json.loads(current_result_urls)
            if isinstance(parsed, list):
                original_urls = [str(u) for u in parsed if u] or original_urls
        except (json.JSONDecodeError, TypeError):
            pass

    clean_urls: list[str] = []
    for url in original_urls:
        mirrored = await mirror_url(url, subdir="feed")
        if mirrored:
            clean_urls.append(mirrored)
        else:
            clean_urls.append(url)
    new_result_url = clean_urls[0] if clean_urls else (current_result_url or '')

    gen.is_public_feed = True
    gen.is_prompt_library = True
    gen.result_url = new_result_url
    gen.result_urls = json.dumps(clean_urls, ensure_ascii=False)
    await session.commit()

    if bot and call.message:
        bot_info = await bot.get_me()
        share_payload = build_start_payload(
            ref_code=getattr(db_user, "referral_code", None),
            target_kind="feed",
            target_id=gen.id,
        )
        share_link = f"https://t.me/{bot_info.username}?start={share_payload}"
        await call.message.answer(
            "📤 <b>Фото добавлено в ленту и библиотеку</b>\n\n"
            f"🔗 Ссылка на пост для повтора:\n{share_link}",
            reply_markup=back_to_menu_kb(),
        )
        await safe_answer_callback(call, "✅ Ссылка на пост готова")
        return

    await safe_answer_callback(call, "Добавлено в библиотеку промптов ✨")


@router.callback_query(F.data.startswith("feed:remove:"))
async def cb_feed_remove(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    if len(parts) >= 5 and parts[2] == "confirm":
        gen_id = int(parts[3])
        source = parts[4]
        index = int(parts[5]) if len(parts) > 5 else 0
        gen = await repo.remove_from_feed(session, gen_id, db_user.id)
        if not gen:
            await call.answer("Можно удалить только свой пост", show_alert=True)
            return
        await call.answer("Пост удалён из ленты")
        await show_feed_from_source(holder=call.message, session=session, source=source, index=index, viewer_user_id=db_user.id)  # type: ignore[arg-type]
        return

    if len(parts) < 5:
        await call.answer("Некорректный запрос", show_alert=True)
        return
    gen_id = int(parts[2])
    source = parts[3]
    index = int(parts[4])
    gen = await repo.get_generation_by_id(session, gen_id)
    if not gen or gen.user_id != db_user.id or not gen.is_public_feed:
        await call.answer("Можно удалить только свой пост", show_alert=True)
        return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да, удалить", callback_data=f"feed:remove:confirm:{gen_id}:{source}:{index}")
    builder.button(text="↩️ Назад", callback_data=f"feed:next:{source}:{index}")
    builder.adjust(1)
    await safe_edit_message(
        call.message,
        "🗑 <b>Удалить пост из ленты?</b>\n\nОн исчезнет из общей ленты и больше не будет участвовать в повторах.",
        reply_markup=builder.as_markup(),
    )
    await safe_answer_callback(call)
