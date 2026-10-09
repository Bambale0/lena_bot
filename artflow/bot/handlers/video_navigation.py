"""Explicit parent screens for the video wizard; back never starts a new model."""

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.models import VIDEO_CAPS, video_mode_kb
from bot.keyboards.video_navigation import video_back_kb
from bot.states import VideoGenFSM
from bot.utils.telegram_ui import safe_answer_callback, safe_edit_message
from db.models import User

router = Router(name="video_navigation")


@router.callback_query(StateFilter(VideoGenFSM), F.data == "vid_nav:models")
async def back_to_models(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    from bot.handlers import video_gen, video_wizard

    data = await state.get_data()
    if data.get("feed_force_reference"):
        from bot.keyboards.models import feed_video_models_kb
        from db import repository as repo

        repeat_data = {
            key: value
            for key, value in data.items()
            if key.startswith("feed_") or key in {"source_feed_gen_id", "parent_generation_id"}
        }
        await state.set_data(repeat_data)
        await state.set_state(VideoGenFSM.model_select)
        costs = await repo.get_all_model_costs(session)
        await safe_edit_message(
            call.message,
            "🎬 <b>Повторить видео</b>\n\nВыбери модель для повтора по твоему фото:",
            reply_markup=feed_video_models_kb(costs),
        )
        await safe_answer_callback(call)
        return
    origin = str(data.get("video_model_menu") or "")
    scenario = data.get("wizard_scenario")
    if origin.startswith("vid_wizard:models:"):
        await video_wizard.show_scenario_models(
            call.model_copy(update={"data": origin}), state, session
        )
    elif scenario in video_wizard.SCENARIOS:
        await video_wizard.choose_video_scenario(
            call.model_copy(update={"data": f"vid_wizard:scenario:{scenario}"}), state, session
        )
    elif origin == "menu:genjutsu":
        await state.clear()
        await video_gen.cb_genjutsu_menu(call, session, state)
    elif origin.startswith("vid_group:"):
        await state.clear()
        await state.set_state(VideoGenFSM.model_select)
        await video_gen.cb_video_group(call.model_copy(update={"data": origin}), session, state)
    else:
        await video_wizard.open_advanced_video_models(call, state, session)


async def show_params(call: CallbackQuery, state: FSMContext) -> None:
    from bot.handlers import video_gen

    data = await state.get_data()
    model_key = data["model_key"]
    await state.set_state(VideoGenFSM.params_select)
    await safe_edit_message(
        call.message,
        "⚙️ <b>Параметры видео</b>\n\n" + video_gen._video_params_hint(model_key, data),
        reply_markup=video_gen._video_params_reply_markup(model_key, data),
    )
    await safe_answer_callback(call)


async def show_references(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, *, photos: bool = False
) -> bool:
    from api.minimax_h3_adapter import PUBLIC_MODEL
    from api.seedance25_adapter import MODEL_KEY
    from bot.handlers import gemini_omni_references as omni
    from bot.handlers import minimax_h3_references as h3
    from bot.handlers import seedance25_references as s25
    from bot.handlers import video_gen, video_references
    from core.gemini_omni import GEMINI_OMNI_VIDEO_MODEL

    data = await state.get_data()
    key = data["model_key"]
    mode = data.get("mode")
    two_step = (
        mode == "motion"
        or key in video_gen.GENJUTSU_MODEL_KEYS
        or data.get("seedance_identity_transfer")
    )
    if data.get("feed_force_reference") and key != MODEL_KEY:
        await video_gen._handle_mode(call, state, session, key, key, mode)
        return True
    if two_step:
        await state.set_state(VideoGenFSM.image_upload)
        if mode == "motion":
            await state.update_data(motion_step="person" if photos else "video_url")
        elif data.get("seedance_identity_transfer"):
            await state.update_data(seedance_identity_step="photos" if photos else "video")
        else:
            await state.update_data(genjutsu_step=None if photos else "video")
        text = "📎 <b>Шаг 1/2: фото-референсы</b>" if photos else "🎞 <b>Шаг 2/2: исходное видео</b>"
        text += "\n\nОтправь новый файл или продолжи с сохранёнными материалами."
        markup = video_back_kb()
        present = (
            (data.get("image_file_id") or data.get("ref_file_ids") or data.get("image_url"))
            if photos
            else data.get("reference_video_url")
        )
        if present:
            markup.inline_keyboard.insert(
                0,
                [
                    InlineKeyboardButton(
                        text="✅ Продолжить",
                        callback_data="vid_nav:video" if photos else "vid_nav:params",
                    )
                ],
            )
    elif key == MODEL_KEY and not data.get("seedance_identity_transfer"):
        await state.set_state(VideoGenFSM.seedance25_reference_upload)
        text, markup = s25._text(data), s25._kb_for_data(data)
    elif key == PUBLIC_MODEL and data.get("wizard_scenario") not in {"text", "image"}:
        await state.set_state(VideoGenFSM.h3_reference_upload)
        text, markup = h3._status_text(data), h3._collection_kb()
    elif key == GEMINI_OMNI_VIDEO_MODEL and mode == "video":
        await state.set_state(VideoGenFSM.image_upload)
        text = (
            "🎞 <b>Референсы видео</b>\n\n"
            + omni._status_text(data)
            + "\nДобавь материалы или нажми «Готово»."
        )
        markup = omni._media_keyboard()
    elif mode == "video" and key in video_references.SEEDANCE_VIDEO_REFERENCE_MODELS:
        await state.set_state(VideoGenFSM.video_upload)
        text = "🎞 <b>Видео-референсы</b>\n\nДобавь видео или нажми «Готово»."
        markup = video_references._done_kb(
            len(data.get("reference_video_urls") or []),
            video_references.video_reference_limits(key).get("max_refs", 1),
        )
    elif mode in {"image", "motion"}:
        await state.set_state(VideoGenFSM.image_upload)
        if mode == "motion":
            await state.update_data(motion_step="person")
        text = "📎 <b>Референсы видео</b>\n\nЗагрузи фото для этой задачи."
        markup = video_back_kb()
        if data.get("image_file_id") or data.get("ref_file_ids") or data.get("image_url"):
            text += "\nУже загруженные референсы сохранены. Можно продолжить с ними."
            markup.inline_keyboard.insert(
                0,
                [
                    InlineKeyboardButton(
                        text="✅ Продолжить с референсами", callback_data="vid_nav:params"
                    )
                ],
            )
    else:
        return False
    await safe_edit_message(call.message, text, reply_markup=markup)
    await safe_answer_callback(call)
    return True


@router.callback_query(VideoGenFSM.image_upload, F.data == "vid_nav:video")
async def continue_to_video(call: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    if not (data.get("image_file_id") or data.get("ref_file_ids") or data.get("image_url")):
        await safe_answer_callback(call, "Сначала загрузи фото", show_alert=True)
        return
    await show_references(call, state, session)


@router.callback_query(VideoGenFSM.image_upload, F.data == "vid_nav:params")
async def continue_with_references(call: CallbackQuery, state: FSMContext) -> None:
    from bot.handlers.video_gen import GENJUTSU_MODEL_KEYS

    data = await state.get_data()
    if not (data.get("image_file_id") or data.get("ref_file_ids") or data.get("image_url")):
        await safe_answer_callback(call, "Сначала загрузи фото", show_alert=True)
        return
    two_step = (
        data.get("mode") == "motion"
        or data.get("seedance_identity_transfer")
        or data.get("model_key") in GENJUTSU_MODEL_KEYS
    )
    if two_step and not data.get("reference_video_url"):
        await safe_answer_callback(
            call, "Для управления движением нужно также видео", show_alert=True
        )
        return
    if data.get("mode") == "motion":
        await state.update_data(motion_step="prompt")
    if data.get("seedance_identity_transfer"):
        await state.update_data(seedance_identity_step=None)
    if data.get("model_key") in GENJUTSU_MODEL_KEYS:
        await state.update_data(genjutsu_step=None)
    await show_params(call, state)


@router.callback_query(StateFilter(VideoGenFSM), F.data == "vid_nav:back")
@router.callback_query(VideoGenFSM.params_select, F.data == "vpar_back")
async def back_in_video(
    call: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    data = await state.get_data()
    current = await state.get_state()
    key = data.get("model_key")
    if not key:
        await back_to_models(call, state, session)
        return
    if current == VideoGenFSM.generating.state:
        await safe_answer_callback(call, "Генерация уже запущена", show_alert=True)
        return
    if current == VideoGenFSM.image_upload.state and (
        data.get("motion_step") == "video_url"
        or data.get("genjutsu_step") == "video"
        or data.get("seedance_identity_step") == "video"
    ):
        await show_references(call, state, session, photos=True)
        return
    if data.get("video_review_edit") and data.get("review_prompt"):
        from bot.handlers.video_wizard import show_video_review

        await show_video_review(
            call.message, state, session, db_user, data["review_prompt"], edit=True
        )
        await safe_answer_callback(call)
        return
    if current in {VideoGenFSM.prompt_input.state, VideoGenFSM.omni_ids_input.state}:
        await show_params(call, state)
        return
    if current == VideoGenFSM.params_select.state:
        if await show_references(call, state, session):
            return
    if data.get("feed_force_reference") or data.get("wizard_mode") or len(VIDEO_CAPS.get(key, {}).get("modes", [])) < 2:
        await back_to_models(call, state, session)
        return
    await state.set_state(VideoGenFSM.mode_select)
    await safe_edit_message(
        call.message, "🎬 <b>Выбери режим видео</b>", reply_markup=video_mode_kb(key)
    )
    await safe_answer_callback(call)
