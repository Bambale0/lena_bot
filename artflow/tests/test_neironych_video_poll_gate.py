from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from api import miniapp_routes
from core import neironych_video_poll_gate as gate
from db.models import GenerationStatus, GenerationType


class FakeRedis:
    def __init__(self):
        self.entries: dict[str, str] = {}
        self.closes = 0

    async def set(self, key, token, *, nx, ex):
        assert nx is True and ex > 240
        if key in self.entries:
            return None
        self.entries[key] = token
        return True

    async def eval(self, script, key_count, key, token):
        assert key_count == 1
        if self.entries.get(key) == token:
            del self.entries[key]
            return 1
        return 0

    async def aclose(self):
        self.closes += 1


@pytest.mark.asyncio
async def test_poll_gate_single_winner_and_safe_unlock(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(gate.aioredis.Redis, "from_url", lambda *a, **k: fake)
    async with gate.neironych_video_poll_guard("neironych:task") as first:
        assert first
        async with gate.neironych_video_poll_guard("neironych:task") as second:
            assert not second
        assert len(fake.entries) == 1
    assert not fake.entries
    async with gate.neironych_video_poll_guard("neironych:task") as retry:
        assert retry
    assert fake.closes == 3


@pytest.mark.asyncio
async def test_poll_gate_fail_closed_when_redis_unavailable(monkeypatch):
    class BrokenRedis(FakeRedis):
        async def set(self, *args, **kwargs):
            raise RedisConnectionError("redis unavailable")
    monkeypatch.setattr(gate.aioredis.Redis, "from_url", lambda *a, **k: BrokenRedis())
    async with gate.neironych_video_poll_guard("neironych:task") as acquired:
        assert acquired is False


@pytest.mark.asyncio
async def test_two_concurrent_calls_use_one_provider_poll(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(gate.aioredis.Redis, "from_url", lambda *args, **kwargs: fake)
    monkeypatch.setattr(miniapp_routes, "neironych_video_poll_guard", gate.neironych_video_poll_guard)
    started = asyncio.Event()
    release = asyncio.Event()

    async def wait_for_provider(_id):
        started.set()
        await release.wait()
        return None

    poll = AsyncMock(side_effect=wait_for_provider)
    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda _: poll)
    gen = SimpleNamespace(
        id=55031, gen_type=GenerationType.video,
        model="bytedance/seedance-2-5", status=GenerationStatus.processing,
        task_id="neironych:task-id", created_at=datetime.now(timezone.utc),
    )
    first = asyncio.create_task(miniapp_routes._reconcile_generation_status(object(), gen))
    await asyncio.wait_for(started.wait(), 2)
    try:
        second = await asyncio.wait_for(
            miniapp_routes._reconcile_generation_status(object(), gen), 2
        )
        assert second is gen
        assert poll.await_count == 1
    finally:
        release.set()
        await first
    assert not fake.entries
