from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.miniapp_auth import get_miniapp_user
from api.miniapp_routes import PreSubmitRejection, VideoGenRequest, _video_prompt_and_source
from api.trends_routes import (
    TrendRunRequest,
    _trend_request_hash,
    _trend_video_duration,
    _validated_model,
)
from db.models import GenerationType, PromptStatus, TrendRunClaim
from db.session import get_session
from db.trend_run_claims import release_pre_submit_claim, reserve_claim
from main import app


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [15, 30])
async def test_selectable_trend_duration_quote_launch_and_identity(trend_client, seconds):
    client, monkeypatch, _, create = trend_client
    trend = SimpleNamespace(id=12, model="wan/3-0-video", tags=["trend", "trend-video", "trend-duration:10"])
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    monkeypatch.setattr("api.wan30_launch.repo.get_model_cost", AsyncMock(return_value=SimpleNamespace(is_active=True, credits=4)))
    quote = await client.get(f"/api/v1/trends/12/checkout?duration={seconds}")
    assert quote.status_code == 200, quote.text
    assert quote.json()["cost_credits"] == seconds * 4
    assert quote.json()["default_duration"] == 10
    assert quote.json()["effective_duration"] == seconds
    assert seconds in quote.json()["duration_options"]
    monkeypatch.setattr("api.trends_routes.quote_video_generation", AsyncMock(return_value={"cost_credits": seconds * 4}))
    payload = {"asset_id": "signed-photo-asset-id", "idempotency_key": "duration-request", "duration": seconds, "quoted_credits": seconds * 4}
    response = await client.post("/api/v1/trends/12/run", json=payload)
    assert response.status_code == 202, response.text
    assert create.await_args.kwargs["body"].duration == seconds
    assert _trend_request_hash(12, TrendRunRequest(**payload)) != _trend_request_hash(12, TrendRunRequest(**{**payload, "duration": 10}))


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [True, 15.5, "15", 0, 31])
async def test_trend_duration_strict_before_launch(trend_client, seconds):
    client, monkeypatch, reserve, create = trend_client
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=SimpleNamespace(
        id=12, model="wan/3-0-video", tags=["trend", "trend-video", "trend-duration:10"],
    )))
    monkeypatch.setattr("api.trends_routes.quote_video_generation", AsyncMock(return_value={"cost_credits": 40}))
    response = await client.post("/api/v1/trends/12/run", json={
        "asset_id": "signed-photo-asset-id", "idempotency_key": "duration-invalid", "duration": seconds,
    })
    assert response.status_code == 422
    reserve.assert_not_awaited()
    create.assert_not_awaited()


def test_absent_duration_preserves_legacy_claim_hash():
    import hashlib
    import json

    body = TrendRunRequest(asset_id="signed-photo-asset-id", idempotency_key="legacy-request", quoted_credits=40)
    encoded = json.dumps([12, body.asset_id, {}, 40.0], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert _trend_request_hash(12, body) == hashlib.sha256(encoded).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("model,expected", [("bytedance/seedance-2-5__resolution=720p", 15), ("wan/3-0-video", 30), ("veo3_fast", 8)])
async def test_admin_duration_uses_installed_caps_and_short_rows(monkeypatch, model, expected):
    from bot.handlers import trends as bot_trends
    state = AsyncMock()
    state.get_data.return_value = {"model": model}
    call = SimpleNamespace(data="trends:scenario:image", message=SimpleNamespace(answer=AsyncMock()), answer=AsyncMock())
    monkeypatch.setattr(bot_trends, "safe_answer_callback", AsyncMock())
    await bot_trends.trend_scenario(call, state)
    rows = call.message.answer.await_args.kwargs["reply_markup"].inline_keyboard
    assert f"trends:duration:{expected}" in {b.callback_data for row in rows for b in row}
    assert all(len(row) <= 4 for row in rows)
    call.data = "trends:duration:garbage"
    await bot_trends.trend_duration(call, state)
    call.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_wan_explicit_duration_requires_fresh_price(trend_client):
    client, monkeypatch, reserve, create = trend_client
    trend = SimpleNamespace(id=12, model="bytedance/seedance-2-5", tags=["trend", "trend-video", "trend-duration:10"])
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    monkeypatch.setattr("api.trends_routes.quote_video_generation", AsyncMock(return_value={"cost_credits": 105}))
    response = await client.post("/api/v1/trends/12/run", json={"asset_id": "signed-photo-asset-id", "idempotency_key": "new-duration", "duration": 15, "quoted_credits": 70})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "trend_quote_stale"
    create.assert_not_awaited()
    reserve.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["true", "15.0", "15.5", "0", "31", "-1"])
