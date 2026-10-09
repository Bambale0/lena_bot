# run_polling.py
"""
Локальный запуск бота в режиме polling.
Используется только для разработки и тестирования.
Webhook не нужен.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage

from api.comet_client import close_client, get_client
from bot.handlers import (
    admin,
    balance,
    image_gen,
    marketplace,
    payment,
    stale_callbacks,
    start,
    video_gen,
)
from bot.middlewares.auth import AuthMiddleware
from bot.middlewares.db import DbSessionMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.utils.dispatcher import create_dispatcher
from core.config import settings
from core.logger import setup_logging
from core.neironych_video_reconcile_scheduler import run_neironych_video_reconcile_scheduler
from db import repository as repo
from db.referral_reward_policy import install_referral_reward_policy
from db.seed import run_seed

install_referral_reward_policy(repo)


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
    from typing import Any, Awaitable, Callable

    from aiogram import BaseMiddleware
    from aiogram.types import TelegramObject

    class NoopThrottle(BaseMiddleware):
        async def __call__(
            self,
            handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
            event: TelegramObject,
            data: dict[str, Any],
        ) -> Any:
            return await handler(event, data)

    return NoopThrottle()


def _require_neironych_recovery_redis(redis_client: object | None) -> None:
    """Fail closed: paid Neironych videos cannot recover in MemoryStorage mode."""
    if redis_client is None and settings.NEIRONYCH_API_KEY:
        raise RuntimeError(
            "Redis is required for Neironych Seedance video reconciliation in polling mode. "
            "The bot must not accept paid Seedance requests without its durable recovery worker."
        )


async def main() -> None:
    setup_logging(logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("Starting APIX in POLLING mode")

    storage, redis_client = await _make_storage()
    _require_neironych_recovery_redis(redis_client)

    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = create_dispatcher(storage)

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
    dp.include_router(stale_callbacks.router)

    await run_seed()
    await bot.delete_webhook(drop_pending_updates=True)
    get_client()
    video_reconcile_stop = asyncio.Event()
    video_reconcile_task = asyncio.create_task(
        run_neironych_video_reconcile_scheduler(video_reconcile_stop)
    )
    logger.info("Bot started. Press Ctrl+C to stop.")

    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
        )
    finally:
        video_reconcile_stop.set()
        try:
            await video_reconcile_task
        except Exception:
            logger.exception("Neironych video reconciliation scheduler shutdown failed")
        await close_client()
        if redis_client:
            await redis_client.aclose()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
