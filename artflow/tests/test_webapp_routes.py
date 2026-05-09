from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.miniapp_auth import get_miniapp_user
from db.session import get_session
from main import app


async def fake_session():
    yield AsyncMock()


async def fake_user():
    return SimpleNamespace(
        id=1,
        tg_id=111,
        username="tester",
        full_name="Test User",
        credits=1003,
        referral_code="REF",
        is_banned=False,
    )


@pytest.fixture
async def client():
    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_miniapp_user] = fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webapp_health_is_public() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/webapp/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_webapp_me_rejects_missing_init_data_without_override() -> None:
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/webapp/me")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_webapp_me_returns_verified_user(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.get_active_image_session", AsyncMock(return_value=None))
    response = await client.get("/api/webapp/me")
    assert response.json()["user"]["credits"] == 1003


@pytest.mark.asyncio
async def test_webapp_feed_returns_items(client, monkeypatch) -> None:
    generation = SimpleNamespace(
        id=5,
        model="nano-banana-pro",
        result_url="https://example.test/static/upload/a.jpg",
        prompt="premium prompt",
        likes_count=2,
        shares_count=1,
        created_at=None,
    )
    card = SimpleNamespace(generation=generation, username="author", full_name=None, remix_count=3)
    monkeypatch.setattr("api.miniapp_routes.repo.get_feed_generations", AsyncMock(return_value=[card]))
    response = await client.get("/api/webapp/feed")
    assert response.json()["items"][0]["remixes"] == 3


@pytest.mark.asyncio
async def test_webapp_prompt_use_updates_session(client, monkeypatch) -> None:
    prompt = SimpleNamespace(
        id=7,
        status=SimpleNamespace(value="approved"),
        is_public=True,
        prompt_text="make it glossy",
        model=None,
        preview_url=None,
    )
    from db.models import PromptStatus

    prompt.status = PromptStatus.approved
    monkeypatch.setattr("api.miniapp_routes.prompt_repository.get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr("api.miniapp_routes.prompt_repository.increment_usage", AsyncMock())
    monkeypatch.setattr("api.miniapp_routes._create_or_update_image_session", AsyncMock())
    response = await client.post("/api/webapp/prompts/7/use")
    assert response.json()["open_bot_required"] is True
