"""Atomic cumulative payment refunds; never call committing helpers mid-refund."""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    CreditLedgerEntry,
    PaymentProvider,
    PaymentRefundEvent,
    PaymentRefundNotice,
    ReferralCommissionLedger,
    Transaction,
    TransactionStatus,
    User,
)

logger = logging.getLogger(__name__)


_DIAGNOSTIC_REASONS = frozenset(['Invalid minor-unit amount', 'Invalid original credit amount', 'Invalid original payment amount', 'Invalid stored refund totals', 'Original provider amount mismatch', 'Partial refund arrived before payment confirmation', 'Partial refund has no reduced amount', 'Partial refund without a local payment', 'Payment provider mismatch', 'Payment user missing', 'Payment/refund notice provider mismatch', 'Refund credit totals require reconciliation', 'Refund currency mismatch', 'Refund notice provider mismatch', 'Refund outside original payment amount', 'Unexpected Tribute currency', 'Unsupported payment state'])


class RefundNeedsReconciliation(ValueError):
    """Unsettled payment state with an allowlisted, non-sensitive log reason."""

    @property
    def reason_code(self) -> str:
        reason = str(self)
        if reason not in _DIAGNOSTIC_REASONS:
            return "unclassified_reconciliation_error"
        return reason.lower().replace(" ", "_").replace("-", "_").replace("/", "_")



@dataclass(frozen=True, slots=True)
class RefundResult:
    transaction_id: int | None
    status: TransactionStatus
    applied: bool
    credits_reversed: float = 0


def money_minor(amount: float) -> int:
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or value <= 0 or value >= Decimal(2**63) / 100:
            raise RefundNeedsReconciliation("Invalid original payment amount")
        result = int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if not 0 < result < 2**63:
            raise RefundNeedsReconciliation("Invalid original payment amount")
        return result
    except InvalidOperation as exc:
        raise RefundNeedsReconciliation("Invalid original payment amount") from exc


def strict_minor(value: object, *, positive: bool = False) -> int:
    # Do not truncate floats or accept booleans as money.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise RefundNeedsReconciliation("Invalid minor-unit amount")
    if isinstance(value, str) and (len(value) > 19 or not value.isascii() or not value.isdigit()):
        raise RefundNeedsReconciliation("Invalid minor-unit amount")
    result = int(value)
    if result < (1 if positive else 0) or result > 2**63 - 1:
        raise RefundNeedsReconciliation("Invalid minor-unit amount")
    return result


async def lock_payment_identity(session: AsyncSession, external_id: str) -> None:
    """Serialize refund/confirmation even before a Transaction row exists.

    PostgreSQL transaction-scoped advisory lock; released by commit/rollback.
    The namespace is stable and separate from generation/referral locks.
    """
    digest = hashlib.sha256(("apix:payment:" + external_id).encode()).digest()[:8]
    key = int.from_bytes(digest, "big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def reverse_referral_share(
    session: AsyncSession, tx: Transaction, *, target: int, original: int,
) -> None:
    """Caller holds the transaction and affected user row locks; never commits."""
    entries = list((await session.scalars(
        select(ReferralCommissionLedger).where(ReferralCommissionLedger.transaction_id == tx.id)
        .order_by(ReferralCommissionLedger.recipient_user_id, ReferralCommissionLedger.id)
    )).all())
    for accrual in (e for e in entries if e.event_type == "accrual"):
        reversed_before = sum(-Decimal(str(e.amount_rub)) for e in entries if
            e.event_type == "reversal" and e.recipient_user_id == accrual.recipient_user_id and e.level == accrual.level)
        goal = (Decimal(str(accrual.amount_rub)) * target / original).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        reversal = goal - reversed_before
        if reversal <= 0:
            continue
        balance = await session.scalar(update(User).where(User.id == accrual.recipient_user_id)
            .values(referral_balance=User.referral_balance - float(reversal)).returning(User.referral_balance))
        session.add(ReferralCommissionLedger(
            transaction_id=tx.id, payer_user_id=tx.user_id,
            recipient_user_id=accrual.recipient_user_id, level=accrual.level,
            rate=accrual.rate, payment_amount_rub=accrual.payment_amount_rub,
            amount_rub=-float(reversal), balance_after_rub=balance,
            event_type="reversal", refund_key=str(target),
        ))


