from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


def test_admin_test_menu_offers_neironych_nano_pro():
    from bot.handlers.nexus_test import _model_selector_kb
    buttons = [b for row in _model_selector_kb().inline_keyboard for b in row]
    assert any(b.callback_data == "nxt:model:neur-nano-pro" for b in buttons)


def test_nano_pro_payload_uses_neironych_image_contract():
    from api.neironych_nano_pro import build_payload
    assert build_payload(prompt="A ceramic cup", aspect_ratio="21:9", quality="4K",
                         image_urls=["https://cdn.example/cup.png"]) == {
        "model": "nano-banana-pro", "prompt": "A ceramic cup", "n": 1,
        "aspect_ratio": "21:9", "resolution": "4k", "response_format": "b64_json",
        "images": [{"image_url": "https://cdn.example/cup.png"}],
    }


@pytest.mark.parametrize("changes", [
    {"prompt": ""}, {"aspect_ratio": "invalid"}, {"quality": "8K"},
    {"image_urls": ["file:///etc/passwd"]},
    {"image_urls": ["https://cdn.example/" + str(i) for i in range(5)]},
])
def test_invalid_parameters_fail_before_submission(changes):
    from api.neironych_nano_pro import build_payload
    with pytest.raises(ValueError):
        build_payload(**{"prompt": "cup", **changes})


@pytest.mark.asyncio
async def test_generation_reuses_safe_transport_without_touching_public_routing(monkeypatch):
    from api import neironych_nano_pro as adapter
    transport = AsyncMock(return_value="https://cdn.example/result.png")
    monkeypatch.setattr(adapter.neironych_image_adapter, "_generate_image", transport)
    await adapter.generate_image(prompt="cup", request_id="4b9c78b2-a3b5-4905-a86d-d8d33ee89951")
    assert transport.await_args.args[0]["model"] == "nano-banana-pro"
    assert transport.await_args.kwargs["request_id"] == "4b9c78b2-a3b5-4905-a86d-d8d33ee89951"
    assert transport.await_count == 1


@pytest.mark.asyncio
async def test_lab_router_rejects_non_admin_callbacks_and_messages(monkeypatch):
    from datetime import datetime, timezone

    from aiogram.types import CallbackQuery, Chat, Message, User

    from bot.handlers import neironych_nano_pro_test as lab
    from core.config import settings

    monkeypatch.setattr(settings, "ADMIN_IDS", [42])
    for user_id, allowed in [(42, True), (43, False)]:
        user = User(id=user_id, is_bot=False, first_name="Tester")
        message = Message(message_id=1, date=datetime.now(timezone.utc),
                          chat=Chat(id=user_id, type="private"), from_user=user, text="test")
        call = CallbackQuery(id="test", from_user=user, chat_instance="test",
                             message=message, data="npro:run")
        assert (await lab.router.callback_query.check_root_filters(call))[0] is allowed
        assert (await lab.router.message.check_root_filters(message))[0] is allowed


@pytest.mark.asyncio
async def test_duplicate_run_submits_once_even_after_ambiguous_failure(monkeypatch):
    from types import SimpleNamespace

    from bot.handlers import neironych_nano_pro_test as lab

    request_id = "4b9c78b2-a3b5-4905-a86d-d8d33ee89951"
    state = AsyncMock()
    state.get_data.return_value = {
        "npro_prompt": "cup", "npro_request_id": request_id,
        "npro_ratio": "1:1", "npro_quality": "2K", "npro_refs": [],
    }
    message = SimpleNamespace(answer=AsyncMock())
    call = SimpleNamespace(message=message, from_user=SimpleNamespace(id=42))
    monkeypatch.setattr(lab.settings, "NEIRONYCH_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(lab, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(lab, "claim_request", AsyncMock(side_effect=[True, False]))
    generate = AsyncMock(side_effect=lab.neironych_image_adapter.NeironychImageError("timeout"))
    monkeypatch.setattr(lab.provider, "generate_image", generate)
    await lab.run(call, state)
    await lab.run(call, state)
    assert generate.await_count == 1
    assert generate.await_args.kwargs["request_id"] == request_id
    assert "уже отправлен" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_redis_claim_uses_atomic_set_nx(monkeypatch):
    from bot.handlers import neironych_nano_pro_test as lab

    cache = AsyncMock()
    cache.set.return_value = True
    context = AsyncMock()
    context.__aenter__.return_value = cache
    monkeypatch.setattr(lab.Redis, "from_url", lambda _: context)
    assert await lab.claim_request("uuid")
    cache.set.assert_awaited_once_with("lab:nano-pro:uuid", "submitted", nx=True)


@pytest.mark.asyncio
async def test_successful_run_delivers_image_document_without_debit(monkeypatch):
    from types import SimpleNamespace

    from bot.handlers import neironych_nano_pro_test as lab

    state = AsyncMock()
    state.get_data.return_value = {**lab.initial_data(), "npro_prompt": "cup"}
    message = SimpleNamespace(answer=AsyncMock(), answer_document=AsyncMock())
    call = SimpleNamespace(message=message, from_user=SimpleNamespace(id=42))
    monkeypatch.setattr(lab.settings, "NEIRONYCH_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(lab, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(lab, "claim_request", AsyncMock(return_value=True))
    monkeypatch.setattr(lab.provider, "generate_image", AsyncMock(return_value="https://cdn.example/result.png"))
    await lab.run(call, state)
    message.answer_document.assert_awaited_once()
    assert message.answer_document.await_args.args[0].url == "https://cdn.example/result.png"


@pytest.mark.asyncio
async def test_claim_outage_prevents_paid_post(monkeypatch):
    from types import SimpleNamespace

    from bot.handlers import neironych_nano_pro_test as lab

    state = AsyncMock()
    state.get_data.return_value = {**lab.initial_data(), "npro_prompt": "cup"}
    call = SimpleNamespace(message=SimpleNamespace(answer=AsyncMock()), from_user=SimpleNamespace(id=42))
    monkeypatch.setattr(lab.settings, "NEIRONYCH_API_KEY", "synthetic-test-key")
    monkeypatch.setattr(lab, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(lab, "claim_request", AsyncMock(side_effect=ConnectionError()))
    generate = AsyncMock()
    monkeypatch.setattr(lab.provider, "generate_image", generate)
    await lab.run(call, state)
    generate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("callback", ["npro:ratio:1:1", "npro:quality:2K", "npro:clear"])
async def test_unchanged_setting_keeps_paid_request_identity(monkeypatch, callback):
    from types import SimpleNamespace

    from bot.handlers import neironych_nano_pro_test as lab

    data = {**lab.initial_data(), "npro_prompt": "cup"}
    state = AsyncMock()
    state.get_data.return_value = data
    monkeypatch.setattr(lab, "safe_answer_callback", AsyncMock())
    monkeypatch.setattr(lab, "show", AsyncMock())
    await lab.change_settings(SimpleNamespace(data=callback, message=object()), state)
    state.update_data.assert_not_awaited()


@pytest.mark.asyncio
async def test_reentering_same_prompt_keeps_request_identity(monkeypatch):
    from types import SimpleNamespace

    from bot.handlers import neironych_nano_pro_test as lab

    state = AsyncMock()
    state.get_data.return_value = {**lab.initial_data(), "npro_prompt": "cup"}
    monkeypatch.setattr(lab, "show", AsyncMock())
    await lab.save_prompt(SimpleNamespace(text=" cup "), state)
    state.update_data.assert_not_awaited()

