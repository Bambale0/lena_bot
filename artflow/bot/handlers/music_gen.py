
from aiogram import Router, F
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from api.music_service import create_music_task

router = Router()

@router.message(F.text == "🎵 Песня")
async def music_entry(msg: Message, state: FSMContext):
    await state.update_data(instrumental=False)
    await msg.answer("🎵 Напиши описание трека")

@router.message()
async def music_prompt(msg: Message, state: FSMContext):
    data = await state.get_data()

    if "instrumental" not in data:
        return

    await msg.answer("⏳ Генерирую...")

    try:
        task_id = await create_music_task(msg.text, data["instrumental"])
        await msg.answer(f"🎵 Запущено! ID: {task_id}")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")

    await state.clear()
