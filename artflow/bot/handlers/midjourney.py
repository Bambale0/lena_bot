# bot/handlers/midjourney.py
"""
Midjourney handler — полный flow:
  Imagine → Poll → Buttons (U/V/🔄) → Action → Poll [→ Modal → Poll]
  Blend → Poll
  Describe → Poll
  Video → Poll
"""
from __future__ import annotations

import asyncio
import base64
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize
from sqlalchemy.ext.asyncio import AsyncSession

from api import midjourney_service as mj
from api import polling
from api.midjourney_service import (
    MJBotType,
    MJButton,
    MJDimensions,
    MJSpeed,
    MJTaskResult,
    MJTaskStatus,
    MJVideoMotion,
)
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.midjourney import (
    mj_action_buttons_kb,
    mj_blend_submit_kb,
    mj_bot_type_kb,
    mj_dimensions_kb,
    mj_skip_prompt_kb,
    mj_speed_kb,
    mj_submenu_kb,
    mj_video_speed_kb,
)
from bot.states import MidjourneyFSM
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="midjourney")

_MJ_IMAGINE_MODEL = "midjourney-imagine"
_MJ_BLEND_MODEL = "midjourney-blend"
_MJ_DESCRIBE_MODEL = "midjourney-describe"
_MJ_VIDEO_MODEL = "midjourney-video"
_MJ_ACTION_MODEL = "midjourney-action"


# ═══════════════════════════════════════════════════════════════════
# SUBMENU
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "menu:mj")
async def cb_mj_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(  # type: ignore[union-attr]
        "🖌️ <b>Midjourney</b>\n\nВыбери действие:",
        reply_markup=mj_submenu_kb(),
    )
    await call.answer()


# ═══════════════════════════════════════════════════════════════════
# IMAGINE FLOW
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "mj:imagine")
async def cb_imagine_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(MidjourneyFSM.bot_type_select)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🤖 Выбери модель бота:",
        reply_markup=mj_bot_type_kb(),
    )
    await call.answer()


@router.callback_query(MidjourneyFSM.bot_type_select, F.data.startswith("mj_bt:"))
async def cb_bot_type(call: CallbackQuery, state: FSMContext) -> None:
    bot_type_val = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(bot_type=bot_type_val)
    await state.set_state(MidjourneyFSM.speed_select)
    await call.message.edit_text(  # type: ignore[union-attr]
        "⚡ Выбери скорость генерации:",
        reply_markup=mj_speed_kb(),
    )
    await call.answer()


