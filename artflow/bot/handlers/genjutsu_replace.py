"""Source-first Genjutsu editor using the shared Seedance launch/billing path."""

from __future__ import annotations

import logging
import secrets
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from api.seedance25_adapter import MODEL_KEY, RESOLUTIONS
from bot.handlers import video_gen as legacy
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from core.seedance_repeat_overrides import (
    build_seedance_content_edit_prompt,
    build_seedance_reference_plan,
    normalize_seedance_content_edit,
    restore_seedance_reference_plan,
)
from db.models import User

logger = logging.getLogger(__name__)
router = Router(name="genjutsu_face_clothing")
FLOW_ID = "genjutsu_face_clothing"


class GenjutsuReplaceFSM(StatesGroup):
    source_video = State()
    identity = State()
    clothing = State()
    number = State()
    resolution = State()
    confirm = State()
    launching = State()


STEPS = [
    GenjutsuReplaceFSM.source_video,
    GenjutsuReplaceFSM.identity,
    GenjutsuReplaceFSM.clothing,
    GenjutsuReplaceFSM.number,
    GenjutsuReplaceFSM.resolution,
    GenjutsuReplaceFSM.confirm,
]


async def _available(session: AsyncSession, resolution: str | None = None):
    if not settings.KIE_API_KEY:
        return None
    base = await legacy.repo.get_model_cost(session, MODEL_KEY)
    if not base or not base.is_active:
        return None
    if resolution is None:
        return base
    cost = await legacy._resolve_video_model_cost(
        session, MODEL_KEY, duration=None, resolution=resolution
    )
    return cost if cost and cost.is_active else None


async def _plan(state: FSMContext):
    data = await state.get_data()
    plan = build_seedance_reference_plan(
        data.get("gj_identity_urls", []), data.get("gj_clothing_url")
    )
    edit = normalize_seedance_content_edit(data.get("seedance_content_edit") or {})
    await state.update_data(
        image_url=list(plan.image_urls),
        seedance_reference_roles=list(plan.roles),
        seedance_content_edit=edit,
    )
    return plan, edit


async def _quote(state: FSMContext, session: AsyncSession) -> float:
    data = await state.get_data()
    plan, edit = await _plan(state)
    build_seedance_content_edit_prompt(plan, edit)  # Validate full technical prompt before charge.
    if data.get("resolution") not in RESOLUTIONS:
        raise ValueError("Выбери качество видео: 480p, 720p или 1080p.")
    duration = await legacy.seedance25_edit_billing_duration(
        "", data.get("reference_video_url"), force_edit=True
    )
    if duration is None:
        raise ValueError("Сначала загрузи исходное видео.")
    cost = await _available(session, data["resolution"])
    if cost is None:
        raise ValueError("Seedance 2.5 сейчас недоступен. Попробуй позже.")
    total = legacy._video_total_credits(MODEL_KEY, duration, float(cost.credits))
    await state.update_data(duration=duration, credits=float(cost.credits), aspect_ratio="adaptive")
    return total


