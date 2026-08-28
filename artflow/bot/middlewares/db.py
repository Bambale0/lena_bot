# bot/middlewares/db.py
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from core.request_identity import clear_current_user, reset_current_user
from db.session import AsyncSessionLocal


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        identity_token = clear_current_user()
        try:
            async with AsyncSessionLocal() as session:
                data["session"] = session
                try:
                    return await handler(event, data)
                except Exception:
                    await session.rollback()
                    raise
        finally:
            reset_current_user(identity_token)
