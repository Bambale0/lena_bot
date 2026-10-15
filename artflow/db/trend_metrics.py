"""Read-only demand metrics for curated trends from actual generation rows.

The legacy UserPrompt.uses_count tracks marketplace uses, not reliably
completed curated trend jobs. Keep it for compatibility but never present
it as the number of successful generations.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, case, cast, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Generation, GenerationStatus


def _trend_runs_query(prompt_ids: list[int], *, now: datetime | None = None):
    metadata = cast(Generation.input_params, JSONB)
    # /trends/{id}/run stores trend_id. Existing photo and video services
    # store prompt_id. Use trend_id first so a row with both counts only once.
    saved_id = func.coalesce(
        func.jsonb_extract_path_text(metadata, "trend_id"),
        func.jsonb_extract_path_text(metadata, "prompt_id"),
    )
    trend_id = cast(
        case(
            (saved_id.op("~")(r"^[0-9]+$"), saved_id),
            else_=None,
        ),
        Integer,
    )
    success = Generation.status == GenerationStatus.done
    failed = Generation.status == GenerationStatus.failed
    active = Generation.status.in_(
        (GenerationStatus.pending, GenerationStatus.processing)
    )
    since = (now or datetime.now(timezone.utc)) - timedelta(days=7)
    return (
        select(
            trend_id.label("trend_id"),
            func.count(Generation.id).label("total_runs"),
            func.count(Generation.id).filter(success).label("successful_runs"),
            func.count(Generation.id).filter(
                success, Generation.finished_at >= since
            ).label("successful_runs_7d"),
            func.count(Generation.id).filter(failed).label("failed_runs"),
            func.count(Generation.id).filter(active).label("active_runs"),
            func.count(func.distinct(Generation.user_id))
            .filter(success).label("unique_users"),
        )
        .where(trend_id.in_(prompt_ids))
        .group_by(trend_id)
    )


async def trend_success_stats(
    session: AsyncSession, prompt_ids: list[int],
) -> dict[int, dict[str, int]]:
    """Aggregate all selected trends in one database query (never N+1)."""
    ids = sorted({int(value) for value in prompt_ids if int(value) > 0})
    if not ids:
        return {}
    result = await session.execute(_trend_runs_query(ids))
    return {
        int(row.trend_id): {
            key: int(getattr(row, key) or 0)
            for key in (
                "total_runs", "successful_runs", "successful_runs_7d",
                "failed_runs", "active_runs", "unique_users",
            )
        }
        for row in result.all()
    }
