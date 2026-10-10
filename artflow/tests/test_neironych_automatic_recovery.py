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

    async def rollback(self):
        self.sync.rollback()

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
    r.review.assert_not_awaited()

    # Native pending without an error is not proof that submission recovered.
    r.client.get_video.return_value = provider_status()
    with r.db() as db:
        ids = await scheduler._pick_ids(db, scheduler._eligible_video_query(), scheduler._ScanCursor(), 4)
        assert ids == [73]
        pending = await run_reconciler(db)
        assert public_generation_status(pending) == "reconciliation_required"
        assert json.loads(pending.input_params)[RECONCILIATION_KEY]["required"] is True
        assert db.sync.get(User, 42).credits == 100
    r.review.assert_not_awaited()
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
    r.review.assert_not_awaited()
    r.done.assert_not_awaited()
    r.failed.assert_not_awaited()
    r.client.create_video.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('lookup_result', [None, TimeoutError('synthetic GET failure'), 'discovered-id'])
async def test_lost_response_identity_survives_restart_without_repost_or_refund(recovery, monkeypatch, lookup_result):
    from core import seedance_reconciliation as recovery_core
    request_id = 'c150cc69-0350-43aa-a4fc-a6b17388ec10'
    r = recovery
    monkeypatch.setattr(recovery_core, 'pause_neironych_route', AsyncMock())
    lookup = AsyncMock(side_effect=lookup_result) if isinstance(lookup_result, Exception) else AsyncMock(return_value=lookup_result)
    monkeypatch.setattr(neironych_seedance_runtime, 'lookup_submission', lookup)
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        assert await repo.begin_seedance_submission(db, 73, request_id, 'synthetic-idem', 'a' * 64, product_model=gen.model)
    # New engine/session simulates crash after durable marker, before response.
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        assert list((await db.execute(scheduler._eligible_video_query())).scalars()) == [73]
        assert not await repo.begin_seedance_submission(db, 73, request_id, 'synthetic-idem', 'a' * 64, product_model=gen.model)
        recovered = await recovery_core.recover_submission_identity(db, gen)
        expected = 'neironych:discovered-id' if lookup_result == 'discovered-id' else 'neironych-submit:' + request_id
        assert recovered.task_id == expected
        assert db.sync.get(User, 42).credits == 100
        assert list(db.sync.scalars(select(CreditLedgerEntry))) == []
        assert public_generation_status(recovered) == ('processing' if lookup_result == 'discovered-id' else 'reconciliation_required')
        # A late create response cannot supersede the already bound identity.
        if lookup_result == 'discovered-id':
            assert not await repo.bind_seedance_submission_task(db, 73, request_id, 'neironych:late-other')
            assert not await repo.mark_seedance_submission_unknown(db, 73, request_id)
    lookup.assert_awaited_once_with(request_id, product_model='bytedance/seedance-2-5', idempotency_key='synthetic-idem')
    r.client.create_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_lookup_race_with_terminal_commit_never_reopens_or_refunds(recovery, monkeypatch):
    from core import seedance_reconciliation as recovery_core
    r = recovery
    request_id = 'c150cc69-0350-43aa-a4fc-a6b17388ec10'
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        assert await repo.begin_seedance_submission(db, 73, request_id, 'synthetic-idem', 'a' * 64, product_model=gen.model)

    async def found_after_terminal(*args, **kwargs):
        with r.db() as other:
            row = other.sync.get(Generation, 73)
            row.status = GenerationStatus.done
            row.task_id = 'neironych:already-finished'
            await other.commit()
        return 'late-result'

    monkeypatch.setattr(neironych_seedance_runtime, 'lookup_submission', found_after_terminal)
    with r.db() as db:
        result = await recovery_core.recover_submission_identity(db, db.sync.get(Generation, 73))
        assert result.status == GenerationStatus.done
        assert result.task_id == 'neironych:already-finished'
        assert db.sync.get(User, 42).credits == 100
        assert list(db.sync.scalars(select(CreditLedgerEntry))) == []
    r.client.create_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_submission_callback_commits_once_and_preserves_web_surface(recovery):
    from api.neironych_seedance import NeironychSubmissionUnknown
    from core import seedance_reconciliation as recovery_core
    r = recovery
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        context = recovery_core.make_submission_context(db, gen.id, gen.model, surface='web')
        await context.before_submit('synthetic-idem', 'b' * 64)
        assert context.started
        with r.db() as check:
            persisted = check.sync.get(Generation, 73)
            assert persisted.task_id == 'web:neironych-submit:' + context.client_request_id
        with pytest.raises(NeironychSubmissionUnknown):
            await context.before_submit('synthetic-idem', 'b' * 64)
        assert await recovery_core.persist_submission_result(db, 73, context, 'neironych:response', surface='web')
        assert gen.task_id == 'web:neironych:response'


