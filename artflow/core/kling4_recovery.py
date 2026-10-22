"""Read-only provider recovery and durable result delivery after restart.

Never re-submit or refund an unknown paid request by elapsed time.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import JSON, cast, or_, select

from api.kling4_contract import KLING4_MODELS
from core.config import settings
from db.models import Generation, GenerationStatus
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)
_scan_after = 0


async def reconcile_kling4_once() -> int:
    from api.miniapp_routes import (
        _deliver_pending_neironych_video_notice,
        _reconcile_generation_status,
    )

    global _scan_after
    query = (
        select(Generation.id)
        .where(
            Generation.model.in_(tuple(KLING4_MODELS)),
            or_(
                Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)),
                cast(Generation.input_params, JSON)["neironych_video_notice"]["state"]
                .as_string()
                .in_(("pending", "sending")),
            ),
        )
        .order_by(Generation.id.asc())
        .limit(settings.NEIRONYCH_VIDEO_RECONCILE_BATCH_SIZE)
    )
    async with AsyncSessionLocal() as session:
        ids = list(
            (await session.execute(query.where(Generation.id > _scan_after))).scalars().all()
        )
        if not ids and _scan_after:
            _scan_after = 0
            ids = list((await session.execute(query)).scalars().all())
    if ids:
        _scan_after = ids[-1]
    semaphore = asyncio.Semaphore(settings.NEIRONYCH_VIDEO_RECONCILE_CONCURRENCY)

    async def process(gen_id):
        async with semaphore:
            await process_one(gen_id)

    async def process_one(gen_id):
        try:
            async with AsyncSessionLocal() as session:
                gen = await session.get(Generation, gen_id)
                async with asyncio.timeout(settings.NEIRONYCH_VIDEO_RECONCILE_TIMEOUT_SECONDS):
                    if gen and gen.status in (
                        GenerationStatus.pending,
                        GenerationStatus.processing,
                    ):
                        await _reconcile_generation_status(session, gen)
                    await _deliver_pending_neironych_video_notice(session, gen_id)
        except Exception as exc:
            logger.warning("Kling4 recovery deferred gen=%s type=%s", gen_id, type(exc).__name__)

    await asyncio.gather(*(process(gen_id) for gen_id in ids))
    return len(ids)


async def run_kling4_recovery(stop: asyncio.Event) -> None:
    from core.config import settings

    while not stop.is_set():
        try:
            await reconcile_kling4_once()
        except Exception as exc:
            logger.warning("Kling4 recovery tick deferred type=%s", type(exc).__name__)
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=settings.NEIRONYCH_VIDEO_RECONCILE_INTERVAL_SECONDS
            )
        except TimeoutError:
            pass
