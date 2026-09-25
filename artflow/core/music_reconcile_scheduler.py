"""Recover Suno generations when KIE callbacks are missed."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from api.miniapp_routes import _reconcile_generation_status
from core.config import settings
from db.models import Generation, GenerationStatus, GenerationType
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def reconcile_active_music_once() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.MUSIC_RECONCILE_MIN_AGE_SECONDS)
    async with AsyncSessionLocal() as session:
        generations = (
            await session.execute(
                select(Generation)
                .where(Generation.gen_type == GenerationType.music)
                .where(Generation.status.in_((GenerationStatus.pending, GenerationStatus.processing)))
                .where(Generation.created_at <= cutoff)
                .order_by(Generation.created_at)
            )
        ).scalars().all()
        for gen in generations:
            try:
                await _reconcile_generation_status(session, gen)
            except Exception:
                logger.exception("Music reconcile error gen=%s model=%s", gen.id, gen.model)
    return len(generations)


async def run_music_reconcile_scheduler(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            scanned = await reconcile_active_music_once()
            if scanned:
                logger.info("Music reconcile scanned=%s", scanned)
        except Exception:
            logger.exception("Music reconcile scan failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.MUSIC_RECONCILE_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
