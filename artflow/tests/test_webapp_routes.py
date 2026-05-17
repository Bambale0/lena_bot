from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from api.miniapp_auth import create_web_auth_token, get_miniapp_user
from api.miniapp_routes import _gen_out, _normalize_video_request
from db.models import GenerationStatus, GenerationType, ImageGenerationAction
from db import repository as repo
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
async def test_missing_static_upload_returns_placeholder() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/static/upload/definitely-missing-upload.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")


@pytest.mark.asyncio
async def test_webapp_me_rejects_missing_init_data_without_override() -> None:
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_webapp_me_accepts_standalone_web_auth_token(monkeypatch) -> None:
    app.dependency_overrides.clear()
    monkeypatch.setattr(
        "api.miniapp_auth.repo.get_user_by_tg_id",
        AsyncMock(return_value=SimpleNamespace(
            id=1,
            tg_id=111,
            username="tester",
            full_name="Test User",
            credits=1003,
            referral_code="REF",
            referral_balance=0.0,
            is_banned=False,
            language="ru",
        )),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/me", headers={"X-Web-Auth-Token": create_web_auth_token(111)})

    assert response.status_code == 200
    assert response.json()["credits"] == 1003


@pytest.mark.asyncio
async def test_upload_requires_auth() -> None:
    app.dependency_overrides.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/upload",
            files={"file": ("ref.png", b"\x89PNG\r\n\x1a\npayload", "image/png")},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_rejects_non_image_reference(client, monkeypatch) -> None:
    save_public_file = MagicMock()
    monkeypatch.setattr("main.save_public_file", save_public_file)

    response = await client.post(
        "/upload",
        files={"file": ("ref.txt", b"not an image", "text/plain")},
    )

    assert response.status_code == 422
    assert "JPEG, PNG and WebP" in response.json()["detail"]
    save_public_file.assert_not_called()


@pytest.mark.asyncio
async def test_upload_accepts_authenticated_image_reference(client, monkeypatch) -> None:
    save_public_file = MagicMock(return_value="https://example.test/static/upload/ref.png")
    monkeypatch.setattr("main.save_public_file", save_public_file)

    response = await client.post(
        "/upload",
        files={"file": ("ref.png", b"\x89PNG\r\n\x1a\npayload", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["url"] == "https://example.test/static/upload/ref.png"
    save_public_file.assert_called_once()


@pytest.mark.asyncio
async def test_webapp_me_returns_verified_user(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.get_active_image_session", AsyncMock(return_value=None))
    response = await client.get("/api/v1/me")
    assert response.json()["credits"] == 1003
    assert response.json()["referral_link"] == "https://t.me/TestBot?start=REF"
    assert response.json()["language"] == "ru"


@pytest.mark.asyncio
async def test_webapp_assistant_filters_history_and_appends_message(client, monkeypatch) -> None:
    generate_reply = AsyncMock(return_value="Готово, вот короткий промпт.")
    monkeypatch.setattr("api.miniapp_routes.generate_assistant_reply", generate_reply)

    response = await client.post(
        "/api/v1/assistant",
        json={
            "message": "  помоги с промптом  ",
            "history": [
                {"role": "system", "content": "ignore"},
                {"role": "assistant", "content": "Привет"},
                {"role": "user", "content": ""},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["reply"] == "Готово, вот короткий промпт."
    generate_reply.assert_awaited_once_with(
        [
            {"role": "assistant", "content": "Привет"},
            {"role": "user", "content": "помоги с промптом"},
        ],
        admin_mode=False,
    )


@pytest.mark.asyncio
async def test_webapp_assistant_rejects_blank_message(client) -> None:
    response = await client.post("/api/v1/assistant", json={"message": "   "})

    assert response.status_code == 422
    assert response.json()["detail"] == "Message cannot be empty"


@pytest.mark.asyncio
async def test_webapp_set_language_updates_common_user_record(client, monkeypatch) -> None:
    set_user_language = AsyncMock()
    monkeypatch.setattr("api.miniapp_routes.repo.set_user_language", set_user_language)

    response = await client.post("/api/v1/settings/language", json={"language": "en"})

    assert response.status_code == 200
    assert response.json() == {"language": "en"}
    set_user_language.assert_awaited_once()
    assert set_user_language.await_args.args[1:] == (1, "en")


@pytest.mark.asyncio
async def test_webapp_set_language_rejects_unknown_language(client, monkeypatch) -> None:
    set_user_language = AsyncMock()
    monkeypatch.setattr("api.miniapp_routes.repo.set_user_language", set_user_language)

    response = await client.post("/api/v1/settings/language", json={"language": "de"})

    assert response.status_code == 422
    set_user_language.assert_not_awaited()


@pytest.mark.asyncio
async def test_webapp_referrals_returns_counts_balance_children_and_withdrawals(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_referrals", AsyncMock(return_value=(2, 1, 0)))
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_user_referral_balance_snapshot",
        AsyncMock(return_value=SimpleNamespace(total_earned=1250.5, pending_withdrawals=300.0, available_to_withdraw=950.5)),
    )
    monkeypatch.setattr("api.miniapp_routes.repo.get_user_feed_remix_reward_rub", AsyncMock(return_value=42.75))
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_user_withdrawal_requests",
        AsyncMock(return_value=[
            SimpleNamespace(
                id=9,
                amount_rub=300.0,
                payout_details="SBP",
                status=SimpleNamespace(value="pending"),
                created_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
            ),
        ]),
    )

    async def fake_children(_session, _user_id, *, level: int, limit: int):
        if level != 1:
            return []
        return [
            SimpleNamespace(
                user=SimpleNamespace(id=15, username="child", full_name="Child User"),
                generations_count=4,
                paid_rub=199.0,
            ),
        ]

    monkeypatch.setattr("api.miniapp_routes.repo.get_referral_children", fake_children)

    response = await client.get("/api/v1/referrals")

    assert response.status_code == 200
    data = response.json()
    assert data["counts"] == {"l1": 2, "l2": 1, "l3": 0}
    assert data["balance"]["available_to_withdraw"] == 950.5
    assert data["feed_remix_reward_rub"] == 42.75
    assert data["children"]["l1"][0]["username"] == "child"
    assert data["withdrawals"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_webapp_referral_withdrawal_creates_request(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.settings.REFERRAL_WITHDRAW_MIN_RUB", 100.0)
    create_withdrawal = AsyncMock(return_value=SimpleNamespace(
        id=10,
        amount_rub=150.0,
        payout_details="SBP +79990000000",
        status=SimpleNamespace(value="pending"),
        created_at=datetime(2026, 5, 15, tzinfo=timezone.utc),
    ))
    monkeypatch.setattr("api.miniapp_routes.repo.create_withdrawal_request", create_withdrawal)

    response = await client.post(
        "/api/v1/referrals/withdrawals",
        json={"amount_rub": 150, "payout_details": "  SBP +79990000000  "},
    )

    assert response.status_code == 201
    assert response.json()["id"] == 10
    assert create_withdrawal.await_args.kwargs["user_id"] == 1
    assert create_withdrawal.await_args.kwargs["amount_rub"] == 150
    assert create_withdrawal.await_args.kwargs["payout_details"] == "SBP +79990000000"


@pytest.mark.asyncio
async def test_webapp_referral_withdrawal_rejects_amount_below_minimum(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.settings.REFERRAL_WITHDRAW_MIN_RUB", 100.0)
    create_withdrawal = AsyncMock()
    monkeypatch.setattr("api.miniapp_routes.repo.create_withdrawal_request", create_withdrawal)

    response = await client.post(
        "/api/v1/referrals/withdrawals",
        json={"amount_rub": 99, "payout_details": "SBP +79990000000"},
    )

    assert response.status_code == 422
    create_withdrawal.assert_not_awaited()


@pytest.mark.asyncio
async def test_webapp_referral_withdrawal_reports_available_balance(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.settings.REFERRAL_WITHDRAW_MIN_RUB", 100.0)
    monkeypatch.setattr(
        "api.miniapp_routes.repo.create_withdrawal_request",
        AsyncMock(side_effect=repo.InsufficientReferralBalanceError(75.25)),
    )

    response = await client.post(
        "/api/v1/referrals/withdrawals",
        json={"amount_rub": 150, "payout_details": "SBP +79990000000"},
    )

    assert response.status_code == 402
    assert "75.25" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webapp_me_normalizes_bot_username_for_referral_link(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.get_active_image_session", AsyncMock(return_value=None))
    monkeypatch.setattr("api.miniapp_routes.settings.BOT_USERNAME", "@TestBot")
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["referral_link"] == "https://t.me/TestBot?start=REF"


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
async def test_webapp_video_models_include_mode_options(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(
                model_key="grok-imagine/text-to-video",
                display_name="Grok T2V",
                credits=35,
            ),
        ]),
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.resolve_video_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=35)),
    )
    response = await client.get("/api/v1/models/video")
    assert response.status_code == 200
    assert response.json()[0]["mode_options"] == ["fun", "normal", "spicy"]


@pytest.mark.asyncio
async def test_webapp_image_models_allow_fractional_credits(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(
                model_key="nano-banana-2",
                display_name="Nano Banana 2",
                credits=2.5,
            ),
        ]),
    )

    response = await client.get("/api/v1/models/image")

    assert response.status_code == 200
    assert response.json()[0]["credits"] == 2.5


def test_normalize_video_request_drops_grok_i2v_ratio_for_single_ref() -> None:
    normalized = _normalize_video_request(
        model_key="grok-imagine/image-to-video",
        mode="image",
        duration=6,
        aspect_ratio="16:9",
        resolution="480p",
        image_url="https://example.test/ref-1.jpg",
        reference_urls=[],
        grok_mode="normal",
    )

    assert normalized["aspect_ratio"] is None


def test_normalize_video_request_keeps_grok_i2v_ratio_for_multi_ref() -> None:
    normalized = _normalize_video_request(
        model_key="grok-imagine/image-to-video",
        mode="image",
        duration=6,
        aspect_ratio="16:9",
        resolution="480p",
        image_url="https://example.test/ref-1.jpg",
        reference_urls=["https://example.test/ref-2.jpg"],
        grok_mode="normal",
    )

    assert normalized["aspect_ratio"] == "16:9"


def test_generation_out_includes_all_result_urls() -> None:
    gen = SimpleNamespace(
        id=55,
        model="wan/2-7-image-pro",
        gen_type=GenerationType.image,
        prompt="fashion editorial",
        status=GenerationStatus.done,
        result_url="https://example.test/1.png",
        result_urls='["https://example.test/1.png","https://example.test/2.png"]',
        credits_spent=5,
        created_at=datetime.now(timezone.utc),
        is_public_feed=False,
        is_prompt_library=False,
    )

    payload = _gen_out(gen).model_dump()

    assert payload["result_url"] == "https://example.test/1.png"
    assert payload["result_urls"] == ["https://example.test/1.png", "https://example.test/2.png"]


def test_generation_out_omits_missing_local_uploads(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("api.public_files.UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr("api.public_files.settings.STATIC_UPLOAD_URL_PATH", "/static/upload")
    gen = SimpleNamespace(
        id=56,
        model="wan/2-7-image-pro",
        gen_type=GenerationType.image,
        prompt="fashion editorial",
        status=GenerationStatus.done,
        result_url="https://example.test/static/upload/missing.jpg",
        result_urls='["https://example.test/static/upload/missing.jpg","https://cdn.test/fallback.png"]',
        credits_spent=5,
        created_at=datetime.now(timezone.utc),
        is_public_feed=False,
        is_prompt_library=False,
    )

    payload = _gen_out(gen).model_dump()

    assert payload["result_url"] == "https://cdn.test/fallback.png"
    assert payload["result_urls"] == ["https://cdn.test/fallback.png"]


@pytest.mark.asyncio
async def test_webapp_public_models_is_public(monkeypatch) -> None:
    app.dependency_overrides.clear()
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(model_key="seedream/4.5-text-to-image", display_name="🌸 Seedream 4.5", credits=3),
            SimpleNamespace(model_key="seedream/4.5-text-to-image__quality=high", display_name="🌸 Seedream 4.5 · 4K", credits=4),
            SimpleNamespace(model_key="kling-3.0/video", display_name="⚡ Kling 3.0", credits=40),
            SimpleNamespace(model_key="suno/v4.5", display_name="🎵 Suno v4.5", credits=20, gen_type=GenerationType.music),
        ]),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous_client:
        response = await anonymous_client.get("/api/v1/public/models")
    assert response.status_code == 200
    assert response.json()["image"] == ["Seedream 4.5"]
    assert response.json()["video"] == ["Kling 3.0"]
    assert response.json()["music"] == ["Suno v4.5"]


@pytest.mark.asyncio
async def test_public_midjourney_catalog_returns_active_models(monkeypatch) -> None:
    app.dependency_overrides.clear()
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(model_key="midjourney-imagine", display_name="MJ Imagine", credits=10, is_active=True),
            SimpleNamespace(model_key="midjourney-video", display_name="MJ Video", credits=15, is_active=True),
            SimpleNamespace(model_key="midjourney-blend", display_name="MJ Blend", credits=12, is_active=False),
            SimpleNamespace(model_key="nano-banana-pro", display_name="Nano Banana Pro", credits=5, is_active=True),
        ]),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous_client:
        response = await anonymous_client.get("/api/v1/public/midjourney")

    assert response.status_code == 200
    payload = {item["key"]: item for item in response.json()}
    assert set(payload) == {"midjourney-imagine", "midjourney-video"}
    assert payload["midjourney-imagine"]["available_in_studio"] is True
    assert payload["midjourney-video"]["available_in_studio"] is True


@pytest.mark.asyncio
async def test_webapp_models_include_midjourney_for_regular_user(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(model_key="midjourney-imagine", display_name="MJ Imagine", credits=10, is_active=True),
            SimpleNamespace(model_key="midjourney-video", display_name="MJ Video", credits=15, is_active=True),
        ]),
    )

    image_response = await client.get("/api/v1/models/image")
    video_response = await client.get("/api/v1/models/video")

    assert image_response.status_code == 200
    assert video_response.status_code == 200
    assert {item["key"] for item in image_response.json()} == {"midjourney-imagine"}
    assert {item["key"] for item in video_response.json()} == {"midjourney-video"}


@pytest.mark.asyncio
async def test_webapp_plans_use_label_as_title(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_active_price_plans",
        AsyncMock(return_value=[
            SimpleNamespace(key="credits_100", label="100 💋", credits=100, price_rub=199.0),
        ]),
    )
    response = await client.get("/api/v1/plans")
    assert response.status_code == 200
    assert response.json()[0]["title"] == "100 💋"
    assert response.json()[0]["label"] == "100 💋"
    assert response.json()[0]["price_rub_display"] == "199₽"
    assert response.json()[0]["price_stars"] == 19
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"


@pytest.mark.asyncio
async def test_topup_stars_returns_invoice_link(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.settings.TELEGRAM_STARS_ENABLED", True)
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_price_plan_by_key",
        AsyncMock(return_value=SimpleNamespace(key="credits_15", label="мини", credits=15, price_rub=150.0, price_stars=100)),
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_transaction_by_external_id",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.create_transaction",
        AsyncMock(return_value=SimpleNamespace(id=901)),
    )
    monkeypatch.setattr(
        "main.bot",
        SimpleNamespace(create_invoice_link=AsyncMock(return_value="https://t.me/invoice/test-stars-link")),
    )

    response = await client.post("/api/v1/topup/stars", json={"plan_key": "credits_15"})

    assert response.status_code == 200
    assert response.json()["invoice_link"] == "https://t.me/invoice/test-stars-link"
    assert response.json()["amount_stars"] == 100


@pytest.mark.asyncio
async def test_webapp_prompt_use_marks_prompt_usage(client, monkeypatch) -> None:
    prompt = SimpleNamespace(
        id=7,
        title="Glossy card",
        description="make it glossy",
        category=SimpleNamespace(value="photo"),
        tags=["photo"],
        uses_count=3,
        likes=2,
        status=None,
        is_public=True,
        prompt_text="make it glossy",
        model=None,
        preview_url=None,
        author_id=2,
        reject_reason=None,
        ai_moderation_decision=None,
        ai_moderation_risk=None,
        ai_moderation_reason=None,
        ai_moderation_recommendation=None,
        ai_moderated_at=None,
        created_at=datetime.now(timezone.utc),
    )
    from db.models import PromptStatus

    prompt.status = PromptStatus.approved
    use_prompt = AsyncMock(return_value=(prompt, {"author": 0, "l2": 0, "l3": 0}))
    monkeypatch.setattr("db.prompt_repository.use_prompt", use_prompt)

    response = await client.post("/api/v1/prompts/7/use")

    assert response.status_code == 200
    assert response.json()["prompt"]["id"] == 7
    use_prompt.assert_awaited_once()
    assert use_prompt.await_args.args[1:] == (7, 1)


@pytest.mark.asyncio
async def test_webapp_remove_generation_from_library(client, monkeypatch) -> None:
    remove_from_library = AsyncMock(return_value=SimpleNamespace(id=77, is_prompt_library=False))
    monkeypatch.setattr("api.miniapp_routes.repo.remove_from_library", remove_from_library)

    response = await client.post("/api/v1/generations/77/remove-library")

    assert response.status_code == 200
    assert response.json() == {"id": 77, "is_prompt_library": False}
    remove_from_library.assert_awaited_once()
    assert remove_from_library.await_args.args[1:] == (77, 1)


@pytest.mark.asyncio
async def test_webapp_remove_missing_generation_from_library_returns_404(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.remove_from_library", AsyncMock(return_value=None))

    response = await client.post("/api/v1/generations/77/remove-library")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_generate_image_rejects_invalid_reference_without_spending_credits(client, monkeypatch) -> None:
    spend_credits = AsyncMock(return_value=True)
    monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend_credits)

    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "nano-banana-pro",
            "prompt": "cat portrait",
            "reference_url": "blob:test-ref",
        },
    )

    assert response.status_code == 422
    spend_credits.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_image_passes_multiple_reference_urls(client, monkeypatch) -> None:
    create_image_session = AsyncMock(return_value=SimpleNamespace(id=77))
    update_generation_task = AsyncMock()
    update_image_session_last_prompt = AsyncMock()
    spend_credits = AsyncMock(return_value=True)
    image_generate = AsyncMock(return_value=SimpleNamespace(task_id="img_task_1"))

    async def fake_create_generation(*args, **kwargs):
        return SimpleNamespace(
            id=501,
            model="nano-banana-pro",
            gen_type=GenerationType.image,
            prompt="cat portrait",
            status=GenerationStatus.processing,
            result_url=None,
            credits_spent=4,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend_credits)
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", create_image_session)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.repo.update_image_session_last_prompt", update_image_session_last_prompt)
    monkeypatch.setattr("api.miniapp_routes.image_service.generate_image", image_generate)

    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "nano-banana-pro",
            "prompt": "cat portrait",
            "reference_urls": [
                "https://example.test/ref-1.jpg",
                "https://example.test/ref-2.jpg",
            ],
        },
    )

    assert response.status_code == 202
    create_image_session.assert_awaited_once()
    assert create_image_session.await_args.kwargs["mode"] == "image"
    assert create_image_session.await_args.kwargs["reference_url"] == "https://example.test/ref-1.jpg"
    assert image_generate.await_args.kwargs["image_url"] == [
        "https://example.test/ref-1.jpg",
        "https://example.test/ref-2.jpg",
    ]


