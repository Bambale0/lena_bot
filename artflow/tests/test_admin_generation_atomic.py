"""Manual admin failure must commit status, wallet and ledger together."""
import asyncio
import hashlib
import hmac
import json
import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlencode
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from api import miniapp_routes  # noqa: F401 - initialize application imports
from api.web import admin
from db import repository as repo
from db.models import Base, CreditLedgerEntry, Generation, GenerationStatus, GenerationType, User
from db.session import get_session


class LocalSession:
    def __init__(self, session):
        self.session = session

    async def execute(self, query):
        return self.session.execute(query)

    async def commit(self):
        self.session.commit()

    async def rollback(self):
        self.session.rollback()

    async def flush(self):
        self.session.flush()

    def add(self, row):
        self.session.add(row)


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [991])
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    engine = create_engine("sqlite:///" + str(tmp_path / "admin.db"))
    Base.metadata.create_all(engine, tables=[User.__table__, Generation.__table__, CreditLedgerEntry.__table__])
    with Session(engine) as session:
        session.add(User(id=42, tg_id=420, credits=100, referral_code="test-admin"))
        session.add(User(id=43, tg_id=991, credits=0, referral_code="test-operator"))
        session.add(Generation(id=73, user_id=42, model="fixture", gen_type=GenerationType.image,
                               status=GenerationStatus.processing, prompt="test", credits_spent=40))
        session.commit()
    yield engine
    engine.dispose()


async def fail(session, refund=True, user=SimpleNamespace(tg_id=991)):
    return await admin.admin_fail_generation(73, admin.AdminGenerationFailRequest(error="Manual test reason", refund=refund), session, user)


