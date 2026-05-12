# bot/handlers/video_gen.py
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlencode

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api import polling, video_service
from api.public_files import mirror_telegram_file
from api.video_service import VideoModel
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    VIDEO_CAPS,
    VIDEO_GROUP_TITLES,
    after_generation_kb,
    video_mode_kb,
    video_model_groups_kb,
    video_models_kb,
    video_params_kb,
)
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from core.config import settings
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="video_gen")


def _kie_callback_url() -> str:
    params = {}
    if settings.KIE_WEBHOOK_SECRET:
        params["secret"] = settings.KIE_WEBHOOK_SECRET
    query = f"?{urlencode(params)}" if params else ""
    return f"{settings.WEBHOOK_URL.rstrip('/')}{settings.KIE_WEBHOOK_PATH}{query}"

_DEFAULT_DURATION: dict[str, int] = {
    VideoModel.KLING_26_T2V: 5,
    VideoModel.KLING_26_I2V: 5,
    VideoModel.KLING_30: 5,
    VideoModel.WAN_27_T2V: 5,
    VideoModel.WAN_27_I2V: 5,
    VideoModel.SEEDANCE_2: 5,
    VideoModel.SEEDANCE_2_FAST: 5,
    VideoModel.GROK_T2V: 6,
    VideoModel.HAPPYHORSE_T2V: 5,
    VideoModel.HAPPYHORSE_I2V: 5,
}
_DEFAULT_RATIO: dict[str, str] = {
    VideoModel.KLING_26_T2V: "16:9",
    VideoModel.KLING_30: "16:9",
    VideoModel.WAN_27_T2V: "16:9",
    VideoModel.SEEDANCE_2: "16:9",
    VideoModel.SEEDANCE_2_FAST: "16:9",
    VideoModel.GROK_T2V: "2:3",
    VideoModel.HAPPYHORSE_T2V: "16:9",
    VideoModel.VEO_3_FAST: "16:9",
    VideoModel.VEO_3: "16:9",
    VideoModel.VEO_3_LITE: "16:9",
}
_DEFAULT_RES: dict[str, str] = {
    VideoModel.WAN_27_T2V: "1080p",
    VideoModel.WAN_27_I2V: "1080p",
    VideoModel.SEEDANCE_2: "720p",
    VideoModel.SEEDANCE_2_FAST: "720p",
    VideoModel.GROK_T2V: "480p",
    VideoModel.GROK_I2V: "480p",
    VideoModel.HAPPYHORSE_T2V: "1080p",
    VideoModel.HAPPYHORSE_I2V: "1080p",
    VideoModel.KLING_30: "pro",
    VideoModel.KLING_26_MOTION: "720p",
    VideoModel.KLING_30_MOTION: "pro",
}
_MOTION_MODELS = {VideoModel.KLING_26_MOTION, VideoModel.KLING_30_MOTION}


def _is_per_second_video_model(model_key: str) -> bool:
    return VIDEO_CAPS.get(model_key, {}).get("billing_mode") == "per_second"


def _video_total_credits(model_key: str, duration: int, rate_or_flat: float) -> float:
    if _is_per_second_video_model(model_key):
        return rate_or_flat * duration
    return rate_or_flat


def _video_price_text(model_key: str, duration: int, rate_or_flat: float) -> str:
    total = _video_total_credits(model_key, duration, rate_or_flat)
    if _is_per_second_video_model(model_key):
        return f"{rate_or_flat:g} 💋/сек × {duration} сек = {total:g} 💋"
    return f"{total:g} 💋"


def _params_summary(data: dict) -> str:
    parts = [p for p in [
        data.get("aspect_ratio"),
        f"{data['duration']} сек" if data.get("duration") else None,
        data.get("resolution"),
        data.get("grok_mode"),
    ] if p]
    return " · ".join(parts) if parts else "по умолчанию"


def _video_params_hint(model_key: str, data: dict) -> str:
    parts = ["Нажимай кнопки ниже: ✅ показывает выбранные параметры."]
    if data.get("mode") == "image" and not _video_ref_count(data) and model_key == VideoModel.GROK_I2V:
        parts.append("Формат кадра появится после загрузки нужного количества референсов.")
    else:
        parts.append("Когда всё готово, нажми <b>Далее</b>.")
    return " ".join(parts)


def _video_ref_count(data: dict) -> int:
    if data.get("mode") != "image":
        return 0
    image_url = data.get("image_url")
    if isinstance(image_url, list):
        return len([item for item in image_url if item])
    if image_url or data.get("image_file_id"):
        return 1
    return 0


