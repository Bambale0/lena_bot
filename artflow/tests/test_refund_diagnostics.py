import pytest
from fastapi import HTTPException

from payments.refund_settlement import settle_tbank_refund, settle_tribute_refund


@pytest.mark.asyncio
async def test_diagnostic_identifies_payment_and_rejection_reason(caplog):
    with pytest.raises(HTTPException):
        await settle_tbank_refund(object(), "test-payment-1", "PARTIAL_REFUNDED", True)
    with pytest.raises(HTTPException):
        await settle_tribute_refund(object(), "digital:42", amount_minor=200, currency="wrong", digital=True)
    assert "test-payment-1" in caplog.text and "digital:42" in caplog.text
    assert "invalid_minor_unit_amount" in caplog.text
    assert "unexpected_tribute_currency" in caplog.text
