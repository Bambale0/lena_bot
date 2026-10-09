from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from api import miniapp_routes, neironych_seedance_runtime
from db.models import GenerationStatus, GenerationType


@pytest.fixture(autouse=True)
def allow_test_neironych_poll_gate(monkeypatch):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def gate(_task_id: str):
        yield True

    monkeypatch.setattr(miniapp_routes, "neironych_video_poll_guard", gate)


def _video(*, age_minutes=12):
    return SimpleNamespace(
        id=789123, user_id=30, model="bytedance/seedance-2-5",
        gen_type=GenerationType.video, status=GenerationStatus.processing,
        task_id="neironych:provider-uuid",
        created_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
        result_url=None, result_urls=None, image_session_id=None,
        prompt="test", action_type=None, source_feed_gen_id=None, input_params="{}",
    )


class _FakeNoticeCursorRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value):
        self.store[key] = str(value)
        return True

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_provider_http_timeout_does_not_refund(monkeypatch):
    gen = _video(age_minutes=150)
    poll = AsyncMock(side_effect=TimeoutError("temporary outage"))
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda _: poll)
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_old_running_video_does_not_refund_after_twenty_minutes(monkeypatch):
    gen = _video(age_minutes=75)
    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda _: AsyncMock(return_value=None))
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_provider_failure_uses_guarded_atomic_refund(monkeypatch):
    gen = _video()
    failed = neironych_seedance_runtime.NeironychVideoTaskFailed("provider-uuid", "video failed")
    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda _: AsyncMock(side_effect=failed))
    refund = AsyncMock(return_value=(True, 17))
    updated = SimpleNamespace(**{**vars(gen), "status": GenerationStatus.failed})
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=updated))
    notify = AsyncMock()
    monkeypatch.setattr(miniapp_routes, "_deliver_pending_neironych_video_notice", notify)
    assert (await miniapp_routes._reconcile_generation_status(object(), gen)).status == GenerationStatus.failed
    refund.assert_awaited_once_with(
        ANY, gen.id, "video failed", expected_task_id=gen.task_id,
        refund_note="reconcile:neironych_provider_failed", video_notice_kind="failed",
    )
    notify.assert_awaited_once_with(ANY, gen.id)


@pytest.mark.asyncio
async def test_neironych_provider_terminal_status_raises_typed_failure(monkeypatch):
    status = SimpleNamespace(failed=True, done=False, error="content rejected", status="failed")
    client = SimpleNamespace(get_video=AsyncMock(return_value=status), aclose=AsyncMock())
    monkeypatch.setattr(neironych_seedance_runtime, "_client", lambda: client)
    with pytest.raises(neironych_seedance_runtime.NeironychVideoTaskFailed) as err:
        await neironych_seedance_runtime.poll_product_video("neironych:provider-uuid")
    assert err.value.request_id == "provider-uuid"


