from urllib.parse import parse_qs, urlsplit

from api import miniapp_routes  # noqa: F401 - initialize application DB import order
from core import kie_seedance_callback as c


def test_signed_kie_callback_preserves_existing_auth_and_binds_one_generation(monkeypatch):
    monkeypatch.setattr(c.settings, "KIE_WEBHOOK_HMAC_KEY", "synthetic-test-only-private-signing-key")
    url = c.callback_url_for_generation(
        "https://example.test/hooks/kie?secret=existing", 345,
    )
    parts = parse_qs(urlsplit(url).query)
    assert parts["secret"] == ["existing"]
    assert parts["apix_generation_id"] == ["345"]
    assert c.verify_generation_signature(345, parts["apix_generation_sig"][0])
    assert not c.verify_generation_signature(346, parts["apix_generation_sig"][0])


def test_unsigned_or_invalid_kie_callback_never_binds_other_generation():
    assert not c.verify_generation_signature(None, None)
    assert not c.verify_generation_signature(12, "incorrect")
    assert c.callback_url_for_generation("https://example.test/test", None) == (
        "https://example.test/test"
    )

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from db import repository as repo
from db.models import Base, CreditLedgerEntry, Generation, GenerationStatus, GenerationType, User


class LocalAsyncSession:
    """Exercise the real repository state machine on durable SQLite rows."""

    def __init__(self, sync):
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
def kie_transaction_db(tmp_path, monkeypatch):
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    engine = create_engine("sqlite:///" + str(tmp_path / "kie-refund.db"))
    Base.metadata.create_all(
        engine, tables=[User.__table__, Generation.__table__, CreditLedgerEntry.__table__],
    )
    with Session(engine) as session:
        session.add(User(id=42, tg_id=4200, credits=100, referral_code="synthetic-kie-review"))
        session.add(Generation(
            id=73, user_id=42, model="bytedance/seedance-2-5",
            gen_type=GenerationType.video, status=GenerationStatus.processing,
            task_id="neironych-submit:synthetic-before-fallback",
            prompt="synthetic scene", credits_spent=40,
            input_params="{}", created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ))
        session.commit()
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_kie_unknown_task_persisted_then_late_signed_binding_is_single_use(kie_transaction_db):
    with Session(kie_transaction_db, expire_on_commit=False) as session:
        db = LocalAsyncSession(session)
        assert await repo.register_kie_video_callback(db, 73, surface="miniapp")
        assert await repo.mark_kie_video_submission_unknown(db, 73)
        gen = session.get(Generation, 73)
        assert gen.task_id == "kie-submit:73"
        assert gen.status == GenerationStatus.processing
        assert session.get(User, 42).credits == 100
        assert list(session.scalars(select(CreditLedgerEntry))) == []

        task_id = "trusted-provider-task-123"
        matched = await repo.bind_kie_video_callback(db, 73, task_id)
        assert matched and matched.task_id == task_id
        assert matched.status == GenerationStatus.processing
        assert not await repo.mark_kie_video_submission_unknown(db, 73)
        assert await repo.bind_kie_video_callback(db, 73, "wrong-second-provider-task") is None
        assert session.get(Generation, 73).task_id == task_id
        assert session.get(User, 42).credits == 100


