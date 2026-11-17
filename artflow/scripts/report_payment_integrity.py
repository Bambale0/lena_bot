#!/usr/bin/env python3
"""Read-only, PII-free payment/ledger integrity report.

Only local PostgreSQL is queried; no payment-provider API requests, refunds,
credits, or invoice creation. Use for triage, NOT to auto-resolve pending invoices.

    docker compose exec -T app python scripts/report_payment_integrity.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import settings  # noqa: E402

# A single grouped query avoids N+1 lookups and reads a consistent PG snapshot.
# source_id is VARCHAR and deliberately matched to the integer transaction ID.
PROVIDER_REPORT_SQL = """
WITH payment_ledger AS (
    SELECT source_id, count(*) AS row_count,
           sum(delta) AS credited_amount,
           min(user_id) AS first_user_id,
           max(user_id) AS last_user_id
    FROM credit_ledger
    WHERE source_type = 'transaction' AND entry_type = 'payment_credit'
    GROUP BY source_id
), checks AS (
    SELECT t.provider::text AS provider, t.status::text AS status,
           t.created_at, t.credits, t.user_id, t.external_id,
           coalesce(pl.row_count, 0) AS ledger_count,
           coalesce(pl.credited_amount, 0) AS credited_amount,
           pl.first_user_id, pl.last_user_id
    FROM transactions AS t
    LEFT JOIN payment_ledger AS pl ON pl.source_id = t.id::text
)
SELECT provider,
       count(*) AS transactions,
       count(*) FILTER (WHERE status = 'paid') AS paid,
       count(*) FILTER (WHERE status = 'pending') AS pending,
       count(*) FILTER (WHERE status = 'failed') AS failed,
       count(*) FILTER (
           WHERE status = 'paid' AND ledger_count = 0
       ) AS paid_without_ledger,
       count(*) FILTER (
           WHERE status = 'paid' AND ledger_count > 1
       ) AS paid_duplicate_ledger,
       count(*) FILTER (
           WHERE status = 'paid' AND ledger_count = 1
                 AND abs(credited_amount - credits) > 0.00001
       ) AS paid_credit_mismatch,
       count(*) FILTER (
           WHERE ledger_count > 0
                 AND (first_user_id <> user_id OR last_user_id <> user_id)
       ) AS ledger_owner_mismatch,
       count(*) FILTER (
           WHERE status <> 'paid' AND ledger_count > 0
       ) AS nonpaid_with_payment_ledger,
       count(*) FILTER (
           WHERE status = 'pending'
                 AND created_at >= now() - interval '24 hours'
       ) AS pending_last_24h,
       count(*) FILTER (
           WHERE status = 'pending'
                 AND created_at < now() - interval '7 days'
       ) AS pending_older_7d,
       count(*) FILTER (
           WHERE status = 'pending'
                 AND created_at < now() - interval '30 days'
       ) AS pending_older_30d,
       count(*) FILTER (
           WHERE status = 'pending'
                 AND created_at < now() - interval '90 days'
       ) AS pending_older_90d,
       count(*) FILTER (
           WHERE status = 'pending'
                 AND (external_id IS NULL OR external_id = '')
       ) AS pending_missing_external_id
FROM checks
GROUP BY provider
ORDER BY provider
"""

ORPHAN_PAYMENT_LEDGER_SQL = """
SELECT count(*) AS orphan_count
FROM credit_ledger AS l
WHERE l.source_type = 'transaction' AND l.entry_type = 'payment_credit'
  AND NOT EXISTS (
      SELECT 1 FROM transactions AS t WHERE t.id::text = l.source_id
  )
"""

INTEGRITY_FIELDS = (
    "paid_without_ledger",
    "paid_duplicate_ledger",
    "paid_credit_mismatch",
    "ledger_owner_mismatch",
    "nonpaid_with_payment_ledger",
)


def make_report(provider_rows: list[dict[str, Any]], orphan_count: int) -> dict[str, Any]:
    """Only aggregate values are serialized. Never include users or payment IDs."""
    providers = []
    summary = {
        "transactions": 0, "paid": 0, "pending": 0, "failed": 0,
        "pending_last_24h": 0, "pending_older_7d": 0,
        "pending_older_30d": 0, "pending_older_90d": 0,
        "pending_missing_external_id": 0,
        **{name: 0 for name in INTEGRITY_FIELDS},
    }
    allowed_fields = (
        "transactions", "paid", "pending", "failed",
        *INTEGRITY_FIELDS, "pending_last_24h", "pending_older_7d",
        "pending_older_30d", "pending_older_90d", "pending_missing_external_id",
    )
    for row in provider_rows:
        item = {"provider": str(row["provider"])}
        for key in allowed_fields:
            item[key] = int(row[key])
            if key in summary:
                summary[key] += item[key]
        providers.append(item)
    summary["orphan_payment_ledger"] = int(orphan_count)
    integrity_ok = not any(summary[key] for key in (*INTEGRITY_FIELDS, "orphan_payment_ledger"))
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": "postgresql/read_only/repeatable_read",
        "integrity_ok": integrity_ok,
        "summary": summary,
        "by_provider": providers,
        "interpretation": (
            "Pending means unconfirmed locally, not necessarily paid externally. "
            "Never auto-credit or fail by age; verify with the authoritative provider."
        ),
    }


async def collect_payment_integrity(session: AsyncSession) -> dict[str, Any]:
    """The SQL transaction itself is read-only and uses a consistent snapshot."""
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
    await session.execute(text("SET LOCAL statement_timeout = '15000ms'"))
    rows = (await session.execute(text(PROVIDER_REPORT_SQL))).mappings().all()
    orphan = (await session.execute(text(ORPHAN_PAYMENT_LEDGER_SQL))).scalar_one()
    return make_report([dict(row) for row in rows], int(orphan))


async def report() -> dict[str, Any]:
    # A self-contained engine avoids importing the live app session/repository
    # (and its API route initialization). Only a read-only PG snapshot is used.
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            try:
                return await collect_payment_integrity(session)
            finally:
                await session.rollback()
    finally:
        await engine.dispose()


def main() -> int:
    try:
        result = asyncio.run(report())
    except Exception as exc:
        # Do not leak PII, query text, DSNs or credentials in operator output.
        print(f"payment_integrity_report_failed={type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["integrity_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
