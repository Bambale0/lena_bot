"""Production-safe T-Bank catch-up decisions. No provider calls or database writes."""
from __future__ import annotations

import subprocess
import sys
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