@pytest.mark.asyncio
async def test_ledger_failure_rolls_back_status_and_wallet_then_retry(local_db):
    def reject_insert(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("INSERT INTO CREDIT_LEDGER"):
            raise RuntimeError("injected ledger failure")
    event.listen(local_db, "before_cursor_execute", reject_insert)
    try:
        with Session(local_db, expire_on_commit=False) as session:
            with pytest.raises(RuntimeError, match="injected ledger failure"):
                await fail(LocalSession(session))
            session.rollback()
    finally:
        event.remove(local_db, "before_cursor_execute", reject_insert)
    with Session(local_db, expire_on_commit=False) as session:
        assert session.get(Generation, 73).status == GenerationStatus.processing
        assert session.get(User, 42).credits == 100
        assert session.scalars(select(CreditLedgerEntry)).all() == []
        response = await fail(LocalSession(session))
        assert response["data"]["refunded_credits"] == 40
        assert response["data"]["changed"] is True
        rows = session.scalars(select(CreditLedgerEntry)).all()
        assert len(rows) == 1 and rows[0].entry_type == "admin_generation_refund"
        assert "991" in rows[0].note
        assert (await fail(LocalSession(session))).status_code == 409
        assert session.get(User, 42).credits == 140


@pytest.mark.asyncio
@pytest.mark.parametrize("refund,spent,expected", [(False, 40, 0), (True, 0, 0), (True, 40, 40)])
async def test_response_reports_actual_refund(local_db, refund, spent, expected):
    with Session(local_db, expire_on_commit=False) as session:
        session.get(Generation, 73).credits_spent = spent
        session.commit()
        data = (await fail(LocalSession(session), refund))["data"]
        assert data["changed"] is True
        assert data["refunded_credits"] == expected
        assert data["refunded"] is (expected > 0)


@pytest.mark.asyncio
async def test_lost_transition_returns_conflict(local_db, monkeypatch):
    monkeypatch.setattr(repo, "fail_generation", AsyncMock(return_value=False))
    monkeypatch.setattr(repo, "fail_generation_and_refund", AsyncMock(return_value=(False, 0)))
    with Session(local_db) as session:
        assert (await fail(LocalSession(session))).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("user", [None, SimpleNamespace(tg_id=123)])
async def test_auth_blocks_before_database(local_db, user):
    response = await fail(None, user=user)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("identity,expected", [(None, 401), ("invalid", 401), (420, 403), (991, 200)])
async def test_mounted_admin_route_signed_telegram_auth(local_db, monkeypatch, identity, expected):
    token = "123:fixture-admin-token"
    monkeypatch.setattr(admin.settings, "BOT_TOKEN", token)
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/web")
    async def sessions():
        with Session(local_db, expire_on_commit=False) as session:
            yield LocalSession(session)
    app.dependency_overrides[get_session] = sessions
    headers = {}
    if isinstance(identity, int):
        data = {"auth_date": str(int(time.time())), "user": json.dumps({"id": identity})}
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        data["hash"] = hmac.new(secret, "\n".join(f"{k}={v}" for k, v in sorted(data.items())).encode(), hashlib.sha256).hexdigest()
        headers["X-Telegram-Init-Data"] = urlencode(data)
    elif identity:
        headers["X-Telegram-Init-Data"] = identity
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/web/admin/generations/73/fail", headers=headers, json={"error": "Reviewed", "refund": True})
        assert response.status_code == expected
    with Session(local_db) as session:
        assert session.get(User, 42).credits == (140 if expected == 200 else 100)


@pytest.mark.asyncio
async def test_postgres_ledger_insert_failure_rolls_back_generation_and_wallet(pg_db):
    factory, engine = pg_db
    def reject_insert(_conn, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("INSERT INTO CREDIT_LEDGER"):
            raise RuntimeError("injected ledger failure")
    event.listen(engine.sync_engine, "before_cursor_execute", reject_insert)
    try:
        async with factory() as session:
            with pytest.raises(RuntimeError, match="injected ledger failure"):
                await fail(session)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", reject_insert)
    async with factory() as session:
        assert (await session.get(Generation, 73)).status == GenerationStatus.processing
        assert (await session.get(User, 42)).credits == 100
        assert (await session.scalars(select(CreditLedgerEntry))).all() == []
        assert (await fail(session))["data"]["refunded_credits"] == 40


@pytest_asyncio.fixture
async def pg_db(monkeypatch):
    url = os.environ.get("APIX_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Requires disposable PostgreSQL; backend-quality CI")
    schema = "admin_generation_" + uuid4().hex
    control = create_async_engine(url)
    async with control.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    tables = [t for t in Base.metadata.sorted_tables if t.name in {"users", "image_sessions", "generations", "credit_ledger"}]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [991])
    monkeypatch.setattr(repo, "_publish_generation_update", AsyncMock())
    monkeypatch.setattr(repo, "mirror_url", AsyncMock(side_effect=lambda url: url))
    async with factory() as session:
        session.add(User(id=42, tg_id=420, credits=100, referral_code="test-admin"))
        await session.flush()
        session.add(Generation(id=73, user_id=42, model="fixture", gen_type=GenerationType.image,
                               status=GenerationStatus.processing, prompt="test", credits_spent=40))
        await session.commit()
    try:
        yield factory, engine
    finally:
        await engine.dispose()
        async with control.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


@pytest.mark.asyncio
async def test_concurrent_admin_refunds_have_one_winner(pg_db):
    factory, _ = pg_db
    async def attempt():
        async with factory() as session:
            return await fail(session)
    results = await asyncio.gather(*(attempt() for _ in range(5)))
    assert sum(isinstance(row, dict) for row in results) == 1
    assert sum(getattr(row, "status_code", 0) == 409 for row in results) == 4
    async with factory() as session:
        assert (await session.get(User, 42)).credits == 140
        assert len((await session.scalars(select(CreditLedgerEntry))).all()) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("winner", ["success", "refund"])
async def test_completion_and_refund_race_respects_first_lock(pg_db, winner):
    factory, _ = pg_db
    locked, attempted = asyncio.Event(), asyncio.Event()
    async def first():
        async with factory() as session:
            await session.execute(select(Generation).where(Generation.id == 73).with_for_update())
            locked.set()
            await attempted.wait()
            if winner == "refund":
                return await fail(session)
            return await repo.finish_generation(session, 73, "https://example.test/result.png")
    async def second():
        await locked.wait()
        async with factory() as session:
            attempted.set()
            if winner == "success":
                return await fail(session)
            return await repo.finish_generation(session, 73, "https://example.test/result.png")
    await asyncio.wait_for(asyncio.gather(first(), second()), 15)
    async with factory() as session:
        assert (await session.get(Generation, 73)).status == (GenerationStatus.done if winner == "success" else GenerationStatus.failed)
        assert (await session.get(User, 42)).credits == (100 if winner == "success" else 140)
        assert len((await session.scalars(select(CreditLedgerEntry))).all()) == (0 if winner == "success" else 1)
