# bot/handlers/marketplace.py
"""
Маркетплейс пользовательских промптов.

Команды/точки входа:
  /prompts          — каталог
  menu:prompts      — кнопка в главном меню
  prompts:add       — загрузить промпт (FSM)
  prompts:my        — мои промпты + статистика
  mod:approve/reject — модерация (только admin)
"""
from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.filters.admin import IsAdmin
from bot.keyboards.prompts import (
    PAGE_SIZE,
    category_filter_kb,
    category_select_kb,
    moderation_kb,
    my_prompt_detail_kb,
    my_prompts_kb,
    prompt_confirm_kb,
    prompt_detail_kb,
    prompts_list_kb,
    use_prompt_model_kb,
)
from bot.states.prompt import PromptModerateFSM, PromptUploadFSM
from db.models import PromptCategory, User
from db.prompt_repository import (
    MAX_ACTIVE_PROMPTS_PER_USER,
    PROMPT_REWARD_CREDITS,
    approve_prompt,
    count_active_prompts_by_author,
    count_approved_prompts,
    create_prompt,
    deactivate_prompt,
    get_approved_prompts,
    get_author_prompts,
    get_author_total_uses,
    get_pending_prompts,
    get_prompt_by_id,
    reject_prompt,
    use_prompt,
)
from db import repository as repo

logger = logging.getLogger(__name__)
router = Router(name="marketplace")


# ── Каталог ───────────────────────────────────────────────────────────────────

@router.message(Command("prompts"))
@router.callback_query(F.data == "menu:prompts")
async def open_catalog(event: Message | CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    text = (
        "🗂 <b>Маркетплейс промптов</b>\n\n"
        "Выбери категорию или просмотри все промпты.\n"
        "Используй чужие промпты — авторы получают бонусы!"
    )
    kb = category_filter_kb(selected=None)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb)


@router.callback_query(F.data == "prompts:open")
async def cb_open_catalog(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        "🗂 <b>Маркетплейс промптов</b>\n\nВыбери категорию:",
        reply_markup=category_filter_kb(selected=None),
    )
    await call.answer()


@router.callback_query(F.data.startswith("prompts:cat:"))
async def cb_category_filter(call: CallbackQuery, session: AsyncSession) -> None:
    raw = call.data.split(":")[2]
    category = None if raw == "all" else PromptCategory(raw)

    prompts = await get_approved_prompts(session, category=category, limit=PAGE_SIZE)
    total = await count_approved_prompts(session, category=category)

    if not prompts:
        await call.answer("В этой категории пока нет промптов", show_alert=True)
        return

    cat_label = "все категории" if not category else category.label()
    text = f"🗂 <b>Промпты — {cat_label}</b>\n<i>Всего: {total}</i>"
    await call.message.edit_text(
        text,
        reply_markup=prompts_list_kb(prompts, page=0, total=total, category=raw if category else None),
    )
    await call.answer()


@router.callback_query(F.data.startswith("prompts:page:"))
async def cb_page(call: CallbackQuery, session: AsyncSession) -> None:
    _, _, page_str, cat_raw = call.data.split(":")
    page = int(page_str)
    category = None if cat_raw == "all" else PromptCategory(cat_raw)

    prompts = await get_approved_prompts(session, category=category, offset=page * PAGE_SIZE, limit=PAGE_SIZE)
    total = await count_approved_prompts(session, category=category)
    cat_label = "все категории" if not category else category.label()

    await call.message.edit_text(
        f"🗂 <b>Промпты — {cat_label}</b>\n<i>Всего: {total}</i>",
        reply_markup=prompts_list_kb(prompts, page=page, total=total, category=cat_raw if category else None),
    )
    await call.answer()


