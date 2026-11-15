"""Production-safe T-Bank catch-up decisions. No provider calls or database writes."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.fix_stuck_tbank_payments import decide_tbank_action


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
    ],
)
def test_unsafe_or_ambiguous_provider_status_never_confirms(response: dict, reason: str) -> None:
    assert decision(response) == ("review", reason)


@pytest.mark.parametrize("provider_status", ["CANCELED", "CANCELLED", "REJECTED", "DEADLINE_EXPIRED", "AUTH_FAIL", "REVERSED"])
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