@pytest.mark.asyncio
async def test_generate_image_from_prompt_library_uses_saved_prompt_and_rewards(client, monkeypatch) -> None:
    from db.models import PromptCategory, PromptStatus

    prompt = SimpleNamespace(
        id=44,
        title="Library prompt",
        description="",
        category=PromptCategory.photo,
        tags=[],
        uses_count=0,
        likes=0,
        status=PromptStatus.approved,
        is_public=True,
        prompt_text="library prompt text",
        model=None,
        preview_url=None,
        author_id=2,
        reject_reason=None,
        ai_moderation_decision=None,
        ai_moderation_risk=None,
        ai_moderation_reason=None,
        ai_moderation_recommendation=None,
        ai_moderated_at=None,
        created_at=datetime.now(timezone.utc),
    )
    use_prompt = AsyncMock(return_value=(prompt, {"author": 1, "l2": 0, "l3": 0}))
    image_generate = AsyncMock(return_value=SimpleNamespace(task_id="img_task_prompt"))

    async def fake_create_generation(_session, _user_id, model, gen_type, prompt_text, credits_spent, **_kwargs):
        assert prompt_text == "library prompt text"
        return SimpleNamespace(
            id=503,
            model=model,
            gen_type=gen_type,
            prompt=prompt_text,
            status=GenerationStatus.processing,
            result_url=None,
            credits_spent=credits_spent,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
        )

    monkeypatch.setattr("db.prompt_repository.get_prompt_by_id", AsyncMock(return_value=prompt))
    monkeypatch.setattr("db.prompt_repository.use_prompt", use_prompt)
    monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", AsyncMock(return_value=SimpleNamespace(id=79)))
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", AsyncMock())
    monkeypatch.setattr("api.miniapp_routes.repo.update_image_session_last_prompt", AsyncMock())
    monkeypatch.setattr("api.miniapp_routes.image_service.generate_image", image_generate)

    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "nano-banana-pro",
            "prompt": "user-visible prompt",
            "prompt_id": 44,
        },
    )

    assert response.status_code == 202
    assert response.json()["prompt"] == "library prompt text"
    assert image_generate.await_args.args[1] == "library prompt text"
    use_prompt.assert_awaited_once()
    assert use_prompt.await_args.args[1:] == (44, 1)
    assert use_prompt.await_args.kwargs["credits_spent"] == 4


