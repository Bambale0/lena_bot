"""Wan KIE tasks must survive restarts and transient provider GET failures."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from api import miniapp_routes, video_service
from core import neironych_video_reconcile_scheduler as recovery
from db.models import GenerationStatus, GenerationType


def wan_pending(*, minutes=25):
    return SimpleNamespace(
        id=1001, model="wan/3-0-video", gen_type=GenerationType.video,
        task_id="kie_wan_123", status=GenerationStatus.processing,
        created_at=datetime.now(timezone.utc)-timedelta(minutes=minutes),
        image_session_id=None, input_params="{}",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("err", [TimeoutError("slow"), OSError("lost GET")])
async def test_wan_poll_transient_does_not_refund(monkeypatch, err):
    gen=wan_pending()
    refunded=AsyncMock()
    monkeypatch.setattr(miniapp_routes.video_service,"poll_kieai_status",AsyncMock(side_effect=err))
    monkeypatch.setattr(miniapp_routes.repo,"fail_generation_and_refund",refunded)
    result=await miniapp_routes._reconcile_generation_status(AsyncMock(),gen)
    assert result is gen
    refunded.assert_not_awaited()


@pytest.mark.asyncio
async def test_wan_stays_pending_at_25min_instead_of_old_global_20min_expiry(monkeypatch):
    gen=wan_pending(minutes=25)
    monkeypatch.setattr(miniapp_routes.video_service,"poll_kieai_status",AsyncMock(return_value=None))
    refunded=AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo,"fail_generation_and_refund",refunded)
    out=await miniapp_routes._reconcile_generation_status(AsyncMock(),gen)
    assert out is gen
    refunded.assert_not_awaited()


@pytest.mark.asyncio
async def test_wan_kie_worker_recognizes_provider_success(monkeypatch):
    gen=wan_pending()
    monkeypatch.setattr(video_service,"poll_kieai_status",AsyncMock(return_value="https://example.test/video.mp4"))
    state, _ = await recovery._final_neironych_provider_status(gen)
    assert state == "done"


@pytest.mark.asyncio
async def test_wan_kie_worker_recognizes_explicit_terminal_failure(monkeypatch):
    gen=wan_pending()
    monkeypatch.setattr(video_service,"poll_kieai_status",AsyncMock(
        side_effect=video_service.KieVideoTaskFailed("provider failed"),
    ))
    state, _=await recovery._final_neironych_provider_status(gen)
    assert state=="failed"


def test_background_worker_scans_wan_regular_kie_tasks():
    query=recovery._eligible_video_query().compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    )
    query_sql=str(query)
    assert "'wan/3-0-video'" in query_sql
    assert "'wan/3-0-video-prime'" in query_sql
    assert "task_id IS NOT NULL" in query_sql


def test_expiry_lane_scans_wan_kie_pending_with_1h_deadline():
    sql=str(recovery._expired_seedance_query().compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    assert "wan/3-0-video" in sql
    assert "wan/3-0-video-prime" in sql

@pytest.mark.asyncio
async def test_neironych_wan_mirrors_result_before_finalizing(monkeypatch):
    from contextlib import asynccontextmanager

    from api import wan30_media

    @asynccontextmanager
    async def free_gate(_task):
        yield True

    upstream = "https://provider.example.test/expiring.mp4"
    owned = "https://apixbotai.com/static/upload/provider-results/verified.mp4"
    monkeypatch.setattr(miniapp_routes, "neironych_video_poll_guard", free_gate)
    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn",
                        lambda _: AsyncMock(return_value=upstream))
    mirror = AsyncMock(return_value=owned)
    monkeypatch.setattr(wan30_media, "mirror_wan30_result", mirror)
    finish = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock())
    gen = wan_pending()
    gen.task_id = "web:neironych:provider-uuid"
    await miniapp_routes._reconcile_generation_status(AsyncMock(), gen)
    mirror.assert_awaited_once_with(upstream)
    assert finish.await_args.args[2] == owned


def test_wan_kie_pending_notices_are_scanned_after_restart():
    sql = str(recovery._eligible_notice_query().compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    assert sql.count("'wan/3-0-video'") >= 2
    assert sql.count("'wan/3-0-video-prime'") >= 2


@pytest.mark.asyncio
async def test_expired_wan_kie_id_enters_atomic_expiry_guard(monkeypatch):
    from contextlib import asynccontextmanager

    gen = wan_pending(minutes=130)
    fake_db = AsyncMock()
    monkeypatch.setattr(recovery.repo, "get_generation_by_id", AsyncMock(return_value=gen))

    @asynccontextmanager
    async def fake_session():
        yield fake_db

    seen = []

    @asynccontextmanager
    async def fake_guard(task):
        seen.append(task)
        yield False

    monkeypatch.setattr(recovery, "AsyncSessionLocal", fake_session)
    monkeypatch.setattr(recovery, "neironych_video_poll_guard", fake_guard)
    await recovery._expire_stuck_seedance_video(gen.id)
    assert seen == [gen.task_id]


@pytest.mark.asyncio
async def test_expired_wan_kie_refund_enqueues_telegram_notice(monkeypatch):
    from contextlib import asynccontextmanager

    pending = wan_pending(minutes=140)
    db = AsyncMock()
    finish = AsyncMock(return_value=(True, 130))
    notify = AsyncMock()
    monkeypatch.setattr(recovery.repo, "get_generation_by_id", AsyncMock(return_value=pending))
    monkeypatch.setattr(recovery.repo, "fail_generation_and_refund", finish)
    monkeypatch.setattr(recovery, "_track_active_video_notice_intent", notify)

    @asynccontextmanager
    async def fake_db():
        yield db

    monkeypatch.setattr(recovery, "AsyncSessionLocal", fake_db)
    success = await recovery._settle_expired_seedance(
        pending.id, pending.task_id, "failed", notify_telegram=True,
    )
    assert success is True
    assert finish.await_args.kwargs["video_notice_kind"] == "failed"
    notify.assert_awaited_once_with(pending.id)


@pytest.mark.asyncio
async def test_wan_poll_confirmed_failure_refunds_and_queues_durable_bot_notice(monkeypatch):
    gen = wan_pending()
    failed = SimpleNamespace(**{**vars(gen), "status": GenerationStatus.failed})
    monkeypatch.setattr(
        miniapp_routes.video_service, "poll_kieai_status",
        AsyncMock(side_effect=video_service.KieVideoTaskFailed("rejected by KIE")),
    )
    refund = AsyncMock(return_value=(True, 15))
    notice = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=failed))
    monkeypatch.setattr(miniapp_routes, "_deliver_pending_neironych_video_notice", notice)
    out = await miniapp_routes._reconcile_generation_status(AsyncMock(), gen)
    assert out.status == GenerationStatus.failed
    assert refund.await_args.kwargs["expected_task_id"] == gen.task_id
    assert refund.await_args.kwargs["video_notice_kind"] == "failed"
    notice.assert_awaited_once()
    assert notice.await_args.args[1] == gen.id


@pytest.mark.asyncio
async def test_wan_web_poll_confirmed_failure_does_not_queue_telegram_notice(monkeypatch):
    gen = wan_pending()
    gen.task_id = "web:kie_paid"
    failed = SimpleNamespace(**{**vars(gen), "status": GenerationStatus.failed})
    monkeypatch.setattr(
        miniapp_routes.video_service, "poll_kieai_status",
        AsyncMock(side_effect=video_service.KieVideoTaskFailed("rejected by KIE")),
    )
    refund = AsyncMock(return_value=(True, 15))
    notice = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation_and_refund", refund)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=failed))
    monkeypatch.setattr(miniapp_routes, "_deliver_pending_neironych_video_notice", notice)
    await miniapp_routes._reconcile_generation_status(AsyncMock(), gen)
    assert refund.await_args.kwargs["expected_task_id"] == gen.task_id
    assert "video_notice_kind" not in refund.await_args.kwargs
    notice.assert_not_awaited()
