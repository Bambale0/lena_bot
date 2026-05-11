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
from aiogram.types import CallbackQuery, Message, PhotoSize, URLInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from api import midjourney_service as mj
from api import polling
from api.public_files import mirror_telegram_file
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
    mj_reference_upload_kb,
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

@router.callback_query(F.data.in_({"menu:mj", "midjourney"}))
async def cb_mj_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(  # type: ignore[union-attr]
        "🖌️ <b>Midjourney</b>\n\n"
        "Мощнейший AI для генерации изображений и видео. Что умеет:\n\n"
        "🎨 <b>Imagine</b> — создать изображение по текстовому промпту "
        "(+ референс-фото опционально). Получаешь 4 варианта с кнопками U (upscale), "
        "V (variation), 🔄 (reroll) и другими действиями.\n\n"
        "🖼️ <b>Blend</b> — смешать от 2 до 5 изображений в одно. "
        "Отлично для создания уникальных стилей.\n\n"
        "🔍 <b>Describe</b> — загрузи любое фото и получи готовый промпт, "
        "который его описывает. Удобно для изучения стилей.\n\n"
        "🎞️ <b>Video</b> — оживи изображение, превратив его в видео "
        "с настраиваемой интенсивностью движения.\n\n"
        "👇 Выбери действие:",
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
        "🎨 <b>Imagine — выбор модели бота</b>\n\n"
        "🎨 <b>Midjourney</b> — универсальный стиль, реализм, концепт-арт, "
        "архитектура, продуктовые снимки. Работает с любыми промптами.\n\n"
        "🌸 <b>Niji Journey</b> — специализирован на аниме, манге и японской "
        "иллюстрации. Идеален для персонажей в аниме-стиле.\n\n"
        "👇 Выбери:",
        reply_markup=mj_bot_type_kb(),
    )
    await call.answer()


@router.callback_query(MidjourneyFSM.bot_type_select, F.data.startswith("mj_bt:"))
async def cb_bot_type(call: CallbackQuery, state: FSMContext) -> None:
    bot_type_val = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(bot_type=bot_type_val)
    await state.set_state(MidjourneyFSM.speed_select)
    await call.message.edit_text(  # type: ignore[union-attr]
        "⚡ <b>Выбери скорость генерации</b>\n\n"
        "⚡ <b>Fast</b> — быстрая очередь, результат за ~1 мин. Стандартный выбор.\n\n"
        "🚀 <b>Turbo</b> — приоритетная очередь, ещё быстрее. "
        "Подходит, когда нужно срочно.\n\n"
        "😌 <b>Relax</b> — дольше, но дешевле. Когда результат не нужен немедленно.",
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
            f"Недостаточно cr! Нужно {credits}, у тебя {db_user.credits}.",
            show_alert=True,
        )
        return

    await state.update_data(speed=speed_val, credits=credits)
    await state.set_state(MidjourneyFSM.reference_upload)

    await call.message.edit_text(  # type: ignore[union-attr]
        f"📎 <b>Референс-изображение</b> (опционально) · {credits} cr\n\n"
        "Если хочешь, чтобы Midjourney ориентировался на стиль конкретного изображения, "
        "загрузи его сейчас. Ссылка будет добавлена в начало промпта автоматически.\n\n"
        "Или нажми «Без референса» и просто введи промпт.",
        reply_markup=mj_reference_upload_kb(),
    )
    await call.answer()