@router.callback_query(MidjourneyFSM.speed_select, F.data.startswith("mj_sp:"))
async def cb_speed(call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    speed_val = call.data.split(":")[1]  # type: ignore[union-attr]

    model_cost = await repo.get_model_cost(session, _MJ_IMAGINE_MODEL)
    credits = model_cost.credits if model_cost else 10

    if db_user.credits < credits:
        await call.answer(
            f"Недостаточно кредитов! Нужно {credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    await state.update_data(speed=speed_val, credits=credits)
    await state.set_state(MidjourneyFSM.prompt_input)

    await call.message.edit_text(  # type: ignore[union-attr]
        f"✏️ Введи промпт для Midjourney:\n\n"
        f"<i>Пример: a cute cat in neon city, cyberpunk, 8k --ar 16:9 --v 6.1</i>\n\n"
        f"Стоимость: <b>{credits} кр.</b>",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(MidjourneyFSM.prompt_input, F.text)
async def handle_imagine_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    prompt = message.text.strip()  # type: ignore[union-attr]
    bot_type = MJBotType(data.get("bot_type", MJBotType.MIDJOURNEY))
    speed = MJSpeed(data.get("speed", MJSpeed.FAST))
    credits: int = data.get("credits", 10)

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно кредитов.", reply_markup=main_menu_kb())
        await state.clear()
        return

    gen = await repo.create_generation(
        session, db_user.id, _MJ_IMAGINE_MODEL, GenerationType.image, prompt, credits
    )
    await state.set_state(MidjourneyFSM.generating)
    status_msg = await message.answer(
        f"⏳ Отправляю запрос в Midjourney...\n"
        f"Модель: <b>{bot_type.label()}</b> · <b>{speed.label()}</b>"
    )

    try:
        task_id = await mj.imagine(prompt, bot_type=bot_type, speed=speed)
    except Exception as e:
        logger.error("MJ imagine submit error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text("❌ Ошибка при отправке запроса. Кредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, task_id)

    async def on_success(url: str) -> None:
        try:
            task_result = await mj.fetch_task(task_id)
        except Exception:
            task_result = MJTaskResult(task_id=task_id, status=MJTaskStatus.SUCCESS, image_url=url)

        await repo.finish_generation(session, gen.id, task_result.image_url or url)
        await state.update_data(
            task_id=task_id,
            buttons=[{"custom_id": b.custom_id, "label": b.label, "emoji": b.emoji} for b in task_result.buttons],
        )
        await state.set_state(MidjourneyFSM.viewing_result)

        try:
            await status_msg.delete()
        except Exception:
            pass

        caption = f"✅ Готово!\n\n<i>{prompt[:200]}</i>"
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=task_result.image_url or url,
            caption=caption,
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )

    async def on_failure(err: str) -> None:
        if err == "__MODAL__":
            await state.set_state(MidjourneyFSM.waiting_modal_input)
            await status_msg.edit_text(
                "🖌 Midjourney запрашивает дополнительный ввод.\n"
                "Введи уточняющий промпт (или нажми 'Без промпта'):",
                reply_markup=mj_skip_prompt_kb(),
            )
            await state.update_data(modal_task_id=task_id)
            return

        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb()
        )
        await state.clear()

    asyncio.create_task(
        polling.poll_until_done(task_id, mj.poll_mj_image, on_success, on_failure)
    )
    await state.clear()


# ═══════════════════════════════════════════════════════════════════
# ACTION BUTTONS (U1/V1/🔄/zoom/pan …)
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(MidjourneyFSM.viewing_result, F.data.startswith("mj_btn:"))
async def cb_mj_action(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    idx = int(call.data.split(":")[1])  # type: ignore[union-attr]
    data = await state.get_data()
    task_id: str = data["task_id"]
    raw_buttons: list[dict] = data.get("buttons", [])

    if idx >= len(raw_buttons):
        await call.answer("Кнопка недоступна", show_alert=True)
        return

    btn_data = raw_buttons[idx]
    custom_id = btn_data["custom_id"]

    model_cost = await repo.get_model_cost(session, _MJ_ACTION_MODEL)
    credits = model_cost.credits if model_cost else 3

    if db_user.credits < credits:
        await call.answer(
            f"Недостаточно кредитов ({credits} кр.)", show_alert=True
        )
        return

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await call.answer("Недостаточно кредитов", show_alert=True)
        return

    label = (btn_data.get("emoji", "") + btn_data.get("label", "")).strip()
    await call.answer(f"⏳ Выполняю: {label}")
    await state.set_state(MidjourneyFSM.action_polling)

    try:
        new_task_id = await mj.action(task_id, custom_id)
    except Exception as e:
        await repo.add_credits(session, db_user.id, credits)
        await call.message.answer(  # type: ignore[union-attr]
            f"❌ Ошибка: {e}", reply_markup=main_menu_kb()
        )
        await state.clear()
        return

    status_msg = await call.message.answer(  # type: ignore[union-attr]
        f"⏳ Обрабатываю <b>{label}</b>..."
    )

    async def on_success(url: str) -> None:
        try:
            task_result = await mj.fetch_task(new_task_id)
        except Exception:
            task_result = MJTaskResult(task_id=new_task_id, status=MJTaskStatus.SUCCESS, image_url=url)

        await state.update_data(
            task_id=new_task_id,
            buttons=[{"custom_id": b.custom_id, "label": b.label, "emoji": b.emoji} for b in task_result.buttons],
        )
        await state.set_state(MidjourneyFSM.viewing_result)

        try:
            await status_msg.delete()
        except Exception:
            pass

        media_url = task_result.image_url or url
        caption = f"✅ <b>{label}</b> готово!"
        await bot.send_photo(
            chat_id=call.message.chat.id,  # type: ignore[union-attr]
            photo=media_url,
            caption=caption,
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )

    async def on_failure(err: str) -> None:
        if err == "__MODAL__":
            await state.update_data(modal_task_id=new_task_id)
            await state.set_state(MidjourneyFSM.waiting_modal_input)
            await status_msg.edit_text(
                "🖌 Midjourney требует дополнительный ввод.\n"
                "Введи уточняющий промпт или нажми 'Без промпта':",
                reply_markup=mj_skip_prompt_kb(),
            )
            return

        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb()
        )
        await state.clear()

    asyncio.create_task(
        polling.poll_until_done(new_task_id, mj.poll_mj_image, on_success, on_failure)
    )


# ═══════════════════════════════════════════════════════════════════
# MODAL INPUT (Custom Zoom / Vary Region)
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(MidjourneyFSM.waiting_modal_input, F.data == "mj_skip_prompt")
async def cb_modal_skip(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await call.answer()
    await _submit_modal(call.message, state, bot, prompt="")  # type: ignore[arg-type]


@router.message(MidjourneyFSM.waiting_modal_input, F.text)
async def handle_modal_prompt(message: Message, state: FSMContext, bot: Bot) -> None:
    await _submit_modal(message, state, bot, prompt=message.text.strip())  # type: ignore[arg-type]


async def _submit_modal(
    message: Message,
    state: FSMContext,
    bot: Bot,
    prompt: str,
) -> None:
    data = await state.get_data()
    modal_task_id: str = data.get("modal_task_id", "")

    status_msg = await message.answer("⏳ Отправляю данные в Midjourney...")

    try:
        new_task_id = await mj.modal(modal_task_id, prompt=prompt)
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка modal: {e}", reply_markup=main_menu_kb())
        await state.clear()
        return

    async def on_success(url: str) -> None:
        try:
            task_result = await mj.fetch_task(new_task_id)
        except Exception:
            task_result = MJTaskResult(task_id=new_task_id, status=MJTaskStatus.SUCCESS, image_url=url)

        await state.update_data(
            task_id=new_task_id,
            buttons=[{"custom_id": b.custom_id, "label": b.label, "emoji": b.emoji} for b in task_result.buttons],
        )
        await state.set_state(MidjourneyFSM.viewing_result)

        try:
            await status_msg.delete()
        except Exception:
            pass

        await bot.send_photo(
            chat_id=message.chat.id,
            photo=task_result.image_url or url,
            caption="✅ Modal готово!",
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )

    async def on_failure(err: str) -> None:
        await status_msg.edit_text(f"❌ Ошибка: {err}", reply_markup=main_menu_kb())
        await state.clear()

    asyncio.create_task(
        polling.poll_until_done(new_task_id, mj.poll_mj_image, on_success, on_failure)
    )


# ═══════════════════════════════════════════════════════════════════
# BLEND FLOW
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "mj:blend")
async def cb_blend_start(call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    model_cost = await repo.get_model_cost(session, _MJ_BLEND_MODEL)
    credits = model_cost.credits if model_cost else 12

    if db_user.credits < credits:
        await call.answer(f"Недостаточно кредитов ({credits} кр.)", show_alert=True)
        return

    await state.update_data(blend_images=[], blend_credits=credits)
    await state.set_state(MidjourneyFSM.blend_collecting)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"🖼️ <b>Blend</b>\n\n"
        f"Отправь 2–5 изображений по одному.\n"
        f"После отправки минимум 2-х появится кнопка «Блендить».\n\n"
        f"Стоимость: <b>{credits} кр.</b>",
        reply_markup=mj_blend_submit_kb(0),
    )
    await call.answer()


@router.message(MidjourneyFSM.blend_collecting, F.photo)
async def handle_blend_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    images: list[str] = data.get("blend_images", [])

    if len(images) >= 5:
        await message.answer("Максимум 5 изображений. Нажми «Блендить».")
        return

    photo: PhotoSize = message.photo[-1]  # type: ignore[index]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)  # type: ignore[arg-type]
    b64 = "data:image/jpeg;base64," + base64.b64encode(file_bytes.read()).decode()  # type: ignore[union-attr]
    images.append(b64)
    await state.update_data(blend_images=images)

    count = len(images)
    await message.answer(
        f"✅ Фото {count}/5 добавлено.",
        reply_markup=mj_blend_submit_kb(count),
    )


@router.callback_query(MidjourneyFSM.blend_collecting, F.data == "mj_blend:submit")
async def cb_blend_submit(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    images: list[str] = data.get("blend_images", [])
    credits: int = data.get("blend_credits", 12)

    if len(images) < 2:
        await call.answer("Нужно минимум 2 изображения", show_alert=True)
        return

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await call.answer("Недостаточно кредитов", show_alert=True)
        return

    await state.set_state(MidjourneyFSM.blend_generating)
    status_msg = await call.message.answer(  # type: ignore[union-attr]
        f"⏳ Блендю {len(images)} изображений..."
    )
    await call.answer()

    gen = await repo.create_generation(
        session, db_user.id, _MJ_BLEND_MODEL, GenerationType.image, f"blend:{len(images)}", credits
    )

    try:
        task_id = await mj.blend(images)
    except Exception as e:
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, task_id)

    async def on_success(url: str) -> None:
        try:
            task_result = await mj.fetch_task(task_id)
        except Exception:
            task_result = MJTaskResult(task_id=task_id, status=MJTaskStatus.SUCCESS, image_url=url)

        await repo.finish_generation(session, gen.id, task_result.image_url or url)
        await state.update_data(
            task_id=task_id,
            buttons=[{"custom_id": b.custom_id, "label": b.label, "emoji": b.emoji} for b in task_result.buttons],
        )
        await state.set_state(MidjourneyFSM.viewing_result)

        try:
            await status_msg.delete()
        except Exception:
            pass

        await bot.send_photo(
            chat_id=call.message.chat.id,  # type: ignore[union-attr]
            photo=task_result.image_url or url,
            caption="✅ Blend готово!",
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()

    asyncio.create_task(
        polling.poll_until_done(task_id, mj.poll_mj_image, on_success, on_failure)
    )
    await state.clear()


@router.callback_query(MidjourneyFSM.blend_collecting, F.data == "mj_blend:add")
async def cb_blend_add(call: CallbackQuery) -> None:
    await call.answer("Отправь следующее фото в чат.")


# ═══════════════════════════════════════════════════════════════════
# DESCRIBE FLOW
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "mj:describe")
async def cb_describe_start(call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    model_cost = await repo.get_model_cost(session, _MJ_DESCRIBE_MODEL)
    credits = model_cost.credits if model_cost else 5

    if db_user.credits < credits:
        await call.answer(f"Недостаточно кредитов ({credits} кр.)", show_alert=True)
        return

    await state.update_data(describe_credits=credits)
    await state.set_state(MidjourneyFSM.describe_upload)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"🔍 <b>Describe</b>\n\n"
        f"Отправь изображение — Midjourney сгенерирует описание-промпт.\n\n"
        f"Стоимость: <b>{credits} кр.</b>",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(MidjourneyFSM.describe_upload, F.photo)
async def handle_describe_photo(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    credits: int = data.get("describe_credits", 5)

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно кредитов.", reply_markup=main_menu_kb())
        await state.clear()
        return

    photo: PhotoSize = message.photo[-1]  # type: ignore[index]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)  # type: ignore[arg-type]
    b64 = "data:image/jpeg;base64," + base64.b64encode(file_bytes.read()).decode()  # type: ignore[union-attr]

    gen = await repo.create_generation(
        session, db_user.id, _MJ_DESCRIBE_MODEL, GenerationType.image, "describe", credits
    )
    await state.set_state(MidjourneyFSM.describe_polling)
    status_msg = await message.answer("⏳ Анализирую изображение...")

    try:
        task_id = await mj.describe(base64=b64)
    except Exception as e:
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, task_id)

    async def on_success(url: str) -> None:
        try:
            task_result = await mj.fetch_task(task_id)
        except Exception:
            task_result = MJTaskResult(task_id=task_id, status=MJTaskStatus.SUCCESS)

        await repo.finish_generation(session, gen.id, task_id)
        await state.clear()

        try:
            await status_msg.delete()
        except Exception:
            pass

        # describe возвращает промпты в поле prompt
        prompts_text = task_result.prompt or "Промпт не получен"
        await bot.send_message(
            chat_id=message.chat.id,
            text=f"🔍 <b>Описание изображения:</b>\n\n{prompts_text}",
            reply_markup=main_menu_kb(),
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()

    asyncio.create_task(
        polling.poll_until_done(task_id, mj.poll_mj_image, on_success, on_failure)
    )
    await state.clear()


# ═══════════════════════════════════════════════════════════════════
# VIDEO FLOW (MJ Image → Video)
# ═══════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "mj:video")
async def cb_mj_video_start(call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User) -> None:
    model_cost = await repo.get_model_cost(session, _MJ_VIDEO_MODEL)
    credits = model_cost.credits if model_cost else 15

    if db_user.credits < credits:
        await call.answer(f"Недостаточно кредитов ({credits} кр.)", show_alert=True)
        return

    await state.update_data(video_credits=credits)
    await state.set_state(MidjourneyFSM.video_upload)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"🎞️ <b>MJ Video</b>\n\n"
        f"Отправь изображение — оно станет первым кадром видео.\n\n"
        f"Стоимость: <b>{credits} кр.</b>",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(MidjourneyFSM.video_upload, F.photo)
async def handle_video_upload(message: Message, state: FSMContext, bot: Bot) -> None:
    photo: PhotoSize = message.photo[-1]  # type: ignore[index]
    file = await bot.get_file(photo.file_id)
    # Сохраняем как URL через file_path
    image_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
    await state.update_data(video_image_url=image_url)
    await state.set_state(MidjourneyFSM.video_speed_select)
    await message.answer(
        "⚡ Выбери интенсивность движения:",
        reply_markup=mj_video_speed_kb(),
    )


@router.callback_query(MidjourneyFSM.video_speed_select, F.data.startswith("mj_vmot:"))
async def cb_video_motion(call: CallbackQuery, state: FSMContext) -> None:
    motion_val = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(video_motion=motion_val)
    await state.set_state(MidjourneyFSM.video_prompt)
    await call.message.edit_text(  # type: ignore[union-attr]
        "✍️ Введи текстовый промпт для видео\n"
        "или нажми «Без промпта»:",
        reply_markup=mj_skip_prompt_kb(),
    )
    await call.answer()


@router.callback_query(MidjourneyFSM.video_prompt, F.data == "mj_skip_prompt")
async def cb_video_skip_prompt(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    await call.answer()
    await _submit_mj_video(call.message, state, session, db_user, bot, prompt="")  # type: ignore[arg-type]


@router.message(MidjourneyFSM.video_prompt, F.text)
async def handle_video_prompt(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot
) -> None:
    await _submit_mj_video(message, state, session, db_user, bot, prompt=message.text.strip())  # type: ignore[arg-type]


async def _submit_mj_video(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
    prompt: str,
) -> None:
    data = await state.get_data()
    credits: int = data.get("video_credits", 15)
    image_url: str = data.get("video_image_url", "")
    motion_val: str = data.get("video_motion", MJVideoMotion.LOW)
    motion = MJVideoMotion(motion_val)

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно кредитов.", reply_markup=main_menu_kb())
        await state.clear()
        return

    gen = await repo.create_generation(
        session, db_user.id, _MJ_VIDEO_MODEL, GenerationType.video, prompt or "mj-video", credits
    )
    await state.set_state(MidjourneyFSM.video_generating)
    status_msg = await message.answer(
        f"⏳ Генерирую видео ({motion.label()})..."
    )

    try:
        task_id = await mj.submit_video(image=image_url, motion=motion, prompt=prompt)
    except Exception as e:
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {e}", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, task_id)

    async def on_success(url: str) -> None:
        await repo.finish_generation(session, gen.id, url)
        await state.clear()

        try:
            await status_msg.delete()
        except Exception:
            pass

        await bot.send_video(
            chat_id=message.chat.id,
            video=url,
            caption="✅ MJ Видео готово!",
            reply_markup=main_menu_kb(),
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()

    asyncio.create_task(
        polling.poll_until_done(task_id, mj.poll_mj_video, on_success, on_failure)
    )
    await state.clear()
