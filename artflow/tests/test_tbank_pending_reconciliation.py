"""Production-safe T-Bank catch-up decisions. No provider calls or database writes."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from scripts import fix_stuck_tbank_payments as audit
from scripts.fix_stuck_tbank_payments import decide_tbank_action, reconcile


def state(*, payment_id: str = "payment-123", status: str = "CONFIRMED",
          amount: object = 15000, success: bool = True, terminal: str = "terminal-1") -> dict:
    return {
        "Success": success, "PaymentId": payment_id, "Status": status,
        "Amount": amount, "TerminalKey": terminal,
    }


def decision(result: dict) -> tuple[str, str]:
    return decide_tbank_action(
        external_id="payment-123",
        amount_rub=150.0,
        provider_amount_minor=15000,
        state=result,
        expected_terminal_key="terminal-1",
    )


def test_confirmed_exact_payment_is_eligible_for_atomic_credit() -> None:
    assert decision(state()) == ("paid", "provider_confirmed")


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (state(payment_id="another-payment"), "payment_identity_mismatch"),
        (state(terminal="another-terminal"), "terminal_identity_mismatch"),
        (state(amount=14999), "amount_mismatch"),
        (state(amount=None), "amount_not_verifiable"),
        (state(amount="15000.00"), "amount_not_verifiable"),
        (state(success=False), "provider_not_successful"),
        (state(status="REFUNDED"), "refund_requires_separate_reconciliation"),
        (state(status="PARTIAL_REFUNDED"), "refund_requires_separate_reconciliation"),
        (state(status="REVERSED"), "refund_requires_separate_reconciliation"),
        (state(status="PARTIAL_REVERSED"), "refund_requires_separate_reconciliation"),
    ],
)
def test_unsafe_or_ambiguous_provider_status_never_confirms(response: dict, reason: str) -> None:
    assert decision(response) == ("review", reason)


@pytest.mark.parametrize("provider_status", ["CANCELED", "CANCELLED", "REJECTED", "DEADLINE_EXPIRED", "AUTH_FAIL"])
def test_final_provider_failure_requires_verified_amount_and_identity(provider_status: str) -> None:
    assert decision(state(status=provider_status)) == ("failed", "provider_terminal_failure")


def test_pending_and_unknown_status_never_credit_or_fail() -> None:
    assert decision(state(status="AUTHORIZED")) == ("pending", "provider_not_final")
    assert decision(state(status="UNKNOWN")) == ("pending", "provider_not_final")


def test_legacy_missing_minor_amount_can_be_validated_from_rubles() -> None:
    assert decide_tbank_action(
        external_id="payment-123", amount_rub=150.0,
        provider_amount_minor=None, state=state(), expected_terminal_key="terminal-1",
    ) == ("paid", "provider_confirmed")


def test_script_never_mutates_user_credits_or_transaction_status_directly() -> None:
    source = (Path(__file__).parents[1] / "scripts/fix_stuck_tbank_payments.py").read_text()
    assert "user.credits =" not in source
    assert "tx.status =" not in source
    assert "repo.confirm_transaction_and_add_credits(" in source
    assert "repo.set_transaction_status(" in source
    assert 'parser.add_argument("--apply", action="store_true"' in source


def test_standalone_cli_help_does_not_trigger_db_api_import_cycle() -> None:
    """The deployed operator CLI must be executable as a fresh Python process."""
    path = Path(__file__).parents[1] / "scripts/fix_stuck_tbank_payments.py"
    process = subprocess.run(
        [sys.executable, str(path), "--help"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert process.returncode == 0
    assert "--apply" in process.stdout
    assert "--offset" in process.stdout
    assert "--aggregate-only" in process.stdout
    assert "--audit-min-age-days" in process.stdout


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("offset", "apply"),
    [(-1, False), (10001, False), (1, True), (50, True)],
)
async def test_tbank_reconcile_rejects_unsafe_audit_offset(offset: int, apply: bool) -> None:
    # Invalid pagination and offset+apply must fail before API/DB access.
    with pytest.raises(ValueError, match="offset"):
        await reconcile(
            limit=2, lookback_days=30, min_age_minutes=30,
            apply=apply, offset=offset,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("days", "lookback", "apply"),
    [(7, 3650, True), (30, 3650, True), (-1, 3650, False),
     (3651, 3650, False), (30, 30, False), (31, 30, False)],
)
async def test_aged_cohort_never_allows_apply_or_invalid_window(
    days: int, lookback: int, apply: bool,
) -> None:
    with pytest.raises(ValueError, match="audit-min-age-days"):
        await reconcile(
            limit=2, lookback_days=lookback, min_age_minutes=30,
            apply=apply, audit_min_age_days=days,
        )


@pytest.mark.asyncio
async def test_aged_cohort_limits_read_only_query_and_never_calls_provider(
    monkeypatch,
) -> None:
    seen_queries = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, query):
            seen_queries.append(query)
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    get_state = AsyncMock()
    monkeypatch.setattr(audit, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(audit, "get_payment_state", get_state)
    monkeypatch.setattr(audit.settings, "TBANK_TERMINAL_KEY", "terminal-test")
    monkeypatch.setattr(audit.settings, "TBANK_PASSWORD", "test-only")

    result = await reconcile(
        limit=5, lookback_days=3650, min_age_minutes=30, apply=False,
        aggregate_only=True, audit_min_age_days=90,
    )
    assert result["checked"] == 0
    assert result["audit_min_age_days"] == 90
    assert result["mode"] == "dry_run"
    get_state.assert_not_awaited()
    assert len(seen_queries) == 1
    date_params = [
        value for value in seen_queries[0].compile().params.values()
        if isinstance(value, datetime)
    ]
    assert len(date_params) == 2
    ages = sorted((datetime.now(timezone.utc) - value).days for value in date_params)
    assert ages[0] in (89, 90)
    assert ages[1] in (3649, 3650)


def test_dry_run_offset_is_bounded_and_write_mode_never_offsets() -> None:
    source = (Path(__file__).parents[1] / "scripts/fix_stuck_tbank_payments.py").read_text()
    assert ".offset(offset)" in source
    assert ".limit(limit + 1)" in source
    assert "if apply and offset:" in source
    assert 'parser.add_argument("--apply", action="store_true"' in source


@pytest.mark.asyncio
async def test_aggregate_only_mode_rejects_any_apply_before_provider_or_db() -> None:
    with pytest.raises(ValueError, match="aggregate-only"):
        await reconcile(
            limit=2, lookback_days=30, min_age_minutes=30,
            apply=True, aggregate_only=True,
        )


@pytest.mark.asyncio
async def test_aggregate_only_dry_run_redacts_transaction_ids(monkeypatch, capsys) -> None:
    transactions = [
        SimpleNamespace(
            id=987654321, external_id="secret-payment-id", amount_rub=150.0,
            provider_amount_minor=15000,
        ),
    ]

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, _statement):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: transactions),
            )

    provider_state = AsyncMock(return_value=state(
        payment_id="secret-payment-id", status="CANCELED",
    ))
    monkeypatch.setattr(audit, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(audit, "get_payment_state", provider_state)
    monkeypatch.setattr(audit.settings, "TBANK_TERMINAL_KEY", "terminal-1")
    monkeypatch.setattr(audit.settings, "TBANK_PASSWORD", "test-only")
    monkeypatch.setattr(audit.asyncio, "sleep", AsyncMock())

    result = await audit.reconcile(
        limit=1, lookback_days=30, min_age_minutes=30,
        apply=False, aggregate_only=True,
    )
    assert result["mode"] == "dry_run"
    assert result["aggregate_only"] is True
    assert result["checked"] == 1
    assert result["outcomes"] == {
        "failed:provider_terminal_failure:observed": 1,
    }
    assert capsys.readouterr().out == ""
    provider_state.assert_awaited_once_with("secret-payment-id")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("has_refund_notice", "latest_status", "changed_field", "expected_outcome", "writes"),
    [
        (True, "pending", None, "refund_notice_requires_review", 0),
        (False, "paid", None, "already_resolved", 0),
        (False, "pending", None, "failed", 1),
        (False, "pending", "amount_rub", "payment_amount_changed_requires_review", 0),
        (False, "pending", "provider_amount_minor", "payment_amount_changed_requires_review", 0),
    ],
)
async def test_tbank_operator_failure_serializes_refunds_and_rechecks_state(
    monkeypatch, has_refund_notice, latest_status, changed_field, expected_outcome, writes,
) -> None:
    from db.models import PaymentProvider, PaymentRefundNotice, Transaction, TransactionStatus

    candidate = SimpleNamespace(
        id=987654321, external_id="private-payment-id", amount_rub=150.0,
        provider_amount_minor=15000,
    )
    current = SimpleNamespace(
        **candidate.__dict__, provider=PaymentProvider.tbank,
        status=TransactionStatus(latest_status),
    )
    if changed_field == "amount_rub":
        current.amount_rub = 155.0
    elif changed_field == "provider_amount_minor":
        current.provider_amount_minor = 15500
    lock = AsyncMock()
    fail = AsyncMock(return_value=current)

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, _query):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [candidate]),
            )

        async def get(self, model, key, **kwargs):
            # Refund notice and current row must be read after the shared lock.
            assert lock.await_count == 1
            if model is PaymentRefundNotice:
                assert key == candidate.external_id
                return SimpleNamespace(provider="tbank") if has_refund_notice else None
            assert model is Transaction
            assert key == candidate.id
            assert kwargs == {"populate_existing": True}
            return current

    monkeypatch.setattr(audit, "AsyncSessionLocal", FakeSession)
    monkeypatch.setattr(audit, "lock_payment_identity", lock)
    monkeypatch.setattr(audit, "get_payment_state", AsyncMock(
        return_value=state(payment_id=candidate.external_id, status="CANCELED"),
    ))
    monkeypatch.setattr(audit.repo, "set_transaction_status", fail)
    monkeypatch.setattr(audit.settings, "TBANK_TERMINAL_KEY", "terminal-1")
    monkeypatch.setattr(audit.settings, "TBANK_PASSWORD", "test-only")
    monkeypatch.setattr(audit.asyncio, "sleep", AsyncMock())

    result = await reconcile(
        limit=1, lookback_days=3650, min_age_minutes=30,
        apply=True,
    )
    assert result["outcomes"] == {
        f"failed:provider_terminal_failure:{expected_outcome}": 1,
    }
    assert lock.await_count == 1
    assert lock.await_args.args[1] == candidate.external_id
    assert fail.await_count == writes
