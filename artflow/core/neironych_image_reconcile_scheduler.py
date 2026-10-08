"""Bounded, fair reconciliation of Nano Banana 2.1 provider tasks.

Provider reads and atomic settlement only. Unknown Nexus submissions recover
through authenticated, correlated callbacks, never another paid POST.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import or_, select

from core.config import settings
from db.models import Generation, GenerationStatus, GenerationType
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
_last_reconciled_id = 0
_revisit_id = 0
_revisit_ceiling = 0
_forward_ids: set[int] = set()
_single_revisit_next = False


def _eligible_query():
    return select(Generation).where(
        Generation.model == "nano-banana-2.1",
        Generation.gen_type == GenerationType.image,
        Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
        or_(
            Generation.task_id.like("%neironych-image:%"),
            Generation.task_id.like("%nexus:%"),
        ),
    )


async def _load_reconcile_rows(session) -> list[Generation]:
    """Reserve revisit capacity and bound every old-row sweep by a fixed ID.

    Independent cursors ensure sustained new work cannot postpone revisits,
    while the revisit ceiling prevents new arrivals from extending a sweep.
    With batch size one, the two lanes alternate.
    """
    global _revisit_id, _revisit_ceiling, _forward_ids, _single_revisit_next
    batch_size = settings.NEIRONYCH_IMAGE_RECONCILE_BATCH_SIZE
    revisit_size = max(1, batch_size // 2) if _last_reconciled_id else 0
    if batch_size == 1 and _last_reconciled_id:
        revisit_size = int(_single_revisit_next)
        _single_revisit_next = not _single_revisit_next
    forward_size = batch_size - revisit_size
    if not _revisit_ceiling and _last_reconciled_id:
        _revisit_ceiling = _last_reconciled_id
        _revisit_id = 0

    rows = []
    if forward_size:
        rows = list((await session.execute(
            _eligible_query()
            .where(Generation.id > _last_reconciled_id)
            .order_by(Generation.id.asc()).limit(forward_size)
        )).scalars().all())[:forward_size]
    _forward_ids = {row.id for row in rows}
    remaining = batch_size - len(rows)
    if remaining and _revisit_ceiling:
        wrapped = list((await session.execute(
            _eligible_query()
            .where(Generation.id > _revisit_id, Generation.id <= _revisit_ceiling)
            .order_by(Generation.id.asc()).limit(remaining)
        )).scalars().all())[:remaining]
        rows.extend(wrapped)
        if not wrapped:
            _revisit_id = 0
            _revisit_ceiling = 0
    return rows


async def reconcile_neironych_images_once(stop: asyncio.Event | None = None) -> int:
    global _last_reconciled_id, _revisit_id, _revisit_ceiling
    checked = 0
    async with AsyncSessionLocal() as session:
        rows = await _load_reconcile_rows(session)
        from api.miniapp_routes import _reconcile_generation_status
        for generation, generation_id in [(row, row.id) for row in rows]:
            if stop is not None and stop.is_set():
                break
            try:
                if isinstance(generation, Generation):
                    await session.refresh(generation)
                await _reconcile_generation_status(session, generation)
            except Exception:
                await session.rollback()
                logger.exception(
                    "Nano Banana 2.1 scheduled reconciliation failed gen=%s", generation_id
                )
            finally:
                if generation_id in _forward_ids:
                    _last_reconciled_id = generation_id
                else:
                    _revisit_id = generation_id
                    if _revisit_id >= _revisit_ceiling:
                        _revisit_id = 0
                        _revisit_ceiling = 0
                checked += 1
    return checked


async def run_neironych_image_reconcile_scheduler(stop: asyncio.Event) -> None:
    logger.info("Nano Banana 2.1 reconciliation scheduler started")
    while not stop.is_set():
        try:
            checked = await reconcile_neironych_images_once(stop)
            if checked:
                logger.info("Nano Banana 2.1 reconciliation checked=%s", checked)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Nano Banana 2.1 reconciliation cycle failed")
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.NEIRONYCH_IMAGE_RECONCILE_INTERVAL_SECONDS
            )
        except asyncio.TimeoutError:
            pass
