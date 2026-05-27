from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from api.web import billing, generations, health, referrals
from api.miniapp_routes import GenerationOut, ImageGenRequest
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


@pytest.mark.asyncio
async def test_referrals_requires_auth() -> None:
    response = await referrals.referrals(session=object(), user=None)

    assert response.status_code == 401


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
