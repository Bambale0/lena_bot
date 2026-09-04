# bot/middlewares/throttling.py
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from core.config import settings

logger = logging.getLogger(__name__)

THROTTLE_LIMIT = 1.5  # seconds between messages
_ADMIN_SET: frozenset[int] = frozenset(settings.ADMIN_IDS)


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis) -> None:  # type: ignore[type-arg]
        self.redis = redis

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        user_id = event.from_user.id if event.from_user else None
        if not user_id:
            return await handler(event, data)

        if user_id in _ADMIN_SET:
            return await handler(event, data)

        key = f"throttle:{user_id}"
        # Use millisecond TTL so the 1.5 second guard is enforced precisely.
        result = await self.redis.set(key, 1, px=int(THROTTLE_LIMIT * 1000), nx=True)
        if result is None:
            logger.debug("Throttled user %s", user_id)
            return  # молча игнорируем

        return await handler(event, data)
