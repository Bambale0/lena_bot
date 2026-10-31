from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

from db import broadcast_repository as broadcast_repo

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)

SEGMENT_LABELS: dict[str, str] = {
    "all": "Все пользователи",
    "paid": "Платившие",
    "new": "Новые за 7 дней",
    "active": "Активные за 14 дней",
}


@dataclass(frozen=True)
class BroadcastReport:
    run_id: str
    segment: str
    selected: int
    delivered: int
    skipped: int
    failed: int
    uncertain: int
    remaining: int


async def get_recipient_ids(session: AsyncSession, segment: str) -> list[int]:
    return await broadcast_repo.get_recipient_ids(session, segment)


async def count_non_telegram_users(session: AsyncSession, segment: str) -> int:
    return await broadcast_repo.count_non_telegram_users(session, segment)


async def queue_broadcast(
    session: AsyncSession,
    *,
    idempotency_key: str,
    segment: str,
    source_chat_id: int,
    source_message_id: int,
    created_by_chat_id: int,
    scheduled_for: datetime,
) -> tuple[Any, bool]:
    recipient_tg_ids = await get_recipient_ids(session, segment)
    skipped = await count_non_telegram_users(session, segment)
    return await broadcast_repo.create_run(
        session,
        idempotency_key=idempotency_key,
        segment=segment,
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        created_by_chat_id=created_by_chat_id,
        scheduled_for=scheduled_for,
        recipient_tg_ids=recipient_tg_ids,
        preselection_skipped_count=skipped,
    )


def _session_factory_or_default(session_factory):
    if session_factory is not None:
        return session_factory
    from db.session import AsyncSessionLocal

    return AsyncSessionLocal


def _report_from_snapshot(snapshot: dict[str, Any]) -> BroadcastReport:
    run = snapshot["run"]
    return BroadcastReport(
        run_id=run.id,
        segment=run.segment,
        selected=snapshot["selected"],
        delivered=snapshot["delivered"],
        skipped=snapshot["skipped"],
        failed=snapshot["failed"],
        uncertain=snapshot["uncertain"],
        remaining=snapshot["remaining"],
    )


def format_broadcast_report(report: BroadcastReport, *, completed: bool) -> str:
    heading = "✅ Рассылка завершена" if completed else "📢 Рассылка выполняется"
    text = (
        f"{heading}\n"
        f"ID: <code>{report.run_id}</code>\n"
        f"Сегмент: <b>{SEGMENT_LABELS.get(report.segment, report.segment)}</b>\n"
        f"Выбрано Telegram-получателей: {report.selected}\n"
        f"Доставлено: {report.delivered}\n"
        f"Пропущено: {report.skipped}\n"
        f"Ошибки: {report.failed}\n"
        f"Неопределённо без повтора: {report.uncertain}"
    )
    if not completed:
        text += f"\nОсталось: {report.remaining}"
    return text


async def _copy_broadcast_message(
    *,
    bot: Bot,
    source_chat_id: int,
    source_message_id: int,
    target_chat_id: int,
) -> int | None:
    result = await bot.copy_message(
        chat_id=target_chat_id,
        from_chat_id=source_chat_id,
        message_id=source_message_id,
    )
    return getattr(result, "message_id", None)


def _error_outcome(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, TelegramForbiddenError):
        return "failed", "forbidden", "bot blocked or chat unavailable"
    if isinstance(exc, TelegramBadRequest):
        return "failed", "bad_request", str(exc.message or "bad request")
    if isinstance(exc, TelegramNetworkError):
        return "uncertain", "network_error", "Telegram response was uncertain; not retried"
    return "uncertain", type(exc).__name__, "Unexpected Telegram result; not retried"


