"""Provider status translation; all accounting is owned by the atomic DB seam."""
from __future__ import annotations

import hashlib
import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.provider_logging import safe_identifier
from db.models import PaymentProvider
from db.payment_refunds import (
    RefundNeedsReconciliation,
    RefundResult,
    apply_payment_refund,
    strict_minor,
)

logger = logging.getLogger(__name__)


def log_refund_rejection(provider: str, external_id: str, error: RefundNeedsReconciliation) -> None:
    payment_id = safe_identifier(external_id)
    if payment_id in {"invalid", "unknown"}:
        payment_id = "sha256:" + hashlib.sha256(str(external_id).encode()).hexdigest()[:16]
    metadata = {"refund_provider": provider, "refund_payment_id": payment_id,
                "refund_reason": error.reason_code}
    logger.warning("payment_refund_deferred provider=%s payment_id=%s reason=%s",
                   provider, payment_id, error.reason_code, extra=metadata)


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
        log_refund_rejection("tbank", external_id, exc)
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
        log_refund_rejection("tribute", external_id, exc)
        raise HTTPException(status_code=503, detail="Payment refund requires reconciliation") from exc