@pytest.mark.asyncio
async def test_generate_image_normalizes_square_4k_before_pricing(client, monkeypatch) -> None:
    resolve_image_model_cost = AsyncMock(return_value=SimpleNamespace(credits=4))
    create_image_session = AsyncMock(return_value=SimpleNamespace(id=78))
    update_generation_task = AsyncMock()
    update_image_session_last_prompt = AsyncMock()
    image_generate = AsyncMock(return_value=SimpleNamespace(task_id="img_task_square"))

    async def fake_create_generation(*args, **kwargs):
        return SimpleNamespace(
            id=502,
            model="nano-banana-pro",
            gen_type=GenerationType.image,
            prompt="cat portrait",
            status=GenerationStatus.processing,
            result_url=None,
            credits_spent=4,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", resolve_image_model_cost)
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", create_image_session)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.repo.update_image_session_last_prompt", update_image_session_last_prompt)
    monkeypatch.setattr("api.miniapp_routes.image_service.generate_image", image_generate)

    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "nano-banana-pro",
            "prompt": "cat portrait",
            "aspect_ratio": "1:1",
            "quality": "4K",
        },
    )

    assert response.status_code == 202
    assert resolve_image_model_cost.await_args.kwargs["quality"] == "2K"
    assert create_image_session.await_args.kwargs["quality"] == "2K"
    assert image_generate.await_args.kwargs["quality"] == "2K"