async def test_checkout_duration_rejects_non_integer_or_out_of_catalog(trend_client, value):
    client, monkeypatch, _, _ = trend_client
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=SimpleNamespace(
        id=12, model="wan/3-0-video", tags=["trend", "trend-video", "trend-duration:10"],
    )))
    response = await client.get(f"/api/v1/trends/12/checkout?duration={value}")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_changed_duration_with_existing_claim_key_conflicts(trend_client):
    client, monkeypatch, reserve, create = trend_client
    original = TrendRunRequest(asset_id="signed-photo-asset-id", idempotency_key="same-key", duration=10, quoted_credits=40)
    monkeypatch.setattr("api.trends_routes.get_claim", AsyncMock(return_value=SimpleNamespace(
        trend_id=12, request_hash=_trend_request_hash(12, original), generation_id=None,
    )))
    response = await client.post("/api/v1/trends/12/run", json={**original.model_dump(), "duration": 15})
    assert response.status_code == 409
    assert "different" in response.json()["detail"]
    reserve.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_snapshot_cannot_accept_new_duration(trend_client):
    import json
    client, monkeypatch, reserve, create = trend_client
    monkeypatch.setattr("api.trends_routes._find_idempotent_trend_run", AsyncMock(return_value=SimpleNamespace(input_params=json.dumps({
        "trend_id": 12, "user_asset_id": "signed-photo-asset-id", "trend_user_values": {},
    }))))
    response = await client.post("/api/v1/trends/12/run", json={"asset_id": "signed-photo-asset-id", "idempotency_key": "legacy-key", "duration": 15})
    assert response.status_code == 409
    reserve.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [8, 10])
