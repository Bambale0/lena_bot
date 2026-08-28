from __future__ import annotations

import hashlib
import logging
import secrets
import time
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from core.config import settings

logger = logging.getLogger(__name__)
_shared_redis_client: Any | None = None


class RateLimiterUnavailable(RuntimeError):
    """Raised when the durable rate-limit backend cannot be reached."""


def _redis_client():
    global _shared_redis_client
    if _shared_redis_client is None:
        _shared_redis_client = aioredis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
            health_check_interval=30,
            max_connections=20,
        )
    return _shared_redis_client


class RedisEventRateLimiter:
    """Durable sliding-window event limiter backed by a Redis sorted set."""

    def __init__(
        self,
        *,
        namespace: str,
        window_seconds: int,
        max_events: int,
        redis_client: Any | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.namespace = str(namespace or "rate-limit").strip(":")
        self.window_seconds = max(1, int(window_seconds))
        self.max_events = max(1, int(max_events))
        self._redis = redis_client
        self._clock = clock

    def _client(self):
        return self._redis if self._redis is not None else _redis_client()

    def _key(self, subject: str) -> str:
        normalized = str(subject or "").strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        env = str(getattr(settings, "ENV", "") or "development").strip().lower()
        return f"apix:{self.namespace}:{env}:{digest}"

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)

    async def retry_after(self, subject: str) -> int:
        key = self._key(subject)
        now_ms = self._now_ms()
        window_ms = self.window_seconds * 1000
        cutoff_ms = now_ms - window_ms

        try:
            pipe = self._client().pipeline(transaction=True)
            pipe.zremrangebyscore(key, 0, cutoff_ms)
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            pipe.pexpire(key, window_ms)
            _, count, oldest, _ = await pipe.execute()
        except RedisError as exc:
            logger.error("Redis rate limiter unavailable namespace=%s: %s", self.namespace, exc)
            raise RateLimiterUnavailable("Rate limiter backend unavailable") from exc

        if int(count or 0) < self.max_events or not oldest:
            return 0

        oldest_score = float(oldest[0][1])
        remaining_ms = max(1, int(window_ms - (now_ms - oldest_score)))
        return max(1, (remaining_ms + 999) // 1000)

    async def record(self, subject: str) -> None:
        key = self._key(subject)
        now_ms = self._now_ms()
        window_ms = self.window_seconds * 1000
        cutoff_ms = now_ms - window_ms
        member = f"{now_ms}:{secrets.token_hex(8)}"

        try:
            pipe = self._client().pipeline(transaction=True)
            pipe.zremrangebyscore(key, 0, cutoff_ms)
            pipe.zadd(key, {member: now_ms})
            pipe.pexpire(key, window_ms)
            await pipe.execute()
        except RedisError as exc:
            logger.error(
                "Redis rate limiter unavailable while recording namespace=%s: %s",
                self.namespace,
                exc,
            )
            raise RateLimiterUnavailable("Rate limiter backend unavailable") from exc

    async def clear(self, subject: str) -> None:
        try:
            await self._client().delete(self._key(subject))
        except RedisError as exc:
            logger.error(
                "Redis rate limiter unavailable while clearing namespace=%s: %s",
                self.namespace,
                exc,
            )
            raise RateLimiterUnavailable("Rate limiter backend unavailable") from exc


class RedisPasswordRateLimiter(RedisEventRateLimiter):
    """Failed-password limiter preserving the existing auth-specific interface."""

    def __init__(
        self,
        *,
        window_seconds: int,
        max_failures: int,
        redis_client: Any | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        super().__init__(
            namespace="auth:password-failures",
            window_seconds=window_seconds,
            max_events=max_failures,
            redis_client=redis_client,
            clock=clock,
        )

    async def record_failure(self, login: str) -> None:
        await self.record(login)
