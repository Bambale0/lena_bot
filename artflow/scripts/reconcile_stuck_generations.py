from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from api.miniapp_routes import _reconcile_generation_status
from db.models import Generation, GenerationStatus
from db.session import AsyncSessionLocal


async def run(*, older_than_minutes: float, limit: int, verbose: bool) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
    scanned = 0
    changed = 0
    finished = 0
    failed = 0

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Generation)
                .where(Generation.status.in_([GenerationStatus.pending, GenerationStatus.processing]))
                .where(Generation.created_at <= cutoff)
                .order_by(Generation.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()

        for gen in rows:
            scanned += 1
            before = gen.status.value
            before_result = bool(gen.result_url)
            reconciled = await _reconcile_generation_status(session, gen)
            after = reconciled.status.value
            after_result = bool(reconciled.result_url)
            if after != before or after_result != before_result:
                changed += 1
                if after == 'done':
                    finished += 1
                elif after == 'failed':
                    failed += 1
            if verbose:
                print(
                    f"gen={gen.id} user={gen.user_id} before={before} after={after} "
                    f"model={gen.model} task={gen.task_id or '-'} result={after_result}"
                )

    print(
        f"reconcile_stuck_generations scanned={scanned} changed={changed} "
        f"done={finished} failed={failed} older_than_minutes={older_than_minutes} limit={limit}"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile stuck active generations")
    parser.add_argument("--older-than-minutes", type=float, default=3.0)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(asyncio.run(run(
        older_than_minutes=args.older_than_minutes,
        limit=args.limit,
        verbose=args.verbose,
    )))
