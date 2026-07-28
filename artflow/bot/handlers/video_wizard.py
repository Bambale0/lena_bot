from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers import video_gen as legacy
from bot.keyboards.main_menu import back_to_menu_kb
from bot.keyboards.models import VIDEO_CAPS, model_cost_display_text, video_models_kb
from bot.states import VideoGenFSM
from bot.ui.model_labels import model_display_name
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db import repository as repo
from db.models import User

router = Router(name="video_wizard_v2")

SCENARIOS = {
    "text": {
        "title": "✍️ Ролик по описанию",
        "description": "Опиши сцену, движение и атмосферу — исходное фото не требуется.",
        "mode": "text",
        "recommended": [
            "kling/v3-turbo-text-to-video",
            "grok-imagine/text-to-video",
            "bytedance/seedance-2-fast",
        ],
        "group": "fast",
    },
    "image": {
        "title": "🖼 Оживить фото",
        "description": "Загрузи изображение и укажи, что должно двигаться или происходить в кадре.",
        "mode": "image",
        "recommended": [
            "kling/v3-turbo-image-to-video",
            "grok-imagine/image-to-video",
            "bytedance/seedance-2-fast",
        ],
        "group": "i2v",
    },
    "video": {
        "title": "🎞 Переработать видео",
        "description": "Используй исходный ролик как референс и измени стиль, сцену или персонажей.",
        "mode": "video",
        "recommended": ["gemini-omni-video"],
        "group": "omni",
    },
    "motion": {
        "title": "🎥 Управлять движением",
        "description": "Задай движение персонажа и камеры по фото и видео-референсу.",
        "mode": "motion",
        "recommended": ["kling-3.0/motion-control", "kling-2.6/motion-control"],
        "group": "motion",
    },
}


def _home_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✍️ Ролик по описанию", callback_data="vid_wizard:scenario:text"),
        InlineKeyboardButton(text="🖼 Оживить фото", callback_data="vid_wizard:scenario:image"),
    )
    builder.row(
        InlineKeyboardButton(text="🎞 Переработать видео", callback_data="vid_wizard:scenario:video"),
        InlineKeyboardButton(text="🎥 Движение и камера", callback_data="vid_wizard:scenario:motion"),
    )
    builder.row(InlineKeyboardButton(text="🧠 Все модели вручную", callback_data="vid_wizard:advanced"))
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"))
    return builder.as_markup()


def _review_kb(credits: float):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"🚀 Запустить за {credits:g} 💋", callback_data="vid_review:launch"))
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить запрос", callback_data="vid_review:prompt"),
        InlineKeyboardButton(text="⚙️ Изменить параметры", callback_data="vid_review:params"),
    )
    builder.row(
        InlineKeyboardButton(text="🔄 Начать заново", callback_data="menu:video"),
        InlineKeyboardButton(text="🏠 Главная", callback_data="menu:main"),
    )
    return builder.as_markup()


