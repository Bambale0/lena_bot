"""Public menu entries terminate abandoned input flows before rendering."""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message

from bot.utils.telegram_ui import safe_answer_callback

logger = logging.getLogger(__name__)

PUBLIC_MENU_ENTRIES = frozenset(
    {
        "menu:main",
        "menu:create",
        "menu:more",
        "menu:settings",
        "menu:help",
        "menu:image",
        "menu:video",
        "menu:music",
        "menu:assistant",
        "menu:mj",
        "menu:feed",
        "menu:top_day",
        "menu:history",
        "menu:prompts",
        "menu:trends",
        "menu:pinterest",
        "menu:topup",
        "menu:balance",
        "menu:referral",
        "menu:genjutsu",
    }
)


class NavigationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery | Message,
        data: dict[str, Any],
    ) -> Any:
        state = data.get("state")
        entry = (
            event.data
            if isinstance(event, CallbackQuery)
            else (event.text or "").split(" ", 1)[0].split("@", 1)[0]
        )
        if state is not None and entry in PUBLIC_MENU_ENTRIES | {
            "/help",
            "/starshelp",
            "/assistant",
        }:
            previous = await state.get_state()
            await state.clear()
            data["raw_state"] = None
            logger.debug("Navigation entry=%s previous_state=%s", entry, previous)
        elif (
            state is not None
            and isinstance(event, CallbackQuery)
            and (entry or "").startswith("vid_mode:")
        ):
            current_data = await state.get_data()
            if entry.split(":", 2)[-1] != current_data.get("model_key"):
                await safe_answer_callback(
                    event, "Эта кнопка от другой задачи. Используй текущее меню.", show_alert=True
                )
                return None
        if (
            state is not None
            and isinstance(event, CallbackQuery)
            and (entry or "").startswith("vid_model:")
        ):
            from bot.handlers.video_wizard import supports_scenario

            current_data = await state.get_data()
            mode = current_data.get("wizard_mode")
            if mode and not supports_scenario(entry.split(":", 1)[-1], mode):
                await safe_answer_callback(
                    event, "Эта модель не подходит для выбранной задачи.", show_alert=True
                )
                return None
        return await handler(event, data)
