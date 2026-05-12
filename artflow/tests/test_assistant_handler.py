from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import assistant
from tests.factories import make_message


@pytest.mark.asyncio
async def test_handle_assistant_message_uses_plain_assistant_for_non_admin(monkeypatch) -> None:
    message = make_message(text="Привет")
    wait_message = AsyncMock()
    wait_message.edit_text = AsyncMock()
    message.answer = AsyncMock(return_value=wait_message)

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"assistant_history": []})
    state.update_data = AsyncMock()

    db_user = SimpleNamespace(tg_id=123, id=7)
    session = AsyncMock()
    bot = AsyncMock()

    moderator_mock = AsyncMock(return_value=SimpleNamespace(text="admin-only"))
    reply_mock = AsyncMock(return_value="Обычный ответ")

    monkeypatch.setattr(assistant, "is_admin_tg_id", lambda _tg_id: False)
    monkeypatch.setattr(assistant, "try_handle_admin_request", moderator_mock)
    monkeypatch.setattr(assistant, "generate_assistant_reply", reply_mock)

    await assistant.handle_assistant_message(message, state, session, db_user, bot)

    moderator_mock.assert_not_awaited()
    reply_mock.assert_awaited_once()
    assert reply_mock.await_args.kwargs["admin_mode"] is False
    wait_message.edit_text.assert_awaited_once()

