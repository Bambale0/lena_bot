from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api.web import assistant, billing, generations, health, landing, referrals, router as web_router
from api.miniapp_routes import (
    AssistantChatRequest,
    FeedRemixRequest,
    GenerationOut,
    ImageGenRequest,
    is_web_task_id,
    provider_task_id,
    task_id_for_surface,
)
from api.web.schemas import FeedCard, ModelCostCard, TransactionCard, UserMe
from db.models import GenerationType, PaymentProvider, TransactionStatus


@pytest.mark.asyncio
async def test_health_payload_has_service_status() -> None:
    payload = await health.health()

    assert payload == {"ok": True, "data": {"service": "api-web", "status": "ok"}}


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
async def test_billing_transactions_requires_auth() -> None:
    response = await billing.billing_transactions(session=object(), user=None)

    assert response.status_code == 401


def test_enabled_payment_methods_match_topup_providers(monkeypatch) -> None:
    monkeypatch.setattr(billing.settings, "TBANK_TERMINAL_KEY", "terminal", raising=False)
    monkeypatch.setattr(billing.settings, "TBANK_PASSWORD", "password", raising=False)
    monkeypatch.setattr(billing.settings, "TELEGRAM_STARS_ENABLED", True, raising=False)
    monkeypatch.setattr(billing.settings, "CRYPTOBOT_TOKEN", "crypto", raising=False)

    methods = billing.enabled_payment_methods()

    assert [item["key"] for item in methods] == ["tbank", "stars", "crypto"]
    assert [item["label"] for item in methods] == ["Карта", "Telegram", "Крипто"]


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