@pytest.mark.asyncio
async def test_unknown_provider_http_status_stays_active(monkeypatch):
    from api.neironych_seedance import NeironychSeedanceError

    gen = _video(age_minutes=125)
    monkeypatch.setattr(
        miniapp_routes.video_service, "get_poll_fn",
        lambda _: AsyncMock(side_effect=NeironychSeedanceError("HTTP 404", status_code=404)),
    )
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsent_video_delivery_is_reported_as_false(monkeypatch):
    gen = _video()
    gen.status = GenerationStatus.done
    gen.result_url = "https://example.test/clip.mp4"
    bot = SimpleNamespace(
        send_video=AsyncMock(side_effect=RuntimeError("video temporarily unavailable")),
        send_message=AsyncMock(side_effect=RuntimeError("telegram offline")),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(miniapp_routes, "Bot", lambda **kwargs: bot)
    success = await miniapp_routes._notify_reconciled_video_result_in_bot(
        user=SimpleNamespace(tg_id=123), gen=gen,
    )
    assert success is False


def test_video_scheduler_is_registered_in_main_lifespan():
    import inspect

    import main
    assert "run_neironych_video_reconcile_scheduler" in inspect.getsource(main.lifespan)


def test_video_notice_repository_operations_exist():
    from db import repository
    assert callable(repository.claim_neironych_video_notice)
    assert callable(repository.complete_neironych_video_notice)


def test_video_scheduler_detects_active_neironych_rows():
    from core import neironych_video_reconcile_scheduler as scheduler
    query = scheduler._eligible_video_query()
    assert "generations" in str(query).lower()


@pytest.mark.asyncio
async def test_scheduler_round_robin_revisits_old_video_under_new_traffic(monkeypatch):
    from core import neironych_video_reconcile_scheduler as scheduler

    class Rows:
        def __init__(self, values):
            self.values = values

        def scalars(self):
            return SimpleNamespace(all=lambda: self.values)

    session = SimpleNamespace(execute=AsyncMock(side_effect=[
        Rows([11, 12]), Rows([1, 2]), Rows([13, 14]), Rows([3, 4]),
    ]))
    cursor = scheduler._ScanCursor(newest_id=10)
    query = scheduler._eligible_video_query()
    assert await scheduler._pick_ids(session, query, cursor, 4) == [11, 12, 1, 2]
    assert await scheduler._pick_ids(session, query, cursor, 4) == [13, 14, 3, 4]


@pytest.mark.asyncio
async def test_scheduler_bounded_provider_polling_prevents_rate_limit_storm(monkeypatch):
    import asyncio

    from core import neironych_video_reconcile_scheduler as scheduler
    from core.config import settings

    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_RECONCILE_CONCURRENCY", 3)
    simultaneous = 0
    peak = 0

    async def job(_gen_id: int) -> bool:
        nonlocal simultaneous, peak
        simultaneous += 1
        peak = max(peak, simultaneous)
        await asyncio.sleep(0.002)
        simultaneous -= 1
        return True

    result = await scheduler._process_bounded_batch(list(range(20)), job, None)
    assert len(result) == 20 and all(result)
    assert peak == 3


@pytest.mark.asyncio
async def test_scheduler_checks_active_tasks_and_pending_telegram_notices(monkeypatch):
    from core import neironych_video_reconcile_scheduler as scheduler

    monkeypatch.setattr(scheduler, "_load_batch", AsyncMock(return_value=[12, 14]))
    monkeypatch.setattr(scheduler, "_load_notice_batch", AsyncMock(return_value=[12, 19]))
    check = AsyncMock(return_value=True)
    send = AsyncMock(side_effect=[True, False])
    monkeypatch.setattr(scheduler, "_process_active_video", check)
    monkeypatch.setattr(scheduler, "_process_delivery_notice", send)
    monkeypatch.setattr(scheduler, "_count_missing_id_alerts", AsyncMock(return_value=0))

    result = await scheduler.reconcile_neironych_videos_once()
    assert result == {"checked": 2, "notices": 2, "sent": 1, "missing_ids": 0}
    assert check.await_count == 2
    assert send.await_count == 2


@pytest.mark.asyncio
async def test_completed_provider_video_download_timeout_keeps_task_processing(monkeypatch):
    gen = _video(age_minutes=120)
    status = SimpleNamespace(failed=False, done=True, error="", status="completed")
    client = SimpleNamespace(
        get_video=AsyncMock(return_value=status),
        download_content_to=AsyncMock(side_effect=TimeoutError("content storage unavailable")),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(neironych_seedance_runtime, "_client", lambda: client)
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(
        miniapp_routes.video_service, "get_poll_fn",
        lambda _: neironych_seedance_runtime.poll_product_video,
    )
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_failed_video_user_receives_refund_notification(monkeypatch):
    import json
    gen = _video()
    gen.status = GenerationStatus.failed
    gen.credits_spent = 70
    gen.input_params = json.dumps({"refund_applied": True})
    fake_bot = SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=31)),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(miniapp_routes, "Bot", lambda **kwargs: fake_bot)
    assert await miniapp_routes._notify_reconciled_video_failure_in_bot(
        user=SimpleNamespace(tg_id=12345), gen=gen,
    )
    kwargs = fake_bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 12345
    assert "70 кредитов" in kwargs["text"]
    assert "provider-uuid" in kwargs["text"]
    fake_bot.session.close.assert_awaited_once()


def test_pending_notice_query_matches_pending_and_sending_but_not_sent():
    import json
    import re

    from sqlalchemy.dialects import postgresql

    from core import neironych_video_reconcile_scheduler as scheduler

    sql = str(scheduler._eligible_notice_query().compile(dialect=postgresql.dialect()))
    assert "neironych_video_notice" not in sql or "~" in sql
    assert " ~ " in sql
    for state, expected in (("pending", True), ("sending", True), ("sent", False)):
        raw = json.dumps({"neironych_video_notice": {
            "kind": "done", "state": state, "attempts": 1,
        }})
        assert bool(re.search(scheduler._NOTICE_PENDING_REGEX, raw)) is expected


