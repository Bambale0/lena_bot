"""Deadline-based per-task timeout for Seedance, independent from provider routing."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from core import neironych_video_reconcile_scheduler as scheduler
from core.config import settings
from db.models import GenerationStatus, GenerationType


def _generation(*, age_seconds=3900, status=GenerationStatus.processing,
                task_id="neironych:source-uuid", gen_id=9001):
    return SimpleNamespace(
        id=gen_id, user_id=42, model="bytedance/seedance-2-5",
        gen_type=GenerationType.video, status=status, task_id=task_id,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        credits_spent=70.0,
    )


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    commit = AsyncMock()
    rollback = AsyncMock()


def test_video_auto_timeout_has_explicit_sixty_minute_default():
    assert settings.SEEDANCE_AUTO_REFUND_SECONDS == 3600


def test_timeout_query_is_explicitly_neironych_only_and_checks_deadline():
    query = scheduler._expired_seedance_query()
    compiled = query.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    values = list(compiled.params.values())
    assert "generations.created_at <=" in sql
    assert "generations.status IN" in sql
    assert "generations.task_id LIKE" in sql
    assert "neironych:%" in values
    assert "neironych-submit:%" in values
    assert "bytedance/seedance-2-5" in str(values) or "bytedance/seedance-2-5" in str(sql)


@pytest.mark.asyncio
async def test_expired_job_gets_final_read_only_poll_then_atomic_refund(monkeypatch):
    gen = _generation()
    result = AsyncMock(return_value=True)
    refunds = AsyncMock(return_value=(True, 70.0))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", result)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    result.assert_awaited_once_with(gen.id)
    assert refunds.await_args.args[1:3] == (gen.id, "Видео не удалось создать вовремя.")
    assert refunds.await_args.kwargs["expected_task_id"] == gen.task_id
    assert refunds.await_args.kwargs["video_notice_kind"] == "failed"
    assert "timeout" in refunds.await_args.kwargs["refund_note"]


@pytest.mark.asyncio
async def test_expiry_does_not_refund_video_completed_by_final_poll(monkeypatch):
    gen = _generation()

    async def complete(_id):
        gen.status = GenerationStatus.done
        return True

    refunds = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", complete)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_skips_newer_and_unrelated_provider_jobs(monkeypatch):
    refunds = AsyncMock()
    polls = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", polls)
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    for gen in (_generation(age_seconds=300), _generation(task_id="kie123")):
        monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
        assert not await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_not_awaited()
    polls.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_covers_unbound_submission_without_paid_retry(monkeypatch):
    gen = _generation(task_id="neironych-submit:pending-uuid")
    refunds = AsyncMock(return_value=(True, 70.0))
    polls = AsyncMock(return_value=False)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", polls)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    assert refunds.await_args.kwargs["video_notice_kind"] == "failed"


@pytest.mark.asyncio
async def test_expiry_refunds_if_redis_poll_intent_is_broken(monkeypatch):
    gen = _generation()
    refunds = AsyncMock(return_value=(True, 70.0))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video",
                        AsyncMock(side_effect=ConnectionError("redis unavailable")))
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_awaited_once()


@pytest.mark.asyncio
async def test_expiry_can_be_retried_without_duplicate_notice(monkeypatch):
    gen = _generation()
    refunds = AsyncMock(side_effect=[(True, 70.0), (False, 0.0)])
    enqueue = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    monkeypatch.setattr(scheduler, "_track_active_video_notice_intent", enqueue)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    assert refunds.await_count == 2
    assert enqueue.await_count == 1


@pytest.mark.asyncio
async def test_scheduler_expires_stuck_jobs_before_loading_redis_notices(monkeypatch):
    events = []
    monkeypatch.setattr(scheduler, "_load_expired_seedance_batch", AsyncMock(return_value=[56773]))
    monkeypatch.setattr(scheduler, "_load_batch", AsyncMock(return_value=[]))
    monkeypatch.setattr(scheduler, "_load_notice_batch", AsyncMock(side_effect=ConnectionError("redis down")))

    async def expire(_id):
        events.append("expire")
        return True

    monkeypatch.setattr(scheduler, "_expire_stuck_seedance_video", expire)
    with pytest.raises(ConnectionError):
        await scheduler.reconcile_neironych_videos_once()
    assert events == ["expire"]


def test_timeout_notice_query_includes_unbound_submission_ids():
    compiled = scheduler._eligible_notice_query().compile(dialect=postgresql.dialect())
    assert "neironych-submit:%" in str(list(compiled.params.values()))


@pytest.mark.asyncio
async def test_web_timeout_never_queues_telegram_notice(monkeypatch):
    gen = _generation(task_id="web:neironych:uuid")
    refunds = AsyncMock(return_value=(True,70.0))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    assert refunds.await_args.kwargs["video_notice_kind"] is None



@pytest.mark.asyncio
async def test_provider_identity_change_during_final_poll_defers_refund(monkeypatch):
    gen = _generation()
    original = gen.task_id

    async def provider_bound_new_identity(_id):
        gen.task_id = "neironych:bound-after-lookup"
        return True

    refunds = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", provider_bound_new_identity)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    assert gen.task_id != original
    refunds.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_defers_without_notice_when_refund_loses_callback_race(monkeypatch):
    gen = _generation()
    refunds = AsyncMock(return_value=(False, 0.0))
    enqueue = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    monkeypatch.setattr(scheduler, "_track_active_video_notice_intent", enqueue)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    enqueue.assert_not_awaited()


def test_timeout_config_rejects_too_short_or_unbounded_value():
    from pydantic import ValidationError

    from core.config import Settings

    for bad in (20, 1799, 86401):
        with pytest.raises(ValidationError):
            Settings(
                _env_file=None,
                BOT_TOKEN="123456:unit",
                COMET_API_KEY="unit",
                SEEDANCE_AUTO_REFUND_SECONDS=bad,
            )

@pytest.mark.asyncio
async def test_http_503_before_deadline_remains_waiting(monkeypatch):
    gen = _generation(age_seconds=200)
    refunds = AsyncMock()
    polls = AsyncMock(side_effect=RuntimeError("Neironych status HTTP 503"))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", polls)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_not_awaited()
    polls.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_503_after_deadline_fails_once_and_refunds(monkeypatch):
    gen = _generation(age_seconds=3900)
    refunds = AsyncMock(return_value=(True, 70.0))
    polls = AsyncMock(side_effect=RuntimeError("Neironych status HTTP 503"))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", polls)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_awaited_once()
    polls.assert_awaited_once()


@pytest.mark.asyncio
async def test_timed_out_pending_response_does_not_wait_forever(monkeypatch):
    gen = _generation(age_seconds=3900)
    refunds = AsyncMock(return_value=(True, 70.0))
    polls = AsyncMock(return_value=True)  # GET reported pending; no terminal result
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", polls)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_awaited_once()


@pytest.mark.asyncio
async def test_refund_succeeds_even_if_telegram_redis_intent_fails(monkeypatch):
    gen = _generation(age_seconds=3900)
    refunds = AsyncMock(return_value=(True, 70.0))
    redis = AsyncMock(side_effect=ConnectionError("Redis down"))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_process_active_video", AsyncMock(return_value=False))
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    monkeypatch.setattr(scheduler, "_track_active_video_notice_intent", redis)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_awaited_once()
    redis.assert_awaited_once()