async def test_fixed_runtime_veo_does_not_offer_fake_fifteen_seconds(trend_client, saved):
    client, monkeypatch, _, create = trend_client
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=SimpleNamespace(
        id=12, model="veo3_fast", tags=["trend", "trend-video", f"trend-duration:{saved}"],
    )))
    monkeypatch.setattr("api.trends_routes.repo.resolve_video_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4, is_active=True)))
    response = await client.get("/api/v1/trends/12/checkout")
    assert response.json()["duration_options"] == [8]
    assert response.json()["effective_duration"] == 8
    assert response.json()["duration_lock_reason"]
    assert (await client.get("/api/v1/trends/12/checkout?duration=15")).status_code == 422
    run = await client.post("/api/v1/trends/12/run", json={"asset_id": "signed-photo-asset-id", "idempotency_key": "fixed-veo-default"})
    assert run.status_code == 202, run.text
    assert create.await_args.kwargs["body"].duration == 8


def test_checkout_openapi_exposes_integer_duration():
    parameters = app.openapi()["paths"]["/api/v1/trends/{trend_id}/checkout"]["get"]["parameters"]
    duration = next(param for param in parameters if param["name"] == "duration")
    assert {"type": "integer"} in duration["schema"]["anyOf"]


@pytest.mark.asyncio
async def test_bot_admin_gemini_duration_buttons_and_forged_duration(monkeypatch):
    from bot.handlers import trends as bot_trends

    state = AsyncMock()
    state.get_data.return_value = {"model": "gemini-omni-video"}
    call = SimpleNamespace(
        data="trends:scenario:image",
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )
    monkeypatch.setattr(bot_trends, "safe_answer_callback", AsyncMock())
    await bot_trends.trend_scenario(call, state)
    markup = call.message.answer.await_args.kwargs["reply_markup"]
    options = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert options == {f"trends:duration:{seconds}" for seconds in (4, 6, 8, 10)}

    call.data = "trends:duration:5"
    await bot_trends.trend_duration(call, state)
    call.answer.assert_awaited_once()
    assert state.update_data.await_count == 1  # scenario only; forged duration was rejected


def test_trend_claim_migration_creates_unique_guard():
    path = Path(__file__).resolve().parents[1] / "db/migrations/versions/044_trend_run_claims.py"
    spec = importlib.util.spec_from_file_location("trend_claim_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")
            connection.exec_driver_sql("CREATE TABLE generations (id INTEGER PRIMARY KEY)")
            with Operations.context(MigrationContext.configure(connection)):
                module.upgrade()
            connection.exec_driver_sql("INSERT INTO users (id) VALUES (7)")
            connection.exec_driver_sql(
                "INSERT INTO trend_run_claims (user_id, request_key, request_hash, trend_id, status) "
                "VALUES (7, 'request-123', 'hash', 12, 'running')"
            )
            with pytest.raises(sa.exc.IntegrityError):
                connection.exec_driver_sql(
                    "INSERT INTO trend_run_claims (user_id, request_key, request_hash, trend_id, status) "
                    "VALUES (7, 'request-123', 'hash', 12, 'running')"
                )
            with Operations.context(MigrationContext.configure(connection)):
                module.downgrade()
            assert "trend_run_claims" not in sa.inspect(connection).get_table_names()
    finally:
        engine.dispose()


@pytest.fixture
async def trend_client(monkeypatch):
    user = SimpleNamespace(id=7, tg_id=111, credits=1000)
    session = AsyncMock()

    async def session_override():
        yield session

    async def user_override():
        return user

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_miniapp_user] = user_override
    monkeypatch.setattr("api.trends_routes.get_claim", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "api.trends_routes._find_idempotent_trend_run", AsyncMock(return_value=None)
    )
    monkeypatch.setattr("api.trends_routes._validated_model", AsyncMock())
    monkeypatch.setattr(
        "api.trends_routes.verify_uploaded_asset",
        lambda *_args, **_kwargs: {"url": "https://example.com/photo.png"},
    )
    monkeypatch.setattr("api.trends_routes._patch_trend_snapshot", AsyncMock())
    claim = SimpleNamespace(generation_id=None, status="running")
    reserve = AsyncMock(return_value=(claim, True))
    monkeypatch.setattr("api.trends_routes.reserve_claim", reserve)
    task = SimpleNamespace(
        id=99, model_dump=lambda: {"id": 99, "gen_type": "video", "credits_spent": 60}
    )
    create = AsyncMock(return_value=task)
    monkeypatch.setattr("api.trends_routes.create_video_generation", create)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, monkeypatch, reserve, create
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_wan_trend_confirms_same_quote_before_paid_launch(trend_client):
    client, monkeypatch, reserve, create = trend_client
    trend = SimpleNamespace(
        id=12,
        model="wan/3-0-video",
        tags=["trend", "trend-video", "trend-duration:5", "trend-resolution:720p"],
    )
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    quote = AsyncMock(return_value={"cost_credits": 60})
    monkeypatch.setattr("api.trends_routes.quote_video_generation", quote)
    payload = {
        "asset_id": "signed-photo-asset-id",
        "idempotency_key": "request-123",
        "quoted_credits": 60,
    }

    response = await client.post("/api/v1/trends/12/run", json=payload)

    assert response.status_code == 202
    assert response.json()["task"]["id"] == 99
    assert quote.await_args.args[0].image_url == "https://example.com/photo.png"
    assert create.await_args.kwargs["body"].quoted_credits == 60
    reserve.assert_awaited_once()


@pytest.mark.asyncio
async def test_wan_trend_checkout_uses_active_resolution_tariff(trend_client):
    client, monkeypatch, _reserve, _create = trend_client
    trend = SimpleNamespace(
        id=12,
        model="wan/3-0-video",
        tags=[
            "trend",
            "trend-video",
            "trend-duration:5",
            "trend-resolution:720p",
        ],
    )
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))

    async def model_cost(_session, key):
        return SimpleNamespace(
            is_active=True, credits=12 if key.endswith("__resolution=720p") else 6
        )

    monkeypatch.setattr("api.wan30_launch.repo.get_model_cost", model_cost)
    response = await client.get("/api/v1/trends/12/checkout")

    assert response.status_code == 200
    assert response.json()["cost_credits"] == 60


