from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.types import MenuButtonCommands

from main import _set_bot_commands


@pytest.mark.asyncio
async def test_set_bot_commands_resets_chat_menu_button_to_commands() -> None:
    bot = AsyncMock()

    await _set_bot_commands(bot)

    bot.set_my_commands.assert_awaited_once()
    bot.set_chat_menu_button.assert_awaited_once()
    assert isinstance(
        bot.set_chat_menu_button.await_args.kwargs["menu_button"],
        MenuButtonCommands,
    )
