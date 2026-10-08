"""Fair, bounded background recovery for Neironych Seedance 2/2.5 videos.

The provider GET and eventual media download never submit another paid POST.
DB transitions and Telegram notice claims remain guarded by repository locks.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select

from api.neironych_seedance_runtime import PRODUCT_MODELS
from core.config import settings
from db import repository as repo
from db.models import Generation, GenerationStatus, GenerationType
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_NOTICE_PENDING_REGEX = (
    r'"neironych_video_notice"\s*:\s*\{[^}]*"state"\s*:\s*"(pending|sending)"'
)


@dataclass
class _ScanCursor:
    newest_id: int = 0
    older_id: int = 0
    older_ceiling: int = 0
    single_old_next: bool = False


_video_cursor = _ScanCursor()
_notice_cursor = _ScanCursor()
_last_overdue_warning: dict[int, datetime] = {}
_last_missing_id_warning: datetime | None = None


def _eligible_video_query():
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.NEIRONYCH_VIDEO_RECONCILE_MIN_AGE_SECONDS
    )
    return select(Generation.id).where(
        Generation.gen_type == GenerationType.video,
        Generation.model.in_(tuple(PRODUCT_MODELS)),
        Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
        or_(
            Generation.task_id.like("neironych:%"),
            Generation.task_id.like("web:neironych:%"),
        ),
        Generation.created_at <= cutoff,
    )


def _eligible_notice_query():
    return select(Generation.id).where(
        Generation.gen_type == GenerationType.video,
        Generation.model.in_(tuple(PRODUCT_MODELS)),
        Generation.status.in_((GenerationStatus.done, GenerationStatus.failed)),
        Generation.task_id.like("neironych:%"),
        Generation.input_params.op("~")(_NOTICE_PENDING_REGEX),
    )


async def _pick_ids(session, query, cursor: _ScanCursor, limit: int) -> list[int]:
    """Reserve fresh + revisit lanes so old jobs cannot starve under new traffic."""
    if cursor.newest_id == 0:
        initial = list((await session.execute(
            query.order_by(Generation.id.asc()).limit(limit)
        )).scalars().all())
        if initial:
            cursor.newest_id = max(initial)
        return initial

    if limit == 1:
        forward_limit = 0 if cursor.single_old_next else 1
        cursor.single_old_next = not cursor.single_old_next
    else:
        forward_limit = max(1, limit // 2)
    revisit_limit = limit - forward_limit

    current_ceiling = cursor.newest_id
    fresh: list[int] = []
    if forward_limit:
        fresh = list((await session.execute(
            query.where(Generation.id > cursor.newest_id)
            .order_by(Generation.id.asc()).limit(forward_limit)
        )).scalars().all())
        if fresh:
            cursor.newest_id = fresh[-1]

    revisit_limit += forward_limit - len(fresh)
    if revisit_limit:
        if not cursor.older_ceiling:
            cursor.older_ceiling = current_ceiling
            cursor.older_id = 0
        older = list((await session.execute(
            query.where(
                Generation.id > cursor.older_id,
                Generation.id <= cursor.older_ceiling,
            ).order_by(Generation.id.asc()).limit(revisit_limit)
        )).scalars().all())
        if not older:
            # Complete the bounded old-row sweep; start a new one at the next
            # maximum, never resetting only to the oldest permanent stuck ID.
            cursor.older_ceiling = cursor.newest_id
            cursor.older_id = 0
            older = list((await session.execute(
                query.where(Generation.id <= cursor.older_ceiling)
                .order_by(Generation.id.asc()).limit(revisit_limit)
            )).scalars().all())
        if older:
            cursor.older_id = older[-1]
            if cursor.older_id >= cursor.older_ceiling:
                cursor.older_ceiling = 0
                cursor.older_id = 0
        fresh.extend(row_id for row_id in older if row_id not in fresh)

    return fresh[:limit]


async def _load_batch(query, cursor: _ScanCursor) -> list[int]:
    async with AsyncSessionLocal() as session:
        ids = await _pick_ids(
            session, query, cursor, settings.NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE,
        )
        await session.rollback()  # Release read-only transaction before HTTP calls.
    return ids


async def _process_active_video(gen_id: int) -> bool:
    from api.miniapp_routes import _reconcile_generation_status

    async with AsyncSessionLocal() as session:
        gen = await repo.get_generation_by_id(session, gen_id)
        if gen is None or gen.status not in (GenerationStatus.pending, GenerationStatus.processing):
            return False
        task_id = str(gen.task_id or "")
        if not (task_id.startswith("neironych:") or task_id.startswith("web:neironych:")):
            return False
        age = (datetime.now(timezone.utc) - gen.created_at).total_seconds()
        if age >= settings.NEIRONYCH_VIDEO_ALERT_AGE_SECONDS:
            now = datetime.now(timezone.utc)
            warned_at = _last_overdue_warning.get(gen.id)
            if warned_at is None or (now - warned_at) >= timedelta(minutes=15):
                _last_overdue_warning[gen.id] = now
                logger.warning(
                    "Neironych video overdue gen=%s model=%s age_seconds=%d provider_task=%s",
                    gen.id, gen.model, age, task_id[:96],
                )
        try:
            final = await asyncio.wait_for(
                _reconcile_generation_status(session, gen),
                timeout=settings.NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS,
            )
            logger.info(
                "Neironych video reconciled gen=%s model=%s status=%s age_seconds=%d",
                gen_id, gen.model, getattr(final.status, "value", final.status), age,
            )
            if final.status in (GenerationStatus.done, GenerationStatus.failed):
                _last_overdue_warning.pop(gen_id, None)
            return True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Neironych video reconciliation delayed gen=%s error=%s",
                gen_id, type(exc).__name__,
            )
            return False


async def _process_delivery_notice(gen_id: int) -> bool:
    from api.miniapp_routes import _deliver_pending_neironych_video_notice

    async with AsyncSessionLocal() as session:
        try:
            return await asyncio.wait_for(
                _deliver_pending_neironych_video_notice(session, gen_id),
                timeout=settings.NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await session.rollback()
            logger.warning(
                "Neironych video notice recovery deferred gen=%s error=%s",
                gen_id, type(exc).__name__,
            )
            return False


async def _count_missing_id_alerts() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.NEIRONYCH_VIDEO_ALERT_AGE_SECONDS
    )
    async with AsyncSessionLocal() as session:
        value = await session.scalar(
            select(func.count()).select_from(Generation).where(
                Generation.gen_type == GenerationType.video,
                Generation.model.in_(tuple(PRODUCT_MODELS)),
                Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
                or_(Generation.task_id.is_(None), Generation.task_id == ""),
                Generation.created_at <= cutoff,
            )
        )
        await session.rollback()
        return int(value or 0)


async def _process_bounded_batch(ids: list[int], action, stop: asyncio.Event | None) -> list[bool]:
    semaphore = asyncio.Semaphore(settings.NEIRONYCH_VIDEO_RECONCILE_CONCURRENCY)

    async def process(gen_id: int) -> bool:
        if stop is not None and stop.is_set():
            return False
        try:
            async with semaphore:
                if stop is not None and stop.is_set():
                    return False
                return await action(gen_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Neironych video recovery item failed gen=%s", gen_id)
            return False

    return list(await asyncio.gather(*(process(gen_id) for gen_id in ids)))


async def reconcile_neironych_videos_once(stop: asyncio.Event | None = None) -> dict[str, int]:
    """Bounded video polling and notice retries operate concurrently."""
    video_ids = await _load_batch(_eligible_video_query(), _video_cursor)
    notice_ids = await _load_batch(_eligible_notice_query(), _notice_cursor)
    video_results, notice_results = await asyncio.gather(
        _process_bounded_batch(video_ids, _process_active_video, stop),
        _process_bounded_batch(notice_ids, _process_delivery_notice, stop),
    )
    checked = len(video_results)
    notices = len(notice_results)
    notice_sent = sum(bool(result) for result in notice_results)
    missing = await _count_missing_id_alerts() if not stop or not stop.is_set() else 0
    global _last_missing_id_warning
    if missing:
        now = datetime.now(timezone.utc)
        if (
            _last_missing_id_warning is None
            or now - _last_missing_id_warning >= timedelta(minutes=15)
        ):
            _last_missing_id_warning = now
            logger.warning("Seedance submitted video missing provider task ID count=%s", missing)
    else:
        _last_missing_id_warning = None
    return {"checked": checked, "notices": notices, "sent": notice_sent, "missing_ids": missing}


async def run_neironych_video_reconcile_scheduler(stop: asyncio.Event) -> None:
    logger.info("Neironych Seedance video recovery scheduler started")
    while not stop.is_set():
        try:
            stats = await reconcile_neironych_videos_once(stop)
            if any(stats.values()):
                logger.info("Neironych Seedance video recovery summary=%s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Neironych Seedance video scheduler cycle failed")
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS
            )
        except asyncio.TimeoutError:
            pass