@pytest.mark.asyncio
async def test_wan_trend_checkout_uses_launch_default_resolution(trend_client):
    client, monkeypatch, _reserve, _create = trend_client
    trend = SimpleNamespace(id=12, model="wan/3-0-video", tags=["trend", "trend-video"])
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))

    async def model_cost(_session, key):
        return SimpleNamespace(
            is_active=True, credits=12 if key.endswith("__resolution=720p") else 6
        )

    monkeypatch.setattr("api.wan30_launch.repo.get_model_cost", model_cost)
    response = await client.get("/api/v1/trends/12/checkout")

    assert response.status_code == 200
    assert response.json()["cost_credits"] == 30


@pytest.mark.asyncio
async def test_legacy_seedance_pricing_variant_quotes_full_duration(trend_client):
    client, monkeypatch, _reserve, _create = trend_client
    trend = SimpleNamespace(
        id=70,
        model="bytedance/seedance-2-5__resolution=720p",
        tags=["trend", "trend-video", "trend-duration:10"],
    )
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    resolve = AsyncMock(
        return_value=SimpleNamespace(
            model_key="bytedance/seedance-2-5__resolution=720p",
            is_active=True,
            credits=7,
        )
    )
    monkeypatch.setattr("api.trends_routes.repo.resolve_video_model_cost", resolve)

    response = await client.get("/api/v1/trends/70/checkout")

    assert response.status_code == 200
    assert response.json()["cost_credits"] == 70
    resolve.assert_awaited_once_with(
        ANY,
        "bytedance/seedance-2-5",
        duration=10,
        resolution="720p",
    )


@pytest.mark.asyncio
async def test_legacy_seedance_pricing_variant_launches_canonical_model(trend_client):
    client, monkeypatch, _reserve, create = trend_client
    trend = SimpleNamespace(
        id=70,
        model="bytedance/seedance-2-5__resolution=720p",
        tags=["trend", "trend-video", "trend-duration:10"],
    )
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))

    response = await client.post(
        "/api/v1/trends/70/run",
        json={
            "asset_id": "signed-photo-asset-id",
            "idempotency_key": "request-123",
            "quoted_credits": 70,
        },
    )

    assert response.status_code == 202
    request = create.await_args.kwargs["body"]
    assert request.model == "bytedance/seedance-2-5"
    assert request.resolution == "720p"
    assert request.duration == 10


@pytest.mark.asyncio
async def test_legacy_trend_accepts_canonical_runtime_model_during_prompt_resolution(monkeypatch):
    prompt = SimpleNamespace(
        id=70,
        prompt_text="animate portrait",
        model="bytedance/seedance-2-5__resolution=720p",
        tags=["trend", "trend-video"],
        status=PromptStatus.approved,
        is_public=True,
        trend_user_fields=[],
    )
    monkeypatch.setattr("db.prompt_repository.get_prompt_by_id", AsyncMock(return_value=prompt))
    body = VideoGenRequest(
        model="bytedance/seedance-2-5",
        prompt="hidden",
        prompt_id=70,
        mode="image",
        image_url="https://example.com/photo.png",
    )

    resolved, source = await _video_prompt_and_source(body, AsyncMock())

    assert resolved == "animate portrait"
    assert source is prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_key", "kind", "gen_type"),
    [
        ("midjourney-imagine", "image", GenerationType.image),
        ("midjourney-blend", "image", GenerationType.image),
        ("midjourney-video", "video", GenerationType.video),
    ],
)
async def test_trend_validation_keeps_midjourney_models_available(
    monkeypatch, model_key, kind, gen_type
):
    model = SimpleNamespace(model_key=model_key, gen_type=gen_type, is_active=True)
    get_model_cost = AsyncMock(return_value=model)
    monkeypatch.setattr("api.trends_routes.repo.get_model_cost", get_model_cost)

    result = await _validated_model(AsyncMock(), model_key, kind)

    assert result is model
    get_model_cost.assert_awaited_once_with(ANY, model_key)


