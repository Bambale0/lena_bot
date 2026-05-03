# run_polling.py
"""
Локальный запуск бота в режиме polling.
Используется только для разработки и тестирования.
Webhook не нужен.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from api.comet_client import close_client, get_client
from bot.handlers import admin, balance, image_gen, marketplace, payment, start, video_gen
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from core.config import settings
from core.logger import setup_logging
from db.session import engine
from db.models import Base
from db.seed import run_seed


async def _make_storage() -> tuple[BaseStorage, object | None]:
    """
    Пробуем Redis; если недоступен — MemoryStorage.
    Возвращает (storage, redis_client | None).
    """
    logger = logging.getLogger(__name__)
    try:
        import redis.asyncio as aioredis
        from aiogram.fsm.storage.redis import RedisStorage

        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await asyncio.wait_for(redis_client.ping(), timeout=2.0)
        logger.info("FSM storage: Redis (%s)", settings.REDIS_URL)
        return RedisStorage(redis=redis_client), redis_client
    except Exception as e:
        logger.warning(
            "Redis недоступен (%s) → MemoryStorage "
            "(FSM сбрасывается при перезапуске, для прода нужен Redis)",
            e,
        )
        return MemoryStorage(), None


async def _make_throttling_middleware(redis_client: object | None):
    """ThrottlingMiddleware без Redis просто пропускает всё."""
    if redis_client is not None:
        return ThrottlingMiddleware(redis_client)

    # Заглушка — не throttlит, но и не падает
    from aiogram import BaseMiddleware
    from aiogram.types import TelegramObject
    from typing import Any, Awaitable, Callable

    class NoopThrottle(BaseMiddleware):
        async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
        ) -> Any:
            return await handler(event, data)

    return NoopThrottle()


async def main() -> None:
    setup_logging(logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Starting ArtFlow AI in POLLING mode")

    storage, redis_client = await _make_storage()

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(AuthMiddleware())
    dp.message.middleware(await _make_throttling_middleware(redis_client))

    # Routers
    dp.include_router(start.router)
    dp.include_router(image_gen.router)
    dp.include_router(video_gen.router)
    dp.include_router(balance.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)
    dp.include_router(marketplace.router)
    dp.include_router(marketplace.mod_router)

    # DB tables (для prod используй alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await run_seed()
    await bot.delete_webhook(drop_pending_updates=True)
    get_client()
    logger.info("Bot started. Press Ctrl+C to stop.")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        await close_client()
        if redis_client:
            await redis_client.aclose()
        await engine.dispose()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