@pytest.mark.asyncio
async def test_unknown_task_identity_is_not_proof_of_failed_paid_submission(monkeypatch):
    gen = _video(age_minutes=180)
    gen.task_id = None
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmed_failure_with_mismatched_request_id_never_refunds(monkeypatch):
    gen = _video(age_minutes=250)
    wrong = neironych_seedance_runtime.NeironychVideoTaskFailed(
        "another-provider-task", "Provider returned an unrelated failure"
    )
    monkeypatch.setattr(
        miniapp_routes.video_service, "get_poll_fn",
        lambda _: AsyncMock(side_effect=wrong),
    )
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_web_video_generation_never_queues_telegram_notice(monkeypatch):
    gen = _video()
    gen.task_id = "web:neironych:provider-uuid"
    updated = _video()
    updated.status = GenerationStatus.done
    updated.task_id = gen.task_id
    updated.result_url = "https://example.test/video.mp4"
    finish = AsyncMock(return_value=updated)
    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn",
                        lambda _: AsyncMock(return_value=updated.result_url))
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id",
                        AsyncMock(return_value=updated))
    notify = AsyncMock()
    monkeypatch.setattr(miniapp_routes, "_deliver_pending_neironych_video_notice", notify)
    result = await miniapp_routes._reconcile_generation_status(object(), gen)
    assert result.status == GenerationStatus.done
    assert finish.await_args.kwargs["expected_task_id"] == gen.task_id
    assert finish.await_args.kwargs["queue_neironych_video_notice"] is False
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_scheduler_bad_row_does_not_starve_other_generations():
    from core import neironych_video_reconcile_scheduler as scheduler

    executed = []

    async def job(gen_id: int) -> bool:
        executed.append(gen_id)
        if gen_id == 2:
            raise RuntimeError("one task has an invalid provider response")
        return True

    assert await scheduler._process_bounded_batch([1, 2, 3], job, None) == [
        True, False, True,
    ]
    assert sorted(executed) == [1, 2, 3]


@pytest.mark.asyncio
async def test_neironych_video_status_rejects_mismatched_provider_response_id():
    import httpx

    from api.neironych_seedance import NeironychSeedanceClient, NeironychSeedanceError

    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "data": {"request_id": "another-task", "status": "failed", "error": "rejected"}
    }))
    async with httpx.AsyncClient(transport=transport, base_url="https://provider.example.test") as transport_client:
        client = NeironychSeedanceClient(
            "test-secret", "https://provider.example.test", client=transport_client
        )
        with pytest.raises(NeironychSeedanceError, match="request_id"):
            await client.get_video("expected-task")


def test_notice_lease_must_exceed_notification_timeout():
    from pydantic import ValidationError

    from core.config import Settings

    with pytest.raises(ValidationError, match="NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS"):
        Settings(
            _env_file=None, BOT_TOKEN="123:unit", COMET_API_KEY="ci",
            NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS=240,
            NEIRONYCH_VIDEO_NOTICE_LEASE_SECONDS=120,
        )


@pytest.mark.asyncio
async def test_video_scheduler_releases_read_transaction_before_provider_poll(monkeypatch):
    from core import neironych_video_reconcile_scheduler as scheduler

    events = []
    row = _video()
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def commit(self):
            events.append("commit")

        async def rollback(self):
            events.append("rollback")

    fake = FakeSession()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: fake)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=row))

    async def fake_reconcile(_session, _generation):
        events.append("provider_get")
        assert "commit" in events
        return row

    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", fake_reconcile)
    assert await scheduler._process_active_video(row.id)
    assert events.index("commit") < events.index("provider_get")


