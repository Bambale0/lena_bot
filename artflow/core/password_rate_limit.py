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


class RateLimiterUnavailable(RuntimeError):
    """Raised when the durable rate-limit backend cannot be reached."""


class RedisPasswordRateLimiter:
    """Sliding-window failed-login limiter backed by Redis sorted sets."""

    def __init__(
        self,
        *,
        window_seconds: int,
        max_failures: int,
        redis_client: Any | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.window_seconds = max(1, int(window_seconds))
        self.max_failures = max(1, int(max_failures))
        self._redis = redis_client
        self._clock = clock

    def _client(self):
        if self._redis is None:
            self._redis = aioredis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=1.0,
                socket_timeout=1.0,
                health_check_interval=30,
                max_connections=20,
            )
        return self._redis

    def _key(self, login: str) -> str:
        normalized = str(login or "").strip().lower()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        env = str(getattr(settings, "ENV", "") or "development").strip().lower()
        return f"apix:auth:password-failures:{env}:{digest}"

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)

    async def retry_after(self, login: str) -> int:
        key = self._key(login)
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
            logger.error("Password rate limiter Redis unavailable: %s", exc)
            raise RateLimiterUnavailable("Password rate limiter backend unavailable") from exc

        if int(count or 0) < self.max_failures:
            return 0
        if not oldest:
            return 0

        oldest_score = float(oldest[0][1])
        remaining_ms = max(1, int(window_ms - (now_ms - oldest_score)))
        return max(1, (remaining_ms + 999) // 1000)

    async def record_failure(self, login: str) -> None:
        key = self._key(login)
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
            logger.error("Password rate limiter Redis unavailable while recording failure: %s", exc)
            raise RateLimiterUnavailable("Password rate limiter backend unavailable") from exc

    async def clear(self, login: str) -> None:
        try:
            await self._client().delete(self._key(login))
        except RedisError as exc:
            logger.error("Password rate limiter Redis unavailable while clearing failures: %s", exc)
            raise RateLimiterUnavailable("Password rate limiter backend unavailable") from exc