# ── Детальный просмотр промпта ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("prompts:view:"))
async def cb_view_prompt(call: CallbackQuery, session: AsyncSession) -> None:
    prompt_id = int(call.data.split(":")[2])
    prompt = await get_prompt_by_id(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return

    author = await repo.get_user_by_id(session, prompt.author_id)
    author_str = f"@{author.username}" if author and author.username else "анонимный"

    text = (
        f"📝 <b>{prompt.title}</b>\n"
        f"<i>{prompt.description}</i>\n\n"
        f"👤 Автор: {author_str}\n"
        f"📂 Категория: {prompt.category.label()}\n"
        f"🔢 Использований: {prompt.uses_count}\n\n"
        f"<blockquote>{prompt.prompt_text}</blockquote>"
    )
    await call.message.edit_text(text, reply_markup=prompt_detail_kb(prompt_id))
    await call.answer()


@router.callback_query(F.data.startswith("prompts:use:"))
async def cb_use_prompt(call: CallbackQuery) -> None:
    prompt_id = int(call.data.split(":")[2])
    await call.message.edit_reply_markup(reply_markup=use_prompt_model_kb(prompt_id))
    await call.answer("Выбери тип генерации")


# ── Использование промпта → запуск генерации ──────────────────────────────────

@router.callback_query(F.data.startswith("prompts:gen_img:"))
async def cb_gen_image_from_prompt(
    call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot
) -> None:
    prompt_id = int(call.data.split(":")[2])
    await _launch_generation(call, session, db_user, state, bot, prompt_id, gen_type="image")


@router.callback_query(F.data.startswith("prompts:gen_vid:"))
async def cb_gen_video_from_prompt(
    call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot
) -> None:
    prompt_id = int(call.data.split(":")[2])
    await _launch_generation(call, session, db_user, state, bot, prompt_id, gen_type="video")


async def _launch_generation(
    call: CallbackQuery,
    session: AsyncSession,
    db_user: User,
    state: FSMContext,
    bot: Bot,
    prompt_id: int,
    gen_type: str,
) -> None:
    """Регистрирует использование промпта и переводит в FSM выбора модели."""
    try:
        prompt, reward_given = await use_prompt(session, prompt_id, db_user.id)
    except ValueError:
        await call.answer("Промпт недоступен", show_alert=True)
        return

    # Уведомляем автора (не себе)
    if reward_given:
        author = await repo.get_user_by_id(session, prompt.author_id)
        if author:
            try:
                await bot.send_message(
                    author.tg_id,
                    f"💰 Ваш промпт «<b>{prompt.title}</b>» использовали!\n"
                    f"+{PROMPT_REWARD_CREDITS} кредитов зачислено.",
                )
            except Exception as e:
                logger.warning("Failed to notify prompt author %s: %s", author.tg_id, e)

    # Сохраняем промпт в FSM и открываем выбор модели
    await state.update_data(prefill_prompt=prompt.prompt_text, from_marketplace=True)

    from bot.keyboards.models import image_models_kb, video_models_kb
    model_costs = await repo.get_all_model_costs(session) if hasattr(repo, "get_all_model_costs") else []

    from db import repository as repo_mod
    model_costs = await repo_mod.get_all_model_costs(session)

    if gen_type == "image":
        from bot.states import ImageGenFSM
        await state.set_state(ImageGenFSM.model_select)
        await call.message.edit_text(
            f"🎨 Промпт «<b>{prompt.title}</b>» выбран.\n\nВыбери модель изображения:",
            reply_markup=image_models_kb(model_costs),
        )
    else:
        from bot.states import VideoGenFSM
        await state.set_state(VideoGenFSM.model_select)
        await call.message.edit_text(
            f"🎬 Промпт «<b>{prompt.title}</b>» выбран.\n\nВыбери модель видео:",
            reply_markup=video_models_kb(model_costs),
        )
    await call.answer()


# ── Добавление промпта (FSM) ──────────────────────────────────────────────────

@router.callback_query(F.data == "prompts:add")
async def cb_add_prompt(call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext) -> None:
    active = await count_active_prompts_by_author(session, db_user.id)
    if active >= MAX_ACTIVE_PROMPTS_PER_USER:
        await call.answer(
            f"Максимум {MAX_ACTIVE_PROMPTS_PER_USER} активных промптов. "
            "Деактивируй старый, чтобы добавить новый.",
            show_alert=True,
        )
        return

    await state.set_state(PromptUploadFSM.title)
    await call.message.edit_text(
        "➕ <b>Добавить промпт</b>\n\n"
        "<b>Шаг 1/4</b> — Введи название промпта (до 60 символов):\n\n"
        "<i>Пример: «Портрет в стиле аниме»</i>",
    )
    await call.answer()


@router.message(PromptUploadFSM.title, F.text)
async def fsm_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if len(title) > 60:
        await message.answer(f"⚠️ Слишком длинное название ({len(title)} символов). Максимум 60.")
        return
    await state.update_data(title=title)
    await state.set_state(PromptUploadFSM.description)
    await message.answer(
        "<b>Шаг 2/4</b> — Добавь описание промпта (до 200 символов):\n\n"
        "<i>Что генерирует этот промпт? Для чего он подходит?</i>"
    )


@router.message(PromptUploadFSM.description, F.text)
async def fsm_description(message: Message, state: FSMContext) -> None:
    desc = message.text.strip()
    if len(desc) > 200:
        await message.answer(f"⚠️ Слишком длинное описание ({len(desc)} символов). Максимум 200.")
        return
    await state.update_data(description=desc)
    await state.set_state(PromptUploadFSM.category)
    await message.answer("<b>Шаг 3/4</b> — Выбери категорию:", reply_markup=category_select_kb())


@router.callback_query(PromptUploadFSM.category, F.data.startswith("prompt_cat:"))
async def fsm_category(call: CallbackQuery, state: FSMContext) -> None:
    cat_value = call.data.split(":")[1]
    category = PromptCategory(cat_value)
    await state.update_data(category=cat_value)
    await state.set_state(PromptUploadFSM.prompt_text)
    await call.message.edit_text(
        f"Категория: <b>{category.label()}</b> ✓\n\n"
        "<b>Шаг 4/4</b> — Введи текст промпта:\n\n"
        "<i>Напиши сам промпт — он будет виден другим пользователям</i>"
    )
    await call.answer()


@router.message(PromptUploadFSM.prompt_text, F.text)
async def fsm_prompt_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    await state.update_data(prompt_text=text)
    await state.set_state(PromptUploadFSM.confirm)

    data = await state.get_data()
    cat = PromptCategory(data["category"])
    preview = (
        f"📋 <b>Предпросмотр промпта</b>\n\n"
        f"<b>Название:</b> {data['title']}\n"
        f"<b>Описание:</b> {data['description']}\n"
        f"<b>Категория:</b> {cat.label()}\n\n"
        f"<b>Текст промпта:</b>\n<blockquote>{text[:500]}</blockquote>"
    )
    await message.answer(preview, reply_markup=prompt_confirm_kb())


@router.callback_query(PromptUploadFSM.confirm, F.data == "prompt_confirm:yes")
async def fsm_confirm(
    call: CallbackQuery, session: AsyncSession, db_user: User, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    await state.clear()

    prompt = await create_prompt(
        session,
        author_id=db_user.id,
        title=data["title"],
        description=data["description"],
        category=PromptCategory(data["category"]),
        prompt_text=data["prompt_text"],
    )

    await call.message.edit_text(
        f"✅ Промпт «<b>{prompt.title}</b>» отправлен на проверку.\n\n"
        "Администратор рассмотрит его в ближайшее время. "
        "Ты получишь уведомление о результате."
    )
    await call.answer()

    # Уведомляем админов
    from core.config import settings
    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"📬 <b>Новый промпт на модерацию</b>\n\n"
                f"ID: {prompt.id}\n"
                f"Название: {prompt.title}\n"
                f"Категория: {prompt.category.label()}\n"
                f"Автор: {db_user.tg_id} (@{db_user.username or '—'})\n\n"
                f"Текст:\n<blockquote>{prompt.prompt_text[:400]}</blockquote>",
                reply_markup=moderation_kb(prompt.id),
            )
        except Exception as e:
            logger.warning("Failed to notify admin %s: %s", admin_id, e)


@router.callback_query(PromptUploadFSM.confirm, F.data == "prompt_confirm:edit")
async def fsm_edit(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromptUploadFSM.title)
    await call.message.edit_text(
        "✏️ Начнём сначала.\n\n"
        "<b>Шаг 1/4</b> — Введи название промпта (до 60 символов):"
    )
    await call.answer()


# ── Мои промпты ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "prompts:my")
async def cb_my_prompts(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    prompts = await get_author_prompts(session, db_user.id)
    total_uses = await get_author_total_uses(session, db_user.id)
    total_earned = total_uses * PROMPT_REWARD_CREDITS  # приблизительно (без учёта своих)

    if not prompts:
        await call.message.edit_text(
            "📊 <b>Мои промпты</b>\n\nУ тебя ещё нет промптов.\n\nДобавь первый!",
            reply_markup=category_filter_kb(),
        )
        await call.answer()
        return

    text = (
        f"📊 <b>Мои промпты</b>\n\n"
        f"Всего промптов: {len(prompts)}\n"
        f"Суммарно использований: {total_uses}\n"
        f"Заработано через промпты: ~{total_earned} кр\n"
    )
    await call.message.edit_text(text, reply_markup=my_prompts_kb(prompts))
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
        f"Категория: {prompt.category.label()}\n\n"
    )
    if prompt.reject_reason:
        text += f"❌ Причина отказа: {prompt.reject_reason}\n\n"
    text += f"<blockquote>{prompt.prompt_text[:500]}</blockquote>"

    await call.message.edit_text(
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


# ── Модерация (только admin) ──────────────────────────────────────────────────

mod_router = Router(name="marketplace_mod")
mod_router.callback_query.filter(IsAdmin())


@mod_router.callback_query(F.data.startswith("mod:approve:"))
async def cb_mod_approve(call: CallbackQuery, session: AsyncSession, bot: Bot) -> None:
    prompt_id = int(call.data.split(":")[2])
    prompt = await approve_prompt(session, prompt_id)
    if not prompt:
        await call.answer("Промпт не найден", show_alert=True)
        return

    await call.message.edit_text(
        f"✅ Промпт <b>#{prompt_id}</b> «{prompt.title}» — одобрен."
    )
    await call.answer("Одобрено ✓")

    # Уведомляем автора
    author = await repo.get_user_by_id(session, prompt.author_id)
    if author:
        try:
            await bot.send_message(
                author.tg_id,
                f"🎉 Ваш промпт «<b>{prompt.title}</b>» опубликован в каталоге!\n\n"
                "Теперь другие пользователи могут его использовать. "
                "Вы будете получать +3 кредита за каждое использование.",
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
async def cb_mod_reject_reason(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
) -> None:
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
                f"❌ Промпт «<b>{prompt.title}</b>» отклонён.\n"
                f"Причина: {reason}\n\n"
                "Ты можешь исправить промпт и загрузить заново.",
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

    await call.message.edit_text(f"🔴 Промпт #{prompt_id} «{prompt.title}» — деактивирован.")
    await call.answer("Деактивировано ✓")

    author = await repo.get_user_by_id(session, prompt.author_id)
    if author:
        try:
            await bot.send_message(
                author.tg_id,
                f"⚠️ Ваш промпт «<b>{prompt.title}</b>» заблокирован администратором.",
            )
        except Exception:
            pass


@mod_router.callback_query(F.data == "adm:prompts")
async def cb_adm_prompts(call: CallbackQuery, session: AsyncSession) -> None:
    """Список промптов на модерации из /admin панели."""
    pending = await get_pending_prompts(session)
    if not pending:
        await call.answer("Нет промптов на модерации ✓", show_alert=True)
        return

    for p in pending[:10]:  # показываем по 10 за раз
        author = await repo.get_user_by_id(session, p.author_id)
        author_str = f"@{author.username}" if author and author.username else str(p.author_id)
        await call.message.answer(
            f"📬 <b>#{p.id}</b> — {p.title}\n"
            f"Категория: {p.category.label()} · Автор: {author_str}\n\n"
            f"<blockquote>{p.prompt_text[:300]}</blockquote>",
            reply_markup=moderation_kb(p.id),
        )
    await call.answer()