@pytest.mark.asyncio
async def test_direct_notification_timeout_returns_unconfirmed_receipt(monkeypatch):
    import asyncio

    from core.config import settings

    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS", 0.02)
    gen = _video()
    gen.status = GenerationStatus.done
    gen.result_url = "https://example.test/result.mp4"
    claim = SimpleNamespace(
        kind="done", generation=gen, token="lease-1", attempt=1,
    )
    get_claim = AsyncMock(return_value=claim)
    user = SimpleNamespace(id=gen.user_id, tg_id=42)
    notice_done = AsyncMock(return_value=True)
    monkeypatch.setattr(miniapp_routes.repo, "claim_neironych_video_notice", get_claim)
    monkeypatch.setattr(miniapp_routes.repo, "get_user_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(miniapp_routes.repo, "complete_neironych_video_notice", notice_done)
    stalled = asyncio.Event()

    async def slow_telegram(**kwargs):
        await stalled.wait()
        return True

    mock_send = AsyncMock(side_effect=slow_telegram)
    monkeypatch.setattr(miniapp_routes, "_notify_reconciled_video_result_in_bot", mock_send)
    session = SimpleNamespace(commit=AsyncMock())
    delivered = await asyncio.wait_for(
        miniapp_routes._deliver_pending_neironych_video_notice(session, gen.id), 0.2
    )
    assert delivered is False
    mock_send.assert_awaited_once()
    notice_done.assert_awaited_once_with(session, gen.id, claim.token, delivered=False)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_lost_provider_poll_ownership_defers_without_refund(monkeypatch):
    from core.neironych_video_poll_gate import NeironychVideoPollLeaseLost

    gen = _video(age_minutes=70)
    monkeypatch.setattr(
        miniapp_routes, "_reconcile_neironych_video_generation",
        AsyncMock(side_effect=NeironychVideoPollLeaseLost("Redis owner changed")),
    )
    refund = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    assert await miniapp_routes._reconcile_generation_status(object(), gen) is gen
    refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_video_reconciliation_releases_db_before_provider_download(monkeypatch):
    gen = _video(age_minutes=3)
    events = []

    class FakeSession:
        async def commit(self):
            events.append("read_transaction_closed")

    async def poll(_task_id):
        assert events == ["read_transaction_closed"]
        events.append("upstream_status_and_download")
        return None

    monkeypatch.setattr(miniapp_routes, "AsyncSession", FakeSession)
    monkeypatch.setattr(
        miniapp_routes.video_service, "get_poll_fn",
        lambda _provider: poll,
    )
    session = FakeSession()
    assert await miniapp_routes._reconcile_generation_status(session, gen) is gen
    assert events == ["read_transaction_closed", "upstream_status_and_download"]


@pytest.mark.asyncio
async def test_user_history_video_check_uses_persisted_state_without_provider_io(monkeypatch):
    gen = _video(age_minutes=2)
    reconcile = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", reconcile)
    monkeypatch.setattr(miniapp_routes, "_gen_out", lambda value: value)
    result = await miniapp_routes.get_generation(
        gen.id, object(), SimpleNamespace(id=gen.user_id),
    )
    assert result is gen
    reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_reconciles_other_models_but_skips_seedance_network(monkeypatch):
    seedance = _video(age_minutes=1)
    kie = _video(age_minutes=1)
    kie.task_id = "kie-task"

    class FakeSession:
        pass

    get_active = AsyncMock(return_value=[seedance, kie])
    reconcile = AsyncMock(return_value=kie)
    monkeypatch.setattr(miniapp_routes.repo, "get_user_active_generations", get_active)
    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", reconcile)
    session = FakeSession()
    await miniapp_routes._reconcile_user_active_generations(session, seedance.user_id)
    reconcile.assert_awaited_once_with(session, kie)


@pytest.mark.asyncio
async def test_website_neironych_status_is_read_from_db_without_polling(monkeypatch):
    gen = _video(age_minutes=40)
    gen.task_id = "web:neironych:provider-uuid"
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=gen))
    reconcile = AsyncMock()
    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", reconcile)
    monkeypatch.setattr(miniapp_routes, "_gen_out", lambda value: value)
    result = await miniapp_routes.get_generation(gen.id, object(), SimpleNamespace(id=gen.user_id))
    assert result is gen
    reconcile.assert_not_awaited()


def test_polling_entrypoint_runs_video_recovery_scheduler():
    import inspect

    import run_polling

    source = inspect.getsource(run_polling.main)
    assert "run_neironych_video_reconcile_scheduler" in source
    assert "video_reconcile_stop.set()" in source

@pytest.mark.asyncio
async def test_notice_scan_advances_over_empty_indexed_id_windows(monkeypatch):
    from core import neironych_video_reconcile_scheduler as scheduler
    from core.config import settings

    class Results:
        def scalars(self):
            return SimpleNamespace(all=lambda: [])

    class FakeSession:
        def __init__(self):
            self.queries = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def scalar(self, _sql):
            return 10000

        async def execute(self, query):
            self.queries.append(str(query))
            return Results()

        async def rollback(self):
            pass

    db = FakeSession()
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", lambda: db)
    monkeypatch.setattr(scheduler, "_notice_cursor", scheduler._ScanCursor())
    redis_store = _FakeNoticeCursorRedis()
    monkeypatch.setattr(
        scheduler.aioredis.Redis, "from_url", lambda *args, **kwargs: redis_store
    )
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE", 4)
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_NOTICE_SCAN_ID_SPAN", 1000, raising=False)
    assert await scheduler._load_notice_batch() == []
    assert scheduler._notice_cursor.older_id == 1000
    assert await scheduler._load_notice_batch() == []
    assert scheduler._notice_cursor.older_id == 2000
    assert db.queries and all("generations.id" in q for q in db.queries)

