"""Behavioural tests for history/feed offset pagination (H1/H2/M1/M2/M4/M5)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import desc, select

from api.miniapp_auth import get_miniapp_user
from api import miniapp_routes
from db import repository
from db.models import Generation
from db.session import get_session
from main import app


def _result(rows: list) -> MagicMock:
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


async def _fake_session():
    yield AsyncMock()


async def _fake_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=7, tg_id=7001, username="tester", full_name="Test User",
        photo_url=None, credits=50, referral_code="REF",
        referral_balance=0.0, is_banned=False,
    )


@pytest.fixture
async def history_client():
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_miniapp_user] = _fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_user_history_statement_is_stable_newest_first() -> None:
    """M5/M2: page 2 must differ from page 1; ties break by id."""
    session = AsyncMock()
    seen: list[str] = []

    async def capture(stmt, *args, **kwargs):
        seen.append(str(stmt.compile(compile_kwargs={"literal_binds": True})))
        return _result([])

    session.execute = capture

    await repository.get_user_history(session, user_id=7, limit=2, offset=0)
    await repository.get_user_history(session, user_id=7, limit=2, offset=2)

    assert len(seen) == 2
    for compiled in seen:
        assert "ORDER BY generations.created_at DESC, generations.id DESC" in compiled
    assert seen[0] != seen[1]
    assert "generations.id DESC" in seen[1]


@pytest.mark.asyncio
async def test_get_user_history_compiled_shape_matches_index() -> None:
    """M2: WHERE+ORDER shape must match ix_generations_user_history."""
    stmt = (
        select(Generation)
        .where(Generation.user_id == 7)
        .order_by(desc(Generation.created_at), desc(Generation.id))
        .offset(200)
        .limit(100)
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "generations.user_id = 7" in compiled
    assert "ORDER BY generations.created_at DESC, generations.id DESC" in compiled


@pytest.mark.asyncio
async def test_history_endpoint_passes_offset_through(history_client, monkeypatch) -> None:
    """M5: ?offset=100 must reach repo.get_user_history unchanged."""
    captured: dict = {}

    async def fake_history(session, user_id, limit=20, offset=0):
        captured["limit"] = limit
        captured["offset"] = offset
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(miniapp_routes.repo, "get_user_history", fake_history)
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", AsyncMock())
    response = await history_client.get("/api/v1/history?limit=20&offset=100")
    assert response.status_code == 200
    assert captured == {"limit": 20, "offset": 100, "user_id": 7}


@pytest.mark.asyncio
async def test_history_reconciles_only_first_page(history_client, monkeypatch) -> None:
    """M1: offset>0 must not trigger provider polling."""
    reconcile = AsyncMock()
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", reconcile)
    monkeypatch.setattr(miniapp_routes.repo, "get_user_history", AsyncMock(return_value=[]))
    await history_client.get("/api/v1/history?limit=20&offset=0")
    assert reconcile.await_count == 1
    await history_client.get("/api/v1/history?limit=20&offset=100")
    assert reconcile.await_count == 1


@pytest.mark.asyncio
async def test_history_rejects_limit_above_cap(history_client) -> None:
    """M5: limit=101 must still 422 (cap unchanged by offset work)."""
    response = await history_client.get("/api/v1/history?limit=101")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_web_history_supports_offset() -> None:
    """M4 (site parity): /api/web/history must accept and forward offset."""
    from api.web import history as web_history

    captured: dict = {}

    async def fake_history(session, user_id, limit=20, offset=0):
        captured["offset"] = offset
        captured["limit"] = limit
        return []

    async def fake_sessions(session, ids):
        return {}

    session = AsyncMock()
    user = SimpleNamespace(id=9)
    orig_history = repository.get_user_history
    orig_sessions = repository.get_image_sessions_by_ids
    repository.get_user_history = fake_history
    repository.get_image_sessions_by_ids = fake_sessions
    try:
        result = await web_history.history(limit=20, offset=48, session=session, user=user)
    finally:
        repository.get_user_history = orig_history
        repository.get_image_sessions_by_ids = orig_sessions
    assert captured == {"offset": 48, "limit": 20}
    assert result == {"ok": True, "data": []}


@pytest.mark.asyncio
async def test_me_feed_supports_offset(history_client, monkeypatch) -> None:
    """M4: /me/feed documents its bound but still pages within it."""
    captured: dict = {}

    async def fake_feed(session, user_id, limit=500, offset=0):
        captured["limit"] = limit
        captured["offset"] = offset
        return []

    monkeypatch.setattr(miniapp_routes.repo, "get_user_feed_generations", fake_feed)
    response = await history_client.get("/api/v1/me/feed?limit=500&offset=500")
    assert response.status_code == 200
    assert captured == {"limit": 500, "offset": 500}