async def _render(
    target: Message, state: FSMContext, *, edit: bool = False, notice: str = ""
) -> None:
    data = await state.get_data()
    current = await state.get_state()
    token = secrets.token_hex(6)
    await state.update_data(gj_token=token)
    kb = InlineKeyboardBuilder()

    def button(text: str, action: str):
        kb.button(text=text, callback_data=f"gjreplace:{action}:{token}")

    texts = {
        GenjutsuReplaceFSM.source_video.state: "🎭 <b>Замена лица / одежды</b> · 1/6\n\nПришли исходное видео файлом: 4–30 секунд. Сохраним движение, камеру и сцену. Можно заменить лицо, одежду или число.",
        GenjutsuReplaceFSM.identity.state: "👤 <b>Лицо</b> · 2/6\n\nПришли 1–3 фото одного человека, первое — основной ракурс. Или пропусти, чтобы сохранить лицо из видео.",
        GenjutsuReplaceFSM.clothing.state: "👕 <b>Одежда</b> · 3/6\n\nПришли фото одежды, описание текстом или фото с подписью (до 300 символов). Лицо и фон с фото одежды переносить не будем. Можно пропустить.",
        GenjutsuReplaceFSM.number.state: "🔢 <b>Число / цифры</b> · 4/6\n\nКакое число должно быть в видео? Например: 25. Или пропусти, чтобы оставить цифры без изменений.",
        GenjutsuReplaceFSM.resolution.state: "⚙️ <b>Качество</b> · 5/6\n\nВыбери разрешение. Длительность будет как у исходного видео; стоимость покажу до запуска.",
    }
    text = texts.get(current, "")
    content = data.get("seedance_content_edit") or {}
    if current == GenjutsuReplaceFSM.source_video.state and data.get("reference_video_url"):
        text += "\n\n✅ Видео сохранено. Пришли другое или продолжи."
        button("Продолжить с этим видео", "next")
    if current == GenjutsuReplaceFSM.identity.state:
        count = len(data.get("gj_identity_urls") or [])
        text += f"\n\nФото лица: {count}/3"
        if count:
            button("Далее ➡️", "next")
            button("Убрать фото лица", "clear")
        button("Пропустить", "skip")
    if current == GenjutsuReplaceFSM.clothing.state:
        photo, description = bool(data.get("gj_clothing_url")), bool(content.get("clothing"))
        if photo or description:
            text += "\n\n✅ Сохранено: " + (
                "фото + текст" if photo and description else "фото" if photo else "текст"
            )
            if description:
                text += "\n" + escape(content["clothing"])
            button("Далее ➡️", "next")
            button("Убрать одежду", "clear")
        button("Пропустить", "skip")
    if current == GenjutsuReplaceFSM.number.state:
        if content.get("number"):
            text += "\n\nСохранённое число: " + escape(content["number"])
            button("Оставить число и продолжить", "next")
        button("Без изменения цифр", "skip")
    if current == GenjutsuReplaceFSM.resolution.state:
        for resolution in RESOLUTIONS:
            button(resolution, f"res:{resolution}")
    if current == GenjutsuReplaceFSM.confirm.state:
        has_photo, has_text = bool(data.get("gj_clothing_url")), bool(content.get("clothing"))
        clothing = (
            "фото + текст"
            if has_photo and has_text
            else "фото"
            if has_photo
            else "текст"
            if has_text
            else "без изменения"
        )
        text = (
            "✅ <b>Проверь замену</b> · 6/6\n\n"
            f"Исходное видео: ✅ · {data['duration']} сек\n"
            f"Фото лица: {len(data.get('gj_identity_urls') or [])}\n"
            f"Одежда: {clothing}\n"
            f"Число: {escape(content.get('number') or 'без изменения')}\n"
            f"Качество: {data['resolution']}\n"
            f"Стоимость: <b>{data['gj_quoted_cost']:g} ROX</b>\n\n"
            "Бот сам распределит роли фото. Остальные детали исходного видео сохраняем."
        )
        button("▶️ Запустить", "launch")
    button("⬅️ Назад", "back")
    button("❌ Отмена", "cancel")
    kb.adjust(1)
    if notice:
        text = escape(notice) + "\n\n" + text
    if edit:
        await safe_edit_message(target, text, reply_markup=kb.as_markup())
    else:
        await target.answer(text, reply_markup=kb.as_markup())


