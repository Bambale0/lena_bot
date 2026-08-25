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
from db.models import (
    GenerationStatus,
    GenerationType,
    ImageGenerationAction,
    PromptStatus,
)
from db.session import get_session
from main import app

pytestmark = pytest.mark.asyncio

SCENARIOS_PER_DOMAIN = 25
DOMAIN_COUNT = 12
EXPECTED_TEST_COUNT = SCENARIOS_PER_DOMAIN * DOMAIN_COUNT
SEEDS = tuple(range(1, SCENARIOS_PER_DOMAIN + 1))

assert EXPECTED_TEST_COUNT == 300

NAV_TABS = ("Лента", "Фото", "Видео", "Motion", "Тренды", "Сервисы", "Профиль", "Настройки")
NAV_ENDPOINTS = {
    "Лента": "/api/v1/feed?source=recent&limit=20",
    "Фото": "/api/v1/models/image",
    "Видео": "/api/v1/models/video",
    "Motion": "/api/v1/models/video",
    "Тренды": "/api/v1/trends?limit=20",
    "Сервисы": "/api/v1/models/music",
    "Профиль": "/api/v1/me",
    "Настройки": "/api/v1/me",
}
VIEWPORT_WIDTHS = (
    320,
    340,
    360,
    361,
    375,
    390,
    414,
    430,
    431,
    480,
    520,
    560,
    561,
    640,
    720,
    768,
    820,
    900,
    901,
    1024,
    1100,
    1180,
    1280,
    1366,
    1440,
)


def _ids(domain: int) -> list[str]:
    return [f"journey-{domain:02d}-{seed:02d}" for seed in SEEDS]


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


def _generation(
    seed: int,
    *,
    gen_type: GenerationType = GenerationType.image,
    user_id: int = 1,
    result_url: str | None = None,
    result_urls: list[str] | None = None,
    prompt: str | None = None,
    model: str | None = None,
    source_feed_gen_id: int | None = None,
) -> SimpleNamespace:
    media = result_url or f"https://cdn.example.test/result-{seed}.{'mp4' if gen_type == GenerationType.video else 'png'}"
    urls = result_urls if result_urls is not None else [media]
    return SimpleNamespace(
        id=10_000 + seed,
        user_id=user_id,
        model=model or ("veo3_fast" if gen_type == GenerationType.video else "nano-banana-2"),
        gen_type=gen_type,
        prompt=prompt or f"Journey prompt {seed}",
        status=GenerationStatus.done,
        result_url=media,
        result_urls=json.dumps(urls, ensure_ascii=False),
        credits_spent=2.5 if gen_type == GenerationType.image else 20.0,
        created_at=datetime(2026, 8, 25, 3, seed % 60, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 25, 3, seed % 60, tzinfo=timezone.utc),
        likes_count=seed % 7,
        shares_count=seed % 5,
        is_public_feed=True,
        is_prompt_library=False,
        source_feed_gen_id=source_feed_gen_id,
        input_params="{}",
    )


def _feed_card(
    seed: int,
    *,
    gen_type: GenerationType = GenerationType.image,
    mine: bool = False,
    user_id: int = 1,
    result_url: str | None = None,
    result_urls: list[str] | None = None,
    author: str | None = None,
) -> SimpleNamespace:
    generation = _generation(
        seed,
        gen_type=gen_type,
        user_id=user_id if mine else user_id + 99,
        result_url=result_url,
        result_urls=result_urls,
    )
    return SimpleNamespace(
        generation=generation,
        username=author or f"author_{seed}",
        full_name=f"Author {seed}",
        author_photo_url=f"https://cdn.example.test/author-{seed}.jpg",
        remix_count=seed % 3,
        aspect_ratio="16:9" if gen_type == GenerationType.video else "1:1",
        quality="720p" if gen_type == GenerationType.video else "2K",
        reference_url=None,
        reference_urls=None,
        score=seed,
    )


def _trend(seed: int, kind: str = "image") -> SimpleNamespace:
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
        model="veo3_fast" if kind == "video" else "nano-banana-2",
        tags=build_trend_tags(kind, settings),
        likes=seed % 7,
        uses_count=seed,
        status=PromptStatus.approved,
        is_public=True,
        created_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
    )


