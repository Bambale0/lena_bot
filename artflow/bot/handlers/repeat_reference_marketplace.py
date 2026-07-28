"""Multi-reference collection for feed repeats and prompt-library launches."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import mirror_telegram_file
from bot.handlers import image_gen, marketplace, repeat_references
from bot.keyboards.main_menu import back_to_menu_kb
from bot.states import PromptUseFSM
from bot.utils.telegram_ui import safe_answer_callback
from db import repository as repo
from db.models import ImageGenerationAction, User


def _keyboard(*, uploaded: int, max_refs: int, feed_repeat: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if uploaded:
        builder.row(
            InlineKeyboardButton(
                text=f"▶️ Запустить · {uploaded} фото",
                callback_data="prompt_multi_ref:run",
            )
        )
    if uploaded < max_refs:
        builder.row(
            InlineKeyboardButton(
                text=f"📸 Добавить ещё · {uploaded}/{max_refs}",
                callback_data="prompt_multi_ref:hint",
            )
        )
    if uploaded:
        builder.row(
            InlineKeyboardButton(text="🧹 Очистить", callback_data="prompt_multi_ref:clear")
        )
    if not feed_repeat:
        builder.row(
            InlineKeyboardButton(text="⏭ Без референса", callback_data="prompt_multi_ref:skip")
        )
    builder.row(InlineKeyboardButton(text="✖️ Отменить", callback_data="prompt_multi_ref:cancel"))
    return builder.as_markup()


def _text(data: dict[str, Any]) -> str:
    uploaded = len(list(data.get("prompt_multi_ref_file_ids") or []))
    max_refs = int(data.get("prompt_multi_ref_max") or 1)
    feed_repeat = data.get("feed_use_prompt") is not None
    title = "🔁 <b>Повтор из ленты</b>" if feed_repeat else "🎨 <b>Генерация по промпту</b>"
    note = (
        "Промпт автора сохранён скрыто. Добавь свои фото-референсы."
        if feed_repeat
        else "Добавь фото для лица, объекта, стиля или композиции."
    )
    return (
        f"{title}\n\n"
        f"Референсы: <b>{uploaded}/{max_refs}</b>\n\n"
        f"{note}\n"
        "Можно отправлять фото по одному или альбомом. Генерация начнётся только после кнопки запуска."
    )


async def _collect_prompt_reference(
    message: Message,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    model_key = str(data.get("use_model_key") or marketplace.DEFAULT_PROMPT_MODEL)
    max_refs = repeat_references._repeat_max_refs(model_key)
    if max_refs <= 1 or not image_gen._supports_img2img(model_key):
        await marketplace.fsm_prompt_use_reference(message, session, db_user, state, bot)
        return

    existing = list(data.get("prompt_multi_ref_file_ids") or [])
    best = sorted(message.photo, key=lambda item: item.file_size or 0, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id
    if file_id not in existing:
        if len(existing) >= max_refs:
            await message.answer(
                f"У выбранной модели максимум {max_refs} референсов.",
                reply_markup=_keyboard(
                    uploaded=len(existing),
                    max_refs=max_refs,
                    feed_repeat=data.get("feed_use_prompt") is not None,
                ),
            )
            return
        existing.append(file_id)

    await state.update_data(
        prompt_multi_ref_file_ids=existing,
        prompt_multi_ref_max=max_refs,
    )
    data = await state.get_data()
    await message.answer(
        _text(data),
        reply_markup=_keyboard(
            uploaded=len(existing),
            max_refs=max_refs,
            feed_repeat=data.get("feed_use_prompt") is not None,
        ),
    )


async def _hint(call: CallbackQuery) -> None:
    await call.answer("Отправь следующее фото обычным сообщением", show_alert=True)


async def _clear(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(prompt_multi_ref_file_ids=[])
    data = await state.get_data()
    await call.message.answer(  # type: ignore[union-attr]
        _text(data),
        reply_markup=_keyboard(
            uploaded=0,
            max_refs=int(data.get("prompt_multi_ref_max") or 1),
            feed_repeat=data.get("feed_use_prompt") is not None,
        ),
    )
    await safe_answer_callback(call, "Референсы очищены")


async def _cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("✖️ Генерация отменена.", reply_markup=back_to_menu_kb())  # type: ignore[union-attr]
    await safe_answer_callback(call)


async def _skip(call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    prompt_id = data.get("use_prompt_id")
    if data.get("feed_use_prompt") is not None:
        await call.answer("Для повтора из ленты нужен хотя бы один референс", show_alert=True)
        return
    if not prompt_id:
        await call.answer("Промпт не найден", show_alert=True)
        return
    # Reuse the legacy, already tested no-reference launch path.
    call.data = f"prompt_skip_ref:{prompt_id}"
    await marketplace.cb_prompt_skip_ref(call, session, db_user, state, bot)


async def _notify_prompt_rewards(bot: Bot, session: AsyncSession, prompt: Any, rewards: dict[str, Any]) -> None:
    if rewards.get("author", 0) <= 0:
        return
    author = await repo.get_user_by_id(session, prompt.author_id)
    if not author:
        return
    try:
        parts = [f"+{rewards['author']} 💋 автору"]
        if rewards.get("l2", 0) > 0:
            parts.append(f"+{rewards['l2']} 💋 lvl2")
        if rewards.get("l3", 0) > 0:
            parts.append(f"+{rewards['l3']} 💋 lvl3")
        await bot.send_message(
            author.tg_id,
            f"💰 Промпт «<b>{prompt.title}</b>» использовали.\n" + " · ".join(parts),
        )
    except Exception:
        marketplace.logger.exception("Failed to notify prompt author %s", author.tg_id)


async def _run(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
) -> None:
    data = await state.get_data()
    model_key = str(data.get("use_model_key") or marketplace.DEFAULT_PROMPT_MODEL)
    file_ids = list(data.get("prompt_multi_ref_file_ids") or [])
    max_refs = repeat_references._repeat_max_refs(model_key)
    file_ids = file_ids[:max_refs]
    if not file_ids:
        await call.answer("Сначала добавь хотя бы одно фото", show_alert=True)
        return

    reference_urls: list[str] = []
    for file_id in file_ids:
        url = await mirror_telegram_file(bot, file_id)
        if url and url not in reference_urls:
            reference_urls.append(url)
    if not reference_urls:
        await call.answer("Не удалось подготовить референсы. Отправь фото ещё раз.", show_alert=True)
        return

    model_cost = await repo.resolve_image_model_cost(
        session,
        model_key,
        quality=marketplace._default_quality_for_model(model_key),
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return
    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно 💋. Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    feed_prompt = data.get("feed_use_prompt")
    if feed_prompt is not None:
        prompt_text = str(feed_prompt)
        source_feed_gen_id = data.get("feed_use_gen_id")
        image_session = await repo.create_image_session(
            session=session,
            user_id=db_user.id,
            model=model_key,
            mode="image",
            aspect_ratio=None,
            quality=marketplace._default_quality_for_model(model_key),
            count=marketplace._default_count_for_model(model_key),
            base_prompt=prompt_text,
            reference_file_id=file_ids[0],
            reference_file_ids=file_ids,
            reference_url=None,
        )
        await state.clear()
        await image_gen._launch_session_generation(
            source_message=call.message,  # type: ignore[arg-type]
            state=state,
            session=session,
            db_user=db_user,
            image_session=image_session,
            prompt=prompt_text,
            action_type=ImageGenerationAction.repeat,
            reference_url=reference_urls,
            parent_generation_id=source_feed_gen_id,
            source_feed_gen_id=source_feed_gen_id,
            launching_text="⏳ <b>Запускаю повтор из ленты с референсами...</b>",
            queued_text="⏳ <b>Повтор из ленты запущен.</b> Результат придёт сюда автоматически.",
        )
        await safe_answer_callback(call, f"Запущено · референсов {len(reference_urls)}")
        return

    prompt_id = data.get("use_prompt_id")
    prompt = await marketplace.get_prompt_by_id(session, prompt_id) if prompt_id else None
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        await state.clear()
        return

    prompt, rewards = await marketplace.use_prompt(
        session,
        prompt.id,
        db_user.id,
        credits_spent=model_cost.credits,
    )
    image_session = await repo.create_image_session(
        session=session,
        user_id=db_user.id,
        model=model_key,
        mode="image",
        aspect_ratio=None,
        quality=marketplace._default_quality_for_model(model_key),
        count=marketplace._default_count_for_model(model_key),
        base_prompt=prompt.prompt_text,
        reference_file_id=file_ids[0],
        reference_file_ids=file_ids,
        reference_url=None,
    )
    await state.clear()
    await image_gen._launch_session_generation(
        source_message=call.message,  # type: ignore[arg-type]
        state=state,
        session=session,
        db_user=db_user,
        image_session=image_session,
        prompt=prompt.prompt_text,
        action_type=ImageGenerationAction.initial,
        reference_url=reference_urls,
        parent_generation_id=None,
        launching_text="⏳ <b>Запускаю генерацию с несколькими референсами...</b>",
        queued_text="⏳ <b>Генерация запущена.</b> Результат придёт сюда автоматически.",
    )
    await _notify_prompt_rewards(bot, session, prompt, rewards)
    await safe_answer_callback(call, f"Запущено · референсов {len(reference_urls)}")


def _register_front(observer: Any, callback: Any, *filters: Any) -> None:
    observer.register(callback, *filters)
    observer.handlers.insert(0, observer.handlers.pop())


_register_front(
    marketplace.router.message,
    _collect_prompt_reference,
    PromptUseFSM.reference_upload,
    F.photo,
)
marketplace.router.callback_query.register(_hint, PromptUseFSM.reference_upload, F.data == "prompt_multi_ref:hint")
marketplace.router.callback_query.register(_clear, PromptUseFSM.reference_upload, F.data == "prompt_multi_ref:clear")
marketplace.router.callback_query.register(_cancel, PromptUseFSM.reference_upload, F.data == "prompt_multi_ref:cancel")
marketplace.router.callback_query.register(_skip, PromptUseFSM.reference_upload, F.data == "prompt_multi_ref:skip")
marketplace.router.callback_query.register(_run, PromptUseFSM.reference_upload, F.data == "prompt_multi_ref:run")
