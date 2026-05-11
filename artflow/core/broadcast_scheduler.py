from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiogram import Bot

from bot.services.broadcasts import SEGMENT_LABELS, deliver_broadcast, get_recipient_ids
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

JOBS_PATH = Path("data/broadcast_jobs.json")


def _read_jobs_sync() -> list[dict[str, Any]]:
    if not JOBS_PATH.exists():
        return []
    try:
        return json.loads(JOBS_PATH.read_text())
    except Exception:
        logger.warning("Failed to read broadcast jobs file; resetting")
        return []


def _write_jobs_sync(jobs: list[dict[str, Any]]) -> None:
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    JOBS_PATH.write_text(json.dumps(jobs, ensure_ascii=False, indent=2))


async def _read_jobs() -> list[dict[str, Any]]:
    return await asyncio.to_thread(_read_jobs_sync)


async def _write_jobs(jobs: list[dict[str, Any]]) -> None:
    await asyncio.to_thread(_write_jobs_sync, jobs)


async def schedule_broadcast_job(
    *,
    source_chat_id: int,
    source_message_id: int,
    segment: str,
    scheduled_for: datetime,
    created_by_chat_id: int,
) -> str:
    jobs = await _read_jobs()
    job_id = secrets.token_hex(8)
    jobs.append(
        {
            "id": job_id,
            "source_chat_id": int(source_chat_id),
            "source_message_id": int(source_message_id),
            "segment": segment,
            "scheduled_for": scheduled_for.astimezone(timezone.utc).isoformat(),
            "created_by_chat_id": int(created_by_chat_id),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await _write_jobs(jobs)
    return job_id


async def pop_due_broadcast_jobs() -> list[dict[str, Any]]:
    jobs = await _read_jobs()
    if not jobs:
        return []

    now = datetime.now(timezone.utc)
    due: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for job in jobs:
        try:
            scheduled_for = datetime.fromisoformat(job["scheduled_for"])
        except Exception:
            logger.warning("Dropping malformed broadcast job: %s", job)
            continue
        if scheduled_for <= now:
            due.append(job)
        else:
            pending.append(job)

    if len(pending) != len(jobs):
        await _write_jobs(pending)
    return due


async def run_broadcast_scheduler(stop_event: asyncio.Event, bot: Bot) -> None:
    while not stop_event.is_set():
        try:
            due_jobs = await pop_due_broadcast_jobs()
            for job in due_jobs:
                async with AsyncSessionLocal() as session:
                    tg_ids = await get_recipient_ids(session, job.get("segment", "all"))
                sent, failed, errors = await deliver_broadcast(
                    bot=bot,
                    tg_ids=tg_ids,
                    source_chat_id=int(job["source_chat_id"]),
                    source_message_id=int(job["source_message_id"]),
                    status_msg=None,
                )
                segment_label = SEGMENT_LABELS.get(job.get("segment", "all"), job.get("segment", "all"))
                report = (
                    "⏰ Отложенная рассылка завершена\n"
                    f"Сегмент: {segment_label}\n"
                    f"Доставлено: {sent} · Ошибок: {failed}"
                )
                if errors:
                    report += "\n\nПервые ошибки:\n" + "\n".join(f"• {item}" for item in errors)
                try:
                    await bot.send_message(int(job["created_by_chat_id"]), report)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to send scheduled broadcast report: %s", exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Broadcast scheduler error: %s", exc)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=15)
        except asyncio.TimeoutError:
            continue
