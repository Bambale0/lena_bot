from __future__ import annotations

import html
from io import BytesIO
from types import SimpleNamespace

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.public_files import local_upload_path_from_url, save_public_file
from bot.filters.admin import IsAdmin
from bot.keyboards.main_menu import back_to_menu_kb
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from core.kling4_access import visible_model_costs
from core.repeat_duration import duration_options
from core.trends import (
    TREND_TAG,
    build_trend_tags,
    is_trend_prompt,
    mirror_trend_category_tag,
    trend_kind,
    trend_user_fields,
)
from db import repository as repo
from db.models import PromptCategory, User, UserPrompt
from db.prompt_repository import (
    approve_prompt,
    create_prompt,
    deactivate_prompt,
    get_prompt_by_id,
    get_prompts_by_tag,
)
from db.trend_category_repository import (
    filter_public_prompt_library_items,
    get_public_category_shelves,
    get_public_category_trends,
    get_visible_trend_category,
    list_visible_trend_categories,
    public_prompt_library_item_is_visible,
    require_existing_trend_category,
)

router = Router(name="trends")
MAX_BOT_PREVIEW_BYTES = 20 * 1024 * 1024
CATEGORY_PAGE_SIZE = 8
FOLDER_TREND_LIMIT = 48


class TrendAdminFSM(StatesGroup):
    title = State()
    description = State()
    category = State()
    model = State()
    scenario = State()
    duration = State()
    preview = State()
    prompt = State()
    confirming = State()


def _is_admin(user: User | None) -> bool:
    return bool(user and user.tg_id in settings.ADMIN_IDS)


def _model_label(model_key: str | None) -> str:
    return str(model_key or "Модель не задана").replace("/", " · ")


def _caption(prompt: UserPrompt, *, index: int, total: int) -> str:
    kind = trend_kind(prompt)
    return (
        f"🔥 <b>Тренды · {index + 1}/{total}</b>\n\n"
        f"<b>{html.escape(prompt.title)}</b>\n"
        f"{html.escape(prompt.description or '')}\n\n"
        f"{'🎬' if kind == 'video' else '🖼'} <b>{'Видео' if kind == 'video' else 'Фото'}</b>\n"
        f"🧠 {html.escape(_model_label(prompt.model))}\n"
        f"🔥 Повторов: <b>{prompt.uses_count}</b>"
    )


