#!/usr/bin/env python3
"""PII-free, read-only overview of refunded Neironych/Nexus image supplier reviews.

No provider calls, image requests, refunds, status transitions, or file changes.
Run on app container: python scripts/report_image_supplier_reviews.py
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

REVIEW_SQL = """
WITH source AS (
    SELECT model::text AS model,
           coalesce(input_params::jsonb #>> '{image_refund_provider_review,provider}', 'unknown') AS provider,
           coalesce(input_params::jsonb #>> '{image_refund_provider_review,state}', 'unknown') AS review_state,
           created_at,
           CASE
             WHEN task_id LIKE '%neironych-image:%' THEN 'neironych_request_id'
             WHEN task_id LIKE '%nexus:%' THEN 'nexus_request_id'
             WHEN task_id LIKE '%kie-submit:%' THEN 'kie_handoff'
             WHEN task_id IS NULL OR task_id = '' THEN 'missing'
             ELSE 'other'
           END AS task_identity_kind
    FROM generations
    WHERE gen_type::text = 'image'
      AND input_params IS NOT NULL
      AND input_params::text LIKE '%image_refund_provider_review%'
)
SELECT provider, model, review_state, task_identity_kind,
       count(*) AS review_count,
       count(*) FILTER (WHERE created_at < now() - interval '7 days') AS older_7d,
       count(*) FILTER (WHERE created_at < now() - interval '30 days') AS older_30d
FROM source
GROUP BY provider, model, review_state, task_identity_kind
ORDER BY provider, model, review_state, task_identity_kind
"""

# Never print free-form model labels, which could include provider or user text.
APPROVED_MODELS = frozenset({
    "nano-banana-2.1", "nano-banana-2", "nano-banana-pro",
    "nano-banana-pro-vip", "seedream/5-pro-text-to-image",
    "seedream/5-pro-image-to-image", "gpt-image-2",
    "gpt-image-2.5-sunburst",
})
STATES = frozenset({
    "pending", "remote_failed", "remote_completed_pending_finance",
    "needs_admin_resolution", "settled",
})
PROVIDERS = frozenset({"neironych", "nexus"})
IDENTITIES = frozenset({
    "neironych_request_id", "nexus_request_id", "kie_handoff", "missing", "other",
})


def _safe_model(value: Any) -> str:
    name = str(value or "")
    return name if name in APPROVED_MODELS else "other_model"


def make_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Whitelist aggregate fields; ignore all caller-supplied IDs, URLs, and prompts."""
    totals = {
        "review_count": 0, "pending": 0,
        "pending_not_covered_by_neironych_task_poller": 0,
        "pending_older_7d": 0, "pending_older_30d": 0,
        "remote_failed": 0, "remote_completed_pending_finance": 0,
    }
    groups = []
    for row in rows:
        provider = str(row.get("provider") or "")
        provider = provider if provider in PROVIDERS else "other_provider"
        state = str(row.get("review_state") or "")
        state = state if state in STATES else "other_state"
        identity = str(row.get("task_identity_kind") or "")
        identity = identity if identity in IDENTITIES else "other"
        count = int(row["review_count"])
        older7 = int(row["older_7d"])
        older30 = int(row["older_30d"])
        if not (0 <= older30 <= older7 <= count):
            raise ValueError("Invalid supplier review age aggregates")
        item = {
            "provider": provider, "model": _safe_model(row.get("model")),
            "review_state": state, "task_identity_kind": identity,
            "review_count": count, "older_7d": older7, "older_30d": older30,
        }
        groups.append(item)
        totals["review_count"] += count
        if state == "pending":
            totals["pending"] += count
            totals["pending_older_7d"] += older7
            totals["pending_older_30d"] += older30
            if provider == "neironych" and identity != "neironych_request_id":
                totals["pending_not_covered_by_neironych_task_poller"] += count
        if state == "remote_failed":
            totals["remote_failed"] += count
        if state == "remote_completed_pending_finance":
            totals["remote_completed_pending_finance"] += count
    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_source": "postgresql/read_only/repeatable_read",
        "summary": totals,
        "by_review_state": groups,
        "interpretation": (
            "Supplier review is separate from customer credit/refund status. "
            "A pending review without a Neironych task ID cannot be polled by "
            "the standard Neironych-image task-ID scheduler. Do not submit "
            "another paid request or change customer balances based on age."
        ),
    }


async def collect_supplier_reviews(session: AsyncSession) -> dict[str, Any]:
    await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
    await session.execute(text("SET LOCAL statement_timeout = '15000ms'"))
    rows = (await session.execute(text(REVIEW_SQL))).mappings().all()
    return make_report([dict(r) for r in rows])


async def report() -> dict[str, Any]:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            try:
                return await collect_supplier_reviews(session)
            finally:
                await session.rollback()
    finally:
        await engine.dispose()


def main() -> int:
    try:
        data = asyncio.run(report())
    except Exception as exc:
        print(f"image_supplier_report_failed={type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
