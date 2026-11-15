#!/usr/bin/env python3
"""Bounded, read-only CryptoBot pending-invoice audit.

Does not settle transactions, credit wallets, or mutate local status.
An externally paid invoice is flagged for reconciliation, not auto-credited.
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

import httpx
from sqlalchemy import select

# Initialize API contracts before db.session to avoid a standalone CLI import cycle.
import api  # noqa: E402,F401
from core.config import settings
from db.models import PaymentProvider, Transaction, TransactionStatus
from db.session import AsyncSessionLocal

MAX_BATCH_SIZE = 50


def classify_invoice(external_id: str, response: dict[str, Any]) -> tuple[str, str]:
    """Fail closed on malformed/mismatched provider responses."""
    if response.get("ok") is not True:
        return "review", "provider_response_not_successful"
    result = response.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("items"), list):
        return "review", "provider_response_invalid"
    items = result["items"]
    if len(items) != 1 or not isinstance(items[0], dict):
        return "review", "provider_invoice_missing_or_ambiguous"
    invoice = items[0]
    if str(invoice.get("invoice_id") or "") != external_id:
        return "review", "invoice_identity_mismatch"
    status = str(invoice.get("status") or "").lower()
    if status == "paid":
        # Existing legacy transactions do not store the USDT invoice amount.
        # Require separate currency/amount verification before any settlement.
        return "review", "provider_paid_requires_amount_verification"
    if status in {"expired", "invalid", "cancelled", "canceled"}:
        return "failed", "provider_terminal_failure"
    if status in {"active", "pending"}:
        return "pending", "provider_not_final"
    return "review", "provider_status_unknown"


async def audit(*, limit: int = 20, offset: int = 0, lookback_days: int = 30, min_age_minutes: int = 30) -> dict[str, Any]:
    if not 1 <= limit <= MAX_BATCH_SIZE:
        raise ValueError(f"limit must be within 1..{MAX_BATCH_SIZE}")
    if not 0 <= offset <= 10000:
        raise ValueError("offset must be within 0..10000")
    if not 1 <= lookback_days <= 3650:
        raise ValueError("lookback-days must be within 1..3650")
    if not 5 <= min_age_minutes <= 1440:
        raise ValueError("min-age-minutes must be within 5..1440")
    if not settings.CRYPTOBOT_TOKEN:
        raise RuntimeError("CryptoBot API token is not configured")

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Transaction).where(
                Transaction.provider == PaymentProvider.cryptobot,
                Transaction.status == TransactionStatus.pending,
                Transaction.external_id.is_not(None),
                Transaction.created_at >= now - timedelta(days=lookback_days),
                Transaction.created_at <= now - timedelta(minutes=min_age_minutes),
            ).order_by(Transaction.created_at.asc(), Transaction.id.asc()).offset(offset).limit(limit)
        )).scalars().all()
    # DB connection released before any provider network call.
    counts: Counter[str] = Counter()
    headers = {"Crypto-Pay-API-Token": settings.CRYPTOBOT_TOKEN}
    async with httpx.AsyncClient(
        base_url=settings.CRYPTOBOT_BASE_URL, headers=headers, timeout=20.0,
    ) as client:
        for tx in rows:
            try:
                response = await client.get(
                    "/getInvoices", params={"invoice_ids": str(tx.external_id)}
                )
                response.raise_for_status()
                decision, reason = classify_invoice(str(tx.external_id), response.json())
            except Exception as exc:
                decision, reason = "review", f"provider_read_{type(exc).__name__}"
            counts[f"{decision}:{reason}"] += 1
            # Never print invoice ids, user ids, token, provider payload, or balance.
            print(json.dumps({"tx_id": tx.id, "decision": decision, "reason": reason}))
            await asyncio.sleep(0.25)
    summary = {"mode": "dry_run", "offset": offset, "checked": len(rows), "outcomes": dict(counts)}
    print(json.dumps({"summary": summary}))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--offset", type=int, default=0, help="Skip earlier pending invoices in stable created_at/id order (0..10000)")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--min-age-minutes", type=int, default=30)
    args = parser.parse_args()
    try:
        asyncio.run(audit(
            limit=args.limit, offset=args.offset, lookback_days=args.lookback_days,
            min_age_minutes=args.min_age_minutes,
        ))
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