async def apply_payment_refund(
    session: AsyncSession,
    external_id: str,
    provider: PaymentProvider,
    *,
    remaining_amount_minor: int | None = None,
    original_amount_minor: int | None = None,
    currency: str | None = None,
) -> RefundResult:
    """Apply a verified *cumulative* refund (None = full) in one DB transaction.

    T-Bank partial notifications carry the current remaining amount, not the
    incremental refund. Serializing on the payment makes duplicate and stale
    snapshots harmless. The same lock must guard referral accrual.
    """
    try:
        await lock_payment_identity(session, external_id)
        notice = await session.get(PaymentRefundNotice, external_id)
        if notice is not None and notice.provider != provider.value:
            raise RefundNeedsReconciliation("Refund notice provider mismatch")
        tx = await session.scalar(
            select(Transaction).where(Transaction.external_id == external_id)
            .with_for_update().execution_options(populate_existing=True)
        )
        if tx is None:
            if remaining_amount_minor is not None:
                raise RefundNeedsReconciliation("Partial refund without a local payment")
            if notice is None:
                session.add(PaymentRefundNotice(external_id=external_id, provider=provider.value))
            await session.commit()
            return RefundResult(None, TransactionStatus.refunded, notice is None)
        if tx.provider != provider:
            raise RefundNeedsReconciliation("Payment provider mismatch")
        if tx.status == TransactionStatus.refunded:
            # Do not guess whether a pre-migration two-commit refund debited its
            # wallet. Legacy rows require an independent read-only reconciliation.
            result = RefundResult(tx.id, tx.status, False)
            await session.commit()
            return result
        original = tx.provider_amount_minor
        if original is None:
            original = strict_minor(original_amount_minor, positive=True) if original_amount_minor is not None else money_minor(tx.amount_rub)
        original = strict_minor(original, positive=True)
        if original_amount_minor is not None and strict_minor(original_amount_minor, positive=True) != original:
            raise RefundNeedsReconciliation("Original provider amount mismatch")
        expected_currency = tx.provider_currency or currency or "rub"
        if currency is not None and currency.lower() != expected_currency.lower():
            raise RefundNeedsReconciliation("Refund currency mismatch")
        target = original if remaining_amount_minor is None else original - strict_minor(remaining_amount_minor)
        if target < 0 or target > original:
            raise RefundNeedsReconciliation("Refund outside original payment amount")
        previous = strict_minor(tx.refunded_amount_minor or 0)
        credits = Decimal(str(tx.credits))
        already_reversed = Decimal(str(tx.refunded_credits or 0))
        if (previous > original or not credits.is_finite() or credits < 0
                or not already_reversed.is_finite() or not 0 <= already_reversed <= credits):
            raise RefundNeedsReconciliation("Invalid stored refund totals")
        if remaining_amount_minor is not None and target == 0 and previous == 0:
            raise RefundNeedsReconciliation("Partial refund has no reduced amount")
        if target <= previous:
            result = RefundResult(tx.id, tx.status, False)
            await session.commit()
            return result
        paid = tx.status == TransactionStatus.paid
        if tx.status not in {TransactionStatus.pending, TransactionStatus.paid, TransactionStatus.failed}:
            raise RefundNeedsReconciliation("Unsupported payment state")
        # A failed legacy row may have been overwritten after a real credit.
        credited = paid or bool(await session.scalar(select(CreditLedgerEntry.id).where(
            CreditLedgerEntry.source_type == "transaction", CreditLedgerEntry.source_id == str(tx.id),
            CreditLedgerEntry.entry_type == "payment_credit",
            CreditLedgerEntry.user_id == tx.user_id, CreditLedgerEntry.delta > 0,
        ).limit(1)))
        if not credited and target != original:
            raise RefundNeedsReconciliation("Partial refund arrived before payment confirmation")
        if credited and not paid:
            # Restore ledger-proven legacy state in the same atomic transaction.
            tx.status = TransactionStatus.paid
        credits = Decimal(str(tx.credits))
        if not credits.is_finite() or credits < 0:
            raise RefundNeedsReconciliation("Invalid original credit amount")
        total_credit_refund = credits if target == original else min(credits, (credits * target / original).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))
        if credited and total_credit_refund < already_reversed:
            raise RefundNeedsReconciliation("Refund credit totals require reconciliation")
        delta = float(total_credit_refund - already_reversed) if credited else 0.0
        entries = list((await session.scalars(select(ReferralCommissionLedger).where(
            ReferralCommissionLedger.transaction_id == tx.id,
        ).order_by(ReferralCommissionLedger.recipient_user_id, ReferralCommissionLedger.id))).all())
        user_ids = sorted({tx.user_id, *(e.recipient_user_id for e in entries)})
        # Identical user lock order across different payments avoids cross-chain
        # deadlocks. Never hold a network/provider request under these locks.
        await session.execute(select(User.id).where(User.id.in_(user_ids)).order_by(User.id).with_for_update())
        if delta:
            balance = await session.scalar(update(User).where(User.id == tx.user_id)
                .values(credits=User.credits - delta).returning(User.credits))
            if balance is None:
                raise RefundNeedsReconciliation("Payment user missing")
            session.add(CreditLedgerEntry(
                user_id=tx.user_id, delta=-delta, balance_after=balance,
                entry_type="payment_refund", source_type="transaction", source_id=str(tx.id),
                note=f"Verified {provider.value} cumulative refund {target}/{original}",
            ))
        await reverse_referral_share(session, tx, target=target, original=original)
        session.add(PaymentRefundEvent(
            transaction_id=tx.id, cumulative_amount_minor=target,
            amount_minor=target - previous, currency=expected_currency.lower(), credits_delta=-delta,
        ))
        tx.provider_amount_minor = original
        tx.provider_currency = expected_currency.lower()
        tx.refunded_amount_minor = target
        tx.refunded_credits = float(total_credit_refund) if credited else 0
        if target == original:
            tx.status = TransactionStatus.refunded
            if notice is None:
                session.add(PaymentRefundNotice(external_id=external_id, provider=provider.value))
        result = RefundResult(tx.id, tx.status, True, delta)
        await session.commit()
        logger.info("payment_refund provider=%s transaction_id=%s cumulative_minor=%s credits_reversed=%s", provider.value, result.transaction_id, target, delta)
        return result
    except Exception:
        await session.rollback()
        raise
