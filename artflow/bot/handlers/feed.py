from __future__ import annotations

import html
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.feed import empty_feed_kb, feed_card_kb
from bot.keyboards.main_menu import back_to_menu_kb
from bot.keyboards.models import IMAGE_CAPS
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import ImageGenerationAction, User
from db.repository import FeedGenerationCard

logger = logging.getLogger(__name__)
router = Router(name="feed")


def _model_label(model_key: str) -> str:
    clean = model_key.split("/")[-1].replace("-", " ").replace("_", " ")
    return clean.title().replace("Nano Banana", "Nano Banana")


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
    prompt = html.escape(gen.prompt[:220])
    if len(gen.prompt) > 220:
        prompt += "..."
    ratio = f"\n📐 {html.escape(card.aspect_ratio)}" if card.aspect_ratio else ""
    return (
        f"{prefix}👤 <b>{_author_label(card)}</b>\n"
        f"🎨 <b>{html.escape(_model_label(gen.model))}</b>{ratio}\n\n"
        f"<i>{prompt}</i>\n\n"
        f"❤️ <b>{gen.likes_count}</b>\n"
        f"📤 <b>{gen.shares_count}</b>\n"
        f"────────────"
    )


def _feed_fallback_text(card: FeedGenerationCard, caption: str) -> str:
    result_url = html.escape(card.generation.result_url or "")
    link = f'\n\n🔗 <a href="{result_url}">Открыть результат</a>' if result_url else ""
    return (
        f"{caption}\n\n"
        "⚠️ Telegram не смог открыть превью как фото, но пост доступен по ссылке."
        f"{link}"
    )


async def _cards_for_source(session: AsyncSession, source: str) -> list[FeedGenerationCard]:
    if source == "top":
        return await repo.get_top_day_generations(session, limit=10)
    return await repo.get_feed_generations(session, limit=30)


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
) -> None:
    caption = _feed_caption(card, position=index + 1 if source == "top" else None)
    reply_markup = feed_card_kb(
        card.generation.id,
        index=index,
        source=source,
        has_next=total > 1,
    )
    result_url = card.generation.result_url

    if result_url and holder.photo:
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

    if result_url:
        try:
            await holder.answer_photo(result_url, caption=caption, reply_markup=reply_markup)
            return
        except TelegramBadRequest as e:
            logger.warning(
                "Feed photo fallback gen=%s url=%s error=%s",
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
                "Feed photo unexpected fallback gen=%s url=%s error=%s",
                card.generation.id,
                result_url,
                e,
            )
            await holder.answer(
                _feed_fallback_text(card, caption),
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
) -> None:
    cards = await _cards_for_source(session, source)
    if not cards:
        await _show_feed_empty(holder, top_day=source == "top")
        return
    idx = index % len(cards)
    await _show_feed_card(
        holder=holder,
        card=cards[idx],
        source=source,
        index=idx,
        total=len(cards),
    )


async def show_feed_card_by_id(
    *,
    message: Message,
    session: AsyncSession,
    gen_id: int,
) -> None:
    card = await repo.get_feed_generation_card(session, gen_id)
    if not card:
        await message.answer("Пост не найден или уже скрыт.", reply_markup=empty_feed_kb())
        return
    await _show_feed_card(holder=message, card=card, source="feed", index=0, total=1)


@router.message(Command("feed"))
@router.callback_query(F.data == "menu:feed")
async def open_feed(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    holder = event.message if isinstance(event, CallbackQuery) else event
    await show_feed_from_source(holder=holder, session=session, source="feed", index=0)  # type: ignore[arg-type]
    if isinstance(event, CallbackQuery):
        await safe_answer_callback(event)


@router.callback_query(F.data == "menu:top_day")
@router.callback_query(F.data == "feed:top")
async def open_top_day(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await show_feed_from_source(holder=call.message, session=session, source="top", index=0)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("feed:next:"))
async def cb_feed_next(call: CallbackQuery, session: AsyncSession) -> None:
    _, _, source, index_raw = call.data.split(":", 3)  # type: ignore[union-attr]
    await show_feed_from_source(
        holder=call.message,  # type: ignore[arg-type]
        session=session,
        source=source,
        index=int(index_raw),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("feed:like:"))
async def cb_feed_like(call: CallbackQuery, session: AsyncSession) -> None:
    _, _, gen_id_raw, source, index_raw = call.data.split(":", 4)  # type: ignore[union-attr]
    await repo.like_feed_generation(session, int(gen_id_raw))
    await show_feed_from_source(
        holder=call.message,  # type: ignore[arg-type]
        session=session,
        source=source,
        index=int(index_raw),
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
    share_link = f"https://t.me/{bot_info.username}?start=feed_{gen.id}"
    await call.message.answer(
        f"📤 <b>Ссылка на пост</b>\n{share_link}\n\n"
        f"👥 Твоя реферальная ссылка:\nhttps://t.me/{bot_info.username}?start={db_user.referral_code}",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call, "Ссылка готова")


@router.callback_query(F.data.startswith("feed:remix:"))
async def cb_feed_remix(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
) -> None:
    from bot.handlers.image_gen import _launch_session_generation, _supports_img2img

    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    card = await repo.get_feed_generation_card(session, gen_id)
    if not card:
        await call.answer("Пост не найден", show_alert=True)
        return

    gen = card.generation
    model_cost = await repo.get_model_cost(session, gen.model)
    if not model_cost:
        await call.answer("Модель этого поста недоступна", show_alert=True)
        return
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋. Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    reference_url = gen.result_url if _supports_img2img(gen.model) else None
    mode = "image" if reference_url else "text"
    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=gen.model,
        mode=mode,
        aspect_ratio=card.aspect_ratio,
        quality=_default_quality_for_model(gen.model, card.quality),
        count=_default_count_for_model(gen.model, card.count),
        base_prompt=gen.prompt,
        reference_file_id=None,
        reference_url=reference_url,
    )

    await state.update_data(
        prompt=gen.prompt,
        model=gen.model,
        aspect_ratio=card.aspect_ratio,
        reference_url=reference_url,
        image_session_id=image_session.id,
    )
    await _launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=gen.prompt,
        action_type=ImageGenerationAction.remix,
        reference_url=reference_url,
        parent_generation_id=gen.id,
        launching_text="✨ <b>Запускаю ремикс из ленты...</b>",
        queued_text="⏳ <b>Ремикс запущен.</b> Результат придёт сюда автоматически.",
    )
    await safe_answer_callback(call, "Ремикс запущен ✨")
