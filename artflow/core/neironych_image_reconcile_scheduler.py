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


async def reconcile_neironych_images_once() -> int:
    # Limit load on the upstream status API. The recent-first slice prevents a
    # large manual-review backlog from starving newly created generations.
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(Generation)
            .where(
                Generation.model == "nano-banana-2.1",
                Generation.gen_type == GenerationType.image,
                Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
                Generation.task_id.like("%neironych-image:%"),
            )
            .order_by(Generation.created_at.desc(), Generation.id.desc())
            .limit(settings.NEIRONYCH_IMAGE_RECONCILE_BATCH_SIZE)
        )).scalars().all()
        from api.miniapp_routes import _reconcile_generation_status
        for generation in rows:
            try:
                await _reconcile_generation_status(session, generation)
            except Exception:
                await session.rollback()
                logger.exception(
                    "Neironych image scheduled reconciliation failed gen=%s", generation.id
                )
        return len(rows)


async def run_neironych_image_reconcile_scheduler(stop: asyncio.Event) -> None:
    logger.info("Neironych image reconciliation scheduler started")
    while not stop.is_set():
        try:
            checked = await reconcile_neironych_images_once()
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
