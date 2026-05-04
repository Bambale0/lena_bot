# bot/handlers/image_gen.py
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from api import image_service, polling
from api.image_service import ImageModel
from bot.keyboards.main_menu import back_to_menu_kb, main_menu_kb
from bot.keyboards.models import (
    IMAGE_CAPS,
    after_generation_kb,
    image_aspect_ratio_kb,
    image_count_kb,
    image_mode_kb,
    image_model_info,
    image_models_kb,
    image_quality_kb,
    reference_upload_kb,
)
from bot.states import ImageGenFSM
from db import repository as repo
from db.models import GenerationType, User

logger = logging.getLogger(__name__)
router = Router(name="image_gen")


# ── Model select ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:image")
async def cb_image_menu(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.set_state(ImageGenFSM.model_select)
    model_costs = await repo.get_all_model_costs(session)
    await call.message.edit_text(  # type: ignore[union-attr]
        "🎨 <b>Генерация изображений</b>\n\n"
        "Выбери AI-модель. Каждая имеет свои сильные стороны:\n\n"
        "• <b>Seedream</b> — максимум деталей и реализма\n"
        "• <b>Gemini Pro/Flash</b> — точное следование описанию, поддержка img2img\n"
        "• <b>WAN</b> — кино-стиль, персонажи, фэнтези\n"
        "• <b>GPT Image</b> — понимает сложные и длинные промпты\n\n"
        "👇 <b>Нажми на модель для выбора:</b>",
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

    await state.update_data(
        model_key=model_key, credits=model_cost.credits,
        aspect_ratio=None, count=1, image_file_id=None, quality="basic",
    )

    caps = IMAGE_CAPS.get(model_key, {})
    modes = caps.get("modes", ["text"])

    if len(modes) > 1:
        await state.set_state(ImageGenFSM.mode_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{model_cost.display_name}</b> ({model_cost.credits} кр)\n\nВыбери режим:",
            reply_markup=image_mode_kb(model_key),
        )
    else:
        await state.update_data(mode=modes[0])
        await _go_to_next_step(call, state, session, model_key, model_cost.display_name)
    await call.answer()


async def _go_to_next_step(
    call: CallbackQuery, state: FSMContext,
    session: AsyncSession, model_key: str, display_name: str,
) -> None:
    caps = IMAGE_CAPS.get(model_key, {})
    data = await state.get_data()
    mode = data.get("mode", "text")

    # img2img — нужно загрузить референс
    if mode == "image" and not data.get("image_file_id"):
        await state.set_state(ImageGenFSM.image_upload)
        await call.message.edit_text(  # type: ignore[union-attr]
            "🖼️ Загрузи референс-изображение:", reply_markup=back_to_menu_kb(),
        )
        return

    # Aspect ratio (для text-режима или если у модели нет img2img)
    if caps.get("aspect_ratios") and mode == "text":
        await state.set_state(ImageGenFSM.aspect_ratio_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\n📐 Соотношение сторон:",
            reply_markup=image_aspect_ratio_kb(model_key),
        )
        return

    # Quality (Seedream 4.5)
    if caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\n💎 Качество изображения:",
            reply_markup=image_quality_kb(),
        )
        return

    # Count (WAN 2.7 Pro)
    if len(caps.get("counts", [1])) > 1:
        await state.set_state(ImageGenFSM.count_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b>\n\n🔢 Количество изображений:",
            reply_markup=image_count_kb(),
        )
        return

    await state.set_state(ImageGenFSM.prompt_input)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>{display_name}</b>\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )


# ── Mode select ───────────────────────────────────────────────────────────────

