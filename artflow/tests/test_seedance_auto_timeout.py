"""Deadline-based per-task timeout for Seedance, independent from provider routing."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from core import neironych_video_reconcile_scheduler as scheduler
from core.config import settings
from db.models import GenerationStatus, GenerationType

_ORIGINAL_FINAL_STATUS = scheduler._final_neironych_provider_status


def _generation(*, age_seconds=3900, status=GenerationStatus.processing,
                task_id="neironych:source-uuid", gen_id=9001):
    return SimpleNamespace(
        id=gen_id, user_id=42, model="bytedance/seedance-2-5",
        gen_type=GenerationType.video, status=status, task_id=task_id,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
        credits_spent=70.0, input_params="{}",
    )


class _Session:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    commit = AsyncMock()
    rollback = AsyncMock()


@pytest.fixture(autouse=True)
def isolate_external_provider(monkeypatch):
    @asynccontextmanager
    async def lease(_id):
        yield True

    monkeypatch.setattr(scheduler, "neironych_video_poll_guard", lease)
    monkeypatch.setattr(
        scheduler, "_final_neironych_provider_status",
        AsyncMock(return_value=("pending", None)),
    )


def test_video_auto_timeout_has_explicit_sixty_minute_default():
    assert settings.SEEDANCE_AUTO_REFUND_SECONDS == 3600


def test_timeout_query_is_explicitly_neironych_only_and_checks_deadline():
    query = scheduler._expired_seedance_query()
    compiled = query.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    values = list(compiled.params.values())
    assert "coalesce" in sql.lower()
    assert "started_at" in str(values)
    assert "generations.status IN" in sql
    assert "generations.task_id LIKE" in sql
    assert "neironych:%" in values
    assert "neironych-submit:%" in values
    assert "bytedance/seedance-2-5" in str(values) or "bytedance/seedance-2-5" in str(sql)


@pytest.mark.asyncio
async def test_expired_job_gets_final_read_only_poll_then_atomic_refund(monkeypatch):
    gen = _generation()
    result = AsyncMock(return_value=("pending", None))
    refunds = AsyncMock(return_value=(True, 70.0))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", result)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    result.assert_awaited_once()
    assert result.await_args.args[0].task_id == gen.task_id
    assert result.await_args.args[0].input_params == {}
    assert refunds.await_args.kwargs["provider_review"]["state"] == "pending"
    assert refunds.await_args.args[1:3] == (gen.id, "Видео не удалось создать вовремя.")
    assert refunds.await_args.kwargs["expected_task_id"] == gen.task_id
    assert refunds.await_args.kwargs["video_notice_kind"] == "failed"
    assert "timeout" in refunds.await_args.kwargs["refund_note"]


@pytest.mark.asyncio
async def test_expiry_does_not_refund_video_completed_by_final_poll(monkeypatch):
    gen = _generation()

    async def complete(_gen):
        return ("done", None)

    refunds = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", complete)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_skips_newer_and_unrelated_provider_jobs(monkeypatch):
    refunds = AsyncMock()
    polls = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", polls)
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
    polls = AsyncMock(return_value=("unknown", None))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", polls)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    assert refunds.await_args.kwargs["video_notice_kind"] == "failed"


@pytest.mark.asyncio
async def test_expiry_waits_for_poll_lease_instead_of_refunding(monkeypatch):
    gen = _generation()
    refunds = AsyncMock()
    polls = AsyncMock()

    @asynccontextmanager
    async def busy(_task):
        yield False

    monkeypatch.setattr(scheduler, "neironych_video_poll_guard", busy)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", polls)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    polls.assert_not_awaited()
    refunds.assert_not_awaited()


@pytest.mark.asyncio
async def test_expiry_can_be_retried_without_duplicate_notice(monkeypatch):
    gen = _generation()
    refunds = AsyncMock(side_effect=[(True, 70.0), (False, 0.0)])
    enqueue = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", AsyncMock(return_value=("pending", None)))
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
    monkeypatch.setattr(scheduler, "_run_refund_supplier_review_lane", AsyncMock(return_value=[]))
    monkeypatch.setattr(scheduler, "_count_missing_id_alerts", AsyncMock(return_value=0))

    async def expire(_id):
        events.append("expire")
        return True

    monkeypatch.setattr(scheduler, "_expire_stuck_seedance_video", expire)
    result = await scheduler.reconcile_neironych_videos_once()
    assert events == ["expire"]
    assert result["expired"] == 1 and result["notices"] == 0


def test_timeout_notice_query_includes_unbound_submission_ids():
    compiled = scheduler._eligible_notice_query().compile(dialect=postgresql.dialect())
    assert "neironych-submit:%" in str(list(compiled.params.values()))


@pytest.mark.asyncio
async def test_web_timeout_never_queues_telegram_notice(monkeypatch):
    gen = _generation(task_id="web:neironych:uuid")
    refunds = AsyncMock(return_value=(True,70.0))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", AsyncMock(return_value=("pending", None)))
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    assert refunds.await_args.kwargs["video_notice_kind"] is None



@pytest.mark.asyncio
async def test_provider_identity_change_during_final_poll_defers_refund(monkeypatch):
    gen = _generation()
    original = gen.task_id

    async def provider_bound_new_identity(_gen):
        gen.task_id = "neironych:bound-after-lookup"
        return ("pending", None)

    refunds = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", provider_bound_new_identity)
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
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", AsyncMock(return_value=("pending", None)))
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
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", polls)
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
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", polls)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_awaited_once()
    polls.assert_awaited_once()


@pytest.mark.asyncio
async def test_timed_out_pending_response_does_not_wait_forever(monkeypatch):
    gen = _generation(age_seconds=3900)
    refunds = AsyncMock(return_value=(True, 70.0))
    polls = AsyncMock(return_value=("pending", None))  # status GET is nonterminal
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", polls)
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
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", AsyncMock(return_value=("pending", None)))
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    monkeypatch.setattr(scheduler, "_track_active_video_notice_intent", redis)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_awaited_once()
    redis.assert_awaited_once()



def test_expiry_uses_neironych_submission_clock_not_generation_creation():
    import json

    from core.config import settings

    gen = _generation(age_seconds=7200)
    began = datetime.now(timezone.utc) - timedelta(seconds=300)
    gen.input_params = json.dumps({
        "neironych_submission": {
            "state": "submitting", "started_at": began.isoformat(),
        }
    })
    assert (datetime.now(timezone.utc) - scheduler._seedance_started_at(gen)).total_seconds() < settings.SEEDANCE_AUTO_REFUND_SECONDS


@pytest.mark.asyncio
async def test_expiry_defers_when_remote_video_done_even_if_download_has_not_succeeded(monkeypatch):
    gen = _generation()
    refunds = AsyncMock()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(
        scheduler, "_final_neironych_provider_status",
        AsyncMock(return_value=("done", None)),
    )
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert not await scheduler._expire_stuck_seedance_video(gen.id)
    refunds.assert_not_awaited()


@pytest.mark.asyncio
async def test_remote_failed_is_refunded_without_unknown_supplier_cost_marker(monkeypatch):
    gen = _generation()
    refunds = AsyncMock(return_value=(True, 70.0))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", _Session)
    monkeypatch.setattr(
        scheduler, "_final_neironych_provider_status",
        AsyncMock(return_value=("failed", None)),
    )
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", refunds)
    assert await scheduler._expire_stuck_seedance_video(gen.id)
    assert refunds.await_args.kwargs["provider_review"] is None


@pytest.mark.asyncio
async def test_post_refund_supplier_review_records_late_completion_without_changing_user_state(monkeypatch):
    import json
    from types import SimpleNamespace

    now = datetime.now(timezone.utc)
    gen = _generation(status=GenerationStatus.failed)
    gen.input_params = json.dumps({
        "seedance_refund_provider_review": {
            "state": "pending",
            "original_task_id": gen.task_id,
            "next_check_at": (now-timedelta(minutes=1)).isoformat(),
            "checks": 0,
        },
        "refund_applied": True,
    })
    commits=[]
    admin_alert = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, "send_admin_alert_once", admin_alert)

    class ReviewSession(_Session):
        async def execute(self, _query):
            return SimpleNamespace(scalar_one_or_none=lambda: gen)

        async def commit(self):
            commits.append(True)

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", ReviewSession)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(
        scheduler, "_final_neironych_provider_status",
        AsyncMock(return_value=("done", None)),
    )
    no_refund=AsyncMock()
    monkeypatch.setattr(scheduler.repo, "fail_generation_and_refund", no_refund)
    assert await scheduler._review_refunded_provider_task(gen.id)
    marker=json.loads(gen.input_params)["seedance_refund_provider_review"]
    assert marker["state"]=="remote_completed_pending_finance"
    assert marker["checks"]==1 and marker["reconciled_at"]
    assert commits==[True] and gen.status==GenerationStatus.failed
    assert json.loads(gen.input_params)["refund_applied"] is True
    no_refund.assert_not_awaited()
    admin_alert.assert_awaited_once()



@pytest.mark.asyncio
async def test_final_get_completed_or_failed_is_read_only(monkeypatch):
    from core import neironych_video_reconcile_scheduler as scheduler

    for succeeded in (True, False):
        remote = SimpleNamespace(done=succeeded, failed=not succeeded)
        client = SimpleNamespace(
            get_video=AsyncMock(return_value=remote),
            aclose=AsyncMock(),
        )
        monkeypatch.setattr(scheduler.neironych_seedance_runtime, "_client", lambda: client)
        gen = _generation(task_id="neironych:abc-123")
        label, bound = await _ORIGINAL_FINAL_STATUS(gen)
        assert label == ("done" if succeeded else "failed")
        assert bound is None
        client.get_video.assert_awaited_once_with("abc-123")
        client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_provider_identity_is_looked_up_without_submitting_again(monkeypatch):
    import json

    gen = _generation(task_id="neironych-submit:request-id")
    gen.input_params = json.dumps({
        "neironych_submission": {
            "client_request_id": "request-id",
            "idempotency_key": "idempotency-original",
        },
    })
    lookup = AsyncMock(return_value="provider-id")
    monkeypatch.setattr(scheduler.neironych_seedance_runtime, "lookup_submission", lookup)
    label, bound = await _ORIGINAL_FINAL_STATUS(gen)
    assert (label, bound) == ("bound", "provider-id")
    lookup.assert_awaited_once_with(
        "request-id", product_model=gen.model, idempotency_key="idempotency-original",
    )


@pytest.mark.asyncio
async def test_slow_expiry_lane_does_not_starve_notice_lane(monkeypatch):
    import asyncio

    delivered = asyncio.Event()

    async def slowly_expire(_stop):
        await asyncio.sleep(0.05)
        return [True]

    async def promptly_notify(_stop):
        delivered.set()
        return [True]

    monkeypatch.setattr(scheduler, "_run_expired_lane", slowly_expire)
    monkeypatch.setattr(scheduler, "_run_notices_lane", promptly_notify)
    monkeypatch.setattr(scheduler, "_run_active_video_lane", AsyncMock(return_value=[]))
    monkeypatch.setattr(scheduler, "_run_refund_supplier_review_lane",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr(scheduler, "_count_missing_id_alerts", AsyncMock(return_value=0))
    task = asyncio.create_task(scheduler.reconcile_neironych_videos_once())
    await asyncio.wait_for(delivered.wait(), timeout=0.025)
    summary = await task
    assert summary["expired"] == 1
    assert summary["sent"] == 1



@pytest.mark.asyncio
async def test_regular_video_lane_does_not_contend_for_expired_seedance_lease(monkeypatch):
    gen=_generation(age_seconds=4000)
    class Session(_Session):
        async def execute(self,_stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [gen]))
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", Session)
    monkeypatch.setattr(scheduler, "_load_batch", AsyncMock(return_value=[gen.id]))
    processor=AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, "_process_active_video", processor)
    assert await scheduler._run_active_video_lane(None)==[]
    processor.assert_not_awaited()


@pytest.mark.asyncio
async def test_supplier_review_expiry_escalates_for_administrator(monkeypatch):
    import json

    gen = _generation(status=GenerationStatus.failed)
    gen.input_params = json.dumps({
        "refund_applied": True,
        "seedance_refund_provider_review": {
            "state": "pending",
            "original_task_id": gen.task_id,
            "refunded_at": (datetime.now(timezone.utc)-timedelta(hours=25)).isoformat(),
            "next_check_at": (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
            "checks": 95,
        },
    })
    class Session(_Session):
        async def execute(self, _statement):
            return SimpleNamespace(scalar_one_or_none=lambda: gen)
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", Session)
    monkeypatch.setattr(scheduler.repo,"get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(scheduler,"_final_neironych_provider_status",
                        AsyncMock(return_value=("unknown",None)))
    alert=AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler,"send_admin_alert_once",alert)
    assert await scheduler._review_refunded_provider_task(gen.id)
    review=json.loads(gen.input_params)["seedance_refund_provider_review"]
    assert review["state"]=="needs_admin_resolution"
    assert review["escalated_at"]
    alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_real_sqlalchemy_rollback_cannot_refund_an_already_completed_remote_video(
    tmp_path, monkeypatch,
):
    '''A real ORM rollback expires attributes; provider GET must get a snapshot.'''
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from db.models import Base, Generation, User

    engine = create_engine("sqlite:///" + str(tmp_path / "detached-paid-video.db"))
    Base.metadata.create_all(engine, tables=[User.__table__, Generation.__table__])
    video_id = 10031
    upstream = "neironych:synthetic-completed"
    with Session(engine) as db:
        db.add(User(id=42, tg_id=4200, credits=100, referral_code="synthetic-snapshot"))
        db.add(Generation(
            id=video_id, user_id=42, model="bytedance/seedance-2-5",
            gen_type=GenerationType.video, status=GenerationStatus.processing,
            task_id=upstream, input_params="{}", credits_spent=40,
            prompt="synthetic red-blue clip",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ))
        db.commit()

    class ActualOrmTransaction:
        def __init__(self):
            self.db = Session(engine)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.db.close()

        async def execute(self, statement):
            return self.db.execute(statement)

        async def rollback(self):
            self.db.rollback()

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", ActualOrmTransaction)
    final_get = AsyncMock()

    async def verified_remote_completed(item):
        # This access raises DetachedInstanceError with an expired ORM object.
        assert item.task_id == upstream
        assert item.input_params == {}
        return "done", None

    final_get.side_effect = verified_remote_completed
    monkeypatch.setattr(scheduler, "_final_neironych_provider_status", final_get)
    settle = AsyncMock(return_value=True)
    monkeypatch.setattr(scheduler, "_settle_expired_seedance", settle)
    try:
        assert not await scheduler._expire_stuck_seedance_video(video_id)
        final_get.assert_awaited_once()
        settle.assert_not_awaited()
    finally:
        engine.dispose()