@router.callback_query(F.data == "menu:video")
async def open_video_wizard(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit_message(
        call.message,
        "🎬 <b>Какое видео хочешь получить?</b>\n\n"
        "Сначала выбери задачу — APIX сам сузит список моделей и выставит безопасные настройки. "
        "Название нейросети знать не нужно.\n\n"
        "После промпта ты увидишь итоговые параметры и точную стоимость до списания.",
        reply_markup=_home_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("vid_wizard:scenario:"))
async def choose_video_scenario(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    scenario_key = (call.data or "").rsplit(":", 1)[-1]
    scenario = SCENARIOS.get(scenario_key)
    if not scenario:
        await safe_answer_callback(call, "Сценарий не найден", show_alert=True)
        return

    costs = await repo.get_all_model_costs(session)
    by_key = {item.model_key: item for item in costs if item.model_key in VIDEO_CAPS}
    recommended = [by_key[key] for key in scenario["recommended"] if key in by_key]
    if not recommended:
        await safe_answer_callback(call, "Подходящие модели временно недоступны", show_alert=True)
        return

    await state.set_state(VideoGenFSM.model_select)
    await state.update_data(
        wizard_review_enabled=True,
        wizard_scenario=scenario_key,
        wizard_mode=scenario["mode"],
    )

    builder = InlineKeyboardBuilder()
    badges = ["⭐ Рекомендуем", "💎 Качество", "⚡ Альтернатива"]
    for index, model in enumerate(recommended[:3]):
        label = badges[index] if index < len(badges) else "Вариант"
        public_name = model_display_name(model.model_key, model.display_name)
        builder.row(
            InlineKeyboardButton(
                text=f"{label}: {public_name} · {model_cost_display_text(model, model_costs=costs)}",
                callback_data=f"vid_model:{model.model_key}",
            )
        )
    builder.row(
        InlineKeyboardButton(
            text="🧠 Выбрать другую модель",
            callback_data=f"vid_group:{scenario['group']}",
        )
    )
    builder.row(InlineKeyboardButton(text="← К сценариям", callback_data="menu:video"))

    await safe_edit_message(
        call.message,
        f"{scenario['title']}\n\n{scenario['description']}\n\n"
        "<b>Что выбрать:</b>\n"
        "⭐ рекомендуемый вариант — лучший баланс простоты и результата;\n"
        "💎 качество — когда важнее детализация;\n"
        "⚡ альтернатива — если хочешь сравнить результат.\n\n"
        "Выбери вариант. Дальше покажу только нужные шаги.",
        reply_markup=builder.as_markup(),
    )
    await safe_answer_callback(call)


@router.callback_query(F.data == "vid_wizard:advanced")
async def open_advanced_video_models(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.set_state(VideoGenFSM.model_select)
    await state.update_data(wizard_review_enabled=True, wizard_scenario="advanced")
    costs = await repo.get_all_model_costs(session)
    await safe_edit_message(
        call.message,
        "🧠 <b>Все видео-модели</b>\n\n"
        "Экспертный режим. Здесь можно выбрать конкретный движок вручную. "
        "После выбора APIX всё равно покажет только поддерживаемые режимы и параметры.",
        reply_markup=video_models_kb(costs),
    )
    await safe_answer_callback(call)


@router.message(VideoGenFSM.prompt_input, F.text)
async def review_video_prompt(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    if not data.get("wizard_review_enabled") or data.get("motion_step") in {"video_url", "prompt"}:
        await legacy.handle_video_prompt(message, state, session, db_user, bot)
        return

    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Опиши, что должно произойти в видео.", reply_markup=back_to_menu_kb())
        return

    model_key = str(data["model_key"])
    duration = int(data.get("duration") or 5)
    resolution = data.get("resolution")
    model_cost = await legacy._resolve_video_model_cost(
        session,
        model_key,
        duration=duration,
        resolution=resolution,
        has_video_input=legacy._has_gemini_omni_video_input(model_key, data),
    )
    if not model_cost:
        await message.answer("Эта модель сейчас недоступна. Начни заново и выбери другую.", reply_markup=_home_kb())
        return

    total = legacy._video_total_credits(model_key, duration, float(model_cost.credits))
    await state.update_data(review_prompt=prompt, credits=float(model_cost.credits))
    await state.set_state(VideoGenFSM.review)

    mode_labels = {
        "text": "по текстовому описанию",
        "image": "по фото-референсу",
        "video": "по видео-референсу",
        "motion": "управление движением и камерой",
    }
    ref_count = legacy._video_ref_count(data)
    materials = "не требуются"
    if data.get("mode") == "image":
        materials = f"{ref_count or 1} фото"
    elif data.get("mode") == "video":
        materials = "1 видео"
    elif data.get("mode") == "motion":
        materials = "фото + видео"

    public_name = model_display_name(model_key, model_cost.display_name)
    await message.answer(
        "✅ <b>Проверь задачу перед запуском</b>\n\n"
        f"🎯 Сценарий: <b>{mode_labels.get(data.get('mode'), data.get('mode') or 'видео')}</b>\n"
        f"🤖 Модель: <b>{escape(public_name)}</b>\n"
        f"📎 Материалы: <b>{materials}</b>\n"
        f"⚙️ Параметры: <code>{escape(legacy._params_summary(data))}</code>\n"
        f"✍️ Запрос: <i>{escape(prompt[:700])}</i>\n\n"
        f"💎 Итоговая стоимость: <b>{total:g} 💋</b>\n"
        f"Баланс после запуска: <b>{max(0, float(db_user.credits) - total):g} 💋</b>\n\n"
        "Списание произойдёт только после нажатия кнопки запуска.",
        reply_markup=_review_kb(total),
    )


@router.callback_query(VideoGenFSM.review, F.data == "vid_review:launch")
async def launch_reviewed_video(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    bot: Bot,
) -> None:
    data = await state.get_data()
    prompt = str(data.get("review_prompt") or "").strip()
    if not prompt:
        await safe_answer_callback(call, "Запрос потерян. Введи его заново.", show_alert=True)
        await state.set_state(VideoGenFSM.prompt_input)
        return
    await safe_answer_callback(call, "Запускаю")
    await legacy._launch_video_generation_from_state(
        source_message=call.message,
        state=state,
        session=session,
        db_user=db_user,
        bot=bot,
        prompt=prompt,
        source_feed_gen_id=data.get("source_feed_gen_id"),
        parent_generation_id=data.get("parent_generation_id"),
    )


@router.callback_query(VideoGenFSM.review, F.data == "vid_review:prompt")
async def edit_review_prompt(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(VideoGenFSM.prompt_input)
    await safe_edit_message(
        call.message,
        "✏️ <b>Измени запрос</b>\n\nОпиши сцену, действие, движение камеры и атмосферу одним сообщением.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)


@router.callback_query(VideoGenFSM.review, F.data == "vid_review:params")
async def edit_review_params(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    model_key = str(data.get("model_key") or "")
    await state.set_state(VideoGenFSM.params_select)
    await safe_edit_message(
        call.message,
        "⚙️ <b>Измени параметры</b>\n\n"
        f"Сейчас: <code>{escape(legacy._params_summary(data))}</code>\n\n"
        "Меняй только нужное. Галочка показывает выбранное значение.",
        reply_markup=legacy._video_params_reply_markup(model_key, data),
    )
    await safe_answer_callback(call)