@pytest.mark.asyncio
async def test_generate_image_rejects_too_many_refs_for_single_ref_model(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))

    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "qwen/image-edit",
            "prompt": "edit this",
            "reference_urls": [
                "https://example.test/ref-1.jpg",
                "https://example.test/ref-2.jpg",
            ],
        },
    )

    assert response.status_code == 422
    assert "at most 1 reference" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_midjourney_image_available_to_regular_user(client, monkeypatch) -> None:
    update_generation_task = AsyncMock()
    update_image_session_last_prompt = AsyncMock()
    imagine = AsyncMock(return_value="mj_task_1")

    async def fake_create_generation(*args, **kwargs):
        return SimpleNamespace(
            id=504,
            model="midjourney-imagine",
            gen_type=GenerationType.image,
            prompt="cat portrait",
            status=GenerationStatus.processing,
            result_url=None,
            result_urls=None,
            credits_spent=10,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=10, is_active=True)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", AsyncMock(return_value=SimpleNamespace(id=80)))
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.repo.update_image_session_last_prompt", update_image_session_last_prompt)
    monkeypatch.setattr("api.miniapp_routes.midjourney_service.imagine", imagine)

    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "midjourney-imagine",
            "prompt": "cat portrait",
            "aspect_ratio": "9:16",
        },
    )

    assert response.status_code == 202
    assert response.json()["model"] == "midjourney-imagine"
    imagine.assert_awaited_once_with("cat portrait", reference_url=None)
    update_generation_task.assert_awaited_once()
    update_image_session_last_prompt.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_image_rejects_missing_reference_for_image_only_model(client, monkeypatch) -> None:
    response = await client.post(
        "/api/v1/generate/image",
        json={
            "model": "qwen/image-edit",
            "prompt": "edit this",
        },
    )

    assert response.status_code == 422
    assert "requires at least one reference image" in response.json()["detail"]


