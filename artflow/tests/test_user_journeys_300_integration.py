from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from api.image_service import normalize_quality_for_aspect_ratio
from api.miniapp_auth import create_web_auth_token, get_miniapp_user
from api.miniapp_routes import GenerationOut
from core.trends import build_trend_tags
from db.models import GenerationStatus, GenerationType, ImageGenerationAction, PromptStatus
from db.session import get_session
from main import app

pytestmark = pytest.mark.asyncio

DOMAINS = range(1, 13)
SEEDS = range(1, 26)
CASES = tuple((domain, seed) for domain in DOMAINS for seed in SEEDS)
CASE_IDS = tuple(f"journey-{domain:02d}-{seed:02d}" for domain, seed in CASES)
assert len(CASES) == 300

VIEWPORTS = (320, 340, 360, 361, 375, 390, 414, 430, 431, 480, 520, 560, 561, 640, 720, 768, 820, 900, 901, 1024, 1100, 1180, 1280, 1366, 1440)


def _user(seed: int = 1, *, tg_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=seed,
        tg_id=tg_id if tg_id is not None else 100_000 + seed,
        username=f"journey_{seed}",
        full_name=f"Пользователь {seed}",
        photo_url=f"https://cdn.example.test/avatar-{seed}.jpg",
        credits=float(100 + seed),
        referral_code=f"J{seed:04d}",
        referral_balance=0.0,
        is_banned=False,
        language="ru",
        created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )


def _generation(seed: int, *, kind: GenerationType = GenerationType.image, user_id: int = 1) -> SimpleNamespace:
    suffix = "mp4" if kind == GenerationType.video else "png"
    media = f"https://cdn.example.test/result-{seed}.{suffix}"
    return SimpleNamespace(
        id=10_000 + seed,
        user_id=user_id,
        model="bytedance/seedance-2-5" if kind == GenerationType.video else "nano-banana-2",
        gen_type=kind,
        prompt=f"Journey prompt {seed}",
        status=GenerationStatus.done,
        result_url=media,
        result_urls=json.dumps([media]),
        credits_spent=20.0 if kind == GenerationType.video else 2.5,
        created_at=datetime(2026, 8, 25, 3, seed % 60, tzinfo=timezone.utc),
        likes_count=seed % 7,
        shares_count=seed % 5,
        is_public_feed=True,
        is_prompt_library=False,
        source_feed_gen_id=None,
        input_params="{}",
    )


def _feed_card(seed: int, *, kind: GenerationType = GenerationType.image, mine: bool = False) -> SimpleNamespace:
    generation = _generation(seed, kind=kind, user_id=1 if mine else 100)
    return SimpleNamespace(
        generation=generation,
        username=f"author_{seed}",
        full_name=f"Author {seed}",
        author_photo_url=f"https://cdn.example.test/author-{seed}.jpg",
        remix_count=seed % 3,
        aspect_ratio="16:9" if kind == GenerationType.video else "1:1",
        quality="720p" if kind == GenerationType.video else "2K",
        reference_url=None,
        reference_urls=None,
        score=seed,
    )


def _trend(seed: int, kind: str) -> SimpleNamespace:
    settings = {
        "category": "portrait" if kind == "image" else "photo-video",
        "requires_reference": True,
        "ratio": "1:1" if kind == "image" else "9:16",
        "quality": "2K",
        "duration": 5,
        "resolution": "720p",
        "scenario": "image",
    }
    return SimpleNamespace(
        id=20_000 + seed,
        author_id=1,
        title=f"Тренд {seed}",
        description=f"Описание тренда {seed}",
        prompt_text=f"SECRET TREND PROMPT {seed}",
        preview_url=f"https://cdn.example.test/trend-{seed}.{'mp4' if kind == 'video' else 'png'}",
        model="bytedance/seedance-2-5" if kind == "video" else "nano-banana-2",
        tags=build_trend_tags(kind, settings),
        likes=seed % 7,
        uses_count=seed,
        status=PromptStatus.approved,
        is_public=True,
        created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )


