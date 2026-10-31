from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from bot.services.broadcasts import process_broadcast_run, reconcile_broadcast_report
from db import broadcast_repository
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def run_broadcast_scheduler(stop_event: asyncio.Event, bot: Bot) -> None:
    while not stop_event.is_set():
        try:
            async with AsyncSessionLocal() as session:
                activated = await broadcast_repository.activate_stale_preparing_runs(
                    session,
                    stale_before=datetime.now(timezone.utc) - timedelta(seconds=30),
                )
                recovered = await broadcast_repository.mark_stale_sending_uncertain(
                    session,
                    stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
                )
                run_ids = await broadcast_repository.get_due_run_ids(session)
                report_run_ids = await broadcast_repository.get_pending_report_run_ids(
                    session
                )
            if activated:
                logger.warning(
                    "Broadcast worker activated unattached runs count=%s",
                    activated,
                )
            if recovered:
                logger.warning(
                    "Broadcast worker recovered interrupted deliveries count=%s",
                    recovered,
                )
            for run_id in run_ids:
                try:
                    await process_broadcast_run(bot=bot, run_id=run_id)
                except Exception:  # noqa: BLE001
                    logger.exception("Broadcast worker failed run=%s", run_id)
            for report_run_id in report_run_ids:
                try:
                    await reconcile_broadcast_report(
                        bot=bot,
                        run_id=report_run_id,
                    )
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Broadcast report reconciliation failed run=%s",
                        report_run_id,
                    )
        except Exception:  # noqa: BLE001
            logger.exception("Broadcast scheduler iteration failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=2)
        except asyncio.TimeoutError:
            continue
