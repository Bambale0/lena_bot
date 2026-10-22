"""Real PostgreSQL transaction seams. Each test owns an isolated schema."""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import api  # noqa: F401 - initialize legacy service/repository bindings before DB imports
from db.kling4_repository import reserve_kling4
from db.models import Base, CreditLedgerEntry, Generation, Kling4Intent, User


@pytest_asyncio.fixture
async def database():
    dsn = os.getenv("APIX_TEST_POSTGRES_URL")
    if not dsn:
        pytest.skip("APIX_TEST_POSTGRES_URL required for isolated PostgreSQL integration")
    url = make_url(dsn)
    if (
        url.host not in {"127.0.0.1", "localhost", "::1"}
        or url.database != "apix_session_migration_test"
    ):
        pytest.fail("Use the dedicated loopback migration test database")
    schema = "kling4_" + uuid4().hex
    admin = create_async_engine(dsn)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(dsn, connect_args={"server_settings": {"search_path": schema}})
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            user = User(tg_id=73123456, referral_code="kling4-test", credits=1000)
            session.add(user)
            await session.commit()
            owner = user.id
        yield sessions, owner
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@pytest.mark.asyncio
async def test_concurrent_same_intent_reserves_exactly_once(database):
    sessions, owner = database
    intent = str(uuid4())

    async def reserve():
        async with sessions() as session:
            gen, fresh = await reserve_kling4(
                session,
                user_id=owner,
                intent_id=intent,
                model="kling-4.0/reference-to-video",
                prompt="A scene",
                params={"duration": 3},
                credits=85.5,
                surface="web",
                max_active_generations=6,
            )
            return gen.id, fresh

    first, second = await asyncio.gather(reserve(), reserve())
    assert first[0] == second[0]
    assert sorted([first[1], second[1]]) == [False, True]
    async with sessions() as session:
        assert (await session.get(User, owner)).credits == 914.5
        for model in [Generation, CreditLedgerEntry, Kling4Intent]:
            assert await session.scalar(select(func.count()).select_from(model)) == 1


@pytest.mark.asyncio
async def test_atomic_reserve_rolls_back_wallet_if_intent_insert_fails(database, monkeypatch):
    sessions, owner = database
    from sqlalchemy import event

    def fail_intent(_mapper, _connection, _target):
        raise RuntimeError("simulated pre-commit crash")

    event.listen(Kling4Intent, "before_insert", fail_intent)
    try:
        async with sessions() as session:
            with pytest.raises(RuntimeError, match="pre-commit"):
                await reserve_kling4(
                    session,
                    user_id=owner,
                    intent_id=str(uuid4()),
                    model="kling-4.0/reference-to-video",
                    prompt="A scene",
                    params={},
                    credits=85.5,
                    surface="web",
                    max_active_generations=6,
                )
            await session.rollback()
    finally:
        event.remove(Kling4Intent, "before_insert", fail_intent)
    async with sessions() as session:
        assert (await session.get(User, owner)).credits == 1000
        for model in [Generation, CreditLedgerEntry, Kling4Intent]:
            assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
async def test_submission_marker_is_single_use_and_unknown_never_rebuys(database):
    sessions, owner = database
    from db import repository as repo

    async with sessions() as session:
        gen, _ = await reserve_kling4(
            session,
            user_id=owner,
            intent_id=str(uuid4()),
            model="kling-4.0/reference-to-video",
            prompt="A scene",
            params={},
            credits=85.5,
            surface="web",
            max_active_generations=6,
        )
        gen_id = gen.id
        assert await repo.begin_kie_video_submission(session, gen_id, "intent")
        assert not await repo.begin_kie_video_submission(session, gen_id, "intent")
        assert await repo.mark_kie_video_submission_unknown(session, gen_id)
        assert not await repo.begin_kie_video_submission(session, gen_id, "intent")
    # A different session simulates a restarted worker.
    async with sessions() as session:
        assert not await repo.begin_kie_video_submission(session, gen_id, "intent")
        assert (await session.get(User, owner)).credits == 914.5
        bound = await repo.bind_kie_video_callback(session, gen_id, "real-kie-task")
        assert bound.task_id == "web:real-kie-task"
        assert await repo.finish_generation(
            session,
            gen_id,
            "https://media.example.org/result.mp4",
            expected_task_id="web:real-kie-task",
        )
        failed, refunded = await repo.fail_generation_and_refund(
            session, gen_id, "late duplicate callback"
        )
        assert not failed and refunded == 0
        assert (await session.get(User, owner)).credits == 914.5
