from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.types import MenuButtonWebApp

from main import _set_bot_commands, _miniapp_entry_url


@pytest.mark.asyncio
async def test_set_bot_commands_sets_chat_menu_button_to_miniapp() -> None:
    bot = AsyncMock()

    await _set_bot_commands(bot)

    bot.set_my_commands.assert_awaited_once()
    bot.set_chat_menu_button.assert_awaited_once()
    menu_button = bot.set_chat_menu_button.await_args.kwargs["menu_button"]
    assert isinstance(menu_button, MenuButtonWebApp)
    assert menu_button.web_app.url == _miniapp_entry_url()
