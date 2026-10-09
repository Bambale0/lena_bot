from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from api.miniapp_auth import create_web_auth_token
from api.web import sessions as web_sessions
from api.web.schemas import ImageSessionCard, ImageSessionCreateRequest
from db import repository as repo
from db.models import (
    Base,
    Generation,
    GenerationStatus,
    GenerationType,
    ImageSession,
    ImageSessionStatus,
    User,
)

SECRET = "synthetic-legacy-foreign-author-secret-617c"
OWN_PROMPT = "My own blue ceramic cup on a table"


class LocalSession:
    """Exercise real repository queries against isolated SQLite."""

    def __init__(self, sync: Session) -> None:
        self.sync = sync

    def add(self, value) -> None:
        self.sync.add(value)

    async def execute(self, statement):
        return self.sync.execute(statement)

    async def commit(self) -> None:
        self.sync.commit()

    async def refresh(self, value) -> None:
        self.sync.refresh(value)


@pytest.fixture
def local_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[User.__table__, ImageSession.__table__, Generation.__table__],
    )
    with Session(engine, expire_on_commit=False) as sync:
        sync.add_all([
            User(id=42, tg_id=4200, credits=100, referral_code="synthetic-reader"),
            User(id=99, tg_id=9900, credits=70, referral_code="synthetic-author"),
        ])
        sync.commit()
        yield LocalSession(sync)
    engine.dispose()


async def _legacy_session(local_session, *, user_id=42, provenance=None):
    image_session = ImageSession(
        user_id=user_id, model="nano-banana-2", mode="image", aspect_ratio="1:1",
        quality="2K", count=1, base_prompt=SECRET, last_prompt=SECRET,
        last_result_url="https://example.test/own-result.jpg",
        reference_url="https://example.test/own-reference.jpg",
        status=ImageSessionStatus.active,
    )
    # Setting the attribute also reproduces the pre-migration missing-column
    # behavior before the new ORM field exists, so red tests catch disclosure.
    image_session.prompt_provenance = provenance
    local_session.add(image_session)
    await local_session.commit()
    return image_session


async def _read(local_session, image_session, endpoint):
    user = local_session.sync.get(User, 42)
    if endpoint == "active":
        return await web_sessions.active_image_session(local_session, user)
    return await web_sessions.archive_image_session(image_session.id, local_session, user)


@pytest.mark.parametrize("endpoint", ["active", "archive"])
@pytest.mark.parametrize("provenance", [None, "unknown", "client_owned"])
async def test_unknown_orphan_session_never_discloses_legacy_prompt(
    local_session, endpoint, provenance,
):
    image_session = await _legacy_session(local_session, provenance=provenance)

    response = await _read(local_session, image_session, endpoint)

    assert SECRET not in json.dumps(response, ensure_ascii=False)
    data = response["data"]
    assert data["base_prompt"] is None
    assert data["last_prompt"] is None
    assert data["prompt_hidden"] is True
    assert data["prompt_actions_allowed"] is False
    assert data["prompt_unavailable_reason"]
    assert data["last_result_url"] == "https://example.test/own-result.jpg"
    # Restoration is read-only with respect to prompts, balance and generation.
    assert image_session.base_prompt == SECRET
    assert image_session.last_prompt == SECRET
    assert local_session.sync.get(User, 42).credits == 100
    assert local_session.sync.scalars(select(Generation)).all() == []


async def test_direct_session_serializer_fails_closed_without_trusted_provenance(local_session):
    image_session = await _legacy_session(local_session)

    card = ImageSessionCard.from_image_session(image_session)

    assert SECRET not in card.model_dump_json()
    assert card.prompt_hidden is True
    assert card.prompt_unavailable_reason


@pytest.mark.parametrize("endpoint", ["active", "archive"])
@pytest.mark.parametrize("client_provenance", [None, "user_supplied", "foreign", {"owner": 42}])
async def test_new_web_session_restores_user_prompt_with_server_only_provenance(
    local_session, endpoint, client_provenance,
):
    body = ImageSessionCreateRequest.model_validate({
        "model": " nano-banana-2 ", "mode": "text", "quality": "2K", "count": 1,
        "base_prompt": f"  {OWN_PROMPT}  ", "prompt_provenance": client_provenance,
    })
    assert "prompt_provenance" not in body.model_dump()

    created = await web_sessions.create_image_session(
        body, local_session, local_session.sync.get(User, 42),
    )
    image_session = local_session.sync.get(ImageSession, created["data"]["id"])
    assert image_session.prompt_provenance == "user_supplied"
    assert created["data"]["base_prompt"] == OWN_PROMPT

    response = await _read(local_session, image_session, endpoint)

    assert response["data"]["base_prompt"] == OWN_PROMPT
    assert response["data"]["last_prompt"] == OWN_PROMPT
    assert response["data"]["prompt_hidden"] is False
    assert response["data"]["prompt_actions_allowed"] is True
    assert response["data"]["prompt_unavailable_reason"] is None
    assert image_session.base_prompt == OWN_PROMPT
    assert local_session.sync.get(User, 42).credits == 100
    assert local_session.sync.scalars(select(Generation)).all() == []


async def test_generic_repository_constructor_never_asserts_ownership_implicitly(local_session):
    image_session = await repo.create_image_session(
        local_session, 42, "nano-banana-2", "text", "1:1", "2K", 1, SECRET,
    )

    assert getattr(image_session, "prompt_provenance", None) is None
    response = await web_sessions.active_image_session(local_session, local_session.sync.get(User, 42))
    assert SECRET not in json.dumps(response)
    assert image_session.base_prompt == SECRET


