from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes  # noqa: F401 - initialise API route/module imports
from db import repository as repo
from db.models import GenerationStatus, GenerationType


def _row(*, kind="done"):
    return SimpleNamespace(
        id=345, user_id=22, gen_type=GenerationType.video,
        status=GenerationStatus.done if kind == "done" else GenerationStatus.failed,
        task_id="neironych:provider-id", source_feed_gen_id=None,
        credits_spent=42, input_params=json.dumps({
            "resolution": "720p", "neironych_video_notice": {
                "kind": kind, "state": "pending", "attempts": 0,
            },
        }), result_url="https://example.test/clip.mp4",
    )


class FakeRowResult:
    def __init__(self, row):
        self.row = row

    def scalar_one_or_none(self):
        return self.row

    def scalar_one(self):
        return self.row


class FakeSession:
    def __init__(self, row):
        self.row = row
        self.statements = []
        self.commit = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, statement):
        self.statements.append(statement)
        return FakeRowResult(self.row)


@pytest.mark.asyncio
async def test_notice_claim_is_single_winner_and_success_is_durable():
    row = _row()
    session = FakeSession(row)
    claim = await repo.claim_neironych_video_notice(session, row.id)
    assert claim and claim.kind == "done" and claim.attempt == 1
    assert await repo.claim_neironych_video_notice(session, row.id) is None
    assert await repo.complete_neironych_video_notice(
        session, row.id, claim.token, delivered=True
    ) is True
    state = json.loads(row.input_params)["neironych_video_notice"]
    assert state["state"] == "sent" and state["sent_at"]
    assert await repo.claim_neironych_video_notice(session, row.id) is None
    assert json.loads(row.input_params)["resolution"] == "720p"


@pytest.mark.asyncio
async def test_notice_retries_with_backoff_and_stale_token_is_rejected():
    row = _row(kind="failed")
    session = FakeSession(row)
    first = await repo.claim_neironych_video_notice(session, row.id)
    assert first
    assert await repo.complete_neironych_video_notice(
        session, row.id, first.token, delivered=False
    )
    notice = json.loads(row.input_params)["neironych_video_notice"]
    assert notice["state"] == "pending" and notice["retry_at"]
    assert await repo.claim_neironych_video_notice(session, row.id) is None

    state = json.loads(row.input_params)
    state["neironych_video_notice"]["retry_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    ).isoformat()
    row.input_params = json.dumps(state)
    second = await repo.claim_neironych_video_notice(session, row.id)
    assert second and second.attempt == 2
    assert second.token != first.token
    assert not await repo.complete_neironych_video_notice(
        session, row.id, first.token, delivered=True
    )
    assert await repo.complete_neironych_video_notice(
        session, row.id, second.token, delivered=True
    )
    assert json.loads(row.input_params)["neironych_video_notice"]["state"] == "sent"


@pytest.mark.asyncio
async def test_expired_delivery_claim_is_recovered_after_restart():
    row = _row()
    session = FakeSession(row)
    first = await repo.claim_neironych_video_notice(session, row.id)
    state = json.loads(row.input_params)
    state["neironych_video_notice"]["claimed_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=2)
    ).isoformat()
    row.input_params = json.dumps(state)
    second = await repo.claim_neironych_video_notice(session, row.id, lease_seconds=60)
    assert second and second.token != first.token and second.attempt == 2


@pytest.mark.asyncio
async def test_web_origin_never_claims_telegram_delivery():
    row = _row()
    row.task_id = "web:neironych:provider-id"
    assert await repo.claim_neironych_video_notice(FakeSession(row), row.id) is None


@pytest.mark.asyncio
async def test_video_completion_commits_delivery_pending_in_same_sql_transition(monkeypatch):
    from sqlalchemy.sql.dml import Update

    row = _row()
    row.status = GenerationStatus.processing
    row.input_params = json.dumps({"duration": 8})
    session = FakeSession(row)
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(return_value="https://example.test/local.mp4"))
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())

    finished = await repo.finish_generation(
        session, row.id, "https://example.test/local.mp4",
        expected_task_id=row.task_id, queue_neironych_video_notice=True,
    )
    assert finished is row
    updates = [statement for statement in session.statements if isinstance(statement, Update)]
    assert len(updates) == 1
    assert updates[0].table.name == "generations"
    from sqlalchemy.dialects.postgresql import dialect

    params = updates[0].compile(dialect=dialect()).params
    meta = json.loads(params["input_params"])
    assert meta["neironych_video_notice"]["kind"] == "done"
    assert meta["neironych_video_notice"]["state"] == "pending"
    assert meta["duration"] == 8
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_terminal_refund_and_failure_notice_are_one_transaction(monkeypatch):
    row = _row(kind="failed")
    row.status = GenerationStatus.processing
    row.input_params = "{}"
    session = FakeSession(row)
    recorded = AsyncMock()
    monkeypatch.setattr(repo, "_insert_credit_ledger", recorded)
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())

    original_execute = session.execute
    async def execute(stmt):
        if getattr(getattr(stmt, "table", None), "name", None) == "users":
            return FakeRowResult(120.0)
        return await original_execute(stmt)
    session.execute = execute

    success, credits = await repo.fail_generation_and_refund(
        session, row.id, "Provider terminal error",
        expected_task_id=row.task_id,
        refund_note="reconcile:neironych_provider_failed",
        video_notice_kind="failed",
        provider_review={
            "state": "pending",
            "reason": "timeout_provider_unconfirmed",
            "original_task_id": row.task_id,
        },
    )
    assert success is True and credits == 42
    assert row.status == GenerationStatus.failed
    params = json.loads(row.input_params)
    assert params["refund_applied"] is True
    assert params["neironych_video_notice"]["kind"] == "failed"
    assert params["neironych_video_notice"]["state"] == "pending"
    assert params["seedance_refund_provider_review"]["state"] == "pending"
    assert params["seedance_refund_provider_review"]["original_task_id"] == row.task_id
    assert recorded.await_count == 1
    assert recorded.await_args.kwargs["delta"] == 42
    session.commit.assert_awaited_once()
    assert (await repo.fail_generation_and_refund(
        session, row.id, "repeat callback", video_notice_kind="failed"
    )) == (False, 0.0)
    assert recorded.await_count == 1


