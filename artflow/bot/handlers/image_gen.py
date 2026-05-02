# bot/handlers/image_gen.py
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, PhotoSize
from sqlalchemy.ext.asyncio import AsyncSession

from api import image_service, polling
from api.image_service import ImageModel
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import after_generation_kb, image_models_kb
from bot.states import ImageGenFSM
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="image_gen")


@router.callback_query(F.data == "menu:image")
async def cb_image_menu(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    await state.set_state(ImageGenFSM.model_select)
    model_costs = await repo.get_all_model_costs(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🎨 <b>Генерация изображений</b>\n\nВыбери модель:",
        reply_markup=image_models_kb(model_costs),
    )
    await call.answer()


@router.callback_query(ImageGenFSM.model_select, F.data.startswith("img_model:"))
async def cb_model_selected(
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
    await state.set_state(ImageGenFSM.prompt_input)

    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ Модель: <b>{model_cost.display_name}</b> ({model_cost.credits} кр)\n\n"
        "Введи промпт на английском для лучшего результата.\n\n"
        "<i>Пример: futuristic city at sunset, cinematic, 4k, detailed</i>",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer()


@router.message(ImageGenFSM.prompt_input, F.text)
async def handle_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    model_key: str = data["model_key"]
    credits: int = data["credits"]
    prompt = message.text.strip()  # type: ignore[union-attr]

    # Списываем кредиты
    ok = await repo.spend_credits(session, db_user.id, credits)
    if not ok:
        await message.answer("❌ Недостаточно кредитов.", reply_markup=main_menu_kb())
        await state.clear()
        return

    # Создаём запись генерации
    gen = await repo.create_generation(
        session, db_user.id, model_key, GenerationType.image, prompt, credits
    )

    await state.set_state(ImageGenFSM.generating)
    status_msg = await message.answer(
        f"⏳ Генерирую изображение...\n"
        f"<code>{model_key}</code> · подожди немного"
    )

    # Запускаем генерацию
    try:
        model = ImageModel(model_key)
        result = await image_service.generate_image(model, prompt)
    except Exception as e:
        logger.error("Image generation error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)  # возврат кредитов
        await status_msg.edit_text("❌ Ошибка генерации. Кредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()
        return

    if not result.is_async:
        # Синхронный результат — сразу отправляем
        await _send_image_result(bot, message.chat.id, result.url, gen.id, prompt, status_msg)
        await repo.finish_generation(session, gen.id, result.url)
        await state.clear()
    else:
        # Асинхронный — запускаем polling
        await repo.update_generation_task(session, gen.id, result.task_id)

        async def on_success(url: str) -> None:
            await repo.finish_generation(session, gen.id, url)
            await _send_image_result(bot, message.chat.id, url, gen.id, prompt, status_msg)

        async def on_failure(err: str) -> None:
            await repo.fail_generation(session, gen.id, err)
            await repo.add_credits(session, db_user.id, credits)
            await status_msg.edit_text(
                f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb()
            )

        check_fn = image_service.poll_seedream_status
        asyncio.create_task(
            polling.poll_until_done(result.task_id, check_fn, on_success, on_failure)
        )
        await state.clear()


async def _send_image_result(
    bot: Bot,
    chat_id: int,
    url: str,
    gen_id: int,
    prompt: str,
    status_msg: Message,
) -> None:
    try:
        await status_msg.delete()
    except Exception:
        pass
    caption = f"✅ Готово!\n\n<i>{prompt[:200]}</i>"
    await bot.send_photo(
        chat_id=chat_id,
        photo=url,
        caption=caption,
        reply_markup=after_generation_kb(gen_id, "image"),
    )


# ── Регенерация ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("regen:image:"))
async def cb_regen_image(
    call: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Повторная генерация с той же моделью и промптом."""
    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    # Получаем предыдущую генерацию
    from sqlalchemy import select
    from db.models import Generation
    result = await session.execute(select(Generation).where(Generation.id == gen_id))
    prev_gen = result.scalar_one_or_none()
    if not prev_gen:
        await call.answer("Генерация не найдена", show_alert=True)
        return

    await state.update_data(model_key=prev_gen.model, credits=prev_gen.credits_spent)
    await state.set_state(ImageGenFSM.prompt_input)
    # Эмулируем ввод промпта
    await state.update_data(regen_prompt=prev_gen.prompt)
    await call.message.answer(prev_gen.prompt)  # type: ignore[union-attr]
    await call.answer()
