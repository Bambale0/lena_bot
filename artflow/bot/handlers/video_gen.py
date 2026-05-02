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
    after_generation_kb,
    motion_control_kb,
    video_mode_kb,
    video_models_kb,
)
from bot.states import VideoGenFSM
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="video_gen")


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

    await state.update_data(model_key=model_key, credits=model_cost.credits)
    await state.set_state(VideoGenFSM.mode_select)

    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ Модель: <b>{model_cost.display_name}</b> ({model_cost.credits} кр)\n\n"
        "Выбери режим генерации:",
        reply_markup=video_mode_kb(model_key),
    )
    await call.answer()


@router.callback_query(VideoGenFSM.mode_select, F.data.startswith("vid_mode:"))
async def cb_video_mode(
    call: CallbackQuery, state: FSMContext
) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    mode = parts[1]  # "text" | "image"
    model_key = parts[2]

    await state.update_data(mode=mode)

    if model_key == VideoModel.KLING_26_MOTION and mode == "text":
        # Предлагаем выбор motion
        await state.set_state(VideoGenFSM.motion_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🎭 <b>Motion Control</b>\n\nВыбери движение камеры:",
            reply_markup=motion_control_kb(),
        )
    elif mode == "image":
        await state.set_state(VideoGenFSM.image_upload)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🖼️ Загрузи изображение (отправь фото в чат):",
            reply_markup=back_to_menu_kb(),
        )
    else:
        await state.set_state(VideoGenFSM.prompt_input)
        await call.message.edit_text(  # type: ignore[union-attr]
            "✍️ Введи промпт для видео:\n\n"
            "<i>Пример: a dragon flying over mountains, cinematic, slow motion</i>",
            reply_markup=back_to_menu_kb(),
        )
    await call.answer()


@router.callback_query(VideoGenFSM.motion_select, F.data.startswith("motion:"))
async def cb_motion_select(
    call: CallbackQuery, state: FSMContext
) -> None:
    direction = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(motion=direction)
    await state.set_state(VideoGenFSM.prompt_input)
    await call.message.edit_text(  # type: ignore[union-attr]
        "✍️ Введи промпт для видео:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(VideoGenFSM.image_upload, F.photo)
async def handle_image_upload(
    message: Message, state: FSMContext
) -> None:
    best_photo: list = sorted(message.photo, key=lambda p: p.file_size, reverse=True)
    file_id = best_photo[0].file_id
    await state.update_data(image_file_id=file_id)
    await state.set_state(VideoGenFSM.prompt_input)
    await message.answer(
        "✅ Изображение получено!\n\nТеперь введи промпт:",
        reply_markup=back_to_menu_kb(),
    )


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
    prompt = message.text.strip()  # type: ignore[union-attr]

    # Получаем публичный URL изображения если загрузили
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
    status_msg = await message.answer(
        "⏳ Генерирую видео...\n"
        f"<code>{model_key}</code> · это займёт до 5 минут"
    )

    motion = MotionDirection(motion_str) if motion_str else None

    try:
        result = await video_service.generate_video(
            VideoModel(model_key), prompt, image_url=image_url, motion=motion
        )
    except Exception as e:
        logger.error("Video generation error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text("❌ Ошибка запуска. Кредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, result.task_id)

    poll_fn = (
        video_service.poll_kling_status
        if result.provider == "kling"
        else video_service.poll_grok_status
    )

    async def on_success(url: str) -> None:
        await repo.finish_generation(session, gen.id, url)
        try:
            await status_msg.delete()
        except Exception:
            pass
        await bot.send_video(
            chat_id=message.chat.id,
            video=url,
            caption=f"✅ Видео готово!\n\n<i>{prompt[:200]}</i>",
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