@pytest.mark.parametrize("endpoint", ["active", "archive"])
@pytest.mark.parametrize("protection", ["feed", "hidden_trend"])
async def test_protected_history_overrides_own_marker_after_later_ordinary_generation(
    local_session, endpoint, protection,
):
    image_session = await _legacy_session(local_session, provenance="user_supplied")
    now = datetime.now(timezone.utc)
    source = Generation(
        user_id=99, model=image_session.model, gen_type=GenerationType.image,
        prompt=SECRET, status=GenerationStatus.done,
    )
    local_session.add(source)
    await local_session.commit()
    local_session.add(Generation(
        user_id=42, image_session_id=image_session.id, model=image_session.model,
        gen_type=GenerationType.image, prompt=SECRET, status=GenerationStatus.done,
        source_feed_gen_id=source.id if protection == "feed" else None,
        input_params=json.dumps({"hidden_prompt": True}) if protection == "hidden_trend" else None,
        created_at=now - timedelta(seconds=1),
    ))
    local_session.add(Generation(
        user_id=42, image_session_id=image_session.id, model=image_session.model,
        gen_type=GenerationType.image, prompt=OWN_PROMPT, status=GenerationStatus.done,
        created_at=now,
    ))
    await local_session.commit()

    response = await _read(local_session, image_session, endpoint)

    assert SECRET not in json.dumps(response)
    assert response["data"]["prompt_hidden"] is True
    assert response["data"]["prompt_actions_allowed"] is False
    assert image_session.base_prompt == SECRET


async def test_active_and_archive_preserve_owner_boundary(local_session):
    foreign = await _legacy_session(local_session, user_id=99, provenance="user_supplied")
    own = await _legacy_session(local_session)

    active = await web_sessions.active_image_session(local_session, local_session.sync.get(User, 42))
    denied = await web_sessions.archive_image_session(
        foreign.id, local_session, local_session.sync.get(User, 42),
    )

    assert active["data"]["id"] == own.id
    assert SECRET not in json.dumps(active)
    assert denied.status_code == 404
    assert foreign.status == ImageSessionStatus.active
    assert local_session.sync.get(User, 42).credits == 100
    assert local_session.sync.get(User, 99).credits == 70
    assert local_session.sync.scalars(select(Generation)).all() == []


async def test_authenticated_http_restore_and_create_cannot_accept_client_ownership(local_session):
    own_legacy = await _legacy_session(local_session)
    foreign = await _legacy_session(local_session, user_id=99)
    app = FastAPI()
    app.include_router(web_sessions.router, prefix="/api/web")

    async def isolated_session():
        yield local_session

    app.dependency_overrides[web_sessions.get_session] = isolated_session
    # Real token authentication and repository lookup remain enabled.
    headers = {"X-Web-Auth-Token": create_web_auth_token(4200)}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        restored = await client.get("/api/web/image-sessions/active", headers=headers)
        assert restored.status_code == 200
        assert restored.json()["data"]["id"] == own_legacy.id
        assert SECRET not in restored.text
        assert restored.json()["data"]["prompt_unavailable_reason"]
        denied = await client.post(f"/api/web/image-sessions/{foreign.id}/archive", headers=headers)
        assert denied.status_code == 404
        created = await client.post("/api/web/image-sessions", headers=headers, json={
            "base_prompt": OWN_PROMPT,
            "user_id": 99,
            "prompt_provenance": "foreign",
            "source_feed_gen_id": 77,
            "id": own_legacy.id,
        })
        assert created.status_code == 200
        restored_new = await client.get("/api/web/image-sessions/active", headers=headers)
        assert restored_new.json()["data"]["base_prompt"] == OWN_PROMPT
        assert restored_new.json()["data"]["last_prompt"] == OWN_PROMPT
        assert restored_new.json()["data"]["prompt_unavailable_reason"] is None
        archived = await client.post(f"/api/web/image-sessions/{own_legacy.id}/archive", headers=headers)
        assert archived.status_code == 200
        assert SECRET not in archived.text

    created_session = local_session.sync.get(ImageSession, created.json()["data"]["id"])
    assert created_session.id != own_legacy.id
    assert created_session.user_id == 42
    assert created_session.prompt_provenance == "user_supplied"
    assert own_legacy.prompt_provenance is None
    assert own_legacy.base_prompt == SECRET
    assert foreign.status == ImageSessionStatus.active
    assert local_session.sync.get(User, 42).credits == 100
    assert local_session.sync.scalars(select(Generation)).all() == []


@pytest.mark.parametrize("method,path", [
    ("get", "/image-sessions/active"),
    ("post", "/image-sessions"),
    ("post", "/image-sessions/1/archive"),
])
async def test_unauthenticated_http_requests_cannot_read_or_mutate_sessions(local_session, method, path):
    saved = await _legacy_session(local_session)
    app = FastAPI()
    app.include_router(web_sessions.router)

    async def isolated_session():
        yield local_session

    app.dependency_overrides[web_sessions.get_session] = isolated_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, path, json={"base_prompt": OWN_PROMPT})
    assert response.status_code == 401
    assert SECRET not in response.text
    assert saved.status == ImageSessionStatus.active
    assert local_session.sync.scalars(select(ImageSession)).all() == [saved]
    assert local_session.sync.scalars(select(Generation)).all() == []
