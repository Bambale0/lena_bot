# bot/handlers/video_gen.py
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api import polling, video_service
from api.video_service import MotionDirection, VideoModel
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    VIDEO_CAPS,
    after_generation_kb,
    motion_control_kb,
    video_mode_kb,
    video_models_kb,
    video_params_kb,
)
from bot.states import VideoGenFSM
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="video_gen")

# Default params per model
_DEFAULT_DURATION: dict[str, int] = {
    VideoModel.KLING_30: 5,
    VideoModel.KLING_26_MOTION: 5,
    VideoModel.GROK_IMAGINE: 10,
    VideoModel.SEEDANCE_20: 5,
    VideoModel.HAPPYHORSE_T2V: 5,
    VideoModel.HAPPYHORSE_I2V: 5,
}
_DEFAULT_RATIO: dict[str, str] = {
    VideoModel.KLING_30: "16:9",
    VideoModel.KLING_26_MOTION: "16:9",
    VideoModel.GROK_IMAGINE: "16:9",
    VideoModel.SEEDANCE_20: "16:9",
    VideoModel.HAPPYHORSE_T2V: "16:9",
    VideoModel.VEO_31_PRO: "16:9",
}
_DEFAULT_RESOLUTION: dict[str, str] = {
    VideoModel.HAPPYHORSE_T2V: "720p",
    VideoModel.HAPPYHORSE_I2V: "720p",
}


def _params_summary(data: dict) -> str:
    parts = []
    if data.get("duration"):
        parts.append(f"{data['duration']} сек")
    if data.get("aspect_ratio"):
        parts.append(data["aspect_ratio"])
    if data.get("resolution"):
        parts.append(data["resolution"])
    return " · ".join(parts) if parts else "по умолчанию"


def _has_params(model_key: str) -> bool:
    caps = VIDEO_CAPS.get(model_key, {})
    return bool(
        caps.get("duration_options") or
        caps.get("aspect_ratios") or
        caps.get("resolutions")
    )


# ── Model select ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:video")
async def cb_video_menu(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.set_state(VideoGenFSM.model_select)
    model_costs = await repo.get_all_model_costs(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🎬 <b>Генерация видео</b>\n\nВыбери модель:",
        reply_markup=video_models_kb(model_costs),
    )
    await call.answer()


@router.callback_query(VideoGenFSM.model_select, F.data.startswith("vid_model:"))
async def cb_video_model(
    call: CallbackQuery, session: AsyncSession, state: FSMContext, db_user: User
) -> None:
    model_key = call.data.split(":")[1]  # type: ignore[union-attr]
    model_cost = await repo.get_model_cost(session, model_key)

    if not model_cost:
        await call.answer("Модель недоступна", show_alert=True)
        return

    if db_user.credits < model_cost.credits:
        await call.answer(
            f"Недостаточно кредитов! Нужно {model_cost.credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    await state.update_data(
        model_key=model_key,
        credits=model_cost.credits,
        duration=_DEFAULT_DURATION.get(model_key, 5),
        aspect_ratio=_DEFAULT_RATIO.get(model_key),
        resolution=_DEFAULT_RESOLUTION.get(model_key),
    )

    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])

    # If model supports only one mode — skip mode selection
    if len(modes) == 1:
        mode = modes[0]
        await state.update_data(mode=mode)
        if mode == "image":
            await state.set_state(VideoGenFSM.image_upload)
            await call.message.edit_text(  # type: ignore[union-attr]
                f"✅ <b>{model_cost.display_name}</b> · i2v\n\n"
                "🖼️ Загрузи первый кадр (отправь фото в чат):",
                reply_markup=back_to_menu_kb(),
            )
        else:
            await _go_to_params_or_prompt(call, state, model_key, model_cost.display_name)
    else:
        await state.set_state(VideoGenFSM.mode_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{model_cost.display_name}</b> ({model_cost.credits} кр)\n\n"
            "Выбери режим генерации:",
            reply_markup=video_mode_kb(model_key),
        )
    await call.answer()


async def _go_to_params_or_prompt(
    call: CallbackQuery, state: FSMContext, model_key: str, display_name: str
) -> None:
    data = await state.get_data()
    if _has_params(model_key):
        await state.set_state(VideoGenFSM.params_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"⚙️ <b>Параметры</b> · {display_name}\n\n"
            f"Нажимай кнопки для выбора (✅ = выбрано), затем — <b>Далее</b>:",
            reply_markup=video_params_kb(
                model_key,
                data.get("duration"),
                data.get("aspect_ratio"),
                data.get("resolution"),
            ),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\n"
            "✍️ Введи промпт для видео:\n\n"
            "<i>Пример: a dragon flying over mountains, cinematic, slow motion</i>",
            reply_markup=back_to_menu_kb(),
        )


# ── Mode select ───────────────────────────────────────────────────────────────

@router.callback_query(VideoGenFSM.mode_select, F.data.startswith("vid_mode:"))
async def cb_video_mode(
    call: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    mode = parts[1]
    model_key = parts[2]

    await state.update_data(mode=mode)

    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    caps = VIDEO_CAPS.get(model_key, {})

    if caps.get("has_motion") and mode == "text":
        await state.set_state(VideoGenFSM.motion_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🎭 <b>Motion Control</b>\n\nВыбери движение камеры:",
            reply_markup=motion_control_kb(),
        )
    elif mode == "image":
        await state.set_state(VideoGenFSM.image_upload)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🖼️ Загрузи первый кадр (отправь фото в чат):",
            reply_markup=back_to_menu_kb(),
        )
    else:
        await _go_to_params_or_prompt(call, state, model_key, display_name)
    await call.answer()


# ── Motion select ─────────────────────────────────────────────────────────────