def _processing(seed: int, *, model: str, kind: GenerationType, prompt: str, credits: float, source_id: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=70_000 + seed,
        model=model,
        gen_type=kind,
        prompt=prompt,
        status=GenerationStatus.processing,
        result_url=None,
        result_urls=None,
        credits_spent=credits,
        created_at=datetime.now(timezone.utc),
        is_public_feed=False,
        is_prompt_library=False,
        source_feed_gen_id=source_id,
    )


@pytest.fixture
async def env():
    session = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    state = {"user": _user()}

    async def fake_session():
        yield session

    async def fake_user():
        return state["user"]

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_miniapp_user] = fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session, state
    app.dependency_overrides.clear()


def _stub_empty_catalogs(monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=[]))
    monkeypatch.setattr("api.miniapp_routes.repo.get_model_cost", AsyncMock(return_value=None))
    monkeypatch.setattr("api.miniapp_routes.repo.get_first_active_model_cost", AsyncMock(return_value=None))
    monkeypatch.setattr("api.miniapp_routes.repo.get_feed_generations", AsyncMock(return_value=[]))
    monkeypatch.setattr("api.miniapp_routes.repo.get_top_day_generations", AsyncMock(return_value=[]))
    monkeypatch.setattr("api.trends_routes.get_prompts_by_tag", AsyncMock(return_value=[]))


