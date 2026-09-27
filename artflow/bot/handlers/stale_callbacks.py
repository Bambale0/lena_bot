"""Last router: acknowledge expired screens without changing the active task."""

from aiogram import Router
from aiogram.types import CallbackQuery

from bot.utils.telegram_ui import safe_answer_callback

router = Router(name="stale_callbacks")


@router.callback_query()
async def expired_screen(call: CallbackQuery) -> None:
    await safe_answer_callback(
        call, "Этот экран устарел. Используй последнее меню или /menu.", show_alert=True
    )
