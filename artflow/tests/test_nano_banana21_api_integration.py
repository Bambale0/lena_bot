from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from api import miniapp_routes, neironych_image_adapter
from api.miniapp_auth import get_miniapp_user
from core.provider_routing import ProviderRoute
from db.models import GenerationStatus, GenerationType
from db.session import get_session
from main import app


@pytest.mark.asyncio
async def test_miniapp_ambiguous_neironych_submit_preserves_charge_and_correlation(monkeypatch):
    gen = SimpleNamespace(
        id=8101, user_id=10, model="nano-banana-2.1",
        gen_type=GenerationType.image, prompt="test photo",
        task_id=None, status=GenerationStatus.pending,
        result_url=None, result_urls=None, credits_spent=2,
        created_at=datetime.now(timezone.utc), finished_at=None,
        is_public_feed=False, is_prompt_library=False, source_feed_gen_id=None,
        image_session_id=12, action_type=None,
    )
    events = []
    request_ids = []

    async def create_generation(*args, **kwargs):
        events.append("db_create")
        return gen

    async def save_task(session, gen_id, task_id):
        assert gen_id == 8101
        events.append("db_save_id")
        gen.task_id = task_id
        gen.status = GenerationStatus.processing

    async def ambiguous(model, prompt, **kwargs):
        events.append("provider_post")
        rid = kwargs["request_id"]
        request_ids.append(rid)
        assert gen.task_id == neironych_image_adapter.encode_task_id(rid)
        assert kwargs["primary_provider"] == "neironych"
        raise neironych_image_adapter.NeironychImageError(
            "response lost", status_code=503, request_id=rid
        )

    refunds = AsyncMock()
    monkeypatch.setattr(miniapp_routes, "get_nano21_route",
                        AsyncMock(return_value=ProviderRoute("nano-banana-2.1", "neironych", "database")))
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", AsyncMock())
    monkeypatch.setattr(miniapp_routes.repo, "resolve_image_model_cost",
                        AsyncMock(return_value=SimpleNamespace(credits=2)))
    monkeypatch.setattr(miniapp_routes.repo, "count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation",
                        AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=2, unlimited=False)))
    monkeypatch.setattr(miniapp_routes.repo, "create_image_session", AsyncMock(return_value=SimpleNamespace(id=12)))
    monkeypatch.setattr(miniapp_routes.repo, "create_generation", create_generation)
    monkeypatch.setattr(miniapp_routes.repo, "update_generation_task", save_task)
    monkeypatch.setattr(miniapp_routes.repo, "fail_generation", refunds)
    monkeypatch.setattr(miniapp_routes.repo, "add_credits", refunds)
    monkeypatch.setattr(miniapp_routes.image_service, "generate_image", ambiguous)

    async def stub_session():
        yield AsyncMock()

    async def stub_user():
        return SimpleNamespace(
            id=10, tg_id=1212121, credits=100, referral_code="REF",
            full_name="Tester", username="tester", photo_url=None,
            referral_balance=0, is_banned=False,
        )

    app.dependency_overrides[get_session] = stub_session
    app.dependency_overrides[get_miniapp_user] = stub_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/generate/image", json={
                "model": "nano-banana-2.1", "prompt": "test photo", "quality": "2K",
            })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "processing"
    assert events == ["db_create", "db_save_id", "provider_post"]
    assert request_ids
    refunds.assert_not_awaited()