@pytest.mark.parametrize(("domain", "seed"), CASES, ids=CASE_IDS)
async def test_user_journey_integration(domain: int, seed: int, env, monkeypatch) -> None:
    client, session, state = env

    if domain == 1:
        _stub_empty_catalogs(monkeypatch)
        endpoints = (
            "/api/v1/feed?source=recent&limit=20",
            "/api/v1/models/image",
            "/api/v1/models/video",
            "/api/v1/models/music",
            "/api/v1/trends?limit=20",
            "/api/v1/me",
        )
        for offset in (0, 2, 4):
            response = await client.get(endpoints[(seed + offset) % len(endpoints)])
            assert response.status_code == 200, response.text
        return

    if domain == 2:
        tg_id = 200_000 + seed
        monkeypatch.setattr("api.miniapp_auth.repo.get_user_by_tg_id", AsyncMock(return_value=_user(seed, tg_id=tg_id)))
        override = app.dependency_overrides.pop(get_miniapp_user)
        try:
            response = await client.get(
                "/api/v1/me",
                headers={"X-Web-Auth-Token": create_web_auth_token(tg_id), "X-APIX-Viewport-Width": str(VIEWPORTS[seed - 1])},
            )
        finally:
            app.dependency_overrides[get_miniapp_user] = override
        assert response.status_code == 200
        assert response.json()["tg_id"] == tg_id
        assert response.json()["username"] == f"journey_{seed}"
        return

    if domain == 3:
        state["user"] = _user(seed)
        plan = SimpleNamespace(key=f"plan-{seed}", label=f"Пакет {seed}", credits=10 + seed, price_rub=float(100 + seed * 10), price_stars=100 + seed * 10)
        monkeypatch.setattr("api.miniapp_routes.repo.get_active_price_plans", AsyncMock(return_value=[plan]))
        me = await client.get("/api/v1/me")
        plans = await client.get("/api/v1/plans")
        assert me.status_code == plans.status_code == 200
        assert me.json()["credits"] == float(100 + seed)
        assert plans.json()[0]["key"] == f"plan-{seed}"
        assert plans.json()[0]["credits"] == 10 + seed
        assert plans.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
        return

    if domain == 4:
        source = ("recent", "top_day", "top")[seed % 3]
        cards = [
            _feed_card(seed * 10 + 1),
            _feed_card(seed * 10 + 2, mine=True),
            _feed_card(seed * 10 + 3, kind=GenerationType.video),
            _feed_card(seed * 10 + 4, kind=GenerationType.video, mine=True),
        ]
        recent = AsyncMock(return_value=cards)
        top_day = AsyncMock(return_value=cards)
        monkeypatch.setattr("api.miniapp_routes.repo.get_feed_generations", recent)
        monkeypatch.setattr("api.miniapp_routes.repo.get_top_day_generations", top_day)
        response = await client.get(f"/api/v1/feed?source={source}&limit=20")
        assert response.status_code == 200
        payload = response.json()
        assert {item["gen_type"] for item in payload} == {"image", "video"}
        assert {item["is_mine"] for item in payload} == {True, False}
        assert len(payload) == 4
        return

    if domain == 5:
        target_id = 5_000 + seed
        canonical = f"https://cdn.example.test/canonical-{seed}.png"
        stale = f"https://cdn.example.test/stale-{seed}.png"
        card = _feed_card(seed)
        card.generation.id = target_id
        card.generation.result_url = stale
        card.generation.result_urls = json.dumps([canonical, stale])
        getter = AsyncMock(return_value=card)
        monkeypatch.setattr("api.web.feed.repo.get_feed_generation_card", getter)
        monkeypatch.setattr("api.web.feed.public_url_is_available", lambda _url: True)
        monkeypatch.setattr("api.web.schemas.public_url_is_available", lambda _url: True)
        monkeypatch.setattr("api.web.feed.preview_public_image_url", lambda url, **_kwargs: url)
        monkeypatch.setattr("api.web.schemas.preview_public_image_url", lambda url, **_kwargs: url)
        response = await client.get(f"/api/web/feed/{target_id}")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["id"] == target_id
        assert data["result_url"] == canonical
        assert data["result_urls"][0] == canonical
        assert getter.await_args.args[1] == target_id
        return

    if domain == 6:
        source_id = 6_000 + seed
        source_url = f"https://cdn.example.test/repeat-source-{seed}.png"
        uploaded = f"https://cdn.example.test/repeat-ref-{seed}.png"
        source = SimpleNamespace(id=source_id, model="nano-banana-2", prompt=f"hidden prompt {seed}", result_url=source_url, result_urls=json.dumps([source_url]))
        image_session = AsyncMock(return_value=SimpleNamespace(id=71_000 + seed))
        image_generate = AsyncMock(return_value=SimpleNamespace(task_id=f"repeat-{seed}"))
        captured: dict = {}

        async def create_generation(_session, _uid, model, kind, prompt, credits, **kwargs):
            captured.update(kwargs)
            return _processing(seed, model=model, kind=kind, prompt=prompt, credits=credits, source_id=kwargs.get("source_feed_gen_id"))

        monkeypatch.setattr("api.miniapp_routes.repo.get_public_feed_generation", AsyncMock(return_value=source))
        monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2.5)))
        monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
        monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
        monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", image_session)
        monkeypatch.setattr("api.miniapp_routes.repo.create_generation", create_generation)
        monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", AsyncMock())
        monkeypatch.setattr("api.miniapp_routes.repo.increment_feed_share", AsyncMock())
        monkeypatch.setattr("api.miniapp_routes.image_service.generate_image", image_generate)
        response = await client.post(
            f"/api/v1/feed/{source_id}/remix",
            json={"model": "nano-banana-2", "mode": "image", "source_image_url": source_url, "image_url": uploaded, "reference_urls": [uploaded], "aspect_ratio": "1:1", "quality": "2K", "count": 1},
        )
        assert response.status_code == 202, response.text
        assert response.json()["prompt_hidden"] is True
        assert captured["parent_generation_id"] == source_id
        assert captured["source_feed_gen_id"] == source_id
        assert captured["action_type"] == ImageGenerationAction.remix
        assert image_session.await_args.kwargs["reference_urls"] == [source_url, uploaded]
        assert image_generate.await_args.kwargs["image_url"] == [source_url, uploaded]
        assert len(image_generate.await_args.kwargs["image_url"]) == 2
        return

    if domain == 7:
        prompt = f"Фотореалистичный портрет сценарий {seed}"
        ratio = ("1:1", "4:5", "9:16")[seed % 3]
        requested_quality = "2K" if seed % 2 else "4K"
        quality = normalize_quality_for_aspect_ratio("nano-banana-2", ratio, requested_quality)
        cost = 1.5 if quality == "2K" else 2.5
        resolve_cost = AsyncMock(return_value=SimpleNamespace(credits=cost))
        image_generate = AsyncMock(return_value=SimpleNamespace(task_id=f"image-{seed}"))

        async def create_generation(_session, _uid, model, kind, prompt_value, credits, **_kwargs):
            return _processing(seed, model=model, kind=kind, prompt=prompt_value, credits=credits)

        monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", resolve_cost)
        monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
        monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
        monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", AsyncMock(return_value=SimpleNamespace(id=72_000 + seed)))
        monkeypatch.setattr("api.miniapp_routes.repo.create_generation", create_generation)
        monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", AsyncMock())
        monkeypatch.setattr("api.miniapp_routes.repo.update_image_session_last_prompt", AsyncMock())
        monkeypatch.setattr("api.miniapp_routes.image_service.generate_image", image_generate)
        response = await client.post("/api/v1/generate/image", json={"model": "nano-banana-2", "prompt": prompt, "aspect_ratio": ratio, "quality": requested_quality, "reference_urls": []})
        assert response.status_code == 202, response.text
        assert response.json()["credits_spent"] == cost
        assert image_generate.await_args.args[1] == prompt
        assert image_generate.await_args.kwargs["aspect_ratio"] == ratio
        assert image_generate.await_args.kwargs["quality"] == quality
        assert resolve_cost.await_args.kwargs["quality"] == quality
        return

    if domain == 8:
        prompt = f"Видео пользовательский сценарий {seed}"
        ratio = "16:9" if seed % 2 else "9:16"
        duration = 5 if seed % 2 else 10
        resolution = "480p" if seed % 3 else "720p"
        rate = 3.0 if resolution == "480p" else 6.0
        resolve_cost = AsyncMock(return_value=SimpleNamespace(credits=rate))
        video_generate = AsyncMock(return_value=SimpleNamespace(task_id=f"video-{seed}", provider="kieai"))

        async def create_generation(_session, _uid, model, kind, prompt_value, credits, **_kwargs):
            return _processing(seed, model=model, kind=kind, prompt=prompt_value, credits=credits)

        monkeypatch.setattr("api.miniapp_routes.repo.resolve_video_model_cost", resolve_cost)
        monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
        monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
        monkeypatch.setattr("api.miniapp_routes.repo.create_generation", create_generation)
        monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", AsyncMock())
        monkeypatch.setattr("api.miniapp_routes.video_service.generate_video", video_generate)
        response = await client.post(
            "/api/v1/generate/video",
            json={"model": "bytedance/seedance-2-5", "prompt": prompt, "mode": "text", "duration": duration, "aspect_ratio": ratio, "resolution": resolution},
        )
        assert response.status_code == 202, response.text
        assert response.json()["model"] == "bytedance/seedance-2-5"
        assert response.json()["credits_spent"] == rate * duration
        assert video_generate.await_args.args[1] == prompt
        assert video_generate.await_args.kwargs["duration"] == duration
        assert video_generate.await_args.kwargs["aspect_ratio"] == ratio
        assert video_generate.await_args.kwargs["resolution"] == resolution
        assert resolve_cost.await_args.kwargs["resolution"] == resolution
        return

    if domain == 9:
        image_trend = _trend(seed, "image")
        video_trend = _trend(100 + seed, "video")
        monkeypatch.setattr("api.trends_routes.get_prompts_by_tag", AsyncMock(return_value=[image_trend, video_trend]))
        kind = "image" if seed % 2 else "video"
        response = await client.get(f"/api/v1/trends?kind={kind}&limit=25")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["kind"] == kind
        assert "prompt" not in payload[0]
        return

    if domain == 10:
        state["user"] = _user(seed)
        trend = _trend(seed, "image")
        asset_url = f"https://cdn.example.test/identity-{seed}.jpg"
        asset_id = f"apixasset.integration.{seed:04d}.signature"
        session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
        create_image = AsyncMock(return_value=GenerationOut(id=74_000 + seed, model="nano-banana-2", gen_type="image", prompt="", prompt_hidden=True, status="processing", result_url=None, credits_spent=2.5, created_at=datetime.now(timezone.utc).isoformat()))
        monkeypatch.setattr("api.trends_routes.get_prompt_by_id", AsyncMock(return_value=trend))
        monkeypatch.setattr("api.trends_routes.repo.get_model_cost", AsyncMock(return_value=SimpleNamespace(model_key="nano-banana-2", gen_type=GenerationType.image, is_active=True)))
        monkeypatch.setattr("api.trends_routes.verify_uploaded_asset", lambda _asset_id, **_kwargs: {"url": asset_url, "kind": "image", "filename": f"identity-{seed}.jpg", "content_type": "image/jpeg", "size": 4})
        monkeypatch.setattr("api.trends_routes.create_image_generation", create_image)
        monkeypatch.setattr("api.trends_routes._patch_trend_snapshot", AsyncMock())
        response = await client.post(f"/api/v1/trends/{trend.id}/run", json={"asset_id": asset_id, "idempotency_key": f"journey10-{seed:02d}"})
        assert response.status_code == 202, response.text
        body = create_image.await_args.kwargs["body"]
        assert body.prompt_id == trend.id
        assert body.reference_url == asset_url
        assert body.reference_urls == [asset_url]
        assert body.prompt == "Использовать скрытый трендовый промпт"
        assert create_image.await_args.kwargs["surface"] == "web"
        return

    if domain == 11:
        state["user"] = _user(seed)
        branch = seed % 3
        if branch == 0:
            setter = AsyncMock()
            monkeypatch.setattr("api.miniapp_routes.repo.set_user_language", setter)
            response = await client.post("/api/v1/settings/language", json={"language": "en"})
            assert response.status_code == 200
            assert response.json() == {"language": "en"}
            assert setter.await_args.args[1:] == (seed, "en")
        elif branch == 1:
            monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=[SimpleNamespace(model_key="suno/v5.5", display_name="Suno 5.5", credits=10 + seed, gen_type=GenerationType.music, is_active=True)]))
            response = await client.get("/api/v1/models/music")
            assert response.status_code == 200
            assert response.json()[0]["key"] == "suno/v5.5"
        else:
            generation = _generation(seed, user_id=seed)
            monkeypatch.setattr("api.miniapp_routes._reconcile_user_active_generations", AsyncMock())
            monkeypatch.setattr("api.miniapp_routes.repo.get_user_history", AsyncMock(return_value=[generation]))
            response = await client.get("/api/v1/history?limit=40")
            assert response.status_code == 200
            assert response.json()[0]["id"] == generation.id
        return

    mode = seed % 5
    if mode == 0:
        monkeypatch.setattr("api.miniapp_routes.repo.get_feed_generations", AsyncMock(side_effect=HTTPException(status_code=503, detail="feed unavailable")))
        response = await client.get("/api/v1/feed?source=recent")
        assert response.status_code == 503
    elif mode == 1:
        monkeypatch.setattr("api.trends_routes.get_prompts_by_tag", AsyncMock(side_effect=HTTPException(status_code=502, detail="trends unavailable")))
        response = await client.get("/api/v1/trends")
        assert response.status_code == 502
    elif mode == 2:
        monkeypatch.setattr("api.miniapp_routes.repo.get_active_price_plans", AsyncMock(return_value=[]))
        response = await client.get("/api/v1/plans")
        assert response.status_code == 200 and response.json() == []
    elif mode == 3:
        monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=[]))
        response = await client.get("/api/v1/models/image")
        assert response.status_code == 200 and response.json() == []
    else:
        monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=[]))
        response = await client.get("/api/v1/models/video")
        assert response.status_code == 200 and response.json() == []