@pytest.fixture
async def journey_env():
    session = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    user_state = {"value": _user(1)}

    async def fake_session():
        yield session

    async def fake_user():
        return user_state["value"]

    app.dependency_overrides[get_session] = fake_session
    app.dependency_overrides[get_miniapp_user] = fake_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, session, user_state
    app.dependency_overrides.clear()


def _stub_bootstrap(monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=[]))
    monkeypatch.setattr("api.miniapp_routes.repo.get_feed_generations", AsyncMock(return_value=[]))
    monkeypatch.setattr("api.miniapp_routes.repo.get_top_day_generations", AsyncMock(return_value=[]))
    monkeypatch.setattr("api.trends_routes.get_prompts_by_tag", AsyncMock(return_value=[]))


def _processing_generation(
    generation_id: int,
    *,
    model: str,
    gen_type: GenerationType,
    prompt: str,
    credits_spent: float,
    source_feed_gen_id: int | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=generation_id,
        model=model,
        gen_type=gen_type,
        prompt=prompt,
        status=GenerationStatus.processing,
        result_url=None,
        result_urls=None,
        credits_spent=credits_spent,
        created_at=datetime.now(timezone.utc),
        is_public_feed=False,
        is_prompt_library=False,
        source_feed_gen_id=source_feed_gen_id,
    )


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(1))
async def test_journey_01_navigation_backend_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    _stub_bootstrap(monkeypatch)
    sequence = (
        NAV_TABS[seed % len(NAV_TABS)],
        NAV_TABS[(seed * 3 + 1) % len(NAV_TABS)],
        NAV_TABS[(seed * 5 + 2) % len(NAV_TABS)],
    )

    for label in sequence:
        response = await client.get(NAV_ENDPOINTS[label])
        assert response.status_code == 200, (label, response.text)


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(2))
async def test_journey_02_telegram_webview_auth_bootstrap(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    width = VIEWPORT_WIDTHS[seed - 1]
    tg_id = 200_000 + seed
    expected = _user(seed, tg_id=tg_id)
    monkeypatch.setattr("api.miniapp_auth.repo.get_user_by_tg_id", AsyncMock(return_value=expected))

    override = app.dependency_overrides.pop(get_miniapp_user)
    try:
        response = await client.get(
            "/api/v1/me",
            headers={
                "X-Web-Auth-Token": create_web_auth_token(tg_id),
                "X-APIX-Viewport-Width": str(width),
            },
        )
    finally:
        app.dependency_overrides[get_miniapp_user] = override

    assert response.status_code == 200
    payload = response.json()
    assert payload["tg_id"] == tg_id
    assert payload["username"] == f"journey_{seed}"


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(3))
async def test_journey_03_profile_and_balance_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, user_state = journey_env
    user_state["value"] = _user(seed)
    plan = SimpleNamespace(
        key=f"plan-{seed}",
        label=f"Пакет {seed}",
        credits=10 + seed,
        price_rub=float(100 + seed * 10),
        price_stars=100 + seed * 10,
        is_active=True,
        sort_order=seed,
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_active_price_plans",
        AsyncMock(return_value=[plan]),
    )

    me, plans = await client.get("/api/v1/me"), await client.get("/api/v1/plans")

    assert me.status_code == 200
    assert me.json()["full_name"] == f"Пользователь {seed}"
    assert me.json()["credits"] == float(100 + seed)
    assert plans.status_code == 200
    assert plans.json()[0]["key"] == f"plan-{seed}"
    assert plans.json()[0]["title"] == f"Пакет {seed}"
    assert plans.json()[0]["credits"] == 10 + seed
    assert plans.json()[0]["price_stars"] == 100 + seed * 10
    assert plans.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(4))