def _catalog_kb(prompt: UserPrompt, *, index: int, total: int, is_admin: bool):
    builder = InlineKeyboardBuilder()
    if total > 1:
        builder.row(
            InlineKeyboardButton(text="◀️", callback_data=f"trends:nav:{(index - 1) % total}"),
            InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="trends:noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"trends:nav:{(index + 1) % total}"),
        )
    builder.row(InlineKeyboardButton(text="🔥 Повторить шаблон", callback_data=f"trends:use:{prompt.id}"))
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="➕ Фото-тренд", callback_data="trends:add:image"),
            InlineKeyboardButton(text="🎬 Видео-тренд", callback_data="trends:add:video"),
        )
        builder.row(InlineKeyboardButton(text="🗑 Убрать тренд", callback_data=f"trends:archive:{prompt.id}"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _category_kb(categories, *, page: int, is_admin: bool):
    builder = InlineKeyboardBuilder()
    total_pages = max(1, (len(categories) + CATEGORY_PAGE_SIZE - 1) // CATEGORY_PAGE_SIZE)
    safe_page = min(max(page, 0), total_pages - 1)
    start = safe_page * CATEGORY_PAGE_SIZE
    for category in categories[start : start + CATEGORY_PAGE_SIZE]:
        builder.row(
            InlineKeyboardButton(
                text=f"📁 {str(category.title)[:56]}",
                callback_data=f"trends:folder:{category.key}:{safe_page}",
            )
        )
    if total_pages > 1:
        buttons = []
        if safe_page > 0:
            buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"trends:categories:{safe_page - 1}"))
        buttons.append(InlineKeyboardButton(text=f"{safe_page + 1}/{total_pages}", callback_data="trends:noop"))
        if safe_page + 1 < total_pages:
            buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"trends:categories:{safe_page + 1}"))
        builder.row(*buttons)
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="➕ Фото-тренд", callback_data="trends:add:image"),
            InlineKeyboardButton(text="🎬 Видео-тренд", callback_data="trends:add:video"),
        )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _folder_kb(
    prompt: UserPrompt,
    *,
    index: int,
    total: int,
    category_key: str,
    category_page: int,
    folder_page: int,
    has_more: bool,
    is_admin: bool,
):
    builder = InlineKeyboardBuilder()
    has_previous = index > 0 or folder_page > 0
    has_next = index + 1 < total or has_more
    if has_previous or has_next:
        buttons = []
        if has_previous:
            previous_page = folder_page if index > 0 else folder_page - 1
            previous_index = index - 1 if index > 0 else FOLDER_TREND_LIMIT - 1
            buttons.append(
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=f"trends:fn:{category_key}:{category_page}:{previous_page}:{previous_index}",
                )
            )
        buttons.append(InlineKeyboardButton(text=f"{index + 1}/{total}", callback_data="trends:noop"))
        if has_next:
            next_page = folder_page if index + 1 < total else folder_page + 1
            next_index = index + 1 if index + 1 < total else 0
            buttons.append(
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=f"trends:fn:{category_key}:{category_page}:{next_page}:{next_index}",
                )
            )
        builder.row(
            *buttons,
        )
    builder.row(InlineKeyboardButton(text="🔥 Повторить шаблон", callback_data=f"trends:use:{prompt.id}"))
    if is_admin:
        builder.row(InlineKeyboardButton(text="🗑 Убрать тренд", callback_data=f"trends:archive:{prompt.id}:{category_key}:{category_page}"))
    builder.row(InlineKeyboardButton(text="← Категории", callback_data=f"trends:categories:{category_page}"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _empty_kb(is_admin: bool):
    builder = InlineKeyboardBuilder()
    if is_admin:
        builder.row(
            InlineKeyboardButton(text="➕ Фото-тренд", callback_data="trends:add:image"),
            InlineKeyboardButton(text="🎬 Видео-тренд", callback_data="trends:add:video"),
        )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _media_source(url: str | None):
    if not url:
        return None
    local = local_upload_path_from_url(url)
    if local and local.exists():
        return FSInputFile(local)
    return url


async def _show(
    holder: Message,
    session: AsyncSession,
    user: User | None,
    index: int = 0,
    *,
    trend_id: int | None = None,
) -> None:
    items = await get_prompts_by_tag(session, TREND_TAG, limit=80)
    items = await filter_public_prompt_library_items(session, items)
    if not items:
        await safe_edit_message(
            holder,
            "🔥 <b>Тренды</b>\n\nАдминистратор пока не опубликовал ни одного шаблона.",
            reply_markup=_empty_kb(_is_admin(user)),
        )
        return
    if trend_id is not None:
        idx = next((pos for pos, item in enumerate(items) if item.id == trend_id), -1)
        if idx < 0:
            await safe_edit_message(
                holder,
                "🔥 <b>Тренд не найден</b>\n\nОн был скрыт или ещё не опубликован.",
                reply_markup=_empty_kb(_is_admin(user)),
            )
            return
    else:
        idx = index % len(items)
    prompt = items[idx]
    caption = _caption(prompt, index=idx, total=len(items))
    markup = _catalog_kb(prompt, index=idx, total=len(items), is_admin=_is_admin(user))
    media = _media_source(prompt.preview_url)
    try:
        if trend_kind(prompt) == "video" and media:
            if getattr(holder, "video", None):
                await holder.edit_media(InputMediaVideo(media=media, caption=caption, parse_mode="HTML"), reply_markup=markup)
            else:
                await holder.answer_video(media, caption=caption, reply_markup=markup)
            return
        if media:
            if holder.photo:
                await holder.edit_media(InputMediaPhoto(media=media, caption=caption, parse_mode="HTML"), reply_markup=markup)
            else:
                await holder.answer_photo(media, caption=caption, reply_markup=markup)
            return
    except Exception:
        pass
    await safe_edit_message(holder, caption, reply_markup=markup)


async def _show_categories(
    holder: Message,
    session: AsyncSession,
    user: User | None,
    *,
    page: int,
    edit: bool = True,
) -> None:
    categories = []
    cursor = None
    seen_cursors: set[str] = set()
    while True:
        category_page = await get_public_category_shelves(
            session, limit=24, cursor=cursor, preview_limit=1
        )
        categories.extend(item.category for item in category_page.items)
        if not category_page.has_more or not category_page.next_cursor:
            break
        if category_page.next_cursor in seen_cursors:
            raise RuntimeError("Trend category pagination repeated a cursor")
        seen_cursors.add(category_page.next_cursor)
        cursor = category_page.next_cursor
    if not categories:
        text = "🔥 <b>Тренды</b>\n\nПока нет доступных категорий."
        markup = _empty_kb(_is_admin(user))
        if edit:
            await safe_edit_message(holder, text, reply_markup=markup)
        else:
            await holder.answer(text, reply_markup=markup, parse_mode="HTML")
        return
    total_pages = max(1, (len(categories) + CATEGORY_PAGE_SIZE - 1) // CATEGORY_PAGE_SIZE)
    safe_page = min(max(page, 0), total_pages - 1)
    text = "🔥 <b>Тренды по категориям</b>\n\nВыбери папку — внутри можно листать живые примеры и сразу повторить понравившийся."
    markup = _category_kb(categories, page=safe_page, is_admin=_is_admin(user))
    if edit:
        await safe_edit_message(holder, text, reply_markup=markup)
    else:
        await holder.answer(text, reply_markup=markup, parse_mode="HTML")


async def _show_folder(
    holder: Message,
    session: AsyncSession,
    user: User | None,
    *,
    category_key: str,
    category_page: int,
    folder_page: int,
    index: int,
) -> None:
    safe_folder_page = max(folder_page, 0)
    folder = await get_public_category_trends(
        session,
        key=category_key,
        limit=FOLDER_TREND_LIMIT,
        cursor=None,
        offset=safe_folder_page * FOLDER_TREND_LIMIT,
    )
    if folder is None:
        await safe_edit_message(
            holder,
            "🔥 <b>Категория недоступна</b>\n\nОна была скрыта или перемещена.",
            reply_markup=InlineKeyboardBuilder()
            .row(InlineKeyboardButton(text="← Категории", callback_data=f"trends:categories:{category_page}"))
            .as_markup(),
        )
        return
    if not folder.items:
        await safe_edit_message(
            holder,
            f"📁 <b>{html.escape(str(folder.category.title))}</b>\n\nВ этой папке пока нет опубликованных трендов.",
            reply_markup=InlineKeyboardBuilder()
            .row(InlineKeyboardButton(text="← Категории", callback_data=f"trends:categories:{category_page}"))
            .as_markup(),
        )
        return
    safe_index = index % len(folder.items)
    prompt = folder.items[safe_index]
    caption = _caption(prompt, index=safe_index, total=len(folder.items))
    caption = f"📁 <b>{html.escape(str(folder.category.title))}</b>\n\n{caption}"
    markup = _folder_kb(
        prompt,
        index=safe_index,
        total=len(folder.items),
        category_key=str(folder.category.key),
        category_page=category_page,
        folder_page=safe_folder_page,
        has_more=folder.has_more,
        is_admin=_is_admin(user),
    )
    media = _media_source(prompt.preview_url)
    try:
        if trend_kind(prompt) == "video" and media:
            if getattr(holder, "video", None) or getattr(holder, "photo", None):
                await holder.edit_media(InputMediaVideo(media=media, caption=caption, parse_mode="HTML"), reply_markup=markup)
            else:
                await holder.answer_video(media, caption=caption, reply_markup=markup)
            return
        if media:
            if getattr(holder, "photo", None) or getattr(holder, "video", None):
                await holder.edit_media(InputMediaPhoto(media=media, caption=caption, parse_mode="HTML"), reply_markup=markup)
            else:
                await holder.answer_photo(media, caption=caption, reply_markup=markup)
            return
    except Exception:
        pass
    await safe_edit_message(holder, caption, reply_markup=markup)


@router.message(Command("trends"))
@router.callback_query(F.data == "menu:trends")
async def open_trends(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User | None = None) -> None:
    await state.clear()
    holder = event.message if isinstance(event, CallbackQuery) else event
    await _show_categories(holder, session, db_user, page=0, edit=isinstance(event, CallbackQuery))  # type: ignore[arg-type]
    if isinstance(event, CallbackQuery):
        await safe_answer_callback(event)


@router.callback_query(F.data.startswith("trends:categories:"))
async def navigate_trend_categories(call: CallbackQuery, session: AsyncSession, db_user: User | None = None) -> None:
    raw_page = str(call.data or "").rsplit(":", 1)[-1]
    page = int(raw_page) if raw_page.isascii() and raw_page.isdecimal() else 0
    await _show_categories(call.message, session, db_user, page=page)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("trends:folder:"))
async def open_trend_folder(call: CallbackQuery, session: AsyncSession, db_user: User | None = None) -> None:
    parts = str(call.data or "").split(":")
    if len(parts) != 4 or not parts[3].isascii() or not parts[3].isdecimal():
        await call.answer("Категория недоступна", show_alert=True)
        return
    await _show_folder(
        call.message,  # type: ignore[arg-type]
        session,
        db_user,
        category_key=parts[2],
        category_page=int(parts[3]),
        folder_page=0,
        index=0,
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("trends:fn:"))
async def navigate_trend_folder(call: CallbackQuery, session: AsyncSession, db_user: User | None = None) -> None:
    parts = str(call.data or "").split(":")
    if len(parts) != 6 or not all(part.isascii() and part.isdecimal() for part in parts[3:]):
        await call.answer("Тренд недоступен", show_alert=True)
        return
    await _show_folder(
        call.message,  # type: ignore[arg-type]
        session,
        db_user,
        category_key=parts[2],
        category_page=int(parts[3]),
        folder_page=int(parts[4]),
        index=int(parts[5]),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("trends:nav:"))
async def navigate_trends(call: CallbackQuery, session: AsyncSession, db_user: User | None = None) -> None:
    await _show(call.message, session, db_user, int(call.data.rsplit(":", 1)[1]))  # type: ignore[arg-type,union-attr]
    await safe_answer_callback(call)


@router.callback_query(F.data == "trends:noop")
async def trends_noop(call: CallbackQuery) -> None:
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("trends:use:"))
async def use_trend(call: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User, bot: Bot) -> None:
    trend_id = int(call.data.rsplit(":", 1)[1])  # type: ignore[union-attr]
    prompt = await get_prompt_by_id(session, trend_id)
    if (
        not is_trend_prompt(prompt)
        or not prompt.is_public
        or getattr(prompt.status, "value", prompt.status) != "approved"
        or not await public_prompt_library_item_is_visible(session, prompt)
    ):
        await call.answer("Тренд уже скрыт", show_alert=True)
        return
    # All surfaces use the same server-side resolver, reference upload,
    # checkout and trend_run_claim. A bot callback must not bypass that runner.
    user_fields = trend_user_fields(prompt)
    kind = trend_kind(prompt)
    url = f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app?trend={prompt.id}"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎛 Настроить и повторить", web_app=WebAppInfo(url=url)))
    builder.row(InlineKeyboardButton(text="🔥 Другие тренды", callback_data="menu:trends"))
    if user_fields:
        text = (
            "🎛 Открой тренд, добавь своё фото и измени разрешённые параметры "
            "(например, число или одежду). Исходный промпт остаётся скрытым."
        )
    elif kind == "video":
        text = "🎬 Открой видео-тренд, добавь своё исходное фото и запусти генерацию в приложении."
    else:
        text = "📷 Открой фото-тренд, добавь своё фото и запусти генерацию в приложении."
    await call.message.answer(text, reply_markup=builder.as_markup())
    await safe_answer_callback(call)