@pytest.mark.asyncio
async def test_kie_late_callback_after_atomic_refund_requires_admin_settlement(kie_transaction_db):
    with Session(kie_transaction_db, expire_on_commit=False) as session:
        db = LocalAsyncSession(session)
        assert await repo.register_kie_video_callback(db, 73, surface="miniapp")
        assert await repo.mark_kie_video_submission_unknown(db, 73)
        review = {
            "state": "pending", "reason": "timeout_provider_unconfirmed",
            "original_task_id": "kie-submit:73",
            "refunded_at": datetime.now(timezone.utc).isoformat(),
            "last_provider_status": "unknown", "checks": 0,
        }
        won, amount = await repo.fail_generation_and_refund(
            db, 73, "Synthetic SLA expired", expected_task_id="kie-submit:73",
            refund_note="test:kie_sla_refund", provider_review=review,
        )
        assert won and amount == 40
        assert session.get(User, 42).credits == 140
        ledger = list(session.scalars(select(CreditLedgerEntry)))
        assert len(ledger) == 1 and ledger[0].delta == 40
        assert (await repo.fail_generation_and_refund(
            db, 73, "repeat callback",
        )) == (False, 0.0)
        assert len(list(session.scalars(select(CreditLedgerEntry)))) == 1

        # The signed late callback is recorded for supplier audit only.
        assert await repo.record_late_kie_video_callback(
            db, 73, "provider-late-id", succeeded=True,
        )
        late = repo.parse_input_params(session.get(Generation, 73).input_params)
        assert late[repo.SEEDANCE_REFUND_PROVIDER_REVIEW_KEY]["state"] == (
            "remote_completed_pending_finance"
        )
        assert await repo._has_pending_refunded_seedance_review(db, 42)
        assert session.get(Generation, 73).status == GenerationStatus.failed
        assert session.get(User, 42).credits == 140

        assert await repo.resolve_refunded_seedance_provider_review(
            db, 73, resolution="cost_reconciled", admin_tg_id=100,
            note="verified supplier invoice was paid separately",
        )
        final = repo.parse_input_params(session.get(Generation, 73).input_params)
        assert final[repo.SEEDANCE_REFUND_PROVIDER_REVIEW_KEY]["state"] == "settled"
        assert not await repo._has_pending_refunded_seedance_review(db, 42)
        assert session.get(User, 42).credits == 140
        assert len(list(session.scalars(select(CreditLedgerEntry)))) == 1


def test_generation_callback_signing_ignores_exposed_url_secret(monkeypatch):
    monkeypatch.setattr(c.settings, "KIE_WEBHOOK_SECRET", "visible-secret")
    monkeypatch.setattr(c.settings, "KIE_WEBHOOK_HMAC_KEY", "private-supplier-hmac-key")
    token = parse_qs(urlsplit(c.callback_url_for_generation(
        "https://example.test/hooks/kie?secret=visible-secret", 345,
    )).query)["apix_generation_sig"][0]
    monkeypatch.setattr(c.settings, "KIE_WEBHOOK_SECRET", "attacker-knows-this")
    assert c.verify_generation_signature(345, token)
    monkeypatch.setattr(c.settings, "KIE_WEBHOOK_HMAC_KEY", "other-key")
    assert not c.verify_generation_signature(345, token)


def test_missing_dedicated_hmac_key_refuses_signatures(monkeypatch):
    monkeypatch.setattr(c.settings, "KIE_WEBHOOK_SECRET", "url-exposed-value")
    monkeypatch.setattr(c.settings, "KIE_WEBHOOK_HMAC_KEY", "")
    with pytest.raises(ValueError, match="HMAC"):
        c.callback_url_for_generation("https://example.test/hooks/kie", 345)
    assert not c.verify_generation_signature(345, "0" * 64)


@pytest.mark.asyncio
async def test_kie_callback_registration_rejects_unresolved_supplier_liability(kie_transaction_db):
    import json

    with Session(kie_transaction_db, expire_on_commit=False) as session:
        session.add(Generation(
            id=74, user_id=42, model="bytedance/seedance-2-5",
            gen_type=GenerationType.video, status=GenerationStatus.failed,
            task_id="kie-submit:74", prompt="synthetic paid work", credits_spent=40,
            input_params=json.dumps({
                repo.SEEDANCE_REFUND_PROVIDER_REVIEW_KEY: {"state": "needs_admin_resolution"},
            }),
        ))
        session.commit()
        assert not await repo.register_kie_video_callback(
            LocalAsyncSession(session), 73, surface="miniapp",
        )
        assert repo.KIE_VIDEO_CALLBACK_KEY not in repo.parse_input_params(
            session.get(Generation, 73).input_params,
        )


@pytest.mark.asyncio
async def test_terminal_signed_kie_callback_returns_loaded_generation_after_rollback(kie_transaction_db):
    with Session(kie_transaction_db, expire_on_commit=False) as session:
        row = session.get(Generation, 73)
        row.status = GenerationStatus.failed
        session.commit()
        result = await repo.bind_kie_video_callback(LocalAsyncSession(session), 73, "late-provider-id")
    # Object is detached; webhook must still inspect its terminal status.
    assert result is not None
    assert result.status == GenerationStatus.failed
