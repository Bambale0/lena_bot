"""CryptoBot pending audit must never confirm/credit legacy invoices."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.reconcile_cryptobot_pending import classify_invoice


def reply(*, invoice_id=123, status="paid", ok=True):
    return {"ok": ok, "result": {"items": [{"invoice_id": invoice_id, "status": status, "amount": "1.50", "asset": "USDT"}]}}


def test_paid_invoice_requires_amount_verification_before_credit():
    assert classify_invoice("123", reply()) == (
        "review", "provider_paid_requires_amount_verification"
    )


@pytest.mark.parametrize(("response", "reason"), [
    (reply(invoice_id=456), "invoice_identity_mismatch"),
    (reply(ok=False), "provider_response_not_successful"),
    ({"ok": True, "result": {}}, "provider_response_invalid"),
    ({"ok": True, "result": {"items": []}}, "provider_invoice_missing_or_ambiguous"),
    ({"ok": True, "result": {"items": [reply()["result"]["items"][0], reply()["result"]["items"][0]]}}, "provider_invoice_missing_or_ambiguous"),
    (reply(status="unknown"), "provider_status_unknown"),
])
def test_untrusted_invoice_never_eligible_for_automatic_settlement(response, reason):
    assert classify_invoice("123", response) == ("review", reason)


@pytest.mark.parametrize("status", ["expired", "invalid", "cancelled", "canceled"])
def test_final_provider_failure_only_classified(status):
    assert classify_invoice("123", reply(status=status)) == (
        "failed", "provider_terminal_failure"
    )


def test_active_invoice_remains_pending():
    assert classify_invoice("123", reply(status="active")) == ("pending", "provider_not_final")


def test_audit_source_excludes_wallet_or_transaction_mutation():
    source = (Path(__file__).parents[1] / "scripts/reconcile_cryptobot_pending.py").read_text()
    assert "confirm_transaction_and_add_credits" not in source
    assert "set_transaction_status" not in source
    assert "session.commit(" not in source
    assert "session.add(" not in source
    assert "--apply" not in source
    assert "MAX_BATCH_SIZE = 50" in source


def test_cli_help_does_not_call_provider():
    script = Path(__file__).parents[1] / "scripts/reconcile_cryptobot_pending.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True, text=True, timeout=15, check=False,
    )
    assert result.returncode == 0
    assert "--lookback-days" in result.stdout