@pytest.mark.asyncio
async def test_image_models_include_max_refs_and_single_count_for_nano_banana_2(client, monkeypatch) -> None:
    model_costs = [SimpleNamespace(model_key="nano-banana-2", display_name="Nano Banana 2", credits=4)]
    monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=model_costs))

    response = await client.get("/api/v1/models/image")

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["counts"] == [1]
    assert payload["max_refs"] == 8


@pytest.mark.asyncio
async def test_image_models_include_updated_wan_reference_limit(client, monkeypatch) -> None:
    model_costs = [SimpleNamespace(model_key="wan/2-7-image-pro", display_name="WAN 2.7 Pro", credits=4)]
    monkeypatch.setattr("api.miniapp_routes.repo.get_all_model_costs", AsyncMock(return_value=model_costs))

    response = await client.get("/api/v1/models/image")

    assert response.status_code == 200
    payload = response.json()[0]
    assert payload["max_refs"] == 9


async def test_generate_video_uses_total_duration_cost(client, monkeypatch) -> None:
    spend_credits = AsyncMock(return_value=True)
    update_generation_task = AsyncMock()
    video_generate = AsyncMock(return_value=SimpleNamespace(task_id="vid_task_1", provider="kieai"))

    async def fake_create_generation(_session, _user_id, model, gen_type, prompt, credits_spent, **_kwargs):
        return SimpleNamespace(
            id=601,
            model=model,
            gen_type=gen_type,
            prompt=prompt,
            status=GenerationStatus.processing,
            result_url=None,
            credits_spent=credits_spent,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.resolve_video_model_cost", AsyncMock(return_value=SimpleNamespace(credits=8)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend_credits)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.video_service.generate_video", video_generate)

    response = await client.post(
        "/api/v1/generate/video",
        json={
            "model": "kling-3.0/video",
            "prompt": "rainy city",
            "mode": "text",
            "duration": 5,
            "resolution": "2K",
        },
    )

    assert response.status_code == 202
    assert spend_credits.await_count == 1
    assert spend_credits.await_args.args[1:] == (1, 40)
    assert response.json()["credits_spent"] == 40


@pytest.mark.asyncio
async def test_generate_video_grok_uses_per_second_cost(client, monkeypatch) -> None:
    spend_credits = AsyncMock(return_value=True)
    update_generation_task = AsyncMock()
    video_generate = AsyncMock(return_value=SimpleNamespace(task_id="vid_task_grok", provider="kieai"))

    async def fake_create_generation(_session, _user_id, model, gen_type, prompt, credits_spent, **_kwargs):
        return SimpleNamespace(
            id=602,
            model=model,
            gen_type=gen_type,
            prompt=prompt,
            status=GenerationStatus.processing,
            result_url=None,
            credits_spent=credits_spent,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.resolve_video_model_cost", AsyncMock(return_value=SimpleNamespace(credits=35)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend_credits)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.video_service.generate_video", video_generate)

    response = await client.post(
        "/api/v1/generate/video",
        json={
            "model": "grok-imagine/text-to-video",
            "prompt": "rainy city",
            "mode": "text",
            "duration": 6,
            "resolution": "480p",
        },
    )

    assert response.status_code == 202
    assert spend_credits.await_count == 1
    assert spend_credits.await_args.args[1:] == (1, 210)
    assert response.json()["credits_spent"] == 210


