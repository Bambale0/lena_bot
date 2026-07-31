from __future__ import annotations

import html
from io import BytesIO

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
from core.trends import (
    TREND_TAG,
    build_trend_tags,
    is_trend_prompt,
    trend_kind,
    trend_settings,
)
from db import repository as repo
from db.models import GenerationType, PromptCategory, User, UserPrompt
from db.prompt_repository import (
    approve_prompt,
    create_prompt,
    deactivate_prompt,
    get_prompt_by_id,
    get_prompts_by_tag,
)

router = Router(name="trends")
MAX_BOT_PREVIEW_BYTES = 20 * 1024 * 1024


class TrendAdminFSM(StatesGroup):
    title = State()
    description = State()
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


@router.message(Command("trends"))
@router.callback_query(F.data == "menu:trends")
async def open_trends(event: Message | CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User | None = None) -> None:
    await state.clear()
    holder = event.message if isinstance(event, CallbackQuery) else event
    await _show(holder, session, db_user, 0)  # type: ignore[arg-type]
    if isinstance(event, CallbackQuery):
        await safe_answer_callback(event)


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
    if not is_trend_prompt(prompt) or not prompt.is_public or getattr(prompt.status, "value", prompt.status) != "approved":
        await call.answer("Тренд уже скрыт", show_alert=True)
        return
    if trend_kind(prompt) == "video":
        url = f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app?trend={prompt.id}"
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🎬 Открыть видео-тренд", web_app=WebAppInfo(url=url)))
        builder.row(InlineKeyboardButton(text="🔥 Другие тренды", callback_data="menu:trends"))
        await call.message.answer(
            "🎬 Настройки видео-тренда готовы. Открой приложение, добавь исходное фото при необходимости и запусти генерацию.",
            reply_markup=builder.as_markup(),
        )
        await safe_answer_callback(call)
        return

    from bot.handlers.marketplace import _launch_prompt_generation

    await _launch_prompt_generation(
        call=call,
        session=session,
        state=state,
        db_user=db_user,
        bot=bot,
        prompt=prompt,
        remix=False,
    )
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
async def trend_description(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = (message.text or "").strip()
    if len(value) > 200:
        await message.answer("Описание длиннее 200 символов.")
        return
    data = await state.get_data()
    kind = data.get("kind", "image")
    models = [
        item for item in await repo.get_all_model_costs(session)
        if getattr(getattr(item, "gen_type", None), "value", None) == kind and getattr(item, "is_active", True)
    ]
    if not models:
        await message.answer("Нет активных моделей этого типа.", reply_markup=back_to_menu_kb())
        await state.clear()
        return
    await state.update_data(description=value)
    await state.set_state(TrendAdminFSM.model)
    builder = InlineKeyboardBuilder()
    for item in models:
        builder.row(InlineKeyboardButton(text=item.display_name[:50], callback_data=f"trends:model:{item.model_key}"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="trends:cancel"))
    await message.answer("Выбери модель:", reply_markup=builder.as_markup())


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
    builder = InlineKeyboardBuilder()
    builder.row(*(InlineKeyboardButton(text=f"{value} сек", callback_data=f"trends:duration:{value}") for value in (5, 8, 10)))
    await call.message.answer("Длительность по умолчанию:", reply_markup=builder.as_markup())
    await safe_answer_callback(call)


@router.callback_query(TrendAdminFSM.duration, F.data.startswith("trends:duration:"), IsAdmin())
async def trend_duration(call: CallbackQuery, state: FSMContext) -> None:
    duration = int(call.data.rsplit(":", 1)[1])  # type: ignore[union-attr]
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
        "scenario": data.get("scenario"),
        "duration": data.get("duration"),
        "requires_reference": bool(data.get("requires_reference")),
    }
    prompt = await create_prompt(
        session,
        author_id=db_user.id,
        title=data["title"],
        description=data.get("description", ""),
        category=PromptCategory.photo if kind == "image" else PromptCategory.other,
        prompt_text=data["prompt_template"],
        preview_url=data["preview_url"],
        model=data["model"],
        tags=build_trend_tags(kind, settings_payload),
        is_public=True,
    )
    await approve_prompt(session, prompt.id)
    await state.clear()
    await call.message.answer("✅ Тренд опубликован.")
    await _show(call.message, session, db_user, 0)
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("trends:archive:"), IsAdmin())
async def archive_trend(call: CallbackQuery, session: AsyncSession, db_user: User) -> None:
    trend_id = int(call.data.rsplit(":", 1)[1])  # type: ignore[union-attr]
    prompt = await get_prompt_by_id(session, trend_id)
    if not is_trend_prompt(prompt):
        await call.answer("Тренд не найден", show_alert=True)
        return
    await deactivate_prompt(session, trend_id)
    await call.answer("Тренд скрыт")
    await _show(call.message, session, db_user, 0)  # type: ignore[arg-type]


@router.callback_query(F.data == "trends:cancel", IsAdmin())
async def cancel_trend(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.answer("Загрузка тренда отменена.", reply_markup=back_to_menu_kb())
    await safe_answer_callback(call)
