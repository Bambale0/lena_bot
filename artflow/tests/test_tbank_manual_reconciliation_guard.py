"""T-Bank manual status check must never mutate a mismatched payment."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers import payment
from db.models import PaymentProvider, TransactionStatus


def _state(**overrides):
    result = {
        "Success": True, "PaymentId": "pay-123", "TerminalKey": "terminal-1",
        "Amount": 15000, "Status": "CONFIRMED",
    }
    result.update(overrides)
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [
    {"Success": False},
    {"PaymentId": "different"},
    {"PaymentId": None},
    {"TerminalKey": "wrong-terminal"},
    {"Amount": 14999},
    {"Amount": None},
    {"Amount": "15000.00"},
])
async def test_manual_tbank_reconciliation_rejects_unverified_state(monkeypatch, overrides):
    tx = SimpleNamespace(
        external_id="pay-123", provider=PaymentProvider.tbank,
        status=TransactionStatus.pending, amount_rub=150.0,
        provider_amount_minor=15000,
    )
    session = AsyncMock()
    confirm = AsyncMock()
    change_status = AsyncMock()
    monkeypatch.setattr(payment.settings, "TBANK_TERMINAL_KEY", "terminal-1")
    monkeypatch.setattr(payment.tbank, "get_payment_state", AsyncMock(return_value=_state(**overrides)))
    monkeypatch.setattr(payment.repo, "confirm_transaction_and_add_credits", confirm)
    monkeypatch.setattr(payment.repo, "set_transaction_status", change_status)

    with pytest.raises(ValueError, match="T-Bank"):
        await payment._reconcile_transaction_status(session, tx)

    confirm.assert_not_awaited()
    change_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_manual_tbank_reconciliation_accepts_matching_provider_response(monkeypatch):
    tx = SimpleNamespace(
        external_id="pay-123", provider=PaymentProvider.tbank,
        status=TransactionStatus.pending, amount_rub=150.0,
        provider_amount_minor=15000,
    )
    session = AsyncMock()
    confirm = AsyncMock(return_value=78.0)
    monkeypatch.setattr(payment.settings, "TBANK_TERMINAL_KEY", "terminal-1")
    monkeypatch.setattr(payment.tbank, "get_payment_state", AsyncMock(return_value=_state()))
    monkeypatch.setattr(payment, "_confirm_paid_transaction", confirm)
    monkeypatch.setattr(payment.repo, "get_transaction_by_external_id", AsyncMock(return_value=SimpleNamespace(status=TransactionStatus.paid)))

    status, balance = await payment._reconcile_transaction_status(session, tx)
    assert status == TransactionStatus.paid
    assert balance == 78.0
    confirm.assert_awaited_once_with(session, "pay-123")


@pytest.mark.asyncio
async def test_authorized_status_does_not_credit_early(monkeypatch):
    tx = SimpleNamespace(
        external_id="pay-123", provider=PaymentProvider.tbank,
        status=TransactionStatus.pending, amount_rub=150.0,
        provider_amount_minor=15000,
    )
    session = AsyncMock()
    confirm = AsyncMock()
    monkeypatch.setattr(payment.settings, "TBANK_TERMINAL_KEY", "terminal-1")
    monkeypatch.setattr(payment.tbank, "get_payment_state", AsyncMock(return_value=_state(Status="AUTHORIZED")))
    monkeypatch.setattr(payment, "_confirm_paid_transaction", confirm)
    monkeypatch.setattr(payment.repo, "get_transaction_by_external_id", AsyncMock(return_value=tx))

    status, balance = await payment._reconcile_transaction_status(session, tx)
    assert status == TransactionStatus.pending
    assert balance is None
    confirm.assert_not_awaited()