@router.callback_query(ImageGenFSM.mode_select, F.data.startswith("img_mode:"))
async def cb_image_mode(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    parts = call.data.split(":")  # type: ignore[union-attr]
    mode, model_key = parts[1], parts[2]
    await state.update_data(mode=mode)
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await _go_to_next_step(call, state, session, model_key, display_name)
    await call.answer()


# ── Aspect ratio ──────────────────────────────────────────────────────────────

@router.callback_query(ImageGenFSM.aspect_ratio_select, F.data.startswith("img_ratio:"))
async def cb_image_ratio(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    ratio = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(aspect_ratio=ratio)
    data = await state.get_data()
    model_key = data["model_key"]
    caps = IMAGE_CAPS.get(model_key, {})
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    if caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b> · {ratio}\n\n💎 Качество:",
            reply_markup=image_quality_kb(),
        )
    elif len(caps.get("counts", [1])) > 1:
        await state.set_state(ImageGenFSM.count_select)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b> · {ratio}\n\n🔢 Количество изображений:",
            reply_markup=image_count_kb(),
        )
    else:
        await state.set_state(ImageGenFSM.prompt_input)
        await call.message.edit_text(  # type: ignore[union-attr]
            f"✅ <b>{display_name}</b> · {ratio}\n\n✍️ Введи промпт:",
            reply_markup=back_to_menu_kb(),
        )
    await call.answer(ratio)


@router.callback_query(ImageGenFSM.aspect_ratio_select, F.data.startswith("img_back:mode:"))
async def cb_image_back_to_mode(call: CallbackQuery, state: FSMContext) -> None:
    model_key = call.data.split(":")[-1]  # type: ignore[union-attr]
    await state.set_state(ImageGenFSM.mode_select)
    await call.message.edit_text(  # type: ignore[union-attr]
        "Выбери режим:", reply_markup=image_mode_kb(model_key),
    )
    await call.answer()




# ── Quality / Count ───────────────────────────────────────────────────────────

