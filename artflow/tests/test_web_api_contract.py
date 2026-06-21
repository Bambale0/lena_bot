from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response

from api.miniapp_routes import (
    AssistantChatRequest,
    FeedRemixRequest,
    GenerationOut,
    ImageGenRequest,
    is_web_task_id,
    provider_task_id,
    task_id_for_surface,
)
from api.web import admin, assistant, auth, billing, generations, health, landing, referrals
from api.web import router as web_router
from api.web.schemas import FeedCard, ModelCostCard, TransactionCard, UserMe
from db.models import GenerationType, PaymentProvider, TransactionStatus


@pytest.mark.asyncio
async def test_health_payload_has_service_status() -> None:
    payload = await health.health()

    assert payload == {"ok": True, "data": {"service": "api-web", "status": "ok"}}


def test_web_router_includes_admin_routes() -> None:
    paths = {getattr(route, "path", "") for route in web_router.routes}

    assert "/admin/overview" in paths
    assert "/admin/users/{user_id}/credits" in paths
    assert "/admin/generations/{generation_id}/fail" in paths


@pytest.mark.asyncio
async def test_web_admin_overview_requires_admin(monkeypatch) -> None:
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [42], raising=False)

    anonymous = await admin.admin_overview(session=object(), user=None)
    regular = await admin.admin_overview(session=object(), user=SimpleNamespace(tg_id=7))

    assert anonymous.status_code == 401
    assert regular.status_code == 403


@pytest.mark.asyncio
async def test_web_admin_overview_returns_payload_for_admin(monkeypatch) -> None:
    payload = {"totals": {"users": 1}}
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [42], raising=False)
    monkeypatch.setattr(admin, "_admin_overview_payload", AsyncMock(return_value=payload))

    response = await admin.admin_overview(session=object(), user=SimpleNamespace(tg_id=42))

    assert response == {"ok": True, "data": payload}


@pytest.mark.asyncio
async def test_web_admin_credit_adjustment_records_admin_source(monkeypatch) -> None:
    session = object()
    add_credits = AsyncMock(return_value=15)
    monkeypatch.setattr(admin.settings, "ADMIN_IDS", [42], raising=False)
    monkeypatch.setattr(admin.repo, "get_user_by_id", AsyncMock(return_value=SimpleNamespace(id=7, credits=5)))
    monkeypatch.setattr(admin.repo, "add_credits", add_credits)

    response = await admin.admin_adjust_user_credits(
        7,
        admin.AdminCreditAdjustmentRequest(amount=10, note="manual bonus"),
        session=session,
        user=SimpleNamespace(tg_id=42),
    )

    assert response["ok"] is True
    assert response["data"] == {"user_id": 7, "balance": 15.0, "delta": 10.0}
    add_credits.assert_awaited_once()
    assert add_credits.await_args.args[:3] == (session, 7, 10.0)
    assert add_credits.await_args.kwargs["entry_type"] == "admin_adjustment"
    assert add_credits.await_args.kwargs["source_type"] == "admin"
    assert add_credits.await_args.kwargs["source_id"] == "42"
    assert add_credits.await_args.kwargs["note"] == "manual bonus"


def test_model_card_exposes_technical_key_and_capabilities() -> None:
    card = ModelCostCard.from_model_cost(
        SimpleNamespace(
            model_key="nano-banana-pro",
            display_name="Nano Banana Pro",
            gen_type=GenerationType.image,
            credits=4,
            is_active=True,
        )
    )

    assert card.technical_key == "nano-banana-pro"
    assert card.capabilities == ["text", "image"]


