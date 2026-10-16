"""Net paid revenue after cumulative refunds, shared by all reporting surfaces."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import Float, Numeric, case, cast, func

from db.models import Transaction, TransactionStatus


def net_paid_amount_expr(transaction=Transaction):
    original = func.coalesce(transaction.provider_amount_minor, 0)
    refunded = func.coalesce(transaction.refunded_amount_minor, 0)
    proportional = (
        cast(transaction.amount_rub, Numeric) * (original - refunded)
        / func.nullif(cast(original, Numeric), 0)
    )
    return cast(case(
        (transaction.status != TransactionStatus.paid, 0),
        (refunded <= 0, transaction.amount_rub),
        (original <= 0, 0),
        (refunded >= original, 0),
        else_=func.round(proportional, 2),
    ), Float)


def net_paid_amount_rub(transaction: Transaction) -> float:
    if getattr(transaction, "status", None) != TransactionStatus.paid:
        return 0.0
    amount = Decimal(str(transaction.amount_rub or 0))
    if not amount.is_finite() or amount < 0:
        return 0.0
    refunded = int(getattr(transaction, "refunded_amount_minor", 0) or 0)
    if refunded <= 0:
        return float(amount)
    original = int(getattr(transaction, "provider_amount_minor", 0) or 0)
    if original <= 0 or refunded >= original:
        return 0.0
    return float((amount * (original - refunded) / original).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def net_paid_credits(transaction: Transaction) -> float:
    if getattr(transaction, "status", None) != TransactionStatus.paid:
        return 0.0
    return max(0.0, float(transaction.credits or 0) - float(getattr(transaction, "refunded_credits", 0) or 0))
