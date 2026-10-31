from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    BroadcastDelivery,
    BroadcastRun,
    Generation,
    Transaction,
    TransactionStatus,
    User,
)

VALID_BROADCAST_SEGMENTS = frozenset({"all", "paid", "new", "active"})


def _segment_conditions(segment: str, *, now: datetime) -> list[Any]:
    if segment not in VALID_BROADCAST_SEGMENTS:
        raise ValueError(f"Unknown broadcast segment: {segment}")
    if segment == "all":
        return []
    if segment == "paid":
        return [
            User.id.in_(
                select(Transaction.user_id).where(
                    Transaction.status == TransactionStatus.paid
                )
            )
        ]
    if segment == "new":
        return [User.created_at >= now - timedelta(days=7)]

    cutoff = now - timedelta(days=14)
    return [
        or_(
            User.last_telegram_activity_at >= cutoff,
            User.created_at >= cutoff,
            User.id.in_(
                select(Generation.user_id).where(Generation.created_at >= cutoff)
            ),
            User.id.in_(
                select(Transaction.user_id).where(
                    Transaction.created_at >= cutoff,
                    Transaction.status == TransactionStatus.paid,
                )
            ),
        )
    ]


async def get_recipient_ids(
    session: AsyncSession,
    segment: str = "all",
    *,
    now: datetime | None = None,
) -> list[int]:
    now = now or datetime.now(timezone.utc)
    statement = (
        select(User.tg_id)
        .where(
            User.is_banned.is_(False),
            User.tg_id > 0,
            *_segment_conditions(segment, now=now),
        )
        .order_by(User.id)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def count_non_telegram_users(
    session: AsyncSession,
    segment: str = "all",
    *,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    statement = select(func.count()).select_from(User).where(
        User.is_banned.is_(False),
        User.tg_id <= 0,
        *_segment_conditions(segment, now=now),
    )
    result = await session.execute(statement)
    return int(result.scalar_one())


async def create_run(
    session: AsyncSession,
    *,
    idempotency_key: str,
    segment: str,
    source_chat_id: int,
    source_message_id: int,
    created_by_chat_id: int,
    scheduled_for: datetime,
    recipient_tg_ids: list[int],
    preselection_skipped_count: int,
) -> tuple[BroadcastRun, bool]:
    _segment_conditions(segment, now=scheduled_for)
    existing = await session.scalar(
        select(BroadcastRun).where(BroadcastRun.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing, False

    unique_tg_ids = sorted({int(tg_id) for tg_id in recipient_tg_ids if int(tg_id) > 0})
    recipients = (
        await session.execute(
            select(User.id, User.tg_id)
            .where(
                User.tg_id.in_(unique_tg_ids),
                User.is_banned.is_(False),
            )
            .order_by(User.id)
        )
    ).all()
    run = BroadcastRun(
        id=secrets.token_hex(16),
        idempotency_key=idempotency_key,
        segment=segment,
        source_chat_id=int(source_chat_id),
        source_message_id=int(source_message_id),
        created_by_chat_id=int(created_by_chat_id),
        scheduled_for=scheduled_for.astimezone(timezone.utc),
        status="preparing",
        selected_count=len(recipients),
        preselection_skipped_count=max(0, int(preselection_skipped_count)),
    )
    session.add(run)
    session.add_all(
        BroadcastDelivery(
            run_id=run.id,
            user_id=int(user_id),
            tg_id=int(tg_id),
            status="pending",
        )
        for user_id, tg_id in recipients
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(BroadcastRun).where(BroadcastRun.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing, False
    return run, True


async def attach_report_message(
    session: AsyncSession,
    *,
    run_id: str,
    chat_id: int,
    message_id: int,
) -> None:
    await session.execute(
        update(BroadcastRun)
        .where(BroadcastRun.id == run_id)
        .values(
            report_chat_id=int(chat_id),
            report_message_id=int(message_id),
            status=case(
                (BroadcastRun.status == "preparing", "queued"),
                else_=BroadcastRun.status,
            ),
        )
    )
    await session.commit()


async def get_due_run_ids(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 10,
) -> list[str]:
    now = now or datetime.now(timezone.utc)
    result = await session.execute(
        select(BroadcastRun.id)
        .where(
            BroadcastRun.status.in_(("queued", "running")),
            BroadcastRun.scheduled_for <= now,
        )
        .order_by(BroadcastRun.scheduled_for, BroadcastRun.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def activate_stale_preparing_runs(
    session: AsyncSession,
    *,
    stale_before: datetime,
) -> int:
    result = await session.execute(
        update(BroadcastRun)
        .where(
            BroadcastRun.status == "preparing",
            BroadcastRun.created_at < stale_before,
        )
        .values(status="queued")
    )
    await session.commit()
    return int(result.rowcount or 0)


async def claim_next_delivery(
    session: AsyncSession,
    *,
    run_id: str,
) -> BroadcastDelivery | None:
    delivery = await session.scalar(
        select(BroadcastDelivery)
        .where(
            BroadcastDelivery.run_id == run_id,
            BroadcastDelivery.status == "pending",
        )
        .order_by(BroadcastDelivery.id)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if delivery is None:
        return None

    now = datetime.now(timezone.utc)
    delivery.status = "sending"
    delivery.attempts += 1
    delivery.last_attempt_at = now
    run = await session.get(BroadcastRun, run_id)
    if run is not None:
        run.status = "running"
        run.started_at = run.started_at or now
    await session.commit()
    return delivery


async def recipient_is_deliverable(
    session: AsyncSession,
    *,
    user_id: int,
    tg_id: int,
) -> bool:
    result = await session.execute(
        select(User.id).where(
            User.id == user_id,
            User.tg_id == tg_id,
            User.tg_id > 0,
            User.is_banned.is_(False),
        )
    )
    return result.scalar_one_or_none() is not None


async def complete_delivery(
    session: AsyncSession,
    *,
    delivery_id: int,
    status: str,
    telegram_message_id: int | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
) -> None:
    if status not in {"delivered", "skipped", "failed", "uncertain"}:
        raise ValueError(f"Invalid terminal broadcast delivery status: {status}")
    delivery = await session.get(BroadcastDelivery, delivery_id, with_for_update=True)
    if delivery is None or delivery.status != "sending":
        return
    delivery.status = status
    delivery.telegram_message_id = telegram_message_id
    delivery.error_code = error_code[:64] if error_code else None
    delivery.error_detail = error_detail[:256] if error_detail else None
    if status == "delivered":
        delivery.delivered_at = datetime.now(timezone.utc)
    await session.commit()


async def mark_stale_sending_uncertain(
    session: AsyncSession,
    *,
    stale_before: datetime,
) -> int:
    result = await session.execute(
        update(BroadcastDelivery)
        .where(
            BroadcastDelivery.status == "sending",
            BroadcastDelivery.last_attempt_at < stale_before,
        )
        .values(
            status="uncertain",
            error_code="worker_interrupted",
            error_detail="Previous delivery was interrupted and was not retried to avoid a duplicate",
        )
    )
    await session.commit()
    return int(result.rowcount or 0)


async def get_run_report(session: AsyncSession, *, run_id: str) -> dict[str, Any]:
    run = await session.get(BroadcastRun, run_id)
    if run is None:
        raise LookupError(f"Broadcast run not found: {run_id}")
    counts = (
        await session.execute(
            select(
                func.count(BroadcastDelivery.id).label("total"),
                func.sum(case((BroadcastDelivery.status == "delivered", 1), else_=0)).label(
                    "delivered"
                ),
                func.sum(case((BroadcastDelivery.status == "skipped", 1), else_=0)).label(
                    "skipped"
                ),
                func.sum(case((BroadcastDelivery.status == "failed", 1), else_=0)).label(
                    "failed"
                ),
                func.sum(case((BroadcastDelivery.status == "uncertain", 1), else_=0)).label(
                    "uncertain"
                ),
                func.sum(
                    case((BroadcastDelivery.status.in_(("pending", "sending")), 1), else_=0)
                ).label("remaining"),
            ).where(BroadcastDelivery.run_id == run_id)
        )
    ).one()
    return {
        "run": run,
        "selected": int(counts.total or 0),
        "delivered": int(counts.delivered or 0),
        "skipped": int(counts.skipped or 0) + int(run.preselection_skipped_count),
        "failed": int(counts.failed or 0),
        "uncertain": int(counts.uncertain or 0),
        "remaining": int(counts.remaining or 0),
    }


async def finalize_run_if_terminal(
    session: AsyncSession,
    *,
    run_id: str,
) -> dict[str, Any]:
    report = await get_run_report(session, run_id=run_id)
    run: BroadcastRun = report["run"]
    if report["remaining"] == 0 and run.status != "completed":
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()
    return report


async def first_delivery_errors(
    session: AsyncSession,
    *,
    run_id: str,
    limit: int = 10,
) -> list[tuple[int, str, str | None]]:
    return list(
        (
            await session.execute(
                select(
                    BroadcastDelivery.tg_id,
                    BroadcastDelivery.status,
                    BroadcastDelivery.error_code,
                )
                .where(
                    BroadcastDelivery.run_id == run_id,
                    BroadcastDelivery.status.in_(("failed", "uncertain")),
                )
                .order_by(BroadcastDelivery.id)
                .limit(limit)
            )
        ).all()
    )
