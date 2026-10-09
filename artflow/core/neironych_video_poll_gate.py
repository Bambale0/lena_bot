"""Redis-backed lease to deduplicate Neironych video polling and downloads.

The lease covers provider GET, media download and DB settlement but never
submits another paid POST. Redis outages fail closed; they cannot refund credits.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from core.config import settings

logger = logging.getLogger(__name__)

_UNLOCK_IF_OWNED = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


@asynccontextmanager
async def neironych_video_poll_guard(task_id: str):
    env = str(settings.ENV or "development").strip().lower()
    key = (
        f"apix:neironych-video-poll:{env}:"
        + hashlib.sha256(str(task_id).encode("utf-8")).hexdigest()
    )
    claim = uuid.uuid4().hex
    client = aioredis.Redis.from_url(
        settings.REDIS_URL, decode_responses=True,
        socket_connect_timeout=1.5, socket_timeout=2.0,
        health_check_interval=30, max_connections=4,
    )
    acquired = False
    try:
        try:
            acquired = bool(await client.set(
                key, claim, nx=True, ex=settings.NEIRONYCH_VIDEO_POLL_LEASE_SECONDS
            ))
        except RedisError as exc:
            logger.warning(
                "Neironych video poll gate unavailable error=%s", type(exc).__name__
            )
        yield acquired
    finally:
        if acquired:
            try:
                await client.eval(_UNLOCK_IF_OWNED, 1, key, claim)
            except RedisError as exc:
                logger.warning(
                    "Neironych video poll gate cleanup deferred error=%s",
                    type(exc).__name__,
                )
        await client.aclose()
