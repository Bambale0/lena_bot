"""Provider status translation; all accounting is owned by the atomic DB seam."""
from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PaymentProvider
from db.payment_refunds import (
    RefundNeedsReconciliation,
    RefundResult,
    apply_payment_refund,
    strict_minor,
)

logger = logging.getLogger(__name__)


async def settle_tbank_refund(
    session: AsyncSession, external_id: str, status: str, amount: object,
) -> RefundResult:
    try:
        # Amount is the current transaction amount, NOT Cancel's requested delta.
        remaining = strict_minor(amount) if status == "PARTIAL_REFUNDED" else None
        return await apply_payment_refund(
            session, external_id, PaymentProvider.tbank,
            remaining_amount_minor=remaining, currency="rub",
        )
    except RefundNeedsReconciliation as exc:
        logger.warning("Payment refund deferred provider=tbank reason=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Payment refund requires reconciliation") from exc


async def settle_tribute_refund(
    session: AsyncSession, external_id: str, *, amount_minor: object,
    currency: str, digital: bool,
) -> RefundResult:
    try:
        if currency != ("usd" if digital else "rub"):
            raise RefundNeedsReconciliation("Unexpected Tribute currency")
        original = strict_minor(amount_minor, positive=True)
        return await apply_payment_refund(
            session, external_id, PaymentProvider.tribute,
            original_amount_minor=original, currency=currency,
        )
    except RefundNeedsReconciliation as exc:
        logger.warning("Payment refund deferred provider=tribute reason=%s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Payment refund requires reconciliation") from exc