def test_feed_card_exposes_result_urls_and_action_eligibility() -> None:
    generation = SimpleNamespace(
        id=42,
        result_url="https://cdn.test/primary.png",
        result_urls='["https://cdn.test/primary.png","https://cdn.test/alt.png"]',
        prompt="portrait",
        model="nano-banana-pro",
        gen_type=GenerationType.image,
        likes_count=2,
        shares_count=3,
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    card = FeedCard.from_feed_card(
        SimpleNamespace(
            generation=generation,
            username="artist",
            full_name=None,
            remix_count=5,
            aspect_ratio="9:16",
            quality="pro",
        )
    )

    assert card.type == "image"
    assert card.result_urls == ["https://cdn.test/primary.png", "https://cdn.test/alt.png"]
    assert card.can_remix is True
    assert card.can_use_reference is True


def test_transaction_card_serializes_enums() -> None:
    card = TransactionCard.from_transaction(
        SimpleNamespace(
            id=7,
            amount_rub=990,
            credits=100,
            provider=PaymentProvider.tbank,
            status=TransactionStatus.pending,
            external_id="pay_1",
            created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        )
    )

    assert card.provider == "tbank"
    assert card.status == "pending"


def test_user_me_includes_sync_fields() -> None:
    card = UserMe.from_user(
        SimpleNamespace(
            id=1,
            tg_id=123,
            username="creator",
            full_name="Creator",
            credits=15,
            referral_code="abc",
            language="ru",
            created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        ),
        admin_ids=[123],
        referral_link="https://t.me/APIXBot?start=abc",
    )

    assert card.referral_link.endswith("abc")
    assert card.language == "ru"
    assert card.is_admin is True
    assert card.connected_surfaces == ["web", "telegram"]


@pytest.mark.asyncio
async def test_web_referrals_return_site_link(monkeypatch) -> None:
    monkeypatch.setattr(referrals.settings, "WEB_PUBLIC_URL", "https://site.example", raising=False)
    monkeypatch.setattr(referrals.repo, "count_user_referrals", AsyncMock(return_value=(1, 0, 0)))
    monkeypatch.setattr(referrals.repo, "get_user_referral_balance_snapshot", AsyncMock(return_value=None))
    monkeypatch.setattr(referrals.repo, "get_user_feed_remix_reward_rub", AsyncMock(return_value=0))
    monkeypatch.setattr(referrals.repo, "get_user_withdrawal_requests", AsyncMock(return_value=[]))
    monkeypatch.setattr(referrals.repo, "get_referral_children", AsyncMock(return_value=[]))

    response = await referrals.referrals(
        session=object(),
        user=SimpleNamespace(id=1, referral_code="REF_123", referral_balance=0),
    )

    assert response["ok"] is True
    assert response["data"]["referral_link"] == "https://site.example/account.html?ref=REF_123"
    assert "t.me" not in response["data"]["referral_link"]


@pytest.mark.asyncio
async def test_password_register_binds_site_referral(monkeypatch) -> None:
    referrer = SimpleNamespace(id=10, tg_id=1000, referrer_id=None)
    created = SimpleNamespace(
        id=2,
        tg_id=-20,
        username=None,
        full_name="New User",
        email="new@example.test",
        phone=None,
        photo_url=None,
        credits=15,
        referral_code="NEW_REF",
        language="ru",
        created_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        password_hash="hash",
        password_set_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        referrer_id=10,
        referrer_l2_id=None,
        referrer_l3_id=None,
    )
    create_contact_user = AsyncMock(return_value=created)
    add_credits = AsyncMock(return_value=20)

    monkeypatch.setattr(auth.settings, "WEB_PUBLIC_URL", "https://site.example", raising=False)
    monkeypatch.setattr(auth.repo, "get_user_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr(auth.repo, "get_user_by_referral_code", AsyncMock(return_value=referrer))
    monkeypatch.setattr(auth.repo, "create_contact_user", create_contact_user)
    monkeypatch.setattr(auth.repo, "add_credits", add_credits)
    monkeypatch.setattr(auth.repo, "set_user_password_hash", AsyncMock(return_value=created))
    monkeypatch.setattr(auth, "hash_password", lambda password: "hash")

    session = object()
    response = await auth.password_register(
        auth.PasswordRegisterRequest(
            email="new@example.test",
            password="supersecret",
            full_name="New User",
            referral_code="REF_123",
        ),
        response=Response(),
        request=SimpleNamespace(headers={}, client=None),
        session=session,
    )

    assert response["ok"] is True
    assert response["data"]["user"]["referral_link"] == "https://site.example/account.html?ref=NEW_REF"
    create_contact_user.assert_awaited_once()
    assert create_contact_user.await_args.kwargs["referrer"] is referrer
    add_credits.assert_awaited_once()
    assert add_credits.await_args.args[:3] == (session, 10, auth.settings.REFERRAL_L1_CREDITS)


@pytest.mark.asyncio
async def test_auth_config_exposes_registration_captcha(monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_ENABLED", True, raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_PROVIDER", "turnstile", raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_SITE_KEY", "site-key", raising=False)

    response = await auth.auth_config()

    assert response["ok"] is True
    assert response["data"]["captcha"] == {
        "enabled": True,
        "required": True,
        "provider": "turnstile",
        "site_key": "site-key",
    }


@pytest.mark.asyncio
async def test_password_register_requires_captcha_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_ENABLED", True, raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_PROVIDER", "turnstile", raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_SITE_KEY", "site-key", raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_SECRET_KEY", "secret-key", raising=False)

    response = await auth.password_register(
        auth.PasswordRegisterRequest(
            email="new@example.test",
            password="supersecret",
            full_name="New User",
        ),
        response=Response(),
        request=SimpleNamespace(headers={}, client=None),
        session=object(),
    )

    assert response.status_code == 400
    assert json.loads(response.body)["error"] == "Подтвердите, что вы не робот"


def test_password_register_accepts_turnstile_captcha_aliases() -> None:
    assert auth.PasswordRegisterRequest(
        email="new@example.test",
        password="supersecret",
        cf_turnstile_response="underscore-token",
    ).captcha_token == "underscore-token"
    assert auth.PasswordRegisterRequest(
        email="new@example.test",
        password="supersecret",
        **{"cf-turnstile-response": "dash-token"},
    ).captcha_token == "dash-token"


@pytest.mark.asyncio
async def test_password_register_verifies_turnstile_token(monkeypatch) -> None:
    class FakeCaptchaResponse:
        status_code = 200

        def json(self) -> dict:
            return {"success": True}

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            pass

        async def post(self, url: str, json: dict):
            captcha_calls.append((url, json))
            return FakeCaptchaResponse()

    captcha_calls = []
    created = SimpleNamespace(
        id=2,
        tg_id=-20,
        username=None,
        full_name="New User",
        email="new@example.test",
        phone=None,
        photo_url=None,
        credits=15,
        referral_code="NEW_REF",
        language="ru",
        created_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
        password_hash="hash",
        password_set_at=datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_ENABLED", True, raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_PROVIDER", "turnstile", raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_SITE_KEY", "site-key", raising=False)
    monkeypatch.setattr(auth.settings, "WEB_CAPTCHA_SECRET_KEY", "secret-key", raising=False)
    monkeypatch.setattr(auth.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(auth.repo, "get_user_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr(auth.repo, "create_contact_user", AsyncMock(return_value=created))
    monkeypatch.setattr(auth.repo, "set_user_password_hash", AsyncMock(return_value=created))
    monkeypatch.setattr(auth, "hash_password", lambda password: "hash")

    response = await auth.password_register(
        auth.PasswordRegisterRequest(
            email="new@example.test",
            password="supersecret",
            full_name="New User",
            captcha_token="captcha-token",
        ),
        response=Response(),
        request=SimpleNamespace(
            headers={"cf-connecting-ip": "203.0.113.7"},
            client=SimpleNamespace(host="198.51.100.1"),
        ),
        session=object(),
    )

    assert response["ok"] is True
    assert captcha_calls == [
        (
            auth.TURNSTILE_VERIFY_URL,
            {
                "secret": "secret-key",
                "response": "captcha-token",
                "remoteip": "203.0.113.7",
            },
        )
    ]


@pytest.mark.asyncio
async def test_billing_transactions_requires_auth() -> None:
    response = await billing.billing_transactions(session=object(), user=None)

    assert response.status_code == 401


def test_enabled_payment_methods_match_topup_providers(monkeypatch) -> None:
    monkeypatch.setattr(billing.settings, "TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr(billing.settings, "TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr(billing.settings, "TELEGRAM_STARS_ENABLED", True, raising=False)
    monkeypatch.setattr(billing.settings, "CRYPTOBOT_TOKEN", "crypto", raising=False)
    monkeypatch.setattr(billing.settings, "LAVA_API_KEY", "lava", raising=False)
    monkeypatch.setenv("LAVA_OFFER_ID_CREDITS_100", "offer-1")

    methods = billing.enabled_payment_methods()

    assert [item["key"] for item in methods] == ["tbank", "stars", "crypto", "lava"]
    assert [item["label"] for item in methods] == ["Карта", "Telegram", "Крипто", "Lava"]


def test_web_router_exposes_realtime_websocket_alias() -> None:
    assert any(getattr(route, "path", "") == "/ws/generations" for route in web_router.routes)


@pytest.mark.asyncio
async def test_landing_payload_aggregates_public_site_data(monkeypatch) -> None:
    model_costs = [
        SimpleNamespace(model_key="nano-banana-pro", display_name="Nano Banana Pro", gen_type=GenerationType.image, credits=4, is_active=True),
        SimpleNamespace(model_key="kling-2-1", display_name="Kling 2.1", gen_type=GenerationType.video, credits=8, is_active=True),
    ]
    generation = SimpleNamespace(
        id=42,
        result_url="https://cdn.test/primary.png",
        result_urls='["https://cdn.test/primary.png"]',
        prompt="portrait",
        model="nano-banana-pro",
        gen_type=GenerationType.image,
        likes_count=2,
        shares_count=1,
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    prompt = SimpleNamespace(
        id=7,
        title="Cover idea",
        description="Premium cover",
        prompt_text="Create a premium cover",
        preview_url="https://cdn.test/preview.png",
        model="nano-banana-pro",
        tags=["cover"],
        likes=3,
        uses_count=5,
        status="approved",
        category="marketing",
        created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
    )
    plan = SimpleNamespace(key="starter", label="Старт", credits=300, price_rub=390, price_stars=None, is_active=True, sort_order=1)

    monkeypatch.setattr(landing.repo, "get_all_model_costs", AsyncMock(return_value=model_costs))
    monkeypatch.setattr(
        landing.repo,
        "get_feed_generations",
        AsyncMock(return_value=[SimpleNamespace(generation=generation, username="artist", full_name=None, remix_count=0)]),
    )
    monkeypatch.setattr(landing, "get_approved_prompts", AsyncMock(return_value=[prompt]))
    monkeypatch.setattr(landing.repo, "get_active_price_plans", AsyncMock(return_value=[plan]))
    monkeypatch.setattr(landing, "enabled_payment_methods", lambda: [{"key": "tbank", "label": "Карта", "status": "enabled"}])

    response = await landing.landing_payload(session=object())
    data = response["data"]

    assert response["ok"] is True
    assert data["models"]["image"][0]["model_key"] == "nano-banana-pro"
    assert data["models"]["video"][0]["model_key"] == "kling-2-1"
    assert data["examples"][0]["result_url"] == "https://cdn.test/primary.png"
    assert data["prompts"]["items"][0]["title"] == "Cover idea"
    assert data["plans"][0]["key"] == "starter"
    assert data["payment_methods"][0]["key"] == "tbank"


@pytest.mark.asyncio
async def test_web_assistant_requires_auth() -> None:
    response = await assistant.assistant_chat(AssistantChatRequest(message="hello"), user=None)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_referrals_requires_auth() -> None:
    response = await referrals.referrals(session=object(), user=None)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_web_referral_exchange_uses_standard_tariff_rate(monkeypatch) -> None:
    monkeypatch.setattr(referrals.settings, "REFERRAL_EXCHANGE_MIN_RUB", 100.0)
    monkeypatch.setattr(referrals.settings, "REFERRAL_EXCHANGE_RUB_PER_CREDIT", 10.0)
    exchange = AsyncMock(
        return_value=SimpleNamespace(
            id=9,
            amount_rub=500.0,
            amount_credits=50.0,
            payout_details="AUTO_CREDITS",
            status="approved",
            created_at=datetime(2026, 5, 16, tzinfo=timezone.utc),
        )
    )
    monkeypatch.setattr(referrals.repo, "convert_referral_balance_to_credits", exchange)

    response = await referrals.exchange_referral_balance(
        referrals.ReferralWithdrawalRequest(amount_rub=500.0),
        session=object(),
        user=SimpleNamespace(id=1),
    )

    assert response["ok"] is True
    assert response["data"]["amount_credits"] == 50.0
    exchange.assert_awaited_once()
    assert exchange.await_args.kwargs["amount_rub"] == 500.0
    assert exchange.await_args.kwargs["rub_per_credit"] == 10.0


@pytest.mark.asyncio
async def test_web_generate_image_requires_auth() -> None:
    response = await generations.generate_image(
        ImageGenRequest(model="nano-banana-2", prompt="premium product"),
        session=object(),
        user=None,
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_web_generate_image_wraps_generation_payload(monkeypatch) -> None:
    async def fake_create_image_generation(*, body, session, user):
        assert body.prompt == "premium product"
        assert user.id == 1
        return GenerationOut(
            id=77,
            model=body.model,
            gen_type="image",
            prompt=body.prompt,
            status="processing",
            result_url=None,
            credits_spent=4,
            created_at="2026-05-24T00:00:00+00:00",
            result_urls=[],
        )

    monkeypatch.setattr(generations, "miniapp_create_image_generation", fake_create_image_generation)

    response = await generations.generate_image(
        ImageGenRequest(model="nano-banana-2", prompt="premium product"),
        session=object(),
        user=SimpleNamespace(id=1),
    )

    assert response["ok"] is True
    assert response["data"]["id"] == 77
    assert response["data"]["status"] == "processing"


@pytest.mark.asyncio
async def test_web_generate_image_marks_surface_when_handler_supports_it(monkeypatch) -> None:
    seen: dict[str, str] = {}

    async def fake_create_image_generation(*, body, session, user, surface="miniapp"):
        seen["surface"] = surface
        return GenerationOut(
            id=78,
            model=body.model,
            gen_type="image",
            prompt=body.prompt,
            status="processing",
            result_url=None,
            credits_spent=4,
            created_at="2026-05-24T00:00:00+00:00",
            result_urls=[],
        )

    monkeypatch.setattr(generations, "miniapp_create_image_generation", fake_create_image_generation)

    response = await generations.generate_image(
        ImageGenRequest(model="nano-banana-2", prompt="premium product"),
        session=object(),
        user=SimpleNamespace(id=1),
    )

    assert response["ok"] is True
    assert seen["surface"] == "web"


@pytest.mark.asyncio
async def test_web_feed_remix_marks_surface_and_keeps_source_reference(monkeypatch) -> None:
    seen: dict[str, object] = {}

    async def fake_remix_feed_post(*, gen_id, body, session, user, surface="miniapp"):
        seen["surface"] = surface
        seen["source_image_url"] = body.source_image_url
        seen["image_url"] = body.image_url
        return GenerationOut(
            id=79,
            model=body.model,
            gen_type="image",
            prompt="",
            prompt_hidden=True,
            status="processing",
            result_url=None,
            credits_spent=4,
            created_at="2026-05-24T00:00:00+00:00",
            result_urls=[],
        )

    monkeypatch.setattr(generations, "miniapp_remix_feed_post", fake_remix_feed_post)

    response = await generations.remix_feed_generation(
        10,
        FeedRemixRequest(
            model="nano-banana-2",
            mode="image",
            image_url="https://cdn.test/user-ref.png",
            source_image_url="https://cdn.test/feed-source.png",
        ),
        session=object(),
        user=SimpleNamespace(id=1),
    )

    assert response["ok"] is True
    assert seen == {
        "surface": "web",
        "source_image_url": "https://cdn.test/feed-source.png",
        "image_url": "https://cdn.test/user-ref.png",
    }


def test_web_task_id_helpers_preserve_provider_id() -> None:
    assert task_id_for_surface("task-1", "web") == "web:task-1"
    assert task_id_for_surface("web:task-1", "web") == "web:task-1"
    assert task_id_for_surface("task-1", "miniapp") == "task-1"
    assert provider_task_id("web:task-1") == "task-1"
    assert is_web_task_id("web:task-1") is True
    assert is_web_task_id("task-1") is False