@pytest.mark.asyncio
async def test_failed_prepost_commit_does_not_allow_post_or_mark_context_started(recovery):
    from core import seedance_reconciliation as recovery_core
    r = recovery
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        context = recovery_core.make_submission_context(db, gen.id, gen.model)
        db.commit = AsyncMock(side_effect=RuntimeError('synthetic failed commit'))
        with pytest.raises(RuntimeError, match='synthetic failed commit'):
            await context.before_submit('synthetic-idem', 'b' * 64)
        assert not context.started
    with r.db() as check:
        assert check.sync.get(Generation, 73).task_id is None
    r.client.create_video.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', ['done', 'failed'])
async def test_discovered_identity_uses_native_settlement_once(recovery, monkeypatch, terminal):
    from core import seedance_reconciliation as recovery_core
    r = recovery
    request_id = 'c150cc69-0350-43aa-a4fc-a6b17388ec10'
    lookup = AsyncMock(return_value='discovered-id')
    monkeypatch.setattr(neironych_seedance_runtime, 'lookup_submission', lookup)
    monkeypatch.setattr(recovery_core, 'pause_neironych_route', AsyncMock())
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        assert await repo.begin_seedance_submission(db, 73, request_id, 'synthetic-idem', 'b' * 64, product_model=gen.model)
    r.client.get_video.return_value = provider_status(terminal, 'confirmed failure' if terminal == 'failed' else '')
    with r.db() as db:
        result = await run_reconciler(db)
        assert result.status.value == terminal
        assert db.sync.get(User, 42).credits == (128 if terminal == 'failed' else 100)
        assert len(list(db.sync.scalars(select(CreditLedgerEntry)))) == int(terminal == 'failed')
    with r.db() as db:
        assert (await run_reconciler(db)).status.value == terminal
        assert not await repo.bind_seedance_submission_task(db, 73, request_id, 'neironych:late')
        assert db.sync.get(User, 42).credits == (128 if terminal == 'failed' else 100)
        assert len(list(db.sync.scalars(select(CreditLedgerEntry)))) == int(terminal == 'failed')
    lookup.assert_awaited_once()
    r.client.get_video.assert_awaited_once()
    r.client.create_video.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsubmitted_fallback_update_cannot_overwrite_durable_marker(recovery):
    r = recovery
    request_id = 'c150cc69-0350-43aa-a4fc-a6b17388ec10'
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        assert await repo.begin_seedance_submission(db, 73, request_id, 'synthetic-idem', 'a' * 64, product_model=gen.model)
        assert not await repo.update_generation_task(db, 73, 'kie:stale', expected_task_id='')
        assert gen.task_id == 'neironych-submit:' + request_id
        assert db.sync.get(User, 42).credits == 100
        assert list(db.sync.scalars(select(CreditLedgerEntry))) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('marker_state', ['none', 'same', 'other', 'bound', 'done'])
async def test_proven_prepost_failure_refunds_only_owned_unsubmitted_attempt(recovery, marker_state):
    from core import seedance_reconciliation as recovery_core
    r = recovery
    request_id = 'c150cc69-0350-43aa-a4fc-a6b17388ec10'
    context = SimpleNamespace(client_request_id=request_id, started=False)
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        if marker_state != 'none':
            owned_id = request_id if marker_state != 'other' else 'd150cc69-0350-43aa-a4fc-a6b17388ec10'
            assert await repo.begin_seedance_submission(db, 73, owned_id, 'synthetic-idem', 'a' * 64, product_model=gen.model)
        if marker_state == 'bound':
            assert await repo.bind_seedance_submission_task(db, 73, request_id, 'neironych:paid')
        if marker_state == 'done':
            gen.status = GenerationStatus.done
            await db.commit()
        expected_refund = marker_state in {'none', 'same'}
        assert await recovery_core.handle_submission_not_sent(db, 73, context) is expected_refund
        assert not await recovery_core.handle_submission_not_sent(db, 73, context)
        assert db.sync.get(User, 42).credits == (128 if expected_refund else 100)
        assert len(list(db.sync.scalars(select(CreditLedgerEntry)))) == int(expected_refund)


@pytest.mark.asyncio
@pytest.mark.parametrize("review_state", ["pending", "remote_completed_pending_finance", "needs_admin_resolution"])
async def test_refunded_unknown_supplier_job_blocks_only_own_account_paid_submission(
    recovery, review_state,
):
    from db import repository as repo

    r = recovery
    request_id = "c150cc69-0350-43aa-a4fc-a6b17388ec10"
    with r.db() as db:
        # A previous 1-hour refund must not be recycled into more charges at
        # an upstream whose original task might still be paid/in progress.
        previous = Generation(
            id=111, user_id=42, model="bytedance/seedance-2-5",
            gen_type=GenerationType.video, status=GenerationStatus.failed,
            prompt="earlier video", task_id="neironych:unknown-original",
            input_params=json.dumps({"seedance_refund_provider_review": {
                "state": review_state, "original_task_id": "neironych:unknown-original",
            }}), credits_spent=28,
        )
        db.add(previous)
        current = db.sync.get(Generation, 73)
        current.task_id = None
        await db.commit()
        with pytest.raises(ValueError, match="refunded Seedance"):
            await repo.begin_seedance_submission(
                db, current.id, request_id, "idem-guard", "a" * 64,
                product_model=current.model,
            )
        # No paid Neironych request has been started.
        assert current.task_id is None
        assert repo.SEEDANCE_SUBMISSION_KEY not in repo.parse_input_params(current.input_params)
        assert db.sync.get(User, 42).credits == 100

        # Other customers remain unaffected, even for the SAME model.
        db.add(User(id=55, tg_id=5500, credits=120, referral_code="other-user"))
        other = Generation(
            id=112, user_id=55, model=current.model,
            gen_type=GenerationType.video, status=GenerationStatus.pending,
            task_id=None, prompt="unrelated", input_params="{}", credits_spent=30,
        )
        db.add(other)
        await db.commit()
        assert await repo.begin_seedance_submission(
            db, 112, request_id, "idem-other", "a" * 64,
            product_model=other.model,
        )
        assert other.task_id == "neironych-submit:" + request_id