@router.callback_query(ImageGenFSM.count_select, F.data.startswith("img_quality:"))
async def cb_image_quality(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    quality = call.data.split(":")[1]  # type: ignore[union-attr]
    await state.update_data(quality=quality)
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    ratio = data.get("aspect_ratio", "1:1")
    q_label = "4K" if quality == "high" else "2K"

    await state.set_state(ImageGenFSM.prompt_input)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>{display_name}</b> · {ratio} · {q_label}\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer(q_label)


@router.callback_query(ImageGenFSM.count_select, F.data.startswith("img_count:"))
async def cb_image_count(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    count = int(call.data.split(":")[1])  # type: ignore[union-attr]
    await state.update_data(count=count)
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    ratio = data.get("aspect_ratio", "1:1")

    await state.set_state(ImageGenFSM.prompt_input)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>{display_name}</b> · {ratio} · {count} изображ.\n\n✍️ Введи промпт:",
        reply_markup=back_to_menu_kb(),
    )
    await call.answer(f"{count} шт")


@router.callback_query(ImageGenFSM.count_select, F.data == "img_back:ratio")
async def cb_count_back(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key
    await state.set_state(ImageGenFSM.aspect_ratio_select)
    await call.message.edit_text(  # type: ignore[union-attr]
        f"✅ <b>{display_name}</b>\n\n📐 Соотношение сторон:",
        reply_markup=image_aspect_ratio_kb(model_key),
    )
    await call.answer()


# ── Image upload (img2img referенс) ──────────────────────────────────────────

@router.message(ImageGenFSM.image_upload, F.photo)
async def handle_reference_upload(
    message: Message, state: FSMContext, session: AsyncSession
) -> None:
    best = sorted(message.photo, key=lambda p: p.file_size, reverse=True)  # type: ignore[union-attr]
    await state.update_data(image_file_id=best[0].file_id)
    data = await state.get_data()
    model_key = data["model_key"]
    model_cost = await repo.get_model_cost(session, model_key)
    display_name = model_cost.display_name if model_cost else model_key

    caps = IMAGE_CAPS.get(model_key, {})
    if caps.get("has_quality"):
        await state.set_state(ImageGenFSM.count_select)
        await message.answer(
            f"✅ Референс загружен!\n\n💎 Качество · <b>{display_name}</b>:",
            reply_markup=image_quality_kb(),
        )
    else:
        await state.set_state(ImageGenFSM.prompt_input)
        await message.answer("✅ Референс загружен!\n\n✍️ Введи промпт:", reply_markup=back_to_menu_kb())


# ── Prompt ────────────────────────────────────────────────────────────────────

@router.message(ImageGenFSM.prompt_input, F.text)
async def handle_prompt(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, bot: Bot,
) -> None:
    data = await state.get_data()
    model_key: str = data["model_key"]
    credits: int = data["credits"]
    aspect_ratio: str | None = data.get("aspect_ratio")
    count: int = data.get("count", 1)
    quality: str = data.get("quality", "basic")
    image_file_id: str | None = data.get("image_file_id")
    prompt = message.text.strip()  # type: ignore[union-attr]

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
        session, db_user.id, model_key, GenerationType.image, prompt, credits
    )

    await state.set_state(ImageGenFSM.generating)
    params_parts = [p for p in [aspect_ratio, f"{count} шт" if count > 1 else None] if p]
    status_msg = await message.answer(
        f"⏳ <b>Генерирую изображение...</b>\n"
        f"<code>{model_key}</code>"
        + (f" · {' · '.join(params_parts)}" if params_parts else "")
    )

    try:
        result = await image_service.generate_image(
            ImageModel(model_key), prompt,
            image_url=image_url, aspect_ratio=aspect_ratio, n=count, quality=quality,
        )
    except Exception as e:
        logger.error("Image generation error: %s", e)
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text("❌ Ошибка генерации. Кредиты возвращены.", reply_markup=main_menu_kb())
        await state.clear()
        return

    await repo.update_generation_task(session, gen.id, result.task_id or "")

    async def on_success(url: str) -> None:
        from api.image_service import ImageResult as IR
        await repo.finish_generation(session, gen.id, url)
        await _send_image_result(
            bot, message.chat.id,
            IR(is_async=False, url=url), gen.id, prompt, status_msg,
        )

    async def on_failure(err: str) -> None:
        await repo.fail_generation(session, gen.id, err)
        await repo.add_credits(session, db_user.id, credits)
        await status_msg.edit_text(
            f"❌ Ошибка: {err}\nКредиты возвращены.", reply_markup=main_menu_kb()
        )

    asyncio.create_task(
        polling.poll_until_done(
            result.task_id or "", image_service.poll_kieai_status, on_success, on_failure
        )
    )
    await state.clear()


async def _send_image_result(
    bot: Bot, chat_id: int,
    result: "image_service.ImageResult",
    gen_id: int, prompt: str, status_msg: Message,
) -> None:
    from aiogram.types import BufferedInputFile
    try:
        await status_msg.delete()
    except Exception:
        pass
    caption = f"✅ <b>Готово!</b>\n\n<i>{prompt[:200]}</i>"
    kb = after_generation_kb(gen_id, "image")
    if result.image_bytes:
        ext = "png" if "png" in (result.mime_type or "") else "jpg"
        photo = BufferedInputFile(result.image_bytes, filename=f"artflow_{gen_id}.{ext}")
    else:
        photo = result.url  # type: ignore[assignment]
    await bot.send_photo(chat_id=chat_id, photo=photo, caption=caption, reply_markup=kb)


# ── Regen ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("regen:image:"))
async def cb_regen_image(call: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    gen_id = int(call.data.split(":")[2])  # type: ignore[union-attr]
    from sqlalchemy import select
    from db.models import Generation
    res = await session.execute(select(Generation).where(Generation.id == gen_id))
    prev = res.scalar_one_or_none()
    if not prev:
        await call.answer("Генерация не найдена", show_alert=True)
        return
    await state.update_data(model_key=prev.model, credits=prev.credits_spent)
    await state.set_state(ImageGenFSM.prompt_input)
    await call.message.answer(prev.prompt)  # type: ignore[union-attr]
    await call.answer()
