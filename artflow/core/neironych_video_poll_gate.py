"""Redis-backed lease to deduplicate Neironych video polling and downloads.

The lease covers provider GET, media download and DB settlement but never
submits another paid POST. Redis outages fail closed; they cannot refund credits.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from contextlib import asynccontextmanager, suppress

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from core.config import settings

logger = logging.getLogger(__name__)


class NeironychVideoPollLeaseLost(RuntimeError):
    """Redis lease lost during a poll; caller must defer without refund."""


_UNLOCK_IF_OWNED = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


_RENEW_IF_OWNED = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[2]))
end
return 0
"""


def _poll_heartbeat_interval_seconds() -> float:
    return max(1.0, settings.NEIRONYCH_VIDEO_POLL_LEASE_SECONDS / 3.0)


async def _renew_poll_lease(
    client, key: str, token: str, owner: asyncio.Task, lease_lost: asyncio.Event,
) -> None:
    """Keep the lease alive throughout provider download AND DB settlement.

    If ownership is lost or Redis cannot renew it, cancel the owning task
    before it can continue doing more work under an expired lease.
    """
    try:
        while True:
            await asyncio.sleep(_poll_heartbeat_interval_seconds())
            refreshed = await client.eval(
                _RENEW_IF_OWNED, 1, key, token,
                settings.NEIRONYCH_VIDEO_POLL_LEASE_SECONDS,
            )
            if int(refreshed or 0) != 1:
                logger.error("Neironych video poll lease ownership lost; aborting owner")
                lease_lost.set()
                owner.cancel()
                return
    except asyncio.CancelledError:
        raise
    except (RedisError, OSError, ValueError) as exc:
        logger.error(
            "Neironych video poll lease renewal failed; aborting owner error=%s",
            type(exc).__name__,
        )
        lease_lost.set()
        owner.cancel()


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
    renewal_task: asyncio.Task | None = None
    lease_lost = asyncio.Event()
    try:
        try:
            acquired = bool(await client.set(
                key, claim, nx=True, ex=settings.NEIRONYCH_VIDEO_POLL_LEASE_SECONDS
            ))
        except RedisError as exc:
            logger.warning(
                "Neironych video poll gate unavailable error=%s", type(exc).__name__
            )
        if acquired:
            owner = asyncio.current_task()
            if owner is None:
                raise RuntimeError("Neironych poll lease requires an asyncio task")
            renewal_task = asyncio.create_task(
                _renew_poll_lease(client, key, claim, owner, lease_lost)
            )
        try:
            yield acquired
        except asyncio.CancelledError:
            if lease_lost.is_set():
                # Distinguish a lost Redis lease from an application shutdown;
                # one bad item must not cancel the whole scheduler task.
                raise NeironychVideoPollLeaseLost("Poll ownership lost") from None
            raise
    finally:
        if renewal_task is not None:
            renewal_task.cancel()
            with suppress(asyncio.CancelledError):
                await renewal_task
        if acquired:
            try:
                await client.eval(_UNLOCK_IF_OWNED, 1, key, claim)
            except RedisError as exc:
                logger.warning(
                    "Neironych video poll gate cleanup deferred error=%s",
                    type(exc).__name__,
                )
        await client.aclose()
