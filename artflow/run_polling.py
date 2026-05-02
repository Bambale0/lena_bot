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
from aiogram.fsm.storage.redis import RedisStorage

import redis.asyncio as aioredis

from api.comet_client import close_client, get_client
from bot.handlers import admin, balance, image_gen, payment, start, video_gen
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from core.config import settings
from core.logger import setup_logging
from db.session import engine
from db.models import Base


async def main() -> None:
    setup_logging(logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Starting ArtFlow AI in POLLING mode (local dev)")

    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    storage = RedisStorage(redis=redis_client)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.update.middleware(DbSessionMiddleware())
    dp.update.middleware(AuthMiddleware())
    dp.message.middleware(ThrottlingMiddleware(redis_client))

    # Routers
    dp.include_router(start.router)
    dp.include_router(image_gen.router)
    dp.include_router(video_gen.router)
    dp.include_router(balance.router)
    dp.include_router(payment.router)
    dp.include_router(admin.router)

    # DB tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Удаляем webhook если был
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
        await redis_client.aclose()
        await engine.dispose()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