@pytest.mark.asyncio
async def test_operator_settles_supplier_review_with_audit_but_without_wallet_mutation(recovery):
    from db import repository as repo
    with recovery.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.status = GenerationStatus.failed
        gen.input_params = json.dumps({
            "refund_applied": True,
            "seedance_refund_provider_review": {
                "state": "needs_admin_resolution",
                "original_task_id": gen.task_id,
                "checks": 96,
            },
        })
        await db.commit()
        before=db.sync.get(User,42).credits
        assert await repo.resolve_refunded_seedance_provider_review(
            db, 73, resolution="confirmed_not_accepted",
            admin_tg_id=339795159,
            note="Confirmed in upstream ArgoLink audit: no task was created.",
        )
        after=repo.parse_input_params(gen.input_params)["seedance_refund_provider_review"]
        assert after["state"]=="settled"
        assert after["resolution"]=="confirmed_not_accepted"
        assert after["resolved_by_admin_tg_id"]==339795159
        assert after["resolved_at"] and after["resolution_note"]
        assert db.sync.get(User,42).credits==before
        assert not await repo._has_pending_refunded_seedance_review(db,42)
        assert not await repo.resolve_refunded_seedance_provider_review(
            db,73,resolution="confirmed_not_accepted",
            admin_tg_id=339795159,note="The same admin operation repeated.",
        )


@pytest.mark.asyncio
async def test_foreground_review_is_silent_and_does_not_change_money(recovery, monkeypatch):
    from bot.handlers import video_gen
    from core import seedance_reconciliation as recovery_core

    r = recovery
    request_id = "c150cc69-0350-43aa-a4fc-a6b17388ec10"
    monkeypatch.setattr(recovery_core, "pause_neironych_route", AsyncMock())
    message = SimpleNamespace(edit_text=AsyncMock())
    state = AsyncMock()
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.task_id = None
        await db.commit()
        assert await repo.begin_seedance_submission(
            db, 73, request_id, "synthetic-idem", "a" * 64, product_model=gen.model,
        )
        assert await repo.mark_seedance_submission_unknown(db, 73, request_id)
        await video_gen._show_video_submission_review(message, state, db, 73)
        notice = repo.parse_input_params(gen.input_params)[repo.NEIRONYCH_VIDEO_NOTICE_KEY]
        assert notice["state"] == "suppressed" and notice["attempts"] == 0
    message.edit_text.assert_not_awaited()
    state.clear.assert_awaited_once()
    with r.db() as db:
        assert not await miniapp_routes._deliver_pending_neironych_video_notice(db, 73)
        assert db.sync.get(User, 42).credits == 100
        assert list(db.sync.scalars(select(CreditLedgerEntry))) == []
    r.review.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreground_review_does_not_touch_claimed_legacy_notice(recovery):
    from bot.handlers import video_gen
    r = recovery
    message, state = SimpleNamespace(edit_text=AsyncMock()), AsyncMock()
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.input_params = json.dumps({repo.NEIRONYCH_VIDEO_NOTICE_KEY: {
            "kind": "reconciliation", "state": "sending", "token": "old-claim", "attempts": 1,
        }})
        await db.commit()
        await video_gen._show_video_submission_review(message, state, db, 73)
        message.edit_text.assert_not_awaited()
        assert not await miniapp_routes._deliver_pending_neironych_video_notice(db, 73)
        assert repo.parse_input_params(gen.input_params)[repo.NEIRONYCH_VIDEO_NOTICE_KEY]["state"] == "suppressed"
    state.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_foreground_review_edit_never_consumes_terminal_notice(recovery):
    from bot.handlers import video_gen

    r = recovery
    message, state = SimpleNamespace(edit_text=AsyncMock()), AsyncMock()
    with r.db() as db:
        gen = db.sync.get(Generation, 73)
        gen.status = GenerationStatus.failed
        params = repo.parse_input_params(gen.input_params)
        params[repo.NEIRONYCH_VIDEO_NOTICE_KEY] = repo._new_neironych_video_notice("failed")
        gen.input_params = json.dumps(params)
        await db.commit()
        before = gen.input_params
        await video_gen._show_video_submission_review(message, state, db, 73)
        assert gen.input_params == before
        message.edit_text.assert_not_awaited()
        assert await miniapp_routes._deliver_pending_neironych_video_notice(db, 73)
    r.failed.assert_awaited_once()
    state.clear.assert_awaited_once()