@pytest.mark.asyncio
async def test_generate_video_rejects_invalid_image_without_spending_credits(client, monkeypatch) -> None:
    spend_credits = AsyncMock(return_value=True)
    monkeypatch.setattr("api.miniapp_routes.repo.resolve_video_model_cost", AsyncMock(return_value=SimpleNamespace(credits=8)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend_credits)

    response = await client.post(
        "/api/v1/generate/video",
        json={
            "model": "kling-3.0/video",
            "prompt": "rainy city",
            "mode": "image",
            "duration": 5,
            "image_url": "blob:test-image",
        },
    )

    assert response.status_code == 422
    spend_credits.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_video_rejects_unsupported_duration_without_spending_credits(client, monkeypatch) -> None:
    spend_credits = AsyncMock(return_value=True)
    resolve_video_model_cost = AsyncMock(return_value=SimpleNamespace(credits=8))
    monkeypatch.setattr("api.miniapp_routes.repo.resolve_video_model_cost", resolve_video_model_cost)
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend_credits)

    response = await client.post(
        "/api/v1/generate/video",
        json={
            "model": "grok-imagine/text-to-video",
            "prompt": "rainy city",
            "mode": "text",
            "duration": 5,
            "resolution": "480p",
        },
    )

    assert response.status_code == 422
    resolve_video_model_cost.assert_not_awaited()
    spend_credits.assert_not_awaited()


@pytest.mark.asyncio
async def test_feed_remix_image_uses_and_saves_reference(client, monkeypatch) -> None:
    source = SimpleNamespace(
        id=88,
        model="seedream-4.0",
        prompt="hidden prompt",
        result_url="https://example.test/source.jpg",
    )
    create_image_session = AsyncMock(return_value=SimpleNamespace(id=77))
    update_generation_task = AsyncMock()
    increment_feed_share = AsyncMock()
    image_generate = AsyncMock(return_value=SimpleNamespace(task_id="img_task_2"))

    async def fake_create_generation(_session, _user_id, model, gen_type, prompt, credits_spent, **kwargs):
        assert kwargs["image_session_id"] == 77
        assert kwargs["parent_generation_id"] == 88
        assert kwargs["action_type"] == ImageGenerationAction.remix
        return SimpleNamespace(
            id=701,
            model=model,
            gen_type=gen_type,
            prompt=prompt,
            status=GenerationStatus.processing,
            result_url=None,
            credits_spent=credits_spent,
            created_at=datetime.now(timezone.utc),
            is_public_feed=False,
            is_prompt_library=False,
        )

    monkeypatch.setattr("api.miniapp_routes.repo.get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr("api.miniapp_routes.repo.resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=4)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", create_image_session)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.repo.increment_feed_share", increment_feed_share)
    monkeypatch.setattr("api.miniapp_routes.image_service.generate_image", image_generate)

    response = await client.post(
        "/api/v1/feed/88/remix",
        json={
            "model": "nano-banana-pro",
            "mode": "image",
            "aspect_ratio": "1:1",
            "quality": "basic",
            "count": 2,
        },
    )

    assert response.status_code == 202
    create_image_session.assert_awaited_once()
    assert create_image_session.await_args.kwargs["mode"] == "image"
    assert create_image_session.await_args.kwargs["reference_url"] == "https://example.test/source.jpg"
    assert create_image_session.await_args.kwargs["base_prompt"] == "hidden prompt"
    assert image_generate.await_args.kwargs["image_url"] == "https://example.test/source.jpg"
    assert image_generate.await_args.kwargs["n"] == 2


@pytest.mark.asyncio
async def test_feed_remix_midjourney_imagine_uses_hidden_prompt_and_source_ref(client, monkeypatch) -> None:
    source = SimpleNamespace(
        id=89,
        model="midjourney-imagine",
        prompt="hidden mj prompt",
        result_url="https://example.test/source-mj.jpg",
    )
    create_image_session = AsyncMock(return_value=SimpleNamespace(id=78))
    update_generation_task = AsyncMock()
    increment_feed_share = AsyncMock()
    imagine = AsyncMock(return_value="mj_remix_task")

    async def fake_create_generation(_session, _user_id, model, gen_type, prompt, credits_spent, **kwargs):
        assert kwargs["image_session_id"] == 78
        assert kwargs["parent_generation_id"] == 89
        assert kwargs["action_type"] == ImageGenerationAction.remix
        assert kwargs["source_feed_gen_id"] == 89
        return SimpleNamespace(
            id=702,
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
        )

    monkeypatch.setattr("api.miniapp_routes.repo.get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr("api.miniapp_routes.repo.get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=10, is_active=True)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", create_image_session)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.repo.increment_feed_share", increment_feed_share)
    monkeypatch.setattr("api.miniapp_routes.midjourney_service.imagine", imagine)

    response = await client.post(
        "/api/v1/feed/89/remix",
        json={
            "model": "midjourney-imagine",
            "mode": "image",
            "aspect_ratio": "9:16",
        },
    )

    assert response.status_code == 202
    assert response.json()["model"] == "midjourney-imagine"
    assert create_image_session.await_args.kwargs["reference_url"] == "https://example.test/source-mj.jpg"
    assert create_image_session.await_args.kwargs["base_prompt"] == "hidden mj prompt"
    imagine.assert_awaited_once_with(
        "https://example.test/source-mj.jpg hidden mj prompt",
        reference_url="https://example.test/source-mj.jpg",
    )
    assert update_generation_task.await_args.args[1:] == (702, "mj_remix_task")
    increment_feed_share.assert_awaited_once()