def _normalize_aspect_ratio_for_state(model_key: str, mode: str | None, aspect_ratio: str | None, ref_count: int) -> str | None:
    min_refs = int(VIDEO_CAPS.get(model_key, {}).get("aspect_ratio_min_refs", 0) or 0)
    if min_refs and mode == "image" and ref_count < min_refs:
        return None
    return aspect_ratio


def _has_params(model_key: str) -> bool:
    caps = VIDEO_CAPS.get(model_key, {})
    return bool(
        caps.get("duration_options") or
        caps.get("aspect_ratios") or
        (caps.get("has_resolution") and caps.get("resolutions")) or
        caps.get("mode_options")
    )


# ── Model select ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:video")
async def cb_video_menu(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.model_select)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        "🎬 <b>Генерация видео</b>\n\n"
        "Модели разложены по типу задачи, чтобы не искать нужную среди всего списка:\n\n"
        "• <b>⚡ Быстрый старт</b> — текст в видео и универсальные модели\n"
        "• <b>🖼️ Из изображения в видео</b> — если хочешь оживить фото\n"
        "• <b>🕺 Управление камерой</b> — если нужно движение камеры и ракурсы\n\n"
        "⏱ Генерация обычно занимает <b>1–5 минут</b> — бот пришлёт видео, когда оно будет готово.\n\n"
        "👇 <b>Сначала выбери категорию:</b>",
        reply_markup=video_model_groups_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.model_select, F.data.startswith("vid_group:"))
async def cb_video_group(call: CallbackQuery, session: AsyncSession) -> None:
    group_key = call.data.split(":")[1]  # type: ignore[union-attr]
    model_costs = await repo.get_all_model_costs(session)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"🎬 <b>{VIDEO_GROUP_TITLES.get(group_key, 'Модели')}</b>\n\n"
        "Выбери модель внутри этой категории:",
        reply_markup=video_models_kb(model_costs, group_key),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.model_select, F.data.startswith("vid_model:"))
async def cb_video_model(
    call: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    model_key = call.data.split(":")[1]  # type: ignore[union-attr]
    default_duration = _DEFAULT_DURATION.get(model_key, 5)
    default_resolution = _DEFAULT_RES.get(model_key)
    model_cost = await repo.resolve_video_model_cost(
        session,
        model_key,
        duration=default_duration,
        resolution=default_resolution,
    )
    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return
    min_credits = _video_total_credits(model_key, default_duration, model_cost.credits)
    if db_user.credits < min_credits:
        await call.answer(
            f"Недостаточно 💋! Нужно минимум {_video_price_text(model_key, default_duration, model_cost.credits)}, у тебя {db_user.credits:g} 💋.",
            show_alert=True,
        )
        return

    await state.update_data(
        model_key=model_key,
        credits=model_cost.credits,
        duration=default_duration,
        aspect_ratio=_DEFAULT_RATIO.get(model_key),
        resolution=default_resolution,
        grok_mode="normal" if VIDEO_CAPS.get(model_key, {}).get("mode_options") else None,
    )

    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])

    if len(modes) == 1:
        await state.update_data(mode=modes[0])
        await _handle_mode(call, state, session, model_key, model_cost.display_name, modes[0])
    else:
        await state.set_state(VideoGenFSM.mode_select)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{model_cost.display_name}</b> ({_video_price_text(model_key, default_duration, model_cost.credits)})\n\nВыбери режим:",
            reply_markup=video_mode_kb(model_key),
        )
    await safe_answer_callback(call)


async def _handle_mode(
    call: CallbackQuery, state: FSMContext,
    session: AsyncSession, model_key: str, display_name: str, mode: str,
) -> None:
    if mode == "image":
        await state.set_state(VideoGenFSM.image_upload)
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · анимация по фото\n\n🖼️ Загрузи первый кадр:",
            reply_markup=back_to_menu_kb(),
        )
    elif mode == "motion":
        await state.set_state(VideoGenFSM.image_upload)
        await state.update_data(motion_step="person")
        await safe_edit_message(
            call.message,  # type: ignore[arg-type]
            f"✅ <b>{display_name}</b> · управление камерой\n\n"
            "👤 <b>Шаг 1/2:</b> Загрузи фото персонажа\n"
            "<i>(голова, плечи, торс; JPEG/PNG; ≤10 МБ)</i>",
            reply_markup=back_to_menu_kb(),
        )
    else:
        await _go_to_params_or_prompt(call, state, model_key, display_name)


