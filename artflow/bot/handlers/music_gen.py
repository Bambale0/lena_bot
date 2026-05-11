
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_to_menu_kb
from bot.states import MusicFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback
from db import repository as repo
from db.models import GenerationType, User

from api.music_service import create_music_task, register_miniapp_task, register_task

MUSIC_MODEL_KEY = "suno/v4.5"
DEFAULT_MUSIC_CREDITS = 20

router = Router(name="music_gen")


@router.callback_query(F.data == "menu:music")
async def music_menu(
    call: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
) -> None:
    await state.set_state(MusicFSM.prompt_input)
    await state.update_data(instrumental=False)
    model_cost = await repo.get_model_cost(session, MUSIC_MODEL_KEY)
    music_cost = float(model_cost.credits) if model_cost and getattr(model_cost, "is_active", True) else float(DEFAULT_MUSIC_CREDITS)
    screen = await render_screen(screen="music", session=session, db_user=db_user, extra={"music_cost": music_cost})
    await call.message.answer(  # type: ignore[union-attr]
        screen.text,
        reply_markup=screen.reply_markup,
    )
    await safe_answer_callback(call)


@router.callback_query(F.data.startswith("music:mode:"))
async def music_mode(call: CallbackQuery, state: FSMContext) -> None:
    mode = call.data.split(":")[-1]  # type: ignore[union-attr]
    await state.set_state(MusicFSM.prompt_input)
    await state.update_data(instrumental=(mode == "instrumental"))
    label = "без текста" if mode == "instrumental" else "с текстом"
    await call.message.answer(  # type: ignore[union-attr]
        f"🎵 Режим выбран: <b>{label}</b>\n\nТеперь напиши описание трека.",
        reply_markup=back_to_menu_kb(),
    )
    await safe_answer_callback(call)

@router.message(F.text == "🎵 Песня")
async def music_entry(msg: Message, state: FSMContext):
    await state.set_state(MusicFSM.prompt_input)
    await state.update_data(instrumental=False)
    await msg.answer("🎵 Напиши описание трека", reply_markup=back_to_menu_kb())

@router.message(MusicFSM.prompt_input, F.text)
async def music_prompt(msg: Message, state: FSMContext, session: AsyncSession, db_user: User):
    data = await state.get_data()
    model_cost = await repo.get_model_cost(session, MUSIC_MODEL_KEY)
    music_cost = float(model_cost.credits) if model_cost and getattr(model_cost, "is_active", True) else float(DEFAULT_MUSIC_CREDITS)

    if db_user.credits < music_cost:
        await msg.answer(
            f"😔 Недостаточно 💋 для музыки.\nНужно: <b>{music_cost:g}</b>, у тебя: <b>{db_user.credits:g}</b>",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    ok = await repo.spend_credits(session, db_user.id, music_cost)
    if not ok:
        await msg.answer(
            "😔 Не удалось списать 💋 для генерации. Попробуй ещё раз.",
            reply_markup=back_to_menu_kb(),
        )
        await state.clear()
        return

    gen = await repo.create_generation(
        session,
        db_user.id,
        MUSIC_MODEL_KEY,
        GenerationType.music,
        msg.text,
        music_cost,
    )

    await msg.answer("⏳ Генерирую...", reply_markup=back_to_menu_kb())

    try:
        task_id = await create_music_task(msg.text, data.get("instrumental", False))
        register_task(task_id, msg.from_user.id)  # type: ignore[union-attr]
        register_miniapp_task(task_id, gen.id)
        await repo.update_generation_task(session, gen.id, task_id)
        await msg.answer(
            "🎵 <b>Генерация запущена!</b>\n\nТрек придёт сюда автоматически (~1-2 мин).",
            reply_markup=back_to_menu_kb(),
        )
    except Exception as e:
        await repo.fail_generation(session, gen.id, str(e))
        await repo.add_credits(session, db_user.id, music_cost)
        await msg.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

    await state.clear()
