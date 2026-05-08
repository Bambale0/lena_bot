
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_to_menu_kb
from bot.states import MusicFSM
from bot.ui.router import render_screen
from bot.utils.telegram_ui import safe_answer_callback
from db.models import User

from api.music_service import create_music_task, register_task

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
    screen = await render_screen(screen="music", session=session, db_user=db_user)
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
async def music_prompt(msg: Message, state: FSMContext):
    data = await state.get_data()

    await msg.answer("⏳ Генерирую...", reply_markup=back_to_menu_kb())

    try:
        task_id = await create_music_task(msg.text, data.get("instrumental", False))
        register_task(task_id, msg.from_user.id)  # type: ignore[union-attr]
        await msg.answer(
            "🎵 <b>Генерация запущена!</b>\n\nТрек придёт сюда автоматически (~1-2 мин).",
            reply_markup=back_to_menu_kb(),
        )
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

    await state.clear()
