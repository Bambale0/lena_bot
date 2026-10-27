"""HTTP 5xx customer refunds retain supplier accounting after late outcomes."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from api import image_http_failure, neironych_image_adapter, nexus_image_adapter
from api.image_http_failure import settle_image_http_5xx
from api.nexusapi_client import NexusApiError
from db import repository as repo
from db.models import Base, CreditLedgerEntry, Generation, GenerationStatus, GenerationType, User


class LocalAsyncSession:
    def __init__(self, sync: Session):
        self.sync = sync

    async def execute(self, query):
        return self.sync.execute(query)

    async def commit(self):
        self.sync.commit()

    async def rollback(self):
        self.sync.rollback()

    async def flush(self):
        self.sync.flush()

    def add(self, entry):
        self.sync.add(entry)


@pytest.fixture
def image_review_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    engine = create_engine("sqlite:///" + str(tmp_path / "image-review.db"))
    Base.metadata.create_all(
        engine, tables=[User.__table__, Generation.__table__, CreditLedgerEntry.__table__],
    )
    with Session(engine) as session:
        session.add(User(id=77, tg_id=7700, credits=10, referral_code="synthetic-image-review"))
        session.add(Generation(
            id=89, user_id=77, model="nano-banana-pro", gen_type=GenerationType.image,
            status=GenerationStatus.processing, task_id=None, prompt="synthetic scene",
            credits_spent=1.5, input_params="{}", created_at=datetime.now(timezone.utc),
        ))
        session.commit()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_nexus_pro_5xx_refund_and_late_outcome_are_auditable(image_review_db, monkeypatch):
    admin_alert = AsyncMock()
    monkeypatch.setattr(image_http_failure, "send_admin_alert_once", admin_alert, raising=False)
    with Session(image_review_db, expire_on_commit=False) as session:
        db = LocalAsyncSession(session)
        result = await settle_image_http_5xx(
            db, 89, NexusApiError("HTTP 502", status_code=502), provider="nexus",
        )
        assert result == (True, 1.5)
        generation = session.get(Generation, 89)
        marker = repo.parse_input_params(generation.input_params)[repo.IMAGE_REFUND_PROVIDER_REVIEW_KEY]
        assert marker["state"] == "pending"
        assert marker["provider"] == "nexus"
        assert session.get(User, 77).credits == 11.5
        assert [(row.entry_type, row.delta) for row in session.scalars(select(CreditLedgerEntry))] == [
            ("generation_refund", 1.5),
        ]
        assert await settle_image_http_5xx(
            db, 89, NexusApiError("HTTP 502", status_code=502), provider="nexus",
        ) == (False, 0.0)
        assert await repo.record_late_image_provider_outcome(
            db, 89, provider="nexus", provider_task_id="nexus:late-task", succeeded=True,
        )
        marker = repo.parse_input_params(generation.input_params)[repo.IMAGE_REFUND_PROVIDER_REVIEW_KEY]
        assert marker["state"] == "remote_completed_pending_finance"
        assert marker["provider_task_id"] == "nexus:late-task"
        assert not await repo.record_late_image_provider_outcome(
            db, 89, provider="nexus", provider_task_id="nexus:late-task", succeeded=True,
        )
        assert await repo.resolve_refunded_image_provider_review(
            db, 89, resolution="cost_reconciled", admin_tg_id=123,
            note="Supplier statement reconciled for synthetic task",
        )
        marker = repo.parse_input_params(generation.input_params)[repo.IMAGE_REFUND_PROVIDER_REVIEW_KEY]
        assert marker["state"] == "settled"
        assert marker["resolved_by_admin_tg_id"] == 123
        assert session.get(User, 77).credits == 11.5
        assert len(list(session.scalars(select(CreditLedgerEntry)))) == 1
        admin_alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_nexus_5xx_does_not_refund_after_callback_binds_task(image_review_db):
    with Session(image_review_db, expire_on_commit=False) as session:
        generation = session.get(Generation, 89)
        generation.task_id = "nexus:already-bound"
        session.commit()
        result = await settle_image_http_5xx(
            LocalAsyncSession(session), 89,
            NexusApiError("HTTP 503", status_code=503), provider="nexus",
        )
        assert result == (False, 0.0)
        assert generation.status == GenerationStatus.processing
        assert session.get(User, 77).credits == 10
        assert list(session.scalars(select(CreditLedgerEntry))) == []


@pytest.mark.asyncio
async def test_pre_review_5xx_refund_can_be_registered_once(image_review_db):
    with Session(image_review_db, expire_on_commit=False) as session:
        generation = session.get(Generation, 89)
        generation.status = GenerationStatus.failed
        generation.task_id = "neironych-image:32929649-2aa4-4736-90e1-d5dc568dcb39"
        generation.input_params = '{"refund_applied":true,"refund_note":"image:http_5xx:neironych:retroactive"}'
        session.commit()
        db = LocalAsyncSession(session)
        assert await repo.register_legacy_image_5xx_supplier_review(
            db, 89, provider="neironych",
        )
        marker = repo.parse_input_params(generation.input_params)[repo.IMAGE_REFUND_PROVIDER_REVIEW_KEY]
        assert marker["state"] == "pending"
        assert marker["original_task_id"] == generation.task_id
        assert not await repo.register_legacy_image_5xx_supplier_review(
            db, 89, provider="neironych",
        )
        assert session.get(User, 77).credits == 10
        assert list(session.scalars(select(CreditLedgerEntry))) == []


@pytest.mark.asyncio
async def test_image_supplier_review_queue_is_admin_only():
    from api.web.admin import (
        _unsettled_image_supplier_reviews_query,
        admin_list_unsettled_image_supplier_reviews,
    )

    statement = str(_unsettled_image_supplier_reviews_query(50).compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True},
    ))
    assert repo.IMAGE_REFUND_PROVIDER_REVIEW_KEY in statement
    assert "remote_completed_pending_finance" in statement
    session = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("unauthorized DB read")))
    result = await admin_list_unsettled_image_supplier_reviews(
        limit=20, session=session, user=None,
    )
    assert result.status_code == 401
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_refunded_neironych_image_poll_records_late_supplier_result(monkeypatch):
    from core import neironych_image_reconcile_scheduler as scheduler

    request_id = "32929649-2aa4-4736-90e1-d5dc568dcb39"
    task_id = neironych_image_adapter.encode_task_id(request_id)
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [(89, task_id)])),
        rollback=AsyncMock(),
    )
    class Context:
        async def __aenter__(self):
            return session
        async def __aexit__(self, exc_type, exc, tb):
            return False
    monkeypatch.setattr(scheduler, "AsyncSessionLocal", Context)
    monkeypatch.setattr(scheduler, "_review_last_id", 0)
    fetch = AsyncMock(return_value={"status": "completed", "result_url": "https://example.test/result.jpg"})
    record = AsyncMock(return_value=True)
    alert = AsyncMock()
    monkeypatch.setattr(scheduler.neironych_image_adapter, "fetch_nano_banana21_status", fetch)
    monkeypatch.setattr(scheduler.repo, "record_late_image_provider_outcome", record)
    monkeypatch.setattr(scheduler, "send_admin_alert_once", alert, raising=False)

    assert await scheduler.reconcile_refunded_neironych_images_once() == 1
    fetch.assert_awaited_once_with(request_id)
    assert record.await_args.kwargs == {
        "provider": "neironych", "provider_task_id": task_id, "succeeded": True,
    }
    alert.assert_not_awaited()


@pytest.mark.asyncio
async def test_signed_nexus_recovery_can_find_refunded_image_without_reopening(monkeypatch):
    import main

    request_id = "5dff1a3f-846c-477c-9c2f-74fb06456685"
    marker = nexus_image_adapter.encode_submission_id(request_id)
    gen = SimpleNamespace(
        id=89, model="nano-banana-2.1", gen_type=GenerationType.image,
        status=GenerationStatus.failed,
        input_params='{"nexus_submission":{"request_id":"' + request_id + '","has_webhook":true}}',
    )
    lookup = AsyncMock(return_value=gen)
    update = AsyncMock(side_effect=AssertionError("refunded generation must remain final"))
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", lookup)
    monkeypatch.setattr(main.repo, "update_generation_task", update)
    monkeypatch.setattr(main.nexus_image_adapter, "submission_scope_matches", lambda raw: True)
    assert await main._recover_nexus_submission(AsyncMock(), request_id, "nexus:provider-task") is gen
    lookup.assert_awaited_once_with(lookup.await_args.args[0], marker)
    update.assert_not_awaited()