async def test_journey_04_feed_source_and_filter_data_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, user_state = journey_env
    user_state["value"] = _user(1)
    source = ("recent", "top_day", "top")[seed % 3]
    cards = [
        _feed_card(seed * 10 + 1, mine=False),
        _feed_card(seed * 10 + 2, mine=True),
        _feed_card(seed * 10 + 3, gen_type=GenerationType.video, mine=False),
        _feed_card(seed * 10 + 4, gen_type=GenerationType.video, mine=True),
    ]
    recent = AsyncMock(return_value=cards)
    top_day = AsyncMock(return_value=cards)
    monkeypatch.setattr("api.miniapp_routes.repo.get_feed_generations", recent)
    monkeypatch.setattr("api.miniapp_routes.repo.get_top_day_generations", top_day)

    response = await client.get(f"/api/v1/feed?source={source}&limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 4
    assert {item["gen_type"] for item in payload} == {"image", "video"}
    assert {item["is_mine"] for item in payload} == {True, False}
    if source == "top_day":
        top_day.assert_awaited_once()
        recent.assert_not_awaited()
    else:
        recent.assert_awaited_once()


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(5))
async def test_journey_05_shared_feed_exact_id_and_canonical_media(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    target_id = 5_000 + seed
    canonical = f"https://cdn.example.test/canonical-{seed}.png"
    stale = f"https://cdn.example.test/stale-{seed}.png"
    card = _feed_card(
        seed,
        result_url=stale,
        result_urls=[canonical, stale],
        author=f"target_{seed}",
    )
    card.generation.id = target_id
    get_card = AsyncMock(return_value=card)
    monkeypatch.setattr("api.web.feed.repo.get_feed_generation_card", get_card)
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
    get_card.assert_awaited_once()
    assert get_card.await_args.args[1] == target_id


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(6))
async def test_journey_06_feed_repeat_preserves_lineage_and_user_refs(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    source_id = 6_000 + seed
    source_url = f"https://cdn.example.test/repeat-source-{seed}.png"
    uploaded = f"https://cdn.example.test/repeat-ref-{seed}.png"
    source = SimpleNamespace(
        id=source_id,
        model="nano-banana-2",
        prompt=f"hidden prompt {seed}",
        result_url=source_url,
        result_urls=json.dumps([source_url]),
    )
    image_session = AsyncMock(return_value=SimpleNamespace(id=70_000 + seed))
    image_generate = AsyncMock(return_value=SimpleNamespace(task_id=f"repeat-task-{seed}"))
    captured: dict = {}

    async def create_generation(_session, _user_id, model, gen_type, prompt, credits_spent, **kwargs):
        captured.update(kwargs)
        return _processing_generation(
            71_000 + seed,
            model=model,
            gen_type=gen_type,
            prompt=prompt,
            credits_spent=credits_spent,
            source_feed_gen_id=kwargs.get("source_feed_gen_id"),
        )

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
        json={
            "model": "nano-banana-2",
            "mode": "image",
            "source_image_url": source_url,
            "image_url": uploaded,
            "reference_urls": [uploaded],
            "aspect_ratio": "1:1",
            "quality": "2K",
            "count": 1,
        },
    )

    assert response.status_code == 202, response.text
    assert response.json()["prompt_hidden"] is True
    assert captured["parent_generation_id"] == source_id
    assert captured["source_feed_gen_id"] == source_id
    assert captured["action_type"] == ImageGenerationAction.remix
    assert image_session.await_args.kwargs["reference_url"] == uploaded
    provider_refs = image_generate.await_args.kwargs["image_url"]
    assert uploaded in ([provider_refs] if isinstance(provider_refs, str) else provider_refs)


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(7))
async def test_journey_07_image_generation_http_to_provider_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    prompt = f"Фотореалистичный портрет сценарий {seed}"
    ratio = ("1:1", "4:5", "9:16")[seed % 3]
    requested_quality = "2K" if seed % 2 else "4K"
    expected_quality = normalize_quality_for_aspect_ratio("nano-banana-2", requested_quality, ratio)
    cost = 1.5 if expected_quality == "2K" else 2.5
    resolve_cost = AsyncMock(return_value=SimpleNamespace(credits=cost))
    spend = AsyncMock(return_value=True)
    image_generate = AsyncMock(return_value=SimpleNamespace(task_id=f"image-task-{seed}"))

    async def create_generation(_session, _user_id, model, gen_type, prompt_value, credits_spent, **_kwargs):
        return _processing_generation(
            72_000 + seed,
            model=model,
            gen_type=gen_type,
            prompt=prompt_value,
            credits_spent=credits_spent,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", resolve_cost)
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend)
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", AsyncMock(return_value=SimpleNamespace(id=72_500 + seed)))
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", AsyncMock())
    monkeypatch.setattr("api.miniapp_routes.repo.update_image_session_last_prompt", AsyncMock())
    monkeypatch.setattr("api.miniapp_routes.image_service.generate_image", image_generate)

    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "nano-banana-2",
            "prompt": prompt,
            "aspect_ratio": ratio,
            "quality": requested_quality,
            "reference_urls": [],
        },
    )

    assert response.status_code == 202, response.text
    assert response.json()["model"] == "nano-banana-2"
    assert response.json()["credits_spent"] == cost
    assert image_generate.await_args.args[1] == prompt
    assert image_generate.await_args.kwargs["aspect_ratio"] == ratio
    assert image_generate.await_args.kwargs["quality"] == expected_quality
    assert resolve_cost.await_args.kwargs["quality"] == expected_quality
    spend.assert_awaited_once()


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(8))
async def test_journey_08_video_generation_http_to_provider_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    prompt = f"Видео пользовательский сценарий {seed}"
    ratio = "16:9" if seed % 2 else "9:16"
    duration = 5 if seed % 2 else 10
    resolution = "720p" if seed % 3 else "1080p"
    per_second = 4.0 if resolution == "720p" else 6.0
    resolve_cost = AsyncMock(return_value=SimpleNamespace(credits=per_second))
    spend = AsyncMock(return_value=True)
    video_generate = AsyncMock(return_value=SimpleNamespace(task_id=f"video-task-{seed}", provider="veo"))

    async def create_generation(_session, _user_id, model, gen_type, prompt_value, credits_spent, **_kwargs):
        return _processing_generation(
            73_000 + seed,
            model=model,
            gen_type=gen_type,
            prompt=prompt_value,
            credits_spent=credits_spent,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.resolve_video_model_cost", resolve_cost)
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", AsyncMock())
    monkeypatch.setattr("api.miniapp_routes.video_service.generate_video", video_generate)

    response = await client.post(
        "/api/v1/generate/video",
        json={
            "model": "veo3_fast",
            "prompt": prompt,
            "mode": "text",
            "duration": duration,
            "aspect_ratio": ratio,
            "resolution": resolution,
        },
    )

    assert response.status_code == 202, response.text
    assert response.json()["model"] == "veo3_fast"
    assert response.json()["credits_spent"] == per_second * duration
    assert video_generate.await_args.kwargs["prompt"] == prompt
    assert video_generate.await_args.kwargs["duration"] == duration
    assert video_generate.await_args.kwargs["aspect_ratio"] == ratio
    assert video_generate.await_args.kwargs["resolution"] == resolution
    assert resolve_cost.await_args.kwargs["resolution"] == resolution


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(9))
async def test_journey_09_trends_catalog_kind_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    image_trend = _trend(seed, "image")
    video_trend = _trend(100 + seed, "video")
    monkeypatch.setattr(
        "api.trends_routes.get_prompts_by_tag",
        AsyncMock(return_value=[image_trend, video_trend]),
    )
    kind = "image" if seed % 2 else "video"

    response = await client.get(f"/api/v1/trends?kind={kind}&limit=25")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["kind"] == kind
    assert payload[0]["id"] == (image_trend.id if kind == "image" else video_trend.id)
    assert "prompt" not in payload[0]


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(10))
async def test_journey_10_upload_first_trend_run_hides_generation_settings(seed, journey_env, monkeypatch) -> None:
    client, session, user_state = journey_env
    user_state["value"] = _user(seed)
    trend = _trend(seed, "image")
    asset_url = f"https://cdn.example.test/identity-{seed}.jpg"
    asset_id = f"apixasset.integration.{seed:04d}.signature"
    idempotency_key = f"journey10-{seed:02d}-idempotency"
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    create_image = AsyncMock(
        return_value=GenerationOut(
            id=74_000 + seed,
            model="nano-banana-2",
            gen_type="image",
            prompt="",
            prompt_hidden=True,
            status="processing",
            result_url=None,
            credits_spent=2.5,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    monkeypatch.setattr("api.trends_routes.get_prompt_by_id", AsyncMock(return_value=trend))
    monkeypatch.setattr(
        "api.trends_routes.repo.get_model_cost",
        AsyncMock(return_value=SimpleNamespace(model_key="nano-banana-2", gen_type=GenerationType.image, is_active=True)),
    )
    monkeypatch.setattr(
        "api.trends_routes.verify_uploaded_asset",
        lambda _asset_id, **_kwargs: {
            "url": asset_url,
            "kind": "image",
            "filename": f"identity-{seed}.jpg",
            "content_type": "image/jpeg",
            "size": 4,
        },
    )
    monkeypatch.setattr("api.trends_routes.create_image_generation", create_image)
    monkeypatch.setattr("api.trends_routes._patch_trend_snapshot", AsyncMock())

    response = await client.post(
        f"/api/v1/trends/{trend.id}/run",
        json={"asset_id": asset_id, "idempotency_key": idempotency_key},
    )

    assert response.status_code == 202, response.text
    assert response.json()["ok"] is True
    body = create_image.await_args.kwargs["body"]
    assert body.prompt_id == trend.id
    assert body.reference_url == asset_url
    assert body.reference_urls == [asset_url]
    assert body.prompt == "Использовать скрытый трендовый промпт"
    assert create_image.await_args.kwargs["surface"] == "web"


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(11))
async def test_journey_11_settings_services_profile_backend_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, user_state = journey_env
    user_state["value"] = _user(seed)
    branch = seed % 3

    if branch == 0:
        set_language = AsyncMock()
        monkeypatch.setattr("api.miniapp_routes.repo.set_user_language", set_language)
        response = await client.post("/api/v1/settings/language", json={"language": "en"})
        assert response.status_code == 200
        assert response.json() == {"language": "en"}
        set_language.assert_awaited_once()
        assert set_language.await_args.args[1:] == (seed, "en")
    elif branch == 1:
        monkeypatch.setattr(
            "api.miniapp_routes.repo.get_all_model_costs",
            AsyncMock(
                return_value=[
                    SimpleNamespace(
                        model_key="suno/v5.5",
                        display_name="Suno 5.5",
                        credits=10 + seed,
                        gen_type=GenerationType.music,
                        is_active=True,
                    )
                ]
            ),
        )
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
        assert response.json()[0]["model"] == generation.model


@pytest.mark.parametrize("seed", SEEDS, ids=_ids(12))
async def test_journey_12_error_and_empty_state_backend_contract(seed, journey_env, monkeypatch) -> None:
    client, _session, _user_state = journey_env
    mode = seed % 5

    if mode == 0:
        monkeypatch.setattr(
            "api.miniapp_routes.repo.get_feed_generations",
            AsyncMock(side_effect=HTTPException(status_code=503, detail="feed unavailable")),
        )
        response = await client.get("/api/v1/feed?source=recent")
        assert response.status_code == 503
        assert response.json()["detail"] == "feed unavailable"
    elif mode == 1:
        monkeypatch.setattr(
            "api.trends_routes.get_prompts_by_tag",
            AsyncMock(side_effect=HTTPException(status_code=502, detail="trends unavailable")),
        )
        response = await client.get("/api/v1/trends")
        assert response.status_code == 502
        assert response.json()["detail"] == "trends unavailable"
    elif mode == 2:
        monkeypatch.setattr("api.miniapp_routes.repo.get_active_price_plans", AsyncMock(return_value=[]))
        response = await client.get("/api/v1/plans")
        assert response.status_code == 200
        assert response.json() == []
    elif mode == 3:
        monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=[]))
        response = await client.get("/api/v1/models/image")
        assert response.status_code == 200
        assert response.json() == []
    else:
        monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=[]))
        response = await client.get("/api/v1/models/video")
        assert response.status_code == 200
        assert response.json() == []
