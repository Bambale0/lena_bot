# api/polling.py
"""
Асинхронный polling задач провайдеров.
Запускает фоновую корутину, которая периодически проверяет статус
и вызывает callback при завершении или ошибке.

Бюджет ожидания можно задать явно (interval/timeout) или через provider:
провайдеры с длинным рендером (Higgsfield Genjutsu) получают собственный
бюджет из настроек, остальные используют общие POLLING_INTERVAL/POLLING_TIMEOUT.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from core.config import settings

logger = logging.getLogger(__name__)

# provider -> (interval setting name, timeout setting name)
_PROVIDER_POLL_BUDGETS: dict[str, tuple[str, str]] = {
    "higgsfield": (
        "HIGGSFIELD_POLL_INTERVAL_SECONDS",
        "HIGGSFIELD_POLL_TIMEOUT_SECONDS",
    ),
}

_MIN_INTERVAL_SECONDS = 0.5
_MIN_TIMEOUT_SECONDS = 30


def poll_budget(provider: str | None = None) -> tuple[float, int]:
    """Вернуть (interval, timeout) для провайдера задачи.

    Неизвестный/пустой провайдер использует общие настройки polling.
    Значения читаются на каждом вызове, поэтому настройки остаются
    управляемыми через окружение без правок кода.
    """
    budget = _PROVIDER_POLL_BUDGETS.get(str(provider or "").strip())
    if budget is None:
        return (
            max(_MIN_INTERVAL_SECONDS, float(settings.POLLING_INTERVAL)),
            max(_MIN_TIMEOUT_SECONDS, int(settings.POLLING_TIMEOUT)),
        )
    interval_attr, timeout_attr = budget
    return (
        max(_MIN_INTERVAL_SECONDS, float(getattr(settings, interval_attr))),
        max(_MIN_TIMEOUT_SECONDS, int(getattr(settings, timeout_attr))),
    )


async def poll_until_done(
    task_id: str,
    check_fn: Callable[[str], Awaitable[str | None]],
    on_success: Callable[[str], Awaitable[None]],
    on_failure: Callable[[str], Awaitable[None]],
    interval: float | None = None,
    timeout: int | None = None,
    provider: str | None = None,
) -> None:
    """
    check_fn(task_id) -> url | None  (None = still processing, raises = error)
    on_success(url)
    on_failure(error_msg)
    """
    if interval is None or timeout is None:
        budget_interval, budget_timeout = poll_budget(provider)
        if interval is None:
            interval = budget_interval
        if timeout is None:
            timeout = budget_timeout

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

    logger.warning(
        "Polling timed out task=%s provider=%s timeout=%.0fs interval=%.1fs",
        task_id,
        provider or "default",
        timeout,
        interval,
    )
    await on_failure("Время ожидания истекло. Попробуй снова.")

