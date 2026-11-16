#!/usr/bin/env python3
"""Conservative, bounded T-Bank pending reconciliation.

Default mode is read-only against the local database and calls only T-Bank GetState.
Use --apply only after reviewing dry-run results; no age-based status changes.
All balance/ledger writes use the atomic repository seam and referral policy.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

# Initialize API routes first: repository imports an API contract whose
# package initializer uses db.session; otherwise standalone CLI can deadlock
# on a partially initialized db.repository.
import api  # noqa: E402,F401
from core.config import settings
from db import repository as repo
from db.models import PaymentProvider, Transaction, TransactionStatus
from db.payment_refunds import RefundNeedsReconciliation, money_minor, strict_minor
from db.referral_reward_policy import install_referral_reward_policy
from db.session import AsyncSessionLocal
from payments.tbank import get_payment_state

FINAL_FAILURES = frozenset({
    "CANCELED", "CANCELLED", "REJECTED", "DEADLINE_EXPIRED", "AUTH_FAIL",
})
REVIEW_STATES = frozenset({"REFUNDED", "PARTIAL_REFUNDED", "REVERSED", "PARTIAL_REVERSED"})
MAX_BATCH_SIZE = 50
MAX_AUDIT_OFFSET = 10000


def decide_tbank_action(
    *,
    external_id: str,
    amount_rub: float,
    provider_amount_minor: int | None,
    state: dict[str, Any],
    expected_terminal_key: str,
) -> tuple[str, str]:
    """Return (paid|failed|pending|review, safe_reason). No writes or provider calls."""
    if state.get("Success") is not True:
        return "review", "provider_not_successful"
    if str(state.get("PaymentId") or "") != external_id:
        return "review", "payment_identity_mismatch"
    terminal_key = state.get("TerminalKey")
    if terminal_key is not None and str(terminal_key) != expected_terminal_key:
        return "review", "terminal_identity_mismatch"
    try:
        expected = provider_amount_minor
        if expected is None:
            expected = money_minor(amount_rub)
        expected = strict_minor(expected, positive=True)
        actual = strict_minor(state.get("Amount"), positive=True)
    except (ValueError, TypeError, RefundNeedsReconciliation):
        return "review", "amount_not_verifiable"
    if actual != expected:
        return "review", "amount_mismatch"

    status = str(state.get("Status") or "").upper()
    if status == "CONFIRMED":
        return "paid", "provider_confirmed"
    if status in FINAL_FAILURES:
        return "failed", "provider_terminal_failure"
    if status in REVIEW_STATES:
        return "review", "refund_requires_separate_reconciliation"
    return "pending", "provider_not_final"


async def reconcile(*, limit: int, lookback_days: int, min_age_minutes: int, apply: bool, offset: int = 0) -> dict[str, object]:
    if not 1 <= limit <= MAX_BATCH_SIZE:
        raise ValueError(f"limit must be within 1..{MAX_BATCH_SIZE}")
    if not 0 <= offset <= MAX_AUDIT_OFFSET:
        raise ValueError(f"offset must be within 0..{MAX_AUDIT_OFFSET}")
    if apply and offset:
        # Applying updates shrinks the pending set. Offset pagination could
        # skip rows; operator writes always start with oldest pending rows.
        raise ValueError("--offset is allowed only in read-only dry-run mode")
    if not 1 <= lookback_days <= 3650:
        raise ValueError("lookback-days must be within 1..3650")
    if not 5 <= min_age_minutes <= 24 * 60:
        raise ValueError("min-age-minutes must be within 5..1440")
    if not settings.TBANK_TERMINAL_KEY or not settings.TBANK_PASSWORD:
        raise RuntimeError("T-Bank credentials are not configured")

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Transaction)
                .where(
                    Transaction.provider == PaymentProvider.tbank,
                    Transaction.status == TransactionStatus.pending,
                    Transaction.external_id.is_not(None),
                    Transaction.created_at >= now - timedelta(days=lookback_days),
                    Transaction.created_at <= now - timedelta(minutes=min_age_minutes),
                )
                .order_by(Transaction.created_at.asc(), Transaction.id.asc())
                .offset(offset)
                .limit(limit + 1)
            )
        ).scalars().all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    # Deliberately release the query transaction before calling the provider.
    # A dry-run does not issue any local write or status mutation.
    counts: Counter[str] = Counter()
    for tx in rows:
        try:
            state = await get_payment_state(str(tx.external_id))
            action, reason = decide_tbank_action(
                external_id=str(tx.external_id),
                amount_rub=tx.amount_rub,
                provider_amount_minor=tx.provider_amount_minor,
                state=state,
                expected_terminal_key=settings.TBANK_TERMINAL_KEY,
            )
        except Exception as exc:
            action, reason = "review", f"provider_read_{type(exc).__name__}"
        outcome = "observed"
        if apply and action in {"paid", "failed"}:
            # Only a verified provider response can reach this code path.
            # Repository helpers atomically guard pending->terminal and ledger exactly-once.
            try:
                async with AsyncSessionLocal() as session:
                    current = await session.get(Transaction, tx.id)
                    if (
                        current is None
                        or current.provider != PaymentProvider.tbank
                        or current.status != TransactionStatus.pending
                        or current.external_id != tx.external_id
                    ):
                        outcome = "already_resolved"
                    elif action == "paid":
                        # Percent-based referral commissions are normally applied by
                        # the webhook's separate commission seam. This CLI must not
                        # silently bypass them for referred users.
                        user = await repo.get_user_by_id(session, current.user_id)
                        if user is None or any((
                            user.referrer_id, user.referrer_l2_id, user.referrer_l3_id,
                        )):
                            outcome = "referral_commissions_require_review"
                        else:
                            result = await repo.confirm_transaction_and_add_credits(
                                session,
                                str(tx.external_id),
                                note="T-Bank verified GetState reconciliation",
                            )
                            outcome = "confirmed" if result else "already_resolved"
                    else:
                        result = await repo.set_transaction_status(
                            session, str(tx.external_id), TransactionStatus.failed
                        )
                        outcome = "failed" if result else "already_resolved"
            except Exception as exc:
                outcome = f"write_failed_{type(exc).__name__}"
        counts[f"{action}:{reason}:{outcome}"] += 1
        # User IDs, payment references, provider payloads and API credentials are not printed.
        print(json.dumps({"tx_id": tx.id, "decision": action, "reason": reason, "outcome": outcome}))
        await asyncio.sleep(0.25)

    return {
        "mode": "apply" if apply else "dry_run",
        "checked": len(rows),
        "offset": offset,
        "next_offset": offset + len(rows) if has_more and not apply else None,
        "has_more": has_more if not apply else False,
        "outcomes": dict(counts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Apply verified paid/final-failure states; default is dry-run")
    parser.add_argument("--limit", type=int, default=20, help="Max pending invoices to query (1..50)")
    parser.add_argument("--lookback-days", type=int, default=30, help="Only newer pending invoices (1..3650)")
    parser.add_argument(
        "--offset", type=int, default=0,
        help="Read-only dry-run pagination offset (0..10000); forbidden with --apply",
    )
    parser.add_argument("--min-age-minutes", type=int, default=30, help="Skip very new invoices (5..1440)")
    args = parser.parse_args()
    install_referral_reward_policy(repo)
    try:
        summary = asyncio.run(reconcile(
            limit=args.limit,
            lookback_days=args.lookback_days,
            min_age_minutes=args.min_age_minutes,
            apply=args.apply,
            offset=args.offset,
        ))
    except (ValueError, RuntimeError) as exc:
        print(f"reconciliation_config_error={type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps({"summary": summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
