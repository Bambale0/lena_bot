"""Scheduled reconciliation of ambiguous Neironych image submissions.

Read-only provider lookups; the per-generation state machine holds the
single-winner completion/refund rule.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from core.config import settings
from db.models import Generation, GenerationStatus, GenerationType
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
_last_reconciled_id = 0


def _eligible_query():
    return select(Generation).where(
        Generation.model == "nano-banana-2.1",
        Generation.gen_type == GenerationType.image,
        Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
        Generation.task_id.like("%neironych-image:%"),
    )


async def _load_reconcile_rows(session) -> list[Generation]:
    """Read a keyset page and wrap, so no persistent row can starve."""
    global _last_reconciled_id
    batch_size = settings.NEIRONYCH_IMAGE_RECONCILE_BATCH_SIZE
    rows = (await session.execute(
        _eligible_query()
        .where(Generation.id > _last_reconciled_id)
        .order_by(Generation.id.asc())
        .limit(batch_size)
    )).scalars().all()
    if len(rows) < batch_size and _last_reconciled_id:
        wrapped = (await session.execute(
            _eligible_query()
            .where(Generation.id <= _last_reconciled_id)
            .order_by(Generation.id.asc())
            .limit(batch_size - len(rows))
        )).scalars().all()
        known = {row.id for row in rows}
        rows.extend(row for row in wrapped if row.id not in known)
    return rows


async def reconcile_neironych_images_once(stop: asyncio.Event | None = None) -> int:
    global _last_reconciled_id
    checked = 0
    async with AsyncSessionLocal() as session:
        rows = await _load_reconcile_rows(session)
        from api.miniapp_routes import _reconcile_generation_status
        for generation in rows:
            if stop is not None and stop.is_set():
                break
            try:
                await _reconcile_generation_status(session, generation)
            except Exception:
                await session.rollback()
                logger.exception(
                    "Neironych image scheduled reconciliation failed gen=%s", generation.id
                )
            finally:
                _last_reconciled_id = generation.id
                checked += 1
    return checked


async def run_neironych_image_reconcile_scheduler(stop: asyncio.Event) -> None:
    logger.info("Neironych image reconciliation scheduler started")
    while not stop.is_set():
        try:
            checked = await reconcile_neironych_images_once(stop)
            if checked:
                logger.info("Neironych image reconciliation checked=%s", checked)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Neironych image reconciliation cycle failed")
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.NEIRONYCH_IMAGE_RECONCILE_INTERVAL_SECONDS
            )
        except asyncio.TimeoutError:
            pass
