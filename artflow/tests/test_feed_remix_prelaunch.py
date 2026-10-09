from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from api import miniapp_routes
from api.miniapp_auth import get_miniapp_user
from db.session import get_session
from main import app


@pytest.fixture
async def client():
    async def session_override():
        yield AsyncMock()

    async def user_override():
        return SimpleNamespace(id=42, tg_id=777, credits=3.0, is_banned=False)

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[get_miniapp_user] = user_override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_feed_remix_quote_prices_variants_and_count_without_spending(client, monkeypatch):
    source = SimpleNamespace(
        id=88, model="nano-banana-2", gen_type="image",
        prompt="secret prompt", result_url="https://public.example/image.jpg",
        result_urls=None,
    )
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    cost = AsyncMock(return_value=SimpleNamespace(credits=2.5, is_active=True))
    charge = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "resolve_image_model_cost", cost)
    monkeypatch.setattr(miniapp_routes.repo, "has_unlimited_image_model", AsyncMock(return_value=False))
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation", charge)
    monkeypatch.setattr(miniapp_routes.repo, "get_active_price_plans", AsyncMock(return_value=[
        SimpleNamespace(key="starter", label="Старт", credits=10, price_rub=100)
    ]))
    response = await client.post("/api/v1/feed/88/remix/quote", json={
        "model": "nano-banana-2", "mode": "image", "quality": "2K",
        "count": 2, "aspect_ratio": "1:1",
    })
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["cost_credits"] == 5.0
    assert data["balance_credits"] == 3.0
    assert data["deficit_credits"] == 2.0
    assert data["can_run"] is False
    assert "prompt" not in data
    cost.assert_awaited_once()
    charge.assert_not_awaited()


@pytest.mark.asyncio
async def test_remix_edit_instructions_exclude_hidden_author_prompt():
    prompt = miniapp_routes._build_feed_remix_prompt(
        "secret author prompt", "заменить куртку на белую, лицо оставить", has_source_media=True,
    )
    assert "secret author prompt" not in prompt
    assert "заменить куртку на белую, лицо оставить" in prompt
    assert miniapp_routes._build_feed_remix_prompt("secret author prompt", "") == "secret author prompt"


@pytest.mark.asyncio
async def test_feed_remix_quote_rejects_nonpublic_post_without_spending(client, monkeypatch):
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=None))
    charge = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation", charge)
    response = await client.post("/api/v1/feed/999/remix/quote", json={"model": "nano-banana-2"})
    assert response.status_code == 404
    charge.assert_not_awaited()

@pytest.mark.asyncio
async def test_edit_is_applied_on_first_paid_image_repeat_without_revealing_author_prompt(client, monkeypatch):
    from datetime import datetime, timezone

    from db.models import GenerationStatus, GenerationType

    source = SimpleNamespace(
        id=91, model="nano-banana-2", gen_type=GenerationType.image,
        prompt="secret creator instructions", result_url="https://example.test/source.png",
        result_urls=None,
    )
    charge = AsyncMock(return_value=SimpleNamespace(allowed=True, charged_credits=5, unlimited=False))
    image_generate = AsyncMock(return_value=SimpleNamespace(task_id="nexus:fake", is_async=True))
    record = SimpleNamespace(
        id=400, gen_type=GenerationType.image, model="nano-banana-2",
        status=GenerationStatus.processing, prompt="", result_url=None, result_urls=None,
        credits_spent=5, created_at=datetime.now(timezone.utc), finished_at=None,
        is_public_feed=False, is_prompt_library=False, source_feed_gen_id=91,
    )
    save_gen = AsyncMock(return_value=record)
    save_session = AsyncMock(return_value=SimpleNamespace(id=200))
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(miniapp_routes.repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2.5)))
    monkeypatch.setattr(miniapp_routes.repo, "count_user_active_generations", AsyncMock(return_value=0))
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation", charge)
    monkeypatch.setattr(miniapp_routes.repo, "create_image_session", save_session)
    monkeypatch.setattr(miniapp_routes.repo, "create_generation", save_gen)
    monkeypatch.setattr(miniapp_routes.repo, "update_generation_task", AsyncMock())
    monkeypatch.setattr(miniapp_routes.repo, "increment_feed_share", AsyncMock())
    monkeypatch.setattr(miniapp_routes.image_service, "generate_image", image_generate)

    response = await client.post("/api/v1/feed/91/remix", json={
        "model": "nano-banana-2", "mode": "image", "count": 2,
        "change_request": "Замени одежду на белый костюм", "quality": "2K",
    })
    assert response.status_code == 202, response.text
    assert response.json()["prompt_hidden"] is True
    assert response.json()["prompt"] == ""
    assert charge.await_args.kwargs["amount"] == 5.0
    assert "secret creator instructions" not in image_generate.await_args.args[1]
    assert "Замени одежду на белый костюм" in image_generate.await_args.args[1]
    assert "Замени одежду" in save_session.await_args.kwargs["base_prompt"]
    assert save_gen.await_args.kwargs["source_feed_gen_id"] == 91


