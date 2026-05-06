from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import CallbackQuery, Chat, Message, Update, User


def make_user(
    user_id: int = 123456,
    username: str = "testuser",
    first_name: str = "Test",
    is_bot: bool = False,
) -> User:
    return User(
        id=user_id,
        is_bot=is_bot,
        first_name=first_name,
        username=username,
        language_code="ru",
    )


def make_chat(chat_id: int = 123456, chat_type: str = "private") -> Chat:
    return Chat(id=chat_id, type=chat_type)


def make_message(
    text: str = "/start",
    user_id: int = 123456,
    chat_id: int = 123456,
    bot: AsyncMock | None = None,
) -> Message:
    msg = MagicMock(spec=Message)
    msg.message_id = 1001
    msg.from_user = make_user(user_id=user_id)
    msg.chat = make_chat(chat_id=chat_id)
    msg.text = text
    msg.date = datetime.now()
    msg.bot = bot or AsyncMock()
    msg.photo = None
    msg.answer = AsyncMock()
    msg.reply = AsyncMock()
    msg.edit_text = AsyncMock()
    msg.edit_caption = AsyncMock()
    msg.edit_media = AsyncMock()
    msg.delete = AsyncMock()
    msg.answer_photo = AsyncMock()
    return msg


def make_callback(
    data: str = "menu:main",
    user_id: int = 123456,
    message_text: str = "Menu",
    bot: AsyncMock | None = None,
) -> CallbackQuery:
    cb = MagicMock(spec=CallbackQuery)
    cb.id = "callback-id"
    cb.from_user = make_user(user_id=user_id)
    cb.data = data
    cb.message = make_message(text=message_text, user_id=user_id, bot=bot)
    cb.bot = bot or AsyncMock()
    cb.answer = AsyncMock()
    return cb


def make_update_with_start_payload(payload: str) -> Update:
    return SimpleNamespace(message=SimpleNamespace(text=f"/start {payload}"))
