"""Real SQLite recovery roundtrips; no provider POST or Telegram I/O.

These tests verify persisted state/outbox/ledger behavior, not PostgreSQL lock
concurrency. The existing guarded repository tests cover that separate boundary.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from api import miniapp_routes, neironych_seedance_runtime
from core import neironych_video_reconcile_scheduler as scheduler
from core.seedance_reconciliation import RECONCILIATION_KEY, public_generation_status
from db import repository as repo
from db.models import Base, CreditLedgerEntry, Generation, GenerationStatus, GenerationType, User


class LocalSession:
    def __init__(self, sync):
        self.sync = sync

    def add(self, row):
        self.sync.add(row)

    async def execute(self, statement):
        return self.sync.execute(statement)

    async def commit(self):
        self.sync.commit()

    async def flush(self):
        self.sync.flush()


@pytest.fixture
def recovery(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'recovery.db'}"
    engine = create_engine(url)
    Base.metadata.create_all(engine, tables=[User.__table__, Generation.__table__, CreditLedgerEntry.__table__])
    with Session(engine) as sync:
        sync.add(User(id=42, tg_id=4200, credits=100, referral_code="synthetic-recovery"))
        sync.add(Generation(
            id=73, user_id=42, model="bytedance/seedance-2-5",
            gen_type=GenerationType.video, status=GenerationStatus.processing,
            task_id="neironych:synthetic-video-id", prompt="synthetic scene",
            input_params=json.dumps({"duration": 7}), credits_spent=28,
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ))
        sync.commit()
    engine.dispose()

    @contextmanager
    def restarted_session():
        # New engine/identity map per cycle; no prior in-memory row or cursor.
        fresh_engine = create_engine(url)
        try:
            with Session(fresh_engine, expire_on_commit=False) as sync:
                yield LocalSession(sync)
        finally:
            fresh_engine.dispose()

    @asynccontextmanager
    async def gate(_task):
        yield True

    async def download(_request_id, path, **_kwargs):
        path.write_bytes(b"synthetic-mp4-fixture")

    client = SimpleNamespace(
        get_video=AsyncMock(), download_content_to=AsyncMock(side_effect=download),
        aclose=AsyncMock(), create_video=AsyncMock(),
    )
    publish, pause = AsyncMock(), AsyncMock()
    review, done, failed = (AsyncMock(return_value=True) for _ in range(3))
    monkeypatch.setattr(neironych_seedance_runtime, "_client", lambda: client)
    monkeypatch.setattr(neironych_seedance_runtime, "save_public_file", lambda *_args, **_kwargs: "https://example.test/result.mp4")
    monkeypatch.setattr(miniapp_routes, "neironych_video_poll_guard", gate)
    monkeypatch.setattr(miniapp_routes, "pause_neironych_route", pause)
    monkeypatch.setattr(repo, "_publish_generation_update", publish)
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    monkeypatch.setattr(miniapp_routes, "_notify_neironych_video_reconciliation_in_bot", review)
    monkeypatch.setattr(miniapp_routes, "_notify_reconciled_video_result_in_bot", done)
    monkeypatch.setattr(miniapp_routes, "_notify_reconciled_video_failure_in_bot", failed)
    return SimpleNamespace(db=restarted_session, client=client, publish=publish, pause=pause, review=review, done=done, failed=failed)


def provider_status(status="pending", error=""):
    return SimpleNamespace(status=status, error=error, failed=status == "failed", done=status == "done")


async def run_reconciler(db):
    gen = db.sync.get(Generation, 73)
    # SQLite strips tzinfo; production PostgreSQL stores timezone-aware dates.
    gen.created_at = gen.created_at.replace(tzinfo=timezone.utc)
    return await miniapp_routes._reconcile_generation_status(db, gen)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["done", "failed"])
async def test_uncertain_video_recovers_automatically_after_restart_exactly_once(recovery, terminal):
    r = recovery
    r.client.get_video.return_value = provider_status(error="submission_outcome_unknown")
    with r.db() as db:
        assert list((await db.execute(scheduler._eligible_video_query())).scalars()) == [73]
        first = await run_reconciler(db)
        assert public_generation_status(first) == "reconciliation_required"
        assert first.status == GenerationStatus.processing
        assert db.sync.get(User, 42).credits == 100
        assert list(db.sync.scalars(select(CreditLedgerEntry))) == []
    r.review.assert_awaited_once()

    # Native pending without an error is not proof that submission recovered.
    r.client.get_video.return_value = provider_status()
    with r.db() as db:
        ids = await scheduler._pick_ids(db, scheduler._eligible_video_query(), scheduler._ScanCursor(), 4)
        assert ids == [73]
        pending = await run_reconciler(db)
        assert public_generation_status(pending) == "reconciliation_required"
        assert json.loads(pending.input_params)[RECONCILIATION_KEY]["required"] is True
        assert db.sync.get(User, 42).credits == 100
    r.review.assert_awaited_once()
    r.pause.assert_awaited_once()
    r.done.assert_not_awaited()
    r.failed.assert_not_awaited()

    r.client.get_video.return_value = provider_status(terminal, "confirmed failure" if terminal == "failed" else "")
    with r.db() as db:
        result = await run_reconciler(db)
        assert public_generation_status(result) == terminal
        assert json.loads(result.input_params)[repo.NEIRONYCH_VIDEO_NOTICE_KEY]["state"] == "sent"
        assert db.sync.get(User, 42).credits == (128 if terminal == "failed" else 100)
        ledger = list(db.sync.scalars(select(CreditLedgerEntry)))
        assert len(ledger) == (1 if terminal == "failed" else 0)
        if ledger:
            assert ledger[0].delta == 28 and ledger[0].source_id == "73"

    # Restart after settlement cannot poll, refund or deliver again.
    with r.db() as db:
        assert list((await db.execute(scheduler._eligible_video_query())).scalars()) == []
        assert (await run_reconciler(db)).status.value == terminal
        assert not await miniapp_routes._deliver_pending_neironych_video_notice(db, 73)
        assert db.sync.get(User, 42).credits == (128 if terminal == "failed" else 100)
        assert len(list(db.sync.scalars(select(CreditLedgerEntry)))) == (1 if terminal == "failed" else 0)
    assert r.client.get_video.await_count == 3
    assert r.done.await_count == (1 if terminal == "done" else 0)
    assert r.failed.await_count == (1 if terminal == "failed" else 0)
    r.client.create_video.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["pending", "transport_error"])
@pytest.mark.parametrize("already_uncertain", [False, True])
async def test_ambiguous_poll_neither_creates_nor_clears_uncertainty(recovery, response, already_uncertain):
    r = recovery
    if already_uncertain:
        r.client.get_video.return_value = provider_status(error="submission_outcome_unknown")
        with r.db() as db:
            await run_reconciler(db)
    r.client.get_video.side_effect = TimeoutError("synthetic GET timeout") if response == "transport_error" else None
    r.client.get_video.return_value = provider_status()
    with r.db() as db:
        gen = await run_reconciler(db)
        assert public_generation_status(gen) == ("reconciliation_required" if already_uncertain else "processing")
        assert db.sync.get(User, 42).credits == 100
        assert list(db.sync.scalars(select(CreditLedgerEntry))) == []
        assert list((await db.execute(scheduler._eligible_video_query())).scalars()) == [73]
    assert r.review.await_count == int(already_uncertain)
    r.done.assert_not_awaited()
    r.failed.assert_not_awaited()
    r.client.create_video.assert_not_awaited()
