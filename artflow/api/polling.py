# api/polling.py
"""
Асинхронный polling CometAPI задач.
Запускает фоновую корутину, которая периодически проверяет статус
и вызывает callback при завершении или ошибке.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from core.config import settings

logger = logging.getLogger(__name__)


async def poll_until_done(
    task_id: str,
    check_fn: Callable[[str], Awaitable[str | None]],
    on_success: Callable[[str], Awaitable[None]],
    on_failure: Callable[[str], Awaitable[None]],
    interval: float = settings.POLLING_INTERVAL,
    timeout: int = settings.POLLING_TIMEOUT,
) -> None:
    """
    check_fn(task_id) -> url | None  (None = still processing, raises = error)
    on_success(url)
    on_failure(error_msg)
    """
    elapsed = 0.0
    while elapsed < timeout:
        try:
            result = await check_fn(task_id)
            if result is not None:
                await on_success(result)
                return
        except Exception as e:
            logger.error("Polling error for task %s: %s", task_id, e)
            await on_failure(str(e))
            return
        await asyncio.sleep(interval)
        elapsed += interval

    await on_failure("Время ожидания истекло. Попробуй снова.")
