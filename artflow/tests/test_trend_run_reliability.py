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
from api.trends_routes import TrendRunRequest, _trend_request_hash, _trend_video_duration
from db.models import PromptStatus, TrendRunClaim
from db.session import get_session
from db.trend_run_claims import release_pre_submit_claim, reserve_claim
from main import app


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
        return SimpleNamespace(is_active=True, credits=12 if key.endswith("__resolution=720p") else 6)

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
    monkeypatch.setattr(
        "api.trends_routes.get_claim", AsyncMock(side_effect=[None, claim])
    )
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
    monkeypatch.setattr(
        "api.trends_routes.trend_admin_payload", lambda _prompt: {"id": 70}
    )

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
    monkeypatch.setattr(
        "api.trends_routes.trend_admin_payload", lambda _prompt: {"id": 70}
    )

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
    claim = SimpleNamespace(trend_id=12, request_hash=_trend_request_hash(12, body), generation_id=None)
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

    response = await client.post("/api/v1/trends/13/run", json={
        "asset_id": "signed-photo-asset-id", "idempotency_key": "request-123",
    })

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

    response = await client.post("/api/v1/trends/13/run", json={
        "asset_id": "signed-photo-asset-id", "idempotency_key": "request-123",
    })

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
                session, user_id=7, request_key="request-123",
                request_hash="a" * 64, trend_id=12,
            )
            assert created
            await release_pre_submit_claim(
                session, user_id=7, request_key="request-123", request_hash="a" * 64,
            )
        async with sessions() as session:
            _claim, created = await reserve_claim(
                session, user_id=7, request_key="request-123",
                request_hash="a" * 64, trend_id=12,
            )
            assert created
    finally:
        await engine.dispose()