# ── Mode select ───────────────────────────────────────────────────────────────

@router.callback_query(VideoGenFSM.mode_select, F.data.startswith("vid_mode:"))
async def cb_video_mode(
    call: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    mode, model_key = parts[1], parts[2]
    await state.update_data(mode=mode)
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await _handle_mode(call, state, session, model_key, display_name, mode)
    await safe_answer_callback(call)


# ── Image / person upload ─────────────────────────────────────────────────────

@router.message(VideoGenFSM.image_upload, F.video)
async def handle_video_upload(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    """Motion Control step 2: user uploads reference video."""
    data = await state.get_data()
    motion_step: str | None = data.get("motion_step")

    if motion_step != "video_url":
        await message.answer("Пожалуйста, загрузи видео только на шаге 2 управления камерой.", reply_markup=back_to_menu_kb())
        return

    video = message.video  # type: ignore[union-attr]
    video_duration: int = video.duration or 5
    file_id = video.file_id
    model_key: str = data["model_key"]
    resolution: str | None = data.get("resolution")

    # Motion Control currently uses Kling, but keep the pricing logic generic.
    model_cost = await repo.resolve_video_model_cost(session, model_key, resolution=resolution)
    rate_or_flat = model_cost.credits if model_cost else int(data.get("credits", 8))
    total_credits = _video_total_credits(model_key, video_duration, rate_or_flat)

    if db_user.credits < total_credits:
        await message.answer(
            f"❌ Недостаточно 💋!\n"
            f"Видео: {_video_price_text(model_key, video_duration, rate_or_flat)}\n"
            f"Баланс: {db_user.credits:g} 💋.",
            reply_markup=back_to_menu_kb(),
        )
        return

    # Mirror video to public storage for KIE API
    video_url = await mirror_telegram_file(bot, file_id, is_video=True)

    await state.update_data(
        reference_video_url=video_url,
        motion_duration=video_duration,
        motion_credits=total_credits,
        credits=rate_or_flat,
        motion_step="prompt",
    )
    await state.set_state(VideoGenFSM.prompt_input)

    model_cost_obj = await repo.get_model_cost(session, model_key)
    display_name = model_cost_obj.display_name if model_cost_obj else model_key
    await message.answer(
        f"✅ Видео загружено! (<b>{_video_price_text(model_key, video_duration, rate_or_flat)}</b>)\n\n"
        f"✅ <b>{display_name}</b>\n\n"
        "✍️ Введи промпт (или отправь <code>-</code> для пропуска):",
        reply_markup=back_to_menu_kb(),
    )


@router.message(VideoGenFSM.image_upload, F.photo)
async def handle_image_upload(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size, reverse=True)  # type: ignore[union-attr]
    file_id = best[0].file_id

    data = await state.get_data()
    model_key: str = data["model_key"]
    motion_step: str | None = data.get("motion_step")

    if motion_step == "person":
        await state.update_data(image_file_id=file_id, motion_step="video_url")
        await message.answer(
            "✅ Фото загружено!\n\n"
            "🎬 <b>Шаг 2/2:</b> Загрузи референсное видео\n"
            "<i>(видеофайл MP4, макс. 30 сек — бот автоматически определит длину)</i>",
            reply_markup=back_to_menu_kb(),
        )
        await state.set_state(VideoGenFSM.image_upload)
        return

    await state.update_data(image_file_id=file_id)
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    if _has_params(model_key):
        updated = await state.get_data()
        await state.set_state(VideoGenFSM.params_select)
        await message.answer(
            f"✅ Фото загружено!\n\n⚙️ <b>Параметры</b> · {display_name}\n"
            f"{_video_params_hint(model_key, updated)}",
            reply_markup=video_params_kb(
                model_key, updated.get("duration"),
                updated.get("aspect_ratio"), updated.get("resolution"), updated.get("grok_mode"),
                selected_mode=updated.get("mode"),
                ref_count=_video_ref_count(updated),
            ),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await message.answer("✅ Фото загружено!\n\n✍️ Введи промпт:", reply_markup=back_to_menu_kb())


# ── Params select ─────────────────────────────────────────────────────────────

async def _go_to_params_or_prompt(
    call: CallbackQuery, state: FSMContext, model_key: str, display_name: str,
) -> None:
    data = await state.get_data()
    if _has_params(model_key):
        await state.set_state(VideoGenFSM.params_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"⚙️ <b>Параметры</b> · {display_name}\n"
            f"{_video_params_hint(model_key, data)}",
            reply_markup=video_params_kb(
                model_key, data.get("duration"),
                data.get("aspect_ratio"), data.get("resolution"), data.get("grok_mode"),
                selected_mode=data.get("mode"),
                ref_count=_video_ref_count(data),
            ),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\n✍️ Введи промпт:",
            reply_markup=back_to_menu_kb(),
        )


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_dur:"))
async def cb_vpar_dur(call: CallbackQuery, state: FSMContext) -> None:
    dur = int(call.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(duration=dur)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=video_params_kb(
            data["model_key"], dur, data.get("aspect_ratio"), data.get("resolution"), data.get("grok_mode"),
            selected_mode=data.get("mode"),
            ref_count=_video_ref_count(data),
        )
    )
    await call.answer(f"{dur} сек")


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_ratio:"))
async def cb_vpar_ratio(call: CallbackQuery, state: FSMContext) -> None:
    ratio = call.data.removeprefix("vpar_ratio:")  # type: ignore[union-attr]
    await state.update_data(aspect_ratio=ratio)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=video_params_kb(
            data["model_key"], data.get("duration"), ratio, data.get("resolution"), data.get("grok_mode"),
            selected_mode=data.get("mode"),
            ref_count=_video_ref_count(data),
        )
    )
    await call.answer(ratio)


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_res:"))
async def cb_vpar_res(call: CallbackQuery, state: FSMContext) -> None:
    res = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(resolution=res)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=video_params_kb(
            data["model_key"], data.get("duration"), data.get("aspect_ratio"), res, data.get("grok_mode"),
            selected_mode=data.get("mode"),
            ref_count=_video_ref_count(data),
        )
    )
    await call.answer(res)


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_mode:"))
async def cb_vpar_mode(call: CallbackQuery, state: FSMContext) -> None:
    mode = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(grok_mode=mode)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=video_params_kb(
            data["model_key"],
            data.get("duration"),
            data.get("aspect_ratio"),
            data.get("resolution"),
            mode,
            selected_mode=data.get("mode"),
            ref_count=_video_ref_count(data),
        )
    )
    await call.answer(mode)