@router.callback_query(MidjourneyFSM.reference_upload, F.data == "mj_ref:skip")
async def cb_mj_ref_skip(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(reference_b64=None)
    await state.set_state(MidjourneyFSM.prompt_input)
    data = await state.get_data()
    credits: int = data.get("credits", 10)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✏️ <b>Введи промпт для Midjourney</b> · {credits} cr\n\n"
        "Пиши на английском — MJ понимает его лучше всего.\n\n"
        "<b>Параметры:</b>\n"
        "• <code>--ar 16:9</code> / <code>--ar 1:1</code> — соотношение сторон\n"
        "• <code>--v 6.1</code> — версия Midjourney\n"
        "• <code>--style raw</code> — меньше AI-обработки, ближе к промпту\n"
        "• <code>--q 2</code> — высокое качество (медленнее)\n\n"
        "<b>Примеры:</b>\n"
        "<i>a cute cat in neon city, cyberpunk, 8k --ar 16:9 --v 6.1</i>\n"
        "<i>portrait of a warrior, epic fantasy, oil painting --ar 2:3</i>",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(MidjourneyFSM.reference_upload, F.photo)
async def handle_mj_reference_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    buf = await bot.download_file(file.file_path)
    raw = buf.read() if hasattr(buf, "read") else bytes(buf)
    b64 = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
    await state.update_data(reference_b64=b64)
    await state.set_state(MidjourneyFSM.prompt_input)
    data = await state.get_data()
    credits: int = data.get("credits", 10)
    await message.answer(
        f"✅ Референс получен! · {credits} cr\n\n"
        "✏️ <b>Введи промпт</b> — изображение будет добавлено как стиль-референс.\n\n"
        "Можно указать вес референса: <code>image.jpg::1.5</code> (чем выше, тем сильнее влияние)\n\n"
        "<i>Пример: same style portrait, cinematic, studio light --ar 3:4</i>",
        reply_markup=back_to_menu_kb(),
    )


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
    reference_b64: str | None = data.get("reference_b64")
    base64_array = [reference_b64] if reference_b64 else None

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно cr.", reply_markup=main_menu_kb())
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
        task_id = await mj.imagine(prompt, bot_type=bot_type, speed=speed, base64_array=base64_array)
    except Exception as e:
        logger.error("MJ imagine submit error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text("❌ Ошибка при отправке запроса. cr возвращены.", reply_markup=main_menu_kb())
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
        _mj_photo_url = task_result.image_url or url
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=URLInputFile(_mj_photo_url, filename="image.jpg"),
            caption=caption,
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )
        await bot.send_document(
            chat_id=message.chat.id,
            document=URLInputFile(_mj_photo_url, filename="image.jpg"),
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
            f"❌ Ошибка: {err}\nвозвращены.", reply_markup=main_menu_kb()
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
            f"Недостаточно cr ({credits})", show_alert=True
        )
        return

    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await call.answer("Недостаточно cr", show_alert=True)
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
            photo=URLInputFile(media_url, filename="image.jpg"),
            caption=caption,
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )
        await bot.send_document(
            chat_id=call.message.chat.id,  # type: ignore[union-attr]
            document=URLInputFile(media_url, filename="image.jpg"),
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
            f"❌ Ошибка: {err}\nвозвращены.", reply_markup=main_menu_kb()
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

        _modal_url = task_result.image_url or url
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=URLInputFile(_modal_url, filename="image.jpg"),
            caption="✅ Modal готово!",
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )
        await bot.send_document(
            chat_id=message.chat.id,
            document=URLInputFile(_modal_url, filename="image.jpg"),
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
        await call.answer(f"Недостаточно cr ({credits})", show_alert=True)
        return

    await state.update_data(blend_images=[], blend_credits=credits)
    await state.set_state(MidjourneyFSM.blend_collecting)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"🖼️ <b>Blend — смешивание изображений</b> · {credits} cr\n\n"
        "Отправляй фото по одному — от 2 до 6 штук. "
        "Midjourney смешает их в одно изображение, сохраняя стиль, цвета и элементы каждого.\n\n"
        "💡 <b>Советы:</b>\n"
        "• Выбирай изображения с похожей композицией\n"
        "• Хорошо сочетаются портрет + текстура или пейзаж + стиль\n"
        "• После 2-х фото появится кнопка «Блендить» (до 6 изображений)",
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

    if len(images) >= 6:
        await message.answer("Максимум 6 изображений. Нажми «Блендить».")
        return

    photo: PhotoSize = message.photo[-1]  # type: ignore[index]
    file = await bot.get_file(photo.file_id)
    file_bytes = await bot.download_file(file.file_path)  # type: ignore[arg-type]
    b64 = "data:image/jpeg;base64," + base64.b64encode(file_bytes.read()).decode()  # type: ignore[union-attr]
    images.append(b64)
    await state.update_data(blend_images=images)

    count = len(images)
    await message.answer(
        f"✅ Фото {count}/6 добавлено.",
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
        await call.answer("Недостаточно cr", show_alert=True)
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

        _blend_url = task_result.image_url or url
        await bot.send_photo(
            chat_id=call.message.chat.id,  # type: ignore[union-attr]
            photo=URLInputFile(_blend_url, filename="image.jpg"),
            caption="✅ Blend готово!",
            reply_markup=mj_action_buttons_kb(task_result.buttons),
        )
        await bot.send_document(
            chat_id=call.message.chat.id,  # type: ignore[union-attr]
            document=URLInputFile(_blend_url, filename="image.jpg"),
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {err}\nвозвращены.", reply_markup=main_menu_kb())
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
        await call.answer(f"Недостаточно cr ({credits})", show_alert=True)
        return

    await state.update_data(describe_credits=credits)
    await state.set_state(MidjourneyFSM.describe_upload)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"🔍 <b>Describe</b> · {credits} cr\n\n"
        "Загрузи любое изображение — Midjourney проанализирует его и выдаст "
        "4 варианта текстового промпта, которые описывают это изображение.\n\n"
        "💡 <b>Зачем это нужно:</b>\n"
        "• Узнать, как описать понравившийся стиль\n"
        "• Получить базу для своего промпта\n"
        "• Изучить язык Midjourney\n\n"
        "👇 Отправь фото:",
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
        await message.answer("❌ Недостаточно cr.", reply_markup=main_menu_kb())
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
        await status_msg.edit_text(f"❌ Ошибка: {err}\nвозвращены.", reply_markup=main_menu_kb())
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
        await call.answer(f"Недостаточно cr ({credits})", show_alert=True)
        return

    await state.update_data(video_credits=credits)
    await state.set_state(MidjourneyFSM.video_upload)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"🎞️ <b>MJ Video — изображение в видео</b> · {credits} cr\n\n"
        "Отправь изображение — оно станет первым кадром. "
        "Midjourney оживит его, добавив движение.\n\n"
        "💡 <b>Лучше всего работает с:</b>\n"
        "• Портретами людей и персонажей\n"
        "• Пейзажами с природой\n"
        "• Абстрактными и фантастическими сценами\n\n"
        "👇 Отправь фото:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(MidjourneyFSM.video_upload, F.photo)
async def handle_video_upload(message: Message, state: FSMContext, bot: Bot) -> None:
    photo: PhotoSize = message.photo[-1]  # type: ignore[index]
    image_url = await mirror_telegram_file(bot, photo.file_id)
    await state.update_data(video_image_url=image_url)
    await state.set_state(MidjourneyFSM.video_speed_select)
    await message.answer(
        "⚡ <b>Интенсивность движения</b>\n\n"
        "🐢 <b>Low</b> — плавное, едва заметное движение. Хорошо для портретов.\n"
        "🏎 <b>High</b> — активное, динамичное движение. Больше эффекта.",
        reply_markup=mj_video_speed_kb(),
    )


@router.callback_query(MidjourneyFSM.video_speed_select, F.data.startswith("mj_vmot:"))
async def cb_video_motion(call: CallbackQuery, state: FSMContext) -> None:
    motion_val = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(video_motion=motion_val)
    await state.set_state(MidjourneyFSM.video_prompt)
    await call.message.edit_text(  # type: ignore[union-attr]
        "✍️ <b>Промпт для видео</b> (опционально)\n\n"
        "Можно добавить текстовое описание движения или атмосферы. "
        "Если не нужно — нажми «Без промпта».\n\n"
        "<i>Пример: gentle wind, hair flowing, soft bokeh</i>",
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
        await message.answer("❌ Недостаточно cr.", reply_markup=main_menu_kb())
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
            video=URLInputFile(url, filename="video.mp4"),
            caption="✅ MJ Видео готово!",
            reply_markup=main_menu_kb(),
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(f"❌ Ошибка: {err}\nвозвращены.", reply_markup=main_menu_kb())
        await state.clear()

    asyncio.create_task(
        polling.poll_until_done(task_id, mj.poll_mj_video, on_success, on_failure)
    )
    await state.clear()