@pytest.mark.asyncio
async def test_http_pre_submit_rejection_releases_trend_key(trend_client):
    client, monkeypatch, _reserve, create = trend_client
    trend = SimpleNamespace(id=13, model="gemini-omni-video", tags=["trend", "trend-video"])
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    create.side_effect = HTTPException(status_code=422, detail="Unknown video model")
    release = AsyncMock()
    monkeypatch.setattr("api.trends_routes.release_pre_submit_claim", release)

    response = await client.post(
        "/api/v1/trends/13/run",
        json={"asset_id": "signed-photo-asset-id", "idempotency_key": "request-123"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Unknown video model"
    release.assert_awaited_once_with(
        ANY,
        user_id=7,
        request_key="request-123",
        request_hash=ANY,
    )


@pytest.mark.asyncio
async def test_http_5xx_keeps_claim_uncertain_to_block_a_paid_replay(trend_client):
    client, monkeypatch, _reserve, create = trend_client
    trend = SimpleNamespace(id=13, model="gemini-omni-video", tags=["trend", "trend-video"])
    claim = SimpleNamespace(generation_id=None, status="running")
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    monkeypatch.setattr("api.trends_routes.get_claim", AsyncMock(side_effect=[None, claim]))
    create.side_effect = HTTPException(status_code=502, detail="Generation service error")
    release = AsyncMock()
    monkeypatch.setattr("api.trends_routes.release_pre_submit_claim", release)

    response = await client.post(
        "/api/v1/trends/13/run",
        json={"asset_id": "signed-photo-asset-id", "idempotency_key": "request-123"},
    )

    assert response.status_code == 502
    assert claim.status == "uncertain"
    release.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_rejects_invalid_gemini_trend_duration(trend_client):
    client, monkeypatch, _reserve, _create = trend_client
    monkeypatch.setattr("api.trends_routes.settings.ADMIN_IDS", [111])
    create_prompt = AsyncMock()
    monkeypatch.setattr("api.trends_routes.create_prompt", create_prompt)

    response = await client.post(
        "/api/v1/admin/trends",
        json={
            "kind": "video",
            "title": "Gemini trend",
            "prompt_template": "animate portrait",
            "preview_url": "https://example.com/preview.png",
            "model": "gemini-omni-video",
            "settings": {"duration": 5},
        },
    )

    assert response.status_code == 422
    create_prompt.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_canonicalizes_pricing_variant_before_publishing(trend_client):
    client, monkeypatch, _reserve, _create = trend_client
    monkeypatch.setattr("api.trends_routes.settings.ADMIN_IDS", [111])
    prompt = SimpleNamespace(id=70, trend_user_fields=None)
    create_prompt = AsyncMock(return_value=prompt)
    monkeypatch.setattr("api.trends_routes.create_prompt", create_prompt)
    monkeypatch.setattr("api.trends_routes.approve_prompt", AsyncMock(return_value=prompt))
    monkeypatch.setattr("api.trends_routes.trend_admin_payload", lambda _prompt: {"id": 70})

    response = await client.post(
        "/api/v1/admin/trends",
        json={
            "kind": "video",
            "title": "Seedance trend",
            "prompt_template": "animate portrait",
            "preview_url": "https://example.com/preview.png",
            "model": "bytedance/seedance-2-5__resolution=720p",
            "settings": {"duration": 10},
        },
    )

    assert response.status_code == 201
    assert create_prompt.await_args.kwargs["model"] == "bytedance/seedance-2-5"
    assert "trend-resolution:720p" in create_prompt.await_args.kwargs["tags"]


@pytest.mark.asyncio
async def test_admin_update_preserves_variant_resolution_as_a_setting(trend_client):
    client, monkeypatch, _reserve, _create = trend_client
    monkeypatch.setattr("api.trends_routes.settings.ADMIN_IDS", [111])
    prompt = SimpleNamespace(
        id=70,
        title="Seedance trend",
        description="",
        prompt_text="animate portrait",
        preview_url="https://example.com/preview.png",
        model="bytedance/seedance-2-5",
        tags=["trend", "trend-video", "trend-duration:10"],
        trend_user_fields=[],
    )
    monkeypatch.setattr("api.trends_routes.get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr("api.trends_routes.trend_admin_payload", lambda _prompt: {"id": 70})

    response = await client.post(
        "/api/v1/admin/trends/70/update",
        json={"model": "bytedance/seedance-2-5__resolution=720p"},
    )

    assert response.status_code == 200
    assert prompt.model == "bytedance/seedance-2-5"
    assert "trend-resolution:720p" in prompt.tags


@pytest.mark.asyncio
async def test_wan_trend_rejects_stale_quote_without_reserving_or_spending(trend_client):
    client, monkeypatch, reserve, create = trend_client
    trend = SimpleNamespace(
        id=12, model="wan/3-0-video", tags=["trend", "trend-video", "trend-duration:5"]
    )
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    monkeypatch.setattr(
        "api.trends_routes.quote_video_generation", AsyncMock(return_value={"cost_credits": 75})
    )

    response = await client.post(
        "/api/v1/trends/12/run",
        json={
            "asset_id": "signed-photo-asset-id",
            "idempotency_key": "request-123",
            "quoted_credits": 60,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "trend_quote_stale"
    reserve.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_in_flight_duplicate_request_cannot_launch_second_generation(trend_client):
    client, monkeypatch, reserve, create = trend_client
    body = TrendRunRequest(asset_id="signed-photo-asset-id", idempotency_key="request-123")
    claim = SimpleNamespace(
        trend_id=12, request_hash=_trend_request_hash(12, body), generation_id=None
    )
    monkeypatch.setattr("api.trends_routes.get_claim", AsyncMock(return_value=claim))

    response = await client.post("/api/v1/trends/12/run", json=body.model_dump())

    assert response.status_code == 409
    reserve.assert_not_awaited()
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_gemini_trend_uses_supported_default_duration(trend_client):
    client, monkeypatch, _reserve, create = trend_client
    trend = SimpleNamespace(id=13, model="gemini-omni-video", tags=["trend", "trend-video"])
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))

    response = await client.post(
        "/api/v1/trends/13/run",
        json={
            "asset_id": "signed-photo-asset-id",
            "idempotency_key": "request-123",
        },
    )

    assert response.status_code == 202
    assert create.await_args.kwargs["body"].duration == 4
    assert _trend_video_duration("gemini-omni-video", {"duration": 5}) == 4


@pytest.mark.asyncio
async def test_legacy_five_second_gemini_trend_still_launches_at_four(trend_client):
    client, monkeypatch, _reserve, create = trend_client
    trend = SimpleNamespace(
        id=13, model="gemini-omni-video", tags=["trend", "trend-video", "trend-duration:5"]
    )
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))

    response = await client.post(
        "/api/v1/trends/13/run",
        json={
            "asset_id": "signed-photo-asset-id",
            "idempotency_key": "request-123",
        },
    )

    assert response.status_code == 202
    assert create.await_args.kwargs["body"].duration == 4


@pytest.mark.asyncio
async def test_definitive_pre_submit_rejection_releases_trend_key(trend_client):
    client, monkeypatch, _reserve, create = trend_client
    trend = SimpleNamespace(id=13, model="gemini-omni-video", tags=["trend", "trend-video"])
    monkeypatch.setattr("api.trends_routes._get_public_trend", AsyncMock(return_value=trend))
    create.side_effect = PreSubmitRejection(status_code=402, detail="Insufficient credits")
    release = AsyncMock()
    monkeypatch.setattr("api.trends_routes.release_pre_submit_claim", release)

    response = await client.post(
        "/api/v1/trends/13/run",
        json={
            "asset_id": "signed-photo-asset-id",
            "idempotency_key": "request-123",
        },
    )

    assert response.status_code == 402
    release.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_trend_claims_admit_only_one_paid_request(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'trend-claims.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(TrendRunClaim.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def attempt():
        async with sessions() as session:
            _claim, created = await reserve_claim(
                session,
                user_id=7,
                request_key="request-123",
                request_hash="a" * 64,
                trend_id=12,
            )
            return created

    try:
        assert sorted(await asyncio.gather(attempt(), attempt())) == [False, True]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_pre_submit_rejection_releases_claim_for_retry(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'released-claim.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(TrendRunClaim.__table__.create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with sessions() as session:
            _claim, created = await reserve_claim(
                session,
                user_id=7,
                request_key="request-123",
                request_hash="a" * 64,
                trend_id=12,
            )
            assert created
            await release_pre_submit_claim(
                session,
                user_id=7,
                request_key="request-123",
                request_hash="a" * 64,
            )
        async with sessions() as session:
            _claim, created = await reserve_claim(
                session,
                user_id=7,
                request_key="request-123",
                request_hash="a" * 64,
                trend_id=12,
            )
            assert created
    finally:
        await engine.dispose()
