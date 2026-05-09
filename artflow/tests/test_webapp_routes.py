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
        referral_balance=0.0,
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
        response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_webapp_me_rejects_missing_init_data_without_override() -> None:
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webapp_me_returns_verified_user(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.get_active_image_session", AsyncMock(return_value=None))
    response = await client.get("/api/v1/me")
    assert response.json()["credits"] == 1003


@pytest.mark.asyncio
async def test_webapp_feed_returns_items(client, monkeypatch) -> None:
    generation = SimpleNamespace(
        id=5,
        model="nano-banana-pro",
        result_url="https://example.test/static/upload/a.jpg",
        prompt="premium prompt",
        likes_count=2,
        shares_count=1,
        user_id=1,
        created_at=None,
    )
    card = SimpleNamespace(generation=generation, username="author", full_name=None, remix_count=3, aspect_ratio="16:9")
    monkeypatch.setattr("api.miniapp_routes.repo.get_feed_generations", AsyncMock(return_value=[card]))
    response = await client.get("/api/v1/feed")
    assert response.json()[0]["remixes"] == 3


@pytest.mark.asyncio
async def test_webapp_prompt_use_returns_404_when_not_implemented(client, monkeypatch) -> None:
    """The /prompts/{id}/use endpoint is not yet implemented — expect 404."""
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
    monkeypatch.setattr("db.prompt_repository.get_prompt_by_id", AsyncMock(return_value=prompt))
    response = await client.post("/api/v1/prompts/7/use")
    assert response.status_code == 404