@pytest.mark.asyncio
async def test_video_post_personalization_requires_source_video_support_when_quoting(client, monkeypatch):
    from db.models import GenerationType

    source = SimpleNamespace(
        id=99, model="veo3_fast", gen_type=GenerationType.video,
        prompt="hidden video", result_url="https://example.test/source.mp4",
        result_urls=None,
    )
    seen = {}
    def normalize_video_request(**kwargs):
        seen.update(kwargs)
        return {"duration": 5, "resolution": "720p", "reference_video_url": None}
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(miniapp_routes, "_normalize_video_request", normalize_video_request)
    monkeypatch.setattr(miniapp_routes.repo, "resolve_video_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2)))
    monkeypatch.setattr(miniapp_routes.repo, "get_active_price_plans", AsyncMock(return_value=[]))
    response = await client.post("/api/v1/feed/99/remix/quote", json={
        "model": "veo3_fast", "mode": "image", "image_url": "https://example.test/user.jpg",
        "video_url": "https://example.test/source.mp4", "resolution": "720p",
        "aspect_ratio": "9:16",
    })
    assert response.status_code == 422, response.text
    assert seen == {}



def test_public_feed_card_opens_webapp_prelaunch_and_keeps_chat_fallback():
    from bot.keyboards.feed import feed_card_kb
    from core.config import settings

    markup = feed_card_kb(gen_id=88, index=0, source="feed")
    buttons = [button for row in markup.inline_keyboard for button in row]
    shortcut = next(button for button in buttons if "Повторить со своим фото" in button.text)
    assert shortcut.web_app is not None
    assert shortcut.web_app.url == f"{settings.WEB_PUBLIC_URL.rstrip('/')}/app?remix=88"
    assert any(button.callback_data == "feed:use:88" for button in buttons)


@pytest.mark.asyncio
async def test_web_quote_proxy_requires_authenticated_user_without_invoicing():
    from api.miniapp_routes import FeedRemixRequest
    from api.web import generations as web_generations

    result = await web_generations.quote_feed_generation(
        generation_id=44,
        body=FeedRemixRequest(model="nano-banana-2"),
        session=object(),
        user=None,
    )
    assert result.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("model,gen_type,refs,aspect_ratio,prompt,detail", [
    ("midjourney-video", "video", [], None, "hidden", "requires a reference image"),
    ("midjourney-video", "image", ["https://example.test/extra.png"], None, "hidden", "at most 1"),
    ("midjourney-imagine", "image", ["https://example.test/extra.png"], None, "hidden", "at most 1"),
    ("midjourney-blend", "image", [f"https://example.test/{i}.png" for i in range(5)], None, "hidden", "at most 5"),
    ("midjourney-imagine", "image", [], "4:7", "hidden", "aspect ratio"),
    ("midjourney-imagine", "image", [], None, "", "Prompt is required"),
])
async def test_midjourney_quote_and_submit_reject_same_invalid_inputs_before_charge(
    client, monkeypatch, model, gen_type, refs, aspect_ratio, prompt, detail,
):
    source = SimpleNamespace(
        id=88, model=model, gen_type=gen_type, prompt=prompt,
        result_url=f"https://example.test/source.{'mp4' if gen_type == 'video' else 'png'}",
        result_urls=None,
    )
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(miniapp_routes.repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=5, is_active=True)))
    monkeypatch.setattr(miniapp_routes.repo, "has_unlimited_image_model", AsyncMock(return_value=False))
    plans = AsyncMock(return_value=[])
    charge = AsyncMock()
    spend = AsyncMock()
    monkeypatch.setattr(miniapp_routes.repo, "get_active_price_plans", plans)
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation", charge)
    monkeypatch.setattr(miniapp_routes.repo, "spend_credits", spend)
    body = {"model": model, "reference_urls": refs, "aspect_ratio": aspect_ratio}
    quote = await client.post("/api/v1/feed/88/remix/quote", json=body)
    submit = await client.post("/api/v1/feed/88/remix", json=body)
    assert quote.status_code == submit.status_code == 422, (quote.text, submit.text)
    assert quote.json()["detail"] == submit.json()["detail"]
    assert detail in quote.json()["detail"]
    plans.assert_not_awaited()
    charge.assert_not_awaited()
    spend.assert_not_awaited()