@pytest.mark.asyncio
async def test_feed_remix_midjourney_blend_requires_refs_before_spending(client, monkeypatch) -> None:
    source = SimpleNamespace(
        id=90,
        model="midjourney-imagine",
        prompt="hidden blend prompt",
        result_url="https://example.test/source-blend.jpg",
    )
    spend_credits = AsyncMock(return_value=True)

    monkeypatch.setattr("api.miniapp_routes.repo.get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr("api.miniapp_routes.repo.get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=12, is_active=True)))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", spend_credits)

    response = await client.post(
        "/api/v1/feed/90/remix",
        json={
            "model": "midjourney-blend",
            "mode": "text",
        },
    )

    assert response.status_code == 422
    assert "Blend requires at least 2 reference images" in response.json()["detail"]
    spend_credits.assert_not_awaited()


@pytest.mark.asyncio
async def test_feed_remix_midjourney_blend_uses_source_ref_and_reference_urls(client, monkeypatch) -> None:
    source = SimpleNamespace(
        id=91,
        model="midjourney-imagine",
        prompt="hidden blend prompt",
        result_url="https://example.test/source-blend.jpg",
    )
    create_image_session = AsyncMock(return_value=SimpleNamespace(id=79))
    update_generation_task = AsyncMock()
    increment_feed_share = AsyncMock()
    data_uri_from_url = AsyncMock(side_effect=["data:image/jpeg;base64,source", "data:image/jpeg;base64,extra"])
    blend = AsyncMock(return_value="mj_blend_task")

    async def fake_create_generation(_session, _user_id, model, gen_type, prompt, credits_spent, **kwargs):
        assert kwargs["image_session_id"] == 79
        assert kwargs["parent_generation_id"] == 91
        assert kwargs["action_type"] == ImageGenerationAction.remix
        assert kwargs["source_feed_gen_id"] == 91
        return SimpleNamespace(
            id=703,
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
        )

    monkeypatch.setattr("api.miniapp_routes.repo.get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr("api.miniapp_routes.repo.get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=12, is_active=True)))
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
    monkeypatch.setattr("api.miniapp_routes.repo.create_image_session", create_image_session)
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", fake_create_generation)
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", update_generation_task)
    monkeypatch.setattr("api.miniapp_routes.repo.increment_feed_share", increment_feed_share)
    monkeypatch.setattr("api.miniapp_routes._data_uri_from_url", data_uri_from_url)
    monkeypatch.setattr("api.miniapp_routes.midjourney_service.blend", blend)

    response = await client.post(
        "/api/v1/feed/91/remix",
        json={
            "model": "midjourney-blend",
            "mode": "image",
            "aspect_ratio": "2:3",
            "reference_urls": ["https://example.test/extra.jpg"],
        },
    )

    assert response.status_code == 202
    assert response.json()["model"] == "midjourney-blend"
    assert create_image_session.await_args.kwargs["reference_url"] == "https://example.test/source-blend.jpg"
    assert data_uri_from_url.await_args_list[0].args == ("https://example.test/source-blend.jpg",)
    assert data_uri_from_url.await_args_list[1].args == ("https://example.test/extra.jpg",)
    blend.assert_awaited_once()
    assert blend.await_args.args[0] == ["data:image/jpeg;base64,source", "data:image/jpeg;base64,extra"]
    assert blend.await_args.kwargs["dimensions"].value == "PORTRAIT"
    update_generation_task.assert_awaited_once()
    increment_feed_share.assert_awaited_once()



@pytest.mark.asyncio
async def test_webapp_image_models_expose_single_ref_caps_and_no_false_count(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(model_key="qwen/image-edit", display_name="Qwen Edit", credits=7),
            SimpleNamespace(model_key="grok-imagine/image-to-image", display_name="Grok I2I", credits=9),
            SimpleNamespace(model_key="gpt-image-2-image-to-image", display_name="GPT Image 2 Edit", credits=8),
            SimpleNamespace(model_key="nano-banana-pro", display_name="Nano Banana Pro", credits=11),
        ]),
    )

    response = await client.get("/api/v1/models/image")

    assert response.status_code == 200
    payload = {item["key"]: item for item in response.json()}
    assert payload["qwen/image-edit"]["counts"] == [1]
    assert payload["qwen/image-edit"]["aspect_ratios"] == []
    assert payload["grok-imagine/image-to-image"]["counts"] == [1]
    assert payload["grok-imagine/image-to-image"]["aspect_ratios"] == []
    assert payload["gpt-image-2-image-to-image"]["aspect_ratios"] == ["1:1", "9:16", "16:9", "4:3", "3:4"]
    assert payload["nano-banana-pro"]["counts"] == [1]
    assert payload["nano-banana-pro"]["quality_options"] == [
        {"value": "2K", "label": "2K"},
        {"value": "4K", "label": "4K"},
    ]


