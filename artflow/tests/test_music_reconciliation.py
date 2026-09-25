from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from api import kieai_client, miniapp_routes, suno_full_service
from db.models import GenerationStatus, GenerationType


def _music_generation(*, status=GenerationStatus.processing, age_minutes=5):
    return SimpleNamespace(
        id=40721,
        user_id=372,
        model="suno/v5.5",
        gen_type=GenerationType.music,
        status=status,
        task_id="music-task",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
        image_session_id=None,
        result_url=None,
    )


@pytest.mark.asyncio
async def test_reconcile_music_terminal_failure_refunds_once(monkeypatch):
    gen = _music_generation(age_minutes=40_000)
    poll = AsyncMock(return_value={"data": {"state": "fail", "failMsg": "413 This audio matches an existing recording in our catalog"}})
    refund = AsyncMock(return_value=(True, 10.0))

    async def get_updated(_session, _gen_id):
        gen.status = GenerationStatus.failed
        return gen

    monkeypatch.setattr(kieai_client, "get_task_status", poll)
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", get_updated)
    result = await miniapp_routes._reconcile_generation_status(object(), gen)
    assert result.status == GenerationStatus.failed
    refund.assert_awaited_once_with(
        ANY,
        40721,
        "413 This audio matches an existing recording in our catalog",
        refund_note="reconcile:music_provider_failure",
    )
    assert poll.await_count == 1
    await miniapp_routes._reconcile_generation_status(object(), gen)
    refund.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_music_success_uses_suno_audio_url(monkeypatch):
    gen = _music_generation()
    monkeypatch.setattr(kieai_client, "get_task_status", AsyncMock(return_value={"data": {"state": "success"}}))
    monkeypatch.setattr(suno_full_service, "get_music_task", AsyncMock(return_value={"data": {"response": {"sunoData": [{"audio_url": "https://cdn.test/track.mp3"}]}}}))
    finish = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    await miniapp_routes._reconcile_generation_status(object(), gen)
    finish.assert_awaited_once_with(ANY, 40721, "https://cdn.test/track.mp3", result_urls=["https://cdn.test/track.mp3"])


@pytest.mark.asyncio
async def test_reconcile_music_processing_and_poll_error_do_not_refund(monkeypatch):
    gen = _music_generation()
    poll = AsyncMock(side_effect=[{"data": {"state": "processing"}}, TimeoutError("KIE unavailable")])
    refund = AsyncMock()
    monkeypatch.setattr(kieai_client, "get_task_status", poll)
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"code": 401, "msg": "Unauthorized"},
    {"data": {"state": "mystery"}},
    {"data": {"state": "success"}},
])
async def test_reconcile_music_ambiguous_old_task_remains_active(monkeypatch, payload):
    gen = _music_generation(age_minutes=40_000)
    refund = AsyncMock()
    monkeypatch.setattr(kieai_client, "get_task_status", AsyncMock(return_value=payload))
    monkeypatch.setattr(suno_full_service, "get_music_task", AsyncMock(return_value={"data": {"response": {"sunoData": []}}}))
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_music_reconcile_job_scans_active_generations(monkeypatch):
    from core import music_reconcile_scheduler

    gen = _music_generation(age_minutes=10)
    called = []

    class FakeSession:
        async def execute(self, _query):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [gen]))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    async def reconcile(_session, row):
        called.append(row.id)

    monkeypatch.setattr(music_reconcile_scheduler, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(music_reconcile_scheduler, "_reconcile_generation_status", reconcile)
    assert await music_reconcile_scheduler.reconcile_active_music_once() == 1
    assert called == [40721]