@router.callback_query(F.data == "gjreplace:start")
async def start(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    if not await _available(session):
        await safe_answer_callback(
            call, "Seedance 2.5 сейчас недоступен. Попробуй позже.", show_alert=True
        )
        return
    await state.clear()
    await state.set_data(
        {
            "flow_id": FLOW_ID,
            "flow_version": 1,
            "model_key": MODEL_KEY,
            "mode": "video",
            "gj_identity_urls": [],
            "gj_clothing_url": None,
            "seedance_content_edit": {"number": "", "clothing": ""},
            "resolution": "720p",
            "audio_ids": [],
        }
    )
    await state.set_state(GenjutsuReplaceFSM.source_video)
    await safe_answer_callback(call)
    await _render(call.message, state, edit=True)


@router.message(GenjutsuReplaceFSM.source_video, F.video | F.document)
async def source_video(message: Message, state: FSMContext, bot: Bot) -> None:
    media = message.video or message.document
    if message.document and not str(message.document.mime_type or "").startswith("video/"):
        await _render(message, state, notice="Нужен видеофайл. Пришли ролик MP4.")
        return
    try:
        url = await legacy.mirror_telegram_file(bot, media.file_id, is_video=True)
        if not url:
            raise ValueError("Видео не удалось сохранить. Пришли файл ещё раз.")
        duration = await legacy.seedance25_edit_billing_duration("", url, force_edit=True)
        if duration is None:
            raise ValueError("Не удалось проверить видео. Пришли ролик 4–30 секунд.")
    except ValueError as exc:
        await _render(message, state, notice=str(exc))
        return
    except Exception as exc:
        logger.warning("flow=%s upload=video error_type=%s", FLOW_ID, type(exc).__name__)
        await _render(
            message,
            state,
            notice="Видео не удалось сохранить или прочитать. Пришли другой файл MP4, 4–30 секунд; при необходимости сожми его.",
        )
        return
    await state.update_data(reference_video_url=url, duration=duration)
    await state.set_state(GenjutsuReplaceFSM.identity)
    await _render(message, state)


@router.message(GenjutsuReplaceFSM.identity, F.photo)
@router.message(GenjutsuReplaceFSM.clothing, F.photo)
async def photo(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    identity = await state.get_state() == GenjutsuReplaceFSM.identity.state
    identities = list(data.get("gj_identity_urls") or [])
    if identity and len(identities) >= 3:
        await _render(message, state, notice="Можно загрузить не больше 3 фото одного человека.")
        return
    try:
        content = dict(data.get("seedance_content_edit") or {})
        if not identity:
            content["clothing"] = message.caption or ""
            content = normalize_seedance_content_edit(content)
        url = await legacy.mirror_telegram_file(bot, message.photo[-1].file_id)
        if not url:
            raise ValueError("Не удалось сохранить фото. Пришли его ещё раз.")
        plan = build_seedance_reference_plan(
            identities + ([url] if identity else []),
            data.get("gj_clothing_url") if identity else url,
        )
    except ValueError as exc:
        await _render(message, state, notice=str(exc))
        return
    except Exception as exc:
        logger.warning("flow=%s upload=image error_type=%s", FLOW_ID, type(exc).__name__)
        await _render(message, state, notice="Фото не удалось сохранить. Пришли его ещё раз.")
        return
    await state.update_data(
        gj_identity_urls=list(plan.image_urls[: plan.identity_count]),
        gj_clothing_url=(plan.image_urls[-1] if plan.clothing_image_index else None),
        seedance_content_edit=content,
    )
    await _render(message, state)


@router.message(GenjutsuReplaceFSM.clothing, F.text)
@router.message(GenjutsuReplaceFSM.number, F.text)
async def text_input(message: Message, state: FSMContext) -> None:
    number = await state.get_state() == GenjutsuReplaceFSM.number.state
    content = dict((await state.get_data()).get("seedance_content_edit") or {})
    content["number" if number else "clothing"] = message.text or ""
    try:
        content = normalize_seedance_content_edit(content)
    except ValueError as exc:
        await _render(message, state, notice=str(exc))
        return
    await state.update_data(seedance_content_edit=content)
    if number:
        await state.set_state(GenjutsuReplaceFSM.resolution)
    await _render(message, state)


@router.callback_query(F.data.startswith("gjreplace:"))
async def navigate(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    data = await state.get_data()
    action, _, token = str(call.data).removeprefix("gjreplace:").rpartition(":")
    current = await state.get_state()
    if (
        not token
        or not secrets.compare_digest(token, str(data.get("gj_token") or ""))
        or current not in {s.state for s in STEPS}
    ):
        await safe_answer_callback(
            call, "Эта кнопка устарела. Используй последнее сообщение.", show_alert=True
        )
        return
    if action == "cancel" or (action == "back" and current == STEPS[0].state):
        await legacy.cb_genjutsu_menu(call, session, state)
        return
    if action == "launch":
        if current != GenjutsuReplaceFSM.confirm.state:
            await safe_answer_callback(call, "Сначала проверь настройки.", show_alert=True)
            return
        try:
            total = await _quote(state, session)
            if total != data.get("gj_quoted_cost"):
                await state.update_data(gj_quoted_cost=total)
                await safe_answer_callback(call)
                await _render(
                    call.message,
                    state,
                    edit=True,
                    notice="Стоимость изменилась. Проверь её перед запуском.",
                )
                return
            if db_user.credits < total:
                raise ValueError(
                    f"Недостаточно ROX: нужно {total:g}. Пополни баланс и повтори запуск."
                )
        except ValueError as exc:
            await safe_answer_callback(call, str(exc), show_alert=True)
            return
        await safe_answer_callback(call, "Запускаю замену")
        saved = await state.get_data()
        await state.set_state(GenjutsuReplaceFSM.launching)
        logger.info(
            "flow=%s model=%s identity_refs=%d clothing_ref=%s number_override=%s source_video=%s resolution=%s",
            FLOW_ID,
            MODEL_KEY,
            len(saved.get("gj_identity_urls") or []),
            bool(saved.get("gj_clothing_url")),
            bool(saved["seedance_content_edit"].get("number")),
            bool(saved.get("reference_video_url")),
            saved["resolution"],
        )
        ok = await legacy._launch_video_generation_from_state(
            source_message=call.message,
            state=state,
            session=session,
            db_user=db_user,
            bot=bot,
            prompt="Замена лица / одежды / цифр с сохранением исходной сцены",
            parent_generation_id=saved.get("parent_generation_id"),
        )
        if not ok:
            await state.set_data(saved)
            await state.set_state(GenjutsuReplaceFSM.confirm)
            await _render(
                call.message,
                state,
                notice="Настройки сохранены. Можно исправить их или повторить запуск.",
            )
        return
    index = next(i for i, step in enumerate(STEPS) if step.state == current)
    content = dict(data.get("seedance_content_edit") or {})
    if action == "back":
        await state.set_state(STEPS[index - 1])
    elif action in {"skip", "clear"} and index in {1, 2, 3}:
        if index == 1:
            await state.update_data(gj_identity_urls=[])
        elif index == 2:
            content["clothing"] = ""
            await state.update_data(gj_clothing_url=None, seedance_content_edit=content)
        else:
            content["number"] = ""
            await state.update_data(seedance_content_edit=content)
        if action == "skip":
            await state.set_state(STEPS[index + 1])
    elif action == "next" and index < 4:
        if index == 0 and not data.get("reference_video_url"):
            await safe_answer_callback(call, "Сначала загрузи видео.", show_alert=True)
            return
        await state.set_state(STEPS[index + 1])
    elif (
        action.startswith("res:")
        and current == GenjutsuReplaceFSM.resolution.state
        and action[4:] in RESOLUTIONS
    ):
        await state.update_data(resolution=action[4:])
        try:
            total = await _quote(state, session)
        except ValueError as exc:
            await safe_answer_callback(call, str(exc), show_alert=True)
            return
        await state.update_data(gj_quoted_cost=total)
        await state.set_state(GenjutsuReplaceFSM.confirm)
    else:
        await safe_answer_callback(call, "Используй кнопки текущего шага.", show_alert=True)
        return
    await safe_answer_callback(call)
    await _render(call.message, state, edit=True)


@router.message(StateFilter(GenjutsuReplaceFSM))
async def unsupported(message: Message, state: FSMContext) -> None:
    if await state.get_state() == GenjutsuReplaceFSM.launching.state:
        await message.answer("⏳ Задача запускается. Дождись подтверждения.")
    else:
        await _render(
            message,
            state,
            notice="Используй кнопки текущего шага или пришли материал, который я запросил.",
        )


async def restore_result(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, prev
) -> bool:
    """Restore exact original inputs for history/retry; never infer roles from images."""
    params = legacy._as_dict(getattr(prev, "input_params", None))
    if params.get("flow_id") != FLOW_ID or str(prev.model) != MODEL_KEY:
        return False
    try:
        plan = restore_seedance_reference_plan(
            legacy._url_list(params.get("image_url")), params.get("seedance_reference_roles")
        )
        await state.clear()
        await state.set_data(
            {
                **params,
                "gj_identity_urls": list(plan.image_urls[: plan.identity_count]),
                "gj_clothing_url": plan.image_urls[-1] if plan.clothing_image_index else None,
                "parent_generation_id": prev.id,
                "audio_ids": [],
                "ref_file_ids": [],
            }
        )
        await state.set_state(GenjutsuReplaceFSM.resolution)
        total = await _quote(state, session)
    except ValueError as exc:
        await safe_answer_callback(call, str(exc), show_alert=True)
        if await state.get_state() == GenjutsuReplaceFSM.resolution.state:
            await state.set_state(GenjutsuReplaceFSM.source_video)
            await _render(
                call.message,
                state,
                edit=True,
                notice="Пришли исходное видео заново. Остальные настройки сохранены.",
            )
        return True
    await state.update_data(gj_quoted_cost=total)
    await state.set_state(GenjutsuReplaceFSM.confirm)
    await safe_answer_callback(call)
    await _render(call.message, state, edit=True)
    return True