@pytest.mark.asyncio
async def test_permanent_delivery_failures_stop_at_dead_letter(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_NOTICE_MAX_ATTEMPTS", 2)
    row = _row(kind="failed")
    session = FakeSession(row)
    for attempt in (1, 2):
        claimed = await repo.claim_neironych_video_notice(session, row.id)
        assert claimed and claimed.attempt == attempt
        assert await repo.complete_neironych_video_notice(
            session, row.id, claimed.token, delivered=False
        )
        status = json.loads(row.input_params)["neironych_video_notice"]
        if attempt == 1:
            assert status["state"] == "pending"
            status["retry_at"] = (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat()
            params = json.loads(row.input_params)
            params["neironych_video_notice"] = status
            row.input_params = json.dumps(params)
    status = json.loads(row.input_params)["neironych_video_notice"]
    assert status["state"] == "dead_letter"
    assert status["failed_at"]
    assert await repo.claim_neironych_video_notice(session, row.id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "sending"])
async def test_expired_or_pending_notice_exhausted_attempts_cannot_reclaim(monkeypatch, state):
    from core.config import settings

    monkeypatch.setattr(settings, "NEIRONYCH_VIDEO_NOTICE_MAX_ATTEMPTS", 2)
    row = _row()
    metadata = json.loads(row.input_params)
    notice = metadata["neironych_video_notice"]
    notice["state"] = state
    notice["attempts"] = 2
    if state == "sending":
        notice["token"] = "abandoned"
        notice["claimed_at"] = (datetime.now(timezone.utc)-timedelta(hours=2)).isoformat()
    metadata["neironych_video_notice"] = notice
    row.input_params = json.dumps(metadata)
    session = FakeSession(row)

    assert await repo.claim_neironych_video_notice(session, row.id, lease_seconds=60) is None
    saved = json.loads(row.input_params)["neironych_video_notice"]
    assert saved["state"] == "dead_letter"
    assert saved["attempts"] == 2
    assert saved.get("failed_at")
    assert "token" not in saved
    assert "claimed_at" not in saved
    assert await repo.claim_neironych_video_notice(session, row.id) is None


@pytest.mark.asyncio
async def test_unbound_submission_timeout_receipt_is_claimable_and_idempotent():
    row = _row(kind="failed")
    row.task_id = "neironych-submit:request-before-provider-id"
    session = FakeSession(row)
    claim = await repo.claim_neironych_video_notice(session, row.id)
    assert claim and claim.kind == "failed"
    assert await repo.claim_neironych_video_notice(session, row.id) is None
    assert await repo.complete_neironych_video_notice(
        session, row.id, claim.token, delivered=True,
    )
    assert json.loads(row.input_params)["neironych_video_notice"]["state"] == "sent"
