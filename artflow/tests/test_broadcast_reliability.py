from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import sqlalchemy as sa
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from bot.services import broadcasts
from db import broadcast_repository
from db.models import (
    Base,
    BroadcastDelivery,
    BroadcastRun,
    Generation,
    Transaction,
    User,
)


class LocalSession:
    def __init__(self, session: Session) -> None:
        self.sync = session

    async def execute(self, statement):
        return self.sync.execute(statement)


def test_broadcast_migration_adds_activity_queue_and_delivery_audit() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "db/migrations/versions/056_broadcast_delivery.py"
    )
    spec = importlib.util.spec_from_file_location("broadcast_delivery_migration", path)
    migration = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE users ("
                "id INTEGER PRIMARY KEY, tg_id BIGINT NOT NULL, is_banned BOOLEAN NOT NULL"
                ")"
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

    inspector = sa.inspect(engine)
    assert "last_telegram_activity_at" in {
        column["name"] for column in inspector.get_columns("users")
    }
    assert {"broadcast_runs", "broadcast_deliveries"}.issubset(
        inspector.get_table_names()
    )
    assert {index["name"] for index in inspector.get_indexes("broadcast_runs")} >= {
        "ix_broadcast_runs_due"
    }
    assert {
        index["name"] for index in inspector.get_indexes("broadcast_deliveries")
    } >= {"ix_broadcast_deliveries_run_status"}
    engine.dispose()


@pytest.mark.asyncio
async def test_broadcast_segments_use_real_telegram_activity_and_skip_web_only_ids() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[User.__table__, Generation.__table__, Transaction.__table__],
    )
    now = datetime.now(timezone.utc)
    with Session(engine, expire_on_commit=False) as sync:
        sync.add_all(
            [
                User(
                    id=1,
                    tg_id=1001,
                    credits=0,
                    referral_code="recent-telegram-user",
                    created_at=now - timedelta(days=90),
                    last_telegram_activity_at=now - timedelta(hours=2),
                ),
                User(
                    id=2,
                    tg_id=1002,
                    credits=0,
                    referral_code="stale-telegram-user",
                    created_at=now - timedelta(days=90),
                    last_telegram_activity_at=now - timedelta(days=30),
                ),
                User(
                    id=3,
                    tg_id=-3003,
                    credits=0,
                    referral_code="web-only-user",
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
        sync.commit()
        session = LocalSession(sync)

        assert await broadcast_repository.get_recipient_ids(session, "all") == [1001, 1002]
        assert await broadcast_repository.get_recipient_ids(session, "active") == [1001]
        assert await broadcast_repository.count_non_telegram_users(session, "all") == 1

    engine.dispose()


@pytest.mark.asyncio
async def test_unknown_broadcast_segment_fails_closed() -> None:
    session = AsyncMock()
    with pytest.raises(ValueError, match="Unknown broadcast segment"):
        await broadcast_repository.get_recipient_ids(session, "typo")
    session.execute.assert_not_awaited()


async def _broadcast_database(tmp_path):
    engine = create_async_engine(
        "sqlite+aiosqlite:///" + str(tmp_path / "broadcast.db")
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=[
                    User.__table__,
                    BroadcastRun.__table__,
                    BroadcastDelivery.__table__,
                ],
            )
        )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_queue_is_idempotent_and_snapshots_each_recipient_once(tmp_path) -> None:
    engine, sessions = await _broadcast_database(tmp_path)
    try:
        async with sessions() as session:
            session.add_all(
                [
                    User(id=1, tg_id=101, credits=0, referral_code="one"),
                    User(id=2, tg_id=202, credits=0, referral_code="two"),
                ]
            )
            await session.commit()

        async with sessions() as session:
            first, first_created = await broadcast_repository.create_run(
                session,
                idempotency_key="draft-123",
                segment="all",
                source_chat_id=900,
                source_message_id=901,
                created_by_chat_id=42,
                scheduled_for=datetime.now(timezone.utc),
                recipient_tg_ids=[101, 202, 202],
                preselection_skipped_count=3,
            )
        async with sessions() as session:
            second, second_created = await broadcast_repository.create_run(
                session,
                idempotency_key="draft-123",
                segment="all",
                source_chat_id=900,
                source_message_id=901,
                created_by_chat_id=42,
                scheduled_for=datetime.now(timezone.utc),
                recipient_tg_ids=[101, 202],
                preselection_skipped_count=3,
            )
            deliveries = (
                await session.execute(
                    select(BroadcastDelivery).where(BroadcastDelivery.run_id == first.id)
                )
            ).scalars().all()

        assert first_created is True
        assert second_created is False
        assert second.id == first.id
        assert first.status == "preparing"
        assert sorted(item.tg_id for item in deliveries) == [101, 202]
        assert first.selected_count == 2
        assert first.preselection_skipped_count == 3
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_is_not_due_until_admin_report_is_attached(tmp_path) -> None:
    engine, sessions = await _broadcast_database(tmp_path)
    try:
        async with sessions() as session:
            session.add(User(id=1, tg_id=101, credits=0, referral_code="one"))
            await session.commit()
            run, _ = await broadcast_repository.create_run(
                session,
                idempotency_key="attach-before-send",
                segment="all",
                source_chat_id=900,
                source_message_id=901,
                created_by_chat_id=42,
                scheduled_for=datetime.now(timezone.utc),
                recipient_tg_ids=[101],
                preselection_skipped_count=0,
            )
            assert await broadcast_repository.get_due_run_ids(session) == []
            await broadcast_repository.attach_report_message(
                session,
                run_id=run.id,
                chat_id=42,
                message_id=500,
            )
            assert await broadcast_repository.get_due_run_ids(session) == [run.id]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_unattached_run_is_recovered_instead_of_lost(tmp_path) -> None:
    engine, sessions = await _broadcast_database(tmp_path)
    try:
        async with sessions() as session:
            session.add(User(id=1, tg_id=101, credits=0, referral_code="one"))
            await session.commit()
            run, _ = await broadcast_repository.create_run(
                session,
                idempotency_key="recover-unattached",
                segment="all",
                source_chat_id=900,
                source_message_id=901,
                created_by_chat_id=42,
                scheduled_for=datetime.now(timezone.utc),
                recipient_tg_ids=[101],
                preselection_skipped_count=0,
            )
            run.created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()
            activated = await broadcast_repository.activate_stale_preparing_runs(
                session,
                stale_before=datetime.now(timezone.utc) - timedelta(seconds=30),
            )
            assert activated == 1
            assert await broadcast_repository.get_due_run_ids(session) == [run.id]

        bot = SimpleNamespace(copy_message=AsyncMock(return_value=SimpleNamespace(message_id=1)))
        report = await broadcasts.process_broadcast_run(
            bot=bot,
            run_id=run.id,
            session_factory=sessions,
            progress_every=100,
            sleep_seconds=0,
        )
        assert bot.copy_message.await_count == 1
        assert report.delivered == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_second_rate_limit_is_definite_failure_after_bounded_retry(
    monkeypatch,
) -> None:
    monkeypatch.setattr("bot.services.broadcasts.asyncio.sleep", AsyncMock())
    bot = SimpleNamespace(
        copy_message=AsyncMock(
            side_effect=[
                TelegramRetryAfter(method="copyMessage", message="retry", retry_after=1),
                TelegramRetryAfter(method="copyMessage", message="retry", retry_after=2),
            ]
        )
    )

    outcome = await broadcasts._deliver_claimed(
        bot=bot,
        delivery=SimpleNamespace(tg_id=101),
        source_chat_id=900,
        source_message_id=901,
    )

    assert outcome == (
        "failed",
        None,
        "retry_rate_limited",
        "Telegram rate limit persisted after the bounded retry",
    )
    assert bot.copy_message.await_count == 2


@pytest.mark.asyncio
async def test_worker_persists_delivered_failed_and_uncertain_without_unsafe_retry(
    tmp_path,
) -> None:
    engine, sessions = await _broadcast_database(tmp_path)
    try:
        async with sessions() as session:
            session.add_all(
                [
                    User(id=1, tg_id=101, credits=0, referral_code="one"),
                    User(id=2, tg_id=202, credits=0, referral_code="two"),
                    User(id=3, tg_id=303, credits=0, referral_code="three"),
                ]
            )
            await session.commit()
            run, _ = await broadcast_repository.create_run(
                session,
                idempotency_key="delivery-123",
                segment="all",
                source_chat_id=900,
                source_message_id=901,
                created_by_chat_id=42,
                scheduled_for=datetime.now(timezone.utc),
                recipient_tg_ids=[101, 202, 303],
                preselection_skipped_count=1,
            )

        bot = SimpleNamespace(copy_message=AsyncMock())
        bot.copy_message.side_effect = [
            SimpleNamespace(message_id=7001),
            TelegramBadRequest(method="copyMessage", message="chat not found"),
            TelegramNetworkError(method="copyMessage", message="connection reset"),
        ]

        report = await broadcasts.process_broadcast_run(
            bot=bot,
            run_id=run.id,
            session_factory=sessions,
            progress_every=100,
            sleep_seconds=0,
        )

        assert bot.copy_message.await_count == 3
        assert report.delivered == 1
        assert report.failed == 1
        assert report.uncertain == 1
        assert report.skipped == 1
        async with sessions() as session:
            statuses = dict(
                (
                    await session.execute(
                        select(BroadcastDelivery.tg_id, BroadcastDelivery.status)
                    )
                ).all()
            )
        assert statuses == {101: "delivered", 202: "failed", 303: "uncertain"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_stale_in_flight_delivery_becomes_uncertain_instead_of_duplicate(
    tmp_path,
) -> None:
    engine, sessions = await _broadcast_database(tmp_path)
    try:
        async with sessions() as session:
            session.add(User(id=1, tg_id=101, credits=0, referral_code="one"))
            await session.commit()
            run, _ = await broadcast_repository.create_run(
                session,
                idempotency_key="interrupted-123",
                segment="all",
                source_chat_id=900,
                source_message_id=901,
                created_by_chat_id=42,
                scheduled_for=datetime.now(timezone.utc),
                recipient_tg_ids=[101],
                preselection_skipped_count=0,
            )
            delivery = await session.scalar(select(BroadcastDelivery))
            delivery.status = "sending"
            delivery.last_attempt_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            await session.commit()

        async with sessions() as session:
            recovered = await broadcast_repository.mark_stale_sending_uncertain(
                session,
                stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
            delivery = await session.scalar(select(BroadcastDelivery))

        assert recovered == 1
        assert delivery.status == "uncertain"
        assert "not retried" in (delivery.error_detail or "")
        bot = SimpleNamespace(copy_message=AsyncMock())
        report = await broadcasts.process_broadcast_run(
            bot=bot,
            run_id=run.id,
            session_factory=sessions,
            progress_every=100,
            sleep_seconds=0,
        )
        bot.copy_message.assert_not_awaited()
        assert report.uncertain == 1
    finally:
        await engine.dispose()
