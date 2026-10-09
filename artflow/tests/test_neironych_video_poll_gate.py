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
        self.renewals = 0

    async def set(self, key, token, *, nx, ex):
        assert nx is True and ex > 240
        if key in self.entries:
            return None
        self.entries[key] = token
        return True

    async def eval(self, script, key_count, key, token, *args):
        assert key_count == 1
        if self.entries.get(key) != token:
            return 0
        if "EXPIRE" in script or "PEXPIRE" in script:
            self.renewals += 1
            return 1
        del self.entries[key]
        return 1

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


@pytest.mark.asyncio
async def test_bot_neironych_uses_durable_scheduler_not_foreground_timeout(monkeypatch):
    from bot.handlers import video_gen

    foreground = AsyncMock()
    monkeypatch.setattr(video_gen.polling, "poll_until_done", foreground)
    video_gen._start_video_polling(
        SimpleNamespace(provider="neironych", task_id="neironych:task"),
        AsyncMock(), AsyncMock(), AsyncMock(),
    )
    await asyncio.sleep(0)
    foreground.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_non_neironych_foreground_poll_is_unchanged(monkeypatch):
    from bot.handlers import video_gen

    foreground = AsyncMock()
    monkeypatch.setattr(video_gen.polling, "poll_until_done", foreground)
    video_gen._start_video_polling(
        SimpleNamespace(provider="higgsfield", task_id="hf-task"),
        AsyncMock(), AsyncMock(), AsyncMock(),
    )
    await asyncio.sleep(0.01)
    foreground.assert_awaited_once()


@pytest.mark.asyncio
async def test_lease_heartbeats_during_slow_storage_settlement(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(gate.aioredis.Redis, "from_url", lambda *a, **kw: fake)
    monkeypatch.setattr(gate, "_poll_heartbeat_interval_seconds", lambda: 0.01, raising=False)
    async with gate.neironych_video_poll_guard("neironych:slow-settlement") as acquired:
        assert acquired
        await asyncio.sleep(0.06)
        assert fake.renewals >= 2, "Lease must be extended while provider/DB work continues"
    assert not fake.entries


@pytest.mark.asyncio
async def test_lost_poll_lease_cancels_owner_before_more_provider_calls(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(gate.aioredis.Redis, "from_url", lambda *a, **kw: fake)
    monkeypatch.setattr(gate, "_poll_heartbeat_interval_seconds", lambda: 0.01, raising=False)
    ready = asyncio.Event()

    async def poll_owner():
        async with gate.neironych_video_poll_guard("neironych:interrupted") as acquired:
            assert acquired
            ready.set()
            await asyncio.sleep(1)

    owner = asyncio.create_task(poll_owner())
    await asyncio.wait_for(ready.wait(), 0.5)
    key = next(iter(fake.entries))
    fake.entries[key] = "new-owner-token"
    with pytest.raises(gate.NeironychVideoPollLeaseLost):
        await asyncio.wait_for(owner, 0.3)
    assert fake.entries[key] == "new-owner-token", "Old owner must not delete new lease"


@pytest.mark.asyncio
async def test_lost_poll_lease_during_post_commit_settlement_does_not_cancel(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(gate.aioredis.Redis, "from_url", lambda *args, **kwargs: fake)
    monkeypatch.setattr(gate, "_poll_heartbeat_interval_seconds", lambda: 0.01)
    settled = asyncio.Event()

    async def critical_work():
        async with gate.neironych_video_poll_guard("neironych:royalty") as acquired:
            assert acquired
            gate.protect_neironych_video_poll_settlement()
            settled.set()
            await asyncio.sleep(0.06)  # Simulate slow post-commit royalty settlement.
            return "royalties_recorded"

    owner = asyncio.create_task(critical_work())
    await asyncio.wait_for(settled.wait(), timeout=1)
    key = next(iter(fake.entries))
    fake.entries[key] = "successor-owner"
    result = await asyncio.wait_for(owner, 0.3)
    assert result == "royalties_recorded", "Redis lease loss cannot abort settled money effects"
    assert fake.entries[key] == "successor-owner"
