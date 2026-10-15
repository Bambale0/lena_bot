"""FastAPI quote must not spend money and never price guessed media lengths."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from api import miniapp_routes
from api.miniapp_auth import get_miniapp_user
from db.session import get_session
from main import app


@pytest.mark.asyncio
async def test_wan30_server_quote_does_not_charge_or_post_provider(monkeypatch):
    async def db():
        yield AsyncMock()
    async def user():
        return SimpleNamespace(id=42,tg_id=42,credits=1000,is_banned=False)
    async def cost(session,key):
        return SimpleNamespace(is_active=True,credits=12)
    charged=AsyncMock()
    sent=AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo,"get_model_cost",cost)
    monkeypatch.setattr(miniapp_routes.repo,"spend_credits",charged)
    monkeypatch.setattr(miniapp_routes.video_service,"generate_video",sent)
    app.dependency_overrides[get_session]=db
    app.dependency_overrides[get_miniapp_user]=user
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
            result=await client.post("/api/v1/generate/video/quote",json={
                "model":"wan/3-0-video","prompt":"A small turtle",
                "mode":"text","duration":5,"resolution":"720p",
                "aspect_ratio":"adaptive",
            })
    finally:
        app.dependency_overrides.clear()
    assert result.status_code==200, result.text
    data=result.json()
    assert data["credits"]==60
    assert data["cost_credits"]==60
    assert data["rate"]==12
    assert data["can_run"] is True
    assert data["billable_seconds"]==5
    assert data["input_video_seconds"]==0
    charged.assert_not_awaited()
    sent.assert_not_awaited()



@pytest.mark.parametrize("duration", [2, 4, 7, 17, 29, 30])
def test_wan30_api_accepts_every_second_not_only_quick_presets(duration):
    result = miniapp_routes._normalize_video_request(
        model_key="wan/3-0-video", mode="text",
        duration=duration, aspect_ratio="adaptive",
        resolution="720p", image_url=None, reference_urls=[],
    )
    assert result["duration"] == duration


@pytest.mark.parametrize("duration", [1, 31])
def test_wan30_api_rejects_out_of_range_duration(duration):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        miniapp_routes._normalize_video_request(
            model_key="wan/3-0-video", mode="text",
            duration=duration, aspect_ratio="adaptive",
            resolution="720p", image_url=None, reference_urls=[],
        )
    assert error.value.status_code == 422

@pytest.mark.asyncio
async def test_wan30_launch_rejects_stale_or_missing_price_before_spending(monkeypatch):
    async def db():
        yield AsyncMock()
    async def user():
        return SimpleNamespace(id=42, tg_id=42, credits=1000, is_banned=False)
    async def rate(session, key):
        return SimpleNamespace(is_active=True, credits=12, model_key=key)
    charged = AsyncMock()
    provider_post = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "get_model_cost", rate)
    monkeypatch.setattr(miniapp_routes.repo, "resolve_video_model_cost", rate_model := AsyncMock(
        return_value=SimpleNamespace(is_active=True, credits=12),
    ))
    monkeypatch.setattr(miniapp_routes.repo, "spend_credits", charged)
    monkeypatch.setattr(miniapp_routes.video_service, "generate_video", provider_post)
    app.dependency_overrides[get_session] = db
    app.dependency_overrides[get_miniapp_user] = user
    try:
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
            for quote in (None, 20.0):
                request = {
                    "model": "wan/3-0-video", "prompt": "A snow fox",
                    "mode": "text", "duration": 5,
                    "resolution": "720p", "aspect_ratio": "adaptive",
                }
                if quote is not None:
                    request["quoted_credits"] = quote
                result = await client.post("/api/v1/generate/video", json=request)
                assert result.status_code == 409, result.text
    finally:
        app.dependency_overrides.clear()
    charged.assert_not_awaited()
    provider_post.assert_not_awaited()
    assert rate_model.await_count == 2