async def _deliver_claimed(
    *,
    bot: Bot,
    delivery,
    source_chat_id: int,
    source_message_id: int,
) -> tuple[str, int | None, str | None, str | None]:
    try:
        message_id = await _copy_broadcast_message(
            bot=bot,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            target_chat_id=delivery.tg_id,
        )
        return "delivered", message_id, None, None
    except TelegramRetryAfter as exc:
        await asyncio.sleep(float(exc.retry_after) + 0.5)
        try:
            message_id = await _copy_broadcast_message(
                bot=bot,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                target_chat_id=delivery.tg_id,
            )
            return "delivered", message_id, None, None
        except Exception as retry_exc:  # noqa: BLE001
            if isinstance(retry_exc, TelegramRetryAfter):
                return (
                    "failed",
                    None,
                    "retry_rate_limited",
                    "Telegram rate limit persisted after the bounded retry",
                )
            status, code, detail = _error_outcome(retry_exc)
            return status, None, f"retry_{code}", detail
    except Exception as exc:  # noqa: BLE001
        status, code, detail = _error_outcome(exc)
        return status, None, code, detail


async def _update_admin_report(
    *,
    bot: Bot,
    snapshot: dict[str, Any],
    completed: bool,
    session_factory,
) -> None:
    run = snapshot["run"]
    report = _report_from_snapshot(snapshot)
    text = format_broadcast_report(report, completed=completed)
    if completed:
        async with session_factory() as session:
            errors = await broadcast_repo.first_delivery_errors(
                session,
                run_id=run.id,
            )
        if errors:
            text += "\n\nПервые ошибки:\n" + "\n".join(
                f"• {tg_id}: {status} ({code or 'unknown'})"
                for tg_id, status, code in errors
            )
    try:
        if run.report_chat_id and run.report_message_id:
            await bot.edit_message_text(
                chat_id=run.report_chat_id,
                message_id=run.report_message_id,
                text=text,
            )
        elif completed:
            await bot.send_message(run.created_by_chat_id, text)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Broadcast admin report failed run=%s error_type=%s",
            run.id,
            type(exc).__name__,
        )


async def process_broadcast_run(
    *,
    bot: Bot,
    run_id: str,
    session_factory: Callable[[], Any] | async_sessionmaker | None = None,
    progress_every: int = 20,
    sleep_seconds: float = 0.05,
) -> BroadcastReport:
    sessions = _session_factory_or_default(session_factory)
    processed = 0
    logger.info("Broadcast worker started run=%s", run_id)

    while True:
        async with sessions() as session:
            delivery = await broadcast_repo.claim_next_delivery(session, run_id=run_id)
            run = await session.get(broadcast_repo.BroadcastRun, run_id)
        if delivery is None:
            break
        if run is None:
            raise LookupError(f"Broadcast run not found: {run_id}")

        async with sessions() as session:
            deliverable = await broadcast_repo.recipient_is_deliverable(
                session,
                user_id=delivery.user_id,
                tg_id=delivery.tg_id,
            )
        if deliverable:
            status, telegram_message_id, error_code, error_detail = await _deliver_claimed(
                bot=bot,
                delivery=delivery,
                source_chat_id=run.source_chat_id,
                source_message_id=run.source_message_id,
            )
        else:
            status, telegram_message_id = "skipped", None
            error_code, error_detail = "recipient_ineligible", "Recipient no longer deliverable"

        async with sessions() as session:
            await broadcast_repo.complete_delivery(
                session,
                delivery_id=delivery.id,
                status=status,
                telegram_message_id=telegram_message_id,
                error_code=error_code,
                error_detail=error_detail,
            )
        if status != "delivered":
            logger.warning(
                "Broadcast delivery terminal run=%s user=%s status=%s error=%s",
                run_id,
                delivery.user_id,
                status,
                error_code,
            )

        processed += 1
        if progress_every > 0 and processed % progress_every == 0:
            async with sessions() as session:
                snapshot = await broadcast_repo.get_run_report(session, run_id=run_id)
            await _update_admin_report(
                bot=bot,
                snapshot=snapshot,
                completed=False,
                session_factory=sessions,
            )
        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

    async with sessions() as session:
        snapshot = await broadcast_repo.finalize_run_if_terminal(session, run_id=run_id)
    completed = snapshot["remaining"] == 0
    await _update_admin_report(
        bot=bot,
        snapshot=snapshot,
        completed=completed,
        session_factory=sessions,
    )
    report = _report_from_snapshot(snapshot)
    logger.info(
        "Broadcast worker finished run=%s delivered=%s skipped=%s failed=%s uncertain=%s remaining=%s",
        run_id,
        report.delivered,
        report.skipped,
        report.failed,
        report.uncertain,
        report.remaining,
    )
    return report