@router.callback_query(VideoGenFSM.motion_select, F.data.startswith("motion:"))
async def cb_motion_select(
    call: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    direction = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(motion=direction)

    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    await _go_to_params_or_prompt(call, state, model_key, display_name)
    await call.answer()


# ── Image upload ──────────────────────────────────────────────────────────────

@router.message(VideoGenFSM.image_upload, F.photo)
async def handle_image_upload(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    best_photo = sorted(message.photo, key=lambda p: p.file_size, reverse=True)  # type: ignore[union-attr]
    file_id = best_photo[0].file_id
    await state.update_data(image_file_id=file_id)

    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    if _has_params(model_key):
        await state.set_state(VideoGenFSM.params_select)
        await message.answer(
            f"✅ Фото загружено!\n\n"
            f"⚙️ <b>Параметры</b> · {display_name}\n"
            "Нажимай кнопки для выбора (✅ = выбрано), затем — <b>Далее</b>:",
            reply_markup=video_params_kb(
                model_key,
                data.get("duration"),
                data.get("aspect_ratio"),
                data.get("resolution"),
            ),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await message.answer(
            "✅ Фото загружено!\n\n✍️ Введи промпт для видео:",
            reply_markup=back_to_menu_kb(),
        )


# ── Params select ─────────────────────────────────────────────────────────────

@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_dur:"))
async def cb_vpar_duration(call: CallbackQuery, state: FSMContext) -> None:
    dur = int(call.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(duration=dur)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=video_params_kb(
            data["model_key"], dur, data.get("aspect_ratio"), data.get("resolution")
        )
    )
    await call.answer(f"Длительность: {dur} сек")


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_ratio:"))
async def cb_vpar_ratio(call: CallbackQuery, state: FSMContext) -> None:
    ratio = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(aspect_ratio=ratio)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=video_params_kb(
            data["model_key"], data.get("duration"), ratio, data.get("resolution")
        )
    )
    await call.answer(f"Соотношение: {ratio}")


@router.callback_query(VideoGenFSM.params_select, F.data.startswith("vpar_res:"))
async def cb_vpar_resolution(call: CallbackQuery, state: FSMContext) -> None:
    res = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(resolution=res)
    data = await state.get_data()
    await call.message.edit_reply_markup(  # type: ignore[union-attr]
        reply_markup=video_params_kb(
            data["model_key"], data.get("duration"), data.get("aspect_ratio"), res
        )
    )
    await call.answer(f"Разрешение: {res}")


@router.callback_query(VideoGenFSM.params_select, F.data == "vpar_next")
async def cb_vpar_next(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    summary = _params_summary(data)

    await state.set_state(VideoGenFSM.prompt_input)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>{display_name}</b>\n"
        f"<code>{summary}</code>\n\n"
        "✍️ Введи промпт для видео:\n\n"
        "<i>Пример: a dragon flying over mountains, cinematic, slow motion</i>",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.callback_query(VideoGenFSM.params_select, F.data == "vpar_back")
async def cb_vpar_back(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    caps = VIDEO_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])

    if len(modes) > 1:
        await state.set_state(VideoGenFSM.mode_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\nВыбери режим генерации:",
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


# ── Prompt input ──────────────────────────────────────────────────────────────

@router.message(VideoGenFSM.prompt_input, F.text)
async def handle_video_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    model_key: str = data["model_key"]
    credits: int = data["credits"]
    mode: str = data.get("mode", "text")
    motion_str: str | None = data.get("motion")
    image_file_id: str | None = data.get("image_file_id")
    duration: int = data.get("duration", 5)
    aspect_ratio: str | None = data.get("aspect_ratio")
    resolution: str | None = data.get("resolution")
    prompt = message.text.strip()  # type: ignore[union-attr]

    # Get image URL from Telegram for i2v
    image_url: str | None = None
    if image_file_id:
        file = await bot.get_file(image_file_id)
        image_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно кредитов.", reply_markup=main_menu_kb())
        await state.clear()
        return

    gen = await repo.create_generation(
        session, db_user.id, model_key, GenerationType.video, prompt, credits
    )

    await state.set_state(VideoGenFSM.generating)
    summary = _params_summary(data)
    status_msg = await message.answer(
        f"⏳ <b>Генерирую видео...</b>\n"
        f"<code>{model_key}</code>\n"
        f"<i>{summary}</i>\n\n"
        "Это займёт 2–10 минут, я пришлю результат."
    )

    motion = MotionDirection(motion_str) if motion_str else None

    # Veo requires binary image bytes
    image_bytes: bytes | None = None
    if model_key == VideoModel.VEO_31_PRO and image_url and image_file_id:
        try:
            file_info = await bot.get_file(image_file_id)
            buf = await bot.download_file(file_info.file_path)
            image_bytes = buf.read() if hasattr(buf, "read") else bytes(buf)
        except Exception as dl_err:
            logger.warning("Veo: failed to download image bytes: %s", dl_err)

    try:
        result = await video_service.generate_video(
            VideoModel(model_key),
            prompt,
            image_url=image_url,
            image_bytes=image_bytes,
            motion=motion,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
        )
    except Exception as e:
        logger.error("Video generation error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text("❌ Ошибка запуска. Кредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, result.task_id)
    poll_fn = video_service.get_poll_fn(result.provider)

    async def on_success(url: str) -> None:
        await repo.finish_generation(session, gen.id, url)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await bot.send_video(
            chat_id=message.chat.id,
            video=url,
            caption=f"✅ <b>Видео готово!</b>\n\n<i>{prompt[:200]}</i>\n<code>{summary}</code>",
            reply_markup=after_generation_kb(gen.id, "video"),
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb()
        )

    asyncio.create_task(
        polling.poll_until_done(result.task_id, poll_fn, on_success, on_failure)
    )
    await state.clear()