@pytest.mark.asyncio
async def test_notice_scan_prioritizes_recent_ids_while_backfilling_old(monkeypatch):
    from core import neironych_video_reconcile_scheduler as scheduler
    from core.config import settings

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False
        async def scalar(self, _query): return 1000000
        async def rollback(self): pass
        async def execute(self, query):
            values = [999995] if "DESC" in str(query) else [12]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: values))

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(scheduler, "_notice_cursor", scheduler._ScanCursor())
    redis_store = _FakeNoticeCursorRedis()
    monkeypatch.setattr(
        scheduler.aioredis.Redis, "from_url", lambda *args, **kwargs: redis_store
    )
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE", 4)
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_NOTICE_SCAN_ID_SPAN", 5000, raising=False)
    found = await scheduler._load_notice_batch()
    assert 999995 in found and 12 in found


@pytest.mark.asyncio
async def test_scheduler_does_not_abort_post_commit_royalty_after_poll_deadline(monkeypatch):
    import asyncio

    from core import neironych_video_reconcile_scheduler as scheduler
    from core.config import settings

    row = _video(age_minutes=2)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

        async def rollback(self):
            pass

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(scheduler.repo, "get_generation_by_id", AsyncMock(return_value=row))
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS", 0.02)
    events = []

    async def after_provider_success(_session, gen):
        events.append("provider_download_completed")
        await asyncio.sleep(0.06)
        events.append("feed_royalty_settlement_completed")
        gen.status = GenerationStatus.done
        return gen

    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", after_provider_success)
    assert await asyncio.wait_for(scheduler._process_active_video(row.id), 0.25)
    assert events == ["provider_download_completed", "feed_royalty_settlement_completed"]


@pytest.mark.asyncio
async def test_notice_worker_does_not_cancel_receipt_commit_after_telegram_sends(monkeypatch):
    import asyncio

    from core import neironych_video_reconcile_scheduler as scheduler
    from core.config import settings

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def rollback(self):
            pass

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS", 0.02)
    recorded = []

    async def delivery(_session, gen_id):
        recorded.append(("telegram_accepted", gen_id))
        await asyncio.sleep(0.05)
        recorded.append(("db_receipt_saved", gen_id))
        return True

    monkeypatch.setattr(miniapp_routes, "_deliver_pending_neironych_video_notice", delivery)
    assert await asyncio.wait_for(scheduler._process_delivery_notice(789123), 0.2)
    assert recorded == [("telegram_accepted", 789123), ("db_receipt_saved", 789123)]


@pytest.mark.asyncio
async def test_notice_historical_cursor_survives_worker_restart(monkeypatch):
    from core import neironych_video_reconcile_scheduler as scheduler
    from core.config import settings

    storage = {}

    class FakeRedis:
        async def get(self, key):
            return storage.get(key)

        async def set(self, key, value):
            storage[key] = str(value)
            return True

        async def aclose(self):
            pass

    class EmptyRows:
        def scalars(self):
            return SimpleNamespace(all=lambda: [])

    class FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False
        async def scalar(self, _statement): return 10000
        async def execute(self, _statement): return EmptyRows()
        async def rollback(self): pass

    monkeypatch.setattr(scheduler, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(scheduler, "_notice_cursor", scheduler._ScanCursor())
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE", 4)
    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_NOTICE_SCAN_ID_SPAN", 1000)
    monkeypatch.setattr(scheduler.aioredis.Redis, "from_url", lambda *args, **kwargs: FakeRedis())
    assert await scheduler._load_notice_batch() == []
    assert scheduler._notice_cursor.older_id == 1000
    assert list(storage.values()) == ["1000"]

    # A deploy creates a fresh process-local cursor, but Redis survives.
    monkeypatch.setattr(scheduler, "_notice_cursor", scheduler._ScanCursor())
    assert await scheduler._load_notice_batch() == []
    assert scheduler._notice_cursor.older_id == 2000
    assert list(storage.values()) == ["2000"]


def test_polling_entry_rejects_memory_fallback_for_billable_neironych(monkeypatch):
    import run_polling
    from core.config import settings

    monkeypatch.setattr(settings, "NEIRONYCH_API_KEY", "test-key-only")
    with pytest.raises(RuntimeError, match="Redis"):
        run_polling._require_neironych_recovery_redis(None)
    assert run_polling._require_neironych_recovery_redis(object()) is None