def _cancel_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    return builder.as_markup()


@router.callback_query(F.data.startswith("trends:add:"), IsAdmin())
async def start_add_trend(call: CallbackQuery, state: FSMContext) -> None:
    kind = call.data.rsplit(":", 1)[1]  # type: ignore[union-attr]
    await state.clear()
    await state.update_data(kind=kind)
    await state.set_state(TrendAdminFSM.title)
    await call.message.answer("Название тренда — до 60 символов:", reply_markup=_cancel_kb())
    await safe_answer_callback(call)


@router.message(TrendAdminFSM.title, IsAdmin())
async def trend_title(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 3 <= len(value) <= 60:
        await message.answer("Название должно быть от 3 до 60 символов.")
        return
    await state.update_data(title=value)
    await state.set_state(TrendAdminFSM.description)
    await message.answer("Короткое публичное описание — до 200 символов:")


@router.message(TrendAdminFSM.description, IsAdmin())
async def trend_description(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    value = (message.text or "").strip()
    if len(value) > 200:
        await message.answer("Описание длиннее 200 символов.")
        return
    await state.update_data(description=value)
    await state.set_state(TrendAdminFSM.category)
    builder = InlineKeyboardBuilder()
    for category in await list_visible_trend_categories(session):
        builder.row(
            InlineKeyboardButton(
                text=str(category.title)[:64],
                callback_data=f"trends:category:{category.key}",
            )
        )
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    await message.answer("Выбери категорию витрины:", reply_markup=builder.as_markup())


@router.callback_query(TrendAdminFSM.category, F.data.startswith("trends:category:"), IsAdmin())
async def trend_category_pick(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    category = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    visible_category = await get_visible_trend_category(session, category)
    if visible_category is None:
        await call.answer("Категория не найдена", show_alert=True)
        return
    category = str(visible_category.key)
    data = await state.get_data()
    kind = data.get("kind", "image")
    models = [
        item for item in await visible_model_costs(session, await repo.get_all_model_costs(session), SimpleNamespace(tg_id=call.from_user.id))
        if getattr(getattr(item, "gen_type", None), "value", None) == kind and getattr(item, "is_active", True)
    ]
    if not models:
        await call.message.answer("Нет активных моделей этого типа.", reply_markup=back_to_menu_kb())
        await state.clear()
        return
    await state.update_data(category=category)
    await state.set_state(TrendAdminFSM.model)
    builder = InlineKeyboardBuilder()
    for item in models:
        builder.row(InlineKeyboardButton(text=item.display_name[:50], callback_data=f"trends:model:{item.model_key}"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    await call.message.answer("Выбери модель:", reply_markup=builder.as_markup())
    await safe_answer_callback(call)


@router.callback_query(TrendAdminFSM.model, F.data.startswith("trends:model:"), IsAdmin())
async def trend_model(call: CallbackQuery, state: FSMContext) -> None:
    model = call.data.split(":", 2)[2]  # type: ignore[union-attr]
    data = await state.get_data()
    await state.update_data(model=model)
    if data.get("kind") == "video":
        await state.set_state(TrendAdminFSM.scenario)
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="Текст → видео", callback_data="trends:scenario:text"),
            InlineKeyboardButton(text="Фото → видео", callback_data="trends:scenario:image"),
        )
        await call.message.answer("Сценарий видео:", reply_markup=builder.as_markup())
    else:
        await state.set_state(TrendAdminFSM.preview)
        await call.message.answer("Пришли preview: JPEG, PNG или WEBP до 20 МБ.")
    await safe_answer_callback(call)


@router.callback_query(TrendAdminFSM.scenario, F.data.startswith("trends:scenario:"), IsAdmin())
async def trend_scenario(call: CallbackQuery, state: FSMContext) -> None:
    scenario = call.data.rsplit(":", 1)[1]  # type: ignore[union-attr]
    await state.update_data(scenario=scenario, requires_reference=scenario == "image")
    await state.set_state(TrendAdminFSM.duration)
    data = await state.get_data()
    durations = duration_options(str(data.get("model") or ""))
    builder = InlineKeyboardBuilder()
    for start in range(0, len(durations), 4):
        builder.row(*(InlineKeyboardButton(text=f"{value} сек", callback_data=f"trends:duration:{value}") for value in durations[start:start + 4]))
    await call.message.answer("Длительность по умолчанию:", reply_markup=builder.as_markup())
    await safe_answer_callback(call)


@router.callback_query(TrendAdminFSM.duration, F.data.startswith("trends:duration:"), IsAdmin())
async def trend_duration(call: CallbackQuery, state: FSMContext) -> None:
    raw = str(call.data or "").rsplit(":", 1)[-1]
    duration = int(raw) if raw.isascii() and raw.isdecimal() and len(raw) <= 2 else None
    data = await state.get_data()
    allowed = duration_options(str(data.get("model") or ""))
    if duration not in allowed:
        await call.answer("Для этой модели выбери доступную длительность", show_alert=True)
        return
    await state.update_data(duration=duration)
    await state.set_state(TrendAdminFSM.preview)
    await call.message.answer("Пришли video preview: MP4, WEBM или MOV до 20 МБ.")
    await safe_answer_callback(call)


def _image_ok(data: bytes, content_type: str) -> bool:
    return content_type in {"image/jpeg", "image/png", "image/webp"} and (
        data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n") or (data.startswith(b"RIFF") and b"WEBP" in data[:16])
    )


def _video_ok(data: bytes, content_type: str) -> bool:
    if content_type == "video/webm":
        return data.startswith(b"\x1aE\xdf\xa3")
    return content_type in {"video/mp4", "video/quicktime"} and len(data) >= 12 and b"ftyp" in data[4:16]


@router.message(TrendAdminFSM.preview, IsAdmin())
async def trend_preview(message: Message, state: FSMContext, bot: Bot) -> None:
    data_state = await state.get_data()
    kind = data_state.get("kind", "image")
    media = None
    content_type = ""
    if kind == "image":
        if message.photo:
            media = message.photo[-1]
            content_type = "image/jpeg"
        elif message.document:
            media = message.document
            content_type = str(message.document.mime_type or "")
    else:
        if message.video:
            media = message.video
            content_type = str(message.video.mime_type or "video/mp4")
        elif message.document:
            media = message.document
            content_type = str(message.document.mime_type or "")
    if media is None:
        await message.answer("Нужен файл подходящего типа.")
        return
    buf = BytesIO()
    await bot.download(media, destination=buf)
    raw = buf.getvalue()
    if not raw or len(raw) > MAX_BOT_PREVIEW_BYTES:
        await message.answer("Файл пустой или больше 20 МБ.")
        return
    valid = _video_ok(raw, content_type) if kind == "video" else _image_ok(raw, content_type)
    if not valid:
        await message.answer("Неподдерживаемый формат preview.")
        return
    url = save_public_file(raw, content_type)
    await state.update_data(preview_url=url)
    await state.set_state(TrendAdminFSM.prompt)
    await message.answer("Теперь пришли скрытый рабочий prompt — до 8000 символов.")


@router.message(TrendAdminFSM.prompt, IsAdmin())
async def trend_prompt(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    if not 1 <= len(value) <= 8000:
        await message.answer("Prompt должен быть от 1 до 8000 символов.")
        return
    await state.update_data(prompt_template=value)
    data = await state.get_data()
    await state.set_state(TrendAdminFSM.confirming)
    preview = html.escape(value[:350])
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Опубликовать", callback_data="trends:confirm"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    await message.answer(
        f"<b>{html.escape(data['title'])}</b>\n"
        f"{html.escape(data.get('description', ''))}\n\n"
        f"Тип: {data.get('kind')}\nМодель: <code>{html.escape(data['model'])}</code>\n\n"
        f"Начало скрытого prompt:\n<code>{preview}</code>",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(TrendAdminFSM.confirming, F.data == "trends:confirm", IsAdmin())
async def confirm_trend(call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    kind = data.get("kind", "image")
    settings_payload = {
        "category": data.get("category", "featured"),
        "scenario": data.get("scenario"),
        "duration": data.get("duration"),
        "requires_reference": bool(data.get("requires_reference")),
    }
    if kind == "video" and data.get("duration") not in duration_options(str(data.get("model") or "")):
        await call.answer("Для этой модели выбери доступную длительность", show_alert=True)
        return
    try:
        category = await require_existing_trend_category(
            session, settings_payload["category"]
        )
    except ValueError:
        await call.answer("Эта категория больше недоступна", show_alert=True)
        return
    settings_payload["category"] = category.key
    trend_tags = mirror_trend_category_tag(
        build_trend_tags(kind, settings_payload), category.key
    )
    prompt = await create_prompt(
        session,
        author_id=db_user.id,
        title=data["title"],
        description=data.get("description", ""),
        category=PromptCategory.photo if kind == "image" else PromptCategory.other,
        prompt_text=data["prompt_template"],
        preview_url=data["preview_url"],
        model=data["model"],
        tags=trend_tags,
        is_public=True,
        trend_category_id=int(category.id),
    )
    await approve_prompt(session, prompt.id)
    await state.clear()
    await call.message.answer("✅ Тренд опубликован.")
    await _show_categories(call.message, session, db_user, page=0)  # type: ignore[arg-type]
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("trends:archive:"), IsAdmin())
async def archive_trend(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    parts = str(call.data or "").split(":")
    if len(parts) not in {3, 5} or not parts[2].isascii() or not parts[2].isdecimal():
        await call.answer("Тренд не найден", show_alert=True)
        return
    trend_id = int(parts[2])
    prompt = await get_prompt_by_id(session, trend_id)
    if not is_trend_prompt(prompt):
        await call.answer("Тренд не найден", show_alert=True)
        return
    await deactivate_prompt(session, trend_id)
    await call.answer("Тренд скрыт")
    category_page = int(parts[4]) if len(parts) == 5 and parts[4].isascii() and parts[4].isdecimal() else 0
    await _show_categories(call.message, session, db_user, page=category_page)  # type: ignore[arg-type]


@router.callback_query(F.data == "trends:cancel", IsAdmin())
async def cancel_trend(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("Загрузка тренда отменена.", reply_markup=back_to_menu_kb())
    await safe_answer_callback(call)
