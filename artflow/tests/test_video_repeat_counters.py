"""Real SQL and HTTP regressions for video repeat attribution and owner counters."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api import miniapp_routes
from api.miniapp_auth import get_miniapp_user
from api.web import generations as web_generations
from api.web import history as web_history
from api.web.deps import get_web_user_or_none
from db import repository
from db.models import Base, Generation, GenerationStatus, GenerationType, ImageSession, User
from db.session import get_session


class SessionFacade:
    """Run repository SQL on disposable SQLite while preserving async call sites."""

    def __init__(self, session: Session):
        self.session = session
        self.statements = []

    async def execute(self, statement, *args, **kwargs):
        self.statements.append(statement)
        return self.session.execute(statement, *args, **kwargs)


@pytest.fixture
def counter_session(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "repeat-counters.db"))
    Base.metadata.create_all(engine, tables=[
        User.__table__, ImageSession.__table__, Generation.__table__,
    ])
    monkeypatch.setattr(repository, "_feed_media_url_is_available", lambda url: bool(url))
    with Session(engine, expire_on_commit=False) as session:
        session.add_all([
            User(id=7, tg_id=7001, referral_code="counter-owner"),
            User(id=8, tg_id=8001, referral_code="counter-reader"),
        ])
        for generation_id, kind, published in [
            (101, GenerationType.video, True),
            (102, GenerationType.image, True),
            (103, GenerationType.image, True),
            (104, GenerationType.video, True),
            (105, GenerationType.video, False),
        ]:
            session.add(Generation(
                id=generation_id, user_id=7, model="fixture-model", gen_type=kind,
                prompt="Fixture source", status=GenerationStatus.done,
                result_url=f"https://media.example.test/{generation_id}.mp4",
                is_public_feed=published, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ))
        # source_feed_gen_id is publication attribution; parent is edit/session lineage.
        children = [
            (201, GenerationType.video, 101, None, GenerationStatus.done),
            (202, GenerationType.image, 101, None, GenerationStatus.done),
            (203, GenerationType.video, 101, 101, GenerationStatus.done),
            (204, GenerationType.image, 101, 102, GenerationStatus.done),
            (205, GenerationType.image, None, 103, GenerationStatus.done),
            (206, GenerationType.video, 101, None, GenerationStatus.failed),
            (207, GenerationType.video, 101, None, GenerationStatus.pending),
            (208, GenerationType.video, 101, None, GenerationStatus.processing),
            (209, GenerationType.video, None, None, GenerationStatus.done),
            (210, GenerationType.video, 105, None, GenerationStatus.done),
        ]
        session.add_all([
            Generation(
                id=identity, user_id=8, model="fixture-model", gen_type=kind,
                prompt="Fixture repeat", status=status, source_feed_gen_id=source,
                parent_generation_id=parent, result_url=f"https://media.example.test/{identity}.mp4",
            )
            for identity, kind, source, parent, status in children
        ])
        session.commit()
        yield SessionFacade(session)
    engine.dispose()


@pytest.mark.asyncio
async def test_feed_counts_source_only_video_and_image_repeats_once(counter_session):
    cards = await repository.get_user_feed_generations(counter_session, user_id=7, limit=20)

    assert {card.generation.id: card.remix_count for card in cards} == {
        101: 4, 102: 0, 103: 1, 104: 0,
    }
    # One canonical source prevents counting both source and technical parent.
    assert len(counter_session.statements) == 1


@pytest.fixture
async def counter_client(counter_session, monkeypatch):
    async def session_override():
        yield counter_session

    async def user_override():
        return SimpleNamespace(id=7, tg_id=7001, is_banned=False)

    app = FastAPI()
    app.include_router(miniapp_routes.router)
    app.include_router(web_history.router, prefix="/api/web")
    app.include_router(web_generations.router, prefix="/api/web")
    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_miniapp_user] = user_override
    app.dependency_overrides[get_web_user_or_none] = user_override
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", AsyncMock())
    monkeypatch.setattr(miniapp_routes, "_reconcile_generation_status", AsyncMock(side_effect=lambda _, generation: generation))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


def _data(response, surface):
    assert response.status_code == 200, response.text
    body = response.json()
    return body["data"] if surface == "web" else body


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_owner_history_exposes_real_counts_zero_and_unpublished_null(counter_client, counter_session, surface):
    response = await counter_client.get(f"/api/{surface}/history?limit=100")
    rows = _data(response, surface)

    assert {row["id"]: row["remixes"] for row in rows} == {
        101: 4, 102: 0, 103: 1, 104: 0, 105: None,
    }
    # History plus one grouped query, independent of the number of cards.
    assert len(counter_session.statements) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_owner_history_counter_query_is_bounded_to_page(counter_client, counter_session, surface):
    response = await counter_client.get(f"/api/{surface}/history?limit=2&offset=1")
    rows = _data(response, surface)

    assert [(row["id"], row["remixes"]) for row in rows] == [(104, 0), (103, 1)]
    assert len(counter_session.statements) == 2
    counter_sql = str(counter_session.statements[-1].compile(compile_kwargs={"literal_binds": True}))
    assert " IN (" in counter_sql
    assert "101" not in counter_sql and "105" not in counter_sql


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_private_only_history_does_not_query_counters(counter_client, counter_session, surface):
    response = await counter_client.get(f"/api/{surface}/history?limit=1")

    assert [(row["id"], row["remixes"]) for row in _data(response, surface)] == [(105, None)]
    assert len(counter_session.statements) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_empty_owner_history_does_not_query_counters(counter_client, counter_session, surface):
    response = await counter_client.get(f"/api/{surface}/history?limit=2&offset=100")

    assert _data(response, surface) == []
    assert len(counter_session.statements) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["v1", "web"])
@pytest.mark.parametrize(("generation_id", "expected"), [(101, 4), (104, 0), (105, None)])
async def test_owner_detail_preserves_counter_after_refresh(counter_client, counter_session, surface, generation_id, expected):
    response = await counter_client.get(f"/api/{surface}/generations/{generation_id}")

    assert _data(response, surface)["remixes"] == expected
    assert len(counter_session.statements) == (1 if expected is None else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["v1", "web"])
async def test_other_users_task_never_exposes_counter(counter_client, counter_session, surface):
    response = await counter_client.get(f"/api/{surface}/generations/201")

    assert response.status_code == 404
    assert "remixes" not in response.text
    assert len(counter_session.statements) == 1