@router.callback_query(VideoGenFSM.params_select, F.data == "vpar_next")
async def cb_vpar_next(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_cost = await repo.resolve_video_model_cost(
        session,
        data["model_key"],
        duration=data.get("duration"),
        resolution=data.get("resolution"),
    )
    display_name = model_cost.display_name if model_cost else data["model_key"]
    if model_cost:
        await state.update_data(credits=model_cost.credits)
    summary = _params_summary(data)
    duration_val = data.get("duration", 5)
    rate_or_flat = float(model_cost.credits if model_cost else data.get("credits", 0))
    await state.update_data(credits=rate_or_flat)
    await state.set_state(VideoGenFSM.prompt_input)
    await safe_edit_message(
        call.message,  # type: ignore[arg-type]
        f"✅ <b>{display_name}</b> ({_video_price_text(data['model_key'], duration_val, rate_or_flat)})"
        f" · <code>{summary}</code>\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.callback_query(VideoGenFSM.params_select, F.data == "vpar_back")
async def cb_vpar_back(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    if len(modes) > 1:
        await state.set_state(VideoGenFSM.mode_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\nВыбери режим:",
            reply_markup=video_mode_kb(model_key),
        )
    else:
        model_costs = await repo.get_all_model_costs(session)
        await state.set_state(VideoGenFSM.model_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🎬 <b>Генерация видео</b>\n\nВыбери модель:",
            reply_markup=video_models_kb(model_costs),
        )
    await call.answer()




# ── Prompt / motion video URL ─────────────────────────────────────────────────

@router.message(VideoGenFSM.prompt_input, F.text)
async def handle_video_prompt(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    data = await state.get_data()
    model_key: str = data["model_key"]
    motion_step: str | None = data.get("motion_step")
    image_file_id: str | None = data.get("image_file_id")
    duration: int = data.get("duration", 5)
    stored_aspect_ratio: str | None = data.get("aspect_ratio")
    aspect_ratio = _normalize_aspect_ratio_for_state(model_key, data.get("mode"), stored_aspect_ratio, _video_ref_count(data))
    if aspect_ratio != stored_aspect_ratio:
        await state.update_data(aspect_ratio=aspect_ratio)
    resolution: str | None = data.get("resolution")
    grok_mode: str = data.get("grok_mode", "normal")
    prompt = message.text.strip()  # type: ignore[union-attr]

    # Motion Control: step 2 — user sent reference video URL
    if motion_step == "video_url":
        await state.update_data(reference_video_url=prompt, motion_step="done")
        await state.set_state(VideoGenFSM.params_select if _has_params(model_key) else VideoGenFSM.generating)
        model_cost = await repo.get_model_cost(session, model_key)
        display_name = model_cost.display_name if model_cost else model_key
        if _has_params(model_key):
            updated = await state.get_data()
            await state.set_state(VideoGenFSM.params_select)
            await message.answer(
                f"✅ Ссылка сохранена!\n\n⚙️ <b>Параметры</b> · {display_name}\n"
                f"{_video_params_hint(model_key, updated)}",
                reply_markup=video_params_kb(
                    model_key, updated.get("duration"),
                    updated.get("aspect_ratio"), updated.get("resolution"), updated.get("grok_mode"),
                    selected_mode=updated.get("mode"),
                    ref_count=_video_ref_count(updated),
                ),
            )
        else:
            await state.set_state(VideoGenFSM.prompt_input)
            await state.update_data(motion_step="prompt")
            await message.answer(
                "✅ Ссылка сохранена!\n\n✍️ Введи промпт (или отправь прочерк \"-\" для пропуска):",
                reply_markup=back_to_menu_kb(),
            )
        return

    # Motion Control: optional prompt step
    if motion_step == "prompt":
        prompt = prompt if prompt != "-" else ""
        await state.update_data(motion_prompt=prompt, motion_step="done")

    image_url = (
        await mirror_telegram_file(bot, image_file_id)
        if image_file_id
        else data.get("image_url")
    )

    model_cost = await repo.resolve_video_model_cost(
        session,
        model_key,
        duration=duration,
        resolution=resolution,
    )
    motion_credits = data.get("motion_credits")  # pre-calculated for motion control
    if motion_credits is not None:
        credits = int(motion_credits)
    else:
        rate_or_flat = model_cost.credits if model_cost else int(data.get("credits", 0))
        credits = int(_video_total_credits(model_key, duration, rate_or_flat))

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно 💋.", reply_markup=main_menu_kb())
        await state.clear()
        return

    gen = await repo.create_generation(
        session, db_user.id, model_key, GenerationType.video, prompt, credits
    )

    await state.set_state(VideoGenFSM.generating)
    summary = _params_summary(data)
    status_msg = await message.answer(
        f"⏳ <b>Генерирую видео...</b>\n"
        f"<b>{model_cost.display_name if model_cost else model_key}</b>"
        + (f" · <i>{summary}</i>" if summary != "по умолчанию" else "") +
        "\n\nЭто займёт 2–10 минут."
    )

    try:
        result = await video_service.generate_video(
            VideoModel(model_key),
            prompt,
            image_url=image_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            reference_video_url=data.get("reference_video_url"),
            grok_mode=grok_mode,
            callback_url=_kie_callback_url(),
        )
    except Exception as e:
        logger.error("Video generation error: %s", e)
        if await repo.fail_generation(session, gen.id, str(e)):
            await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text("❌ Ошибка запуска генерации. 💋 возвращены.\n\nПопробуй другую модель или повтори через минуту.", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, result.task_id)
    if result.provider == "kieai":
        await status_msg.edit_text(
            "⏳ <b>Видео-задача запущена.</b>\n"
            "Пришлю результат автоматически, как только видео будет готово."
        )
        await state.clear()
        return

    poll_fn = video_service.get_poll_fn(result.provider)

    async def on_success(url: str) -> None:
        await repo.finish_generation(session, gen.id, url)
        try:
            await status_msg.delete()
        except Exception:
            pass
        caption = f"✅ <b>Видео готово!</b>\n\n<i>{prompt[:200]}</i>"
        if summary != "по умолчанию":
            caption += f"\n<code>{summary}</code>"
        await bot.send_video(
            chat_id=message.chat.id, video=url,
            caption=caption, reply_markup=after_generation_kb(gen.id, "video"),
        )

    async def on_failure(err: str) -> None:
        if await repo.fail_generation(session, gen.id, err):
            await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            f"❌ Ошибка: {err}\nвозвращены.", reply_markup=main_menu_kb()
        )

    asyncio.create_task(polling.poll_until_done(result.task_id, poll_fn, on_success, on_failure))
    await state.clear()