@pytest.mark.asyncio
async def test_midjourney_quote_deduplicates_source_and_primary_reference(client, monkeypatch):
    source_url = "https://example.test/source.png"
    source = SimpleNamespace(id=88, model="midjourney-imagine", gen_type="image", prompt="secret", result_url=source_url, result_urls=None)
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    monkeypatch.setattr(miniapp_routes.repo, "get_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2, is_active=True)))
    monkeypatch.setattr(miniapp_routes.repo, "has_unlimited_image_model", AsyncMock(return_value=False))
    quote = await client.post("/api/v1/feed/88/remix/quote", json={
        "model": "midjourney-imagine", "image_url": source_url,
        "source_image_url": source_url, "reference_urls": [source_url],
    })
    assert quote.status_code == 200, quote.text
    assert quote.json()["cost_credits"] == 2


@pytest.mark.asyncio
async def test_public_feed_share_card_works_without_user_and_keeps_prompt_hidden(client, monkeypatch):
    source = SimpleNamespace(
        id=88, user_id=42, model="nano-banana-2", gen_type="image",
        prompt="secret author prompt", result_url="https://example.test/source.png", result_urls=None,
        likes_count=1, shares_count=2,
    )
    card = SimpleNamespace(generation=source, aspect_ratio="1:1", username="creator", full_name=None, remix_count=3)
    monkeypatch.setattr(miniapp_routes.repo, "get_feed_generation_card", AsyncMock(return_value=card))
    response = await client.get("/api/v1/public/feed/88")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == 88
    assert response.json()["is_mine"] is False
    assert "secret author prompt" not in response.text
    assert not response.json().get("prompt")


@pytest.mark.asyncio
async def test_image_quote_and_submit_reject_excess_refs_before_charge(client, monkeypatch):
    source = SimpleNamespace(id=88, model="nano-banana-2", gen_type="image", prompt="secret", result_url="https://example.test/source.png", result_urls=None)
    monkeypatch.setattr(miniapp_routes.repo, "get_public_feed_generation", AsyncMock(return_value=source))
    charge = AsyncMock(return_value=SimpleNamespace(allowed=False))
    monkeypatch.setattr(miniapp_routes.repo, "charge_image_generation", charge)
    monkeypatch.setattr(miniapp_routes.repo, "resolve_image_model_cost", AsyncMock(return_value=SimpleNamespace(credits=2, is_active=True)))
    monkeypatch.setattr(miniapp_routes, "_reconcile_user_active_generations", AsyncMock())
    monkeypatch.setattr(miniapp_routes.repo, "count_user_active_generations", AsyncMock(return_value=0))
    body = {"model": "nano-banana-2", "reference_urls": [f"https://example.test/{i}.png" for i in range(5)]}
    quote = await client.post("/api/v1/feed/88/remix/quote", json=body)
    submit = await client.post("/api/v1/feed/88/remix", json=body)
    assert quote.status_code == submit.status_code == 422
    assert quote.json()["detail"] == submit.json()["detail"]
    charge.assert_not_awaited()