@pytest.mark.asyncio
async def test_webapp_video_models_expose_kling_caps_and_per_second_pricing(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(model_key="kling-3.0/video", display_name="Kling 3.0 Video", credits=8),
            SimpleNamespace(model_key="kling-3.0/motion-control", display_name="Kling 3.0 Motion", credits=6),
        ]),
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.resolve_video_model_cost",
        AsyncMock(side_effect=[SimpleNamespace(credits=8), SimpleNamespace(credits=6)]),
    )

    response = await client.get("/api/v1/models/video")

    assert response.status_code == 200
    payload = {item["key"]: item for item in response.json()}
    assert payload["kling-3.0/video"]["is_per_second"] is True
    assert payload["kling-3.0/video"]["credits"] == 8
    assert payload["kling-3.0/video"]["credits_per_sec"] == 8
    assert payload["kling-3.0/video"]["durations"] == [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    assert payload["kling-3.0/video"]["resolutions"] == ["std", "pro", "4K"]
    assert payload["kling-3.0/motion-control"]["modes"] == ["motion"]
    assert payload["kling-3.0/motion-control"]["is_per_second"] is True
    assert payload["kling-3.0/motion-control"]["resolutions"] == ["720p", "1080p"]
    assert payload["kling-3.0/motion-control"]["quality_options"] == [
        {"value": "720p", "label": "720p"},
        {"value": "1080p", "label": "1080p"},
    ]


def test_normalize_video_request_maps_legacy_kling_30_motion_aliases() -> None:
    normalized = _normalize_video_request(
        model_key="kling-3.0/motion-control",
        mode="motion",
        duration=5,
        aspect_ratio=None,
        resolution="pro",
        image_url="https://example.test/ref-1.jpg",
        reference_urls=["https://example.test/ref-2.mp4"],
        grok_mode="normal",
    )

    assert normalized["resolution"] == "1080p"


@pytest.mark.asyncio
async def test_webapp_video_models_expose_grok_as_per_second(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(model_key="grok-imagine/text-to-video", display_name="Grok T2V", credits=35),
        ]),
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.resolve_video_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=35)),
    )

    response = await client.get("/api/v1/models/video")

    assert response.status_code == 200
    payload = {item["key"]: item for item in response.json()}
    assert payload["grok-imagine/text-to-video"]["is_per_second"] is True
    assert payload["grok-imagine/text-to-video"]["credits"] == 35
    assert payload["grok-imagine/text-to-video"]["credits_per_sec"] == 35


@pytest.mark.asyncio
async def test_webapp_video_models_expose_grok_i2v_ratio_min_refs(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_all_model_costs",
        AsyncMock(return_value=[
            SimpleNamespace(model_key="grok-imagine/image-to-video", display_name="Grok I2V", credits=35),
        ]),
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.resolve_video_model_cost",
        AsyncMock(return_value=SimpleNamespace(credits=35)),
    )

    response = await client.get("/api/v1/models/video")

    assert response.status_code == 200
    payload = {item["key"]: item for item in response.json()}
    assert payload["grok-imagine/image-to-video"]["aspect_ratio_min_refs"] == 2


@pytest.mark.asyncio
async def test_music_generation_uses_model_cost_from_db(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_model_cost",
        AsyncMock(return_value=SimpleNamespace(model_key="suno/v4.5", credits=37.0, is_active=True)),
    )
    monkeypatch.setattr("api.miniapp_routes.repo.count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr("api.miniapp_routes.repo.spend_credits", AsyncMock(return_value=True))
    gen = SimpleNamespace(
        id=77,
        model="suno/v4.5",
        gen_type=GenerationType.music,
        prompt="lofi",
        status=GenerationStatus.pending,
        result_url=None,
        credits_spent=37.0,
        created_at=datetime.now(timezone.utc),
        is_public_feed=False,
        is_prompt_library=False,
    )
    monkeypatch.setattr("api.miniapp_routes.repo.create_generation", AsyncMock(return_value=gen))
    monkeypatch.setattr("api.miniapp_routes.repo.update_generation_task", AsyncMock(return_value=None))
    monkeypatch.setattr("api.music_service.create_music_task", AsyncMock(return_value="task-1"))
    monkeypatch.setattr("api.music_service.register_miniapp_task", lambda *args, **kwargs: None)

    response = await client.post("/api/v1/generate/music", json={"prompt": "lofi", "instrumental": True})

    assert response.status_code == 202
    assert response.json()["credits_spent"] == 37


@pytest.mark.asyncio
async def test_topup_stars_reuses_pending_transaction(client, monkeypatch) -> None:
    monkeypatch.setattr("api.miniapp_routes.settings.TELEGRAM_STARS_ENABLED", True)
    pending_tx = SimpleNamespace(
        id=902,
        user_id=1,
        provider="telegram_stars",
        status="pending",
    )
    pending_tx.provider = __import__("db.models", fromlist=["PaymentProvider"]).PaymentProvider.telegram_stars
    pending_tx.status = __import__("db.models", fromlist=["TransactionStatus"]).TransactionStatus.pending

    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_price_plan_by_key",
        AsyncMock(return_value=SimpleNamespace(key="credits_15", label="мини", credits=15, price_rub=150.0, price_stars=100)),
    )
    monkeypatch.setattr(
        "api.miniapp_routes.repo.get_transaction_by_external_id",
        AsyncMock(return_value=pending_tx),
    )
    create_transaction = AsyncMock()
    monkeypatch.setattr("api.miniapp_routes.repo.create_transaction", create_transaction)
    monkeypatch.setattr(
        "main.bot",
        SimpleNamespace(create_invoice_link=AsyncMock(return_value="https://t.me/invoice/test-stars-link-2")),
    )

    response = await client.post("/api/v1/topup/stars", json={"plan_key": "credits_15"})

    assert response.status_code == 200
    assert response.json()["transaction_id"] == 902
    create_transaction.assert_not_awaited()


@pytest.mark.asyncio
async def test_prompt_improve_music_uses_music_template(client) -> None:
    response = await client.post("/api/v1/prompt/improve", json={"kind": "music", "prompt": "lofi rain"})

    assert response.status_code == 200
    improved = response.json()["prompt"]
    assert "Original music track" in improved
    assert "Premium detailed image" not in improved
