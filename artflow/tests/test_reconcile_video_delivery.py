from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from api import miniapp_routes
from db.models import GenerationStatus, GenerationType


def _video_generation(*, task_id: str = "neironych:req-123"):
    return SimpleNamespace(
        id=70001,
        user_id=13,
        model="bytedance/seedance-2-5",
        gen_type=GenerationType.video,
        status=GenerationStatus.processing,
        task_id=task_id,
        created_at=datetime.now(timezone.utc),
        image_session_id=None,
        result_url=None,
        result_urls=None,
        prompt="test prompt",
        action_type=None,
        source_feed_gen_id=None,
    )


@pytest.mark.asyncio
async def test_reconcile_video_success_notifies_telegram_once(monkeypatch):
    gen = _video_generation()
    result_url = "https://cdn.example/video.mp4"
    finalized = _video_generation()
    finalized.status = GenerationStatus.done
    finalized.result_url = result_url

    poll = AsyncMock(return_value=result_url)
    finish = AsyncMock(return_value=finalized)
    notify = AsyncMock()
    user = SimpleNamespace(id=13, tg_id=645180669)

    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda provider: poll)
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=finalized))
    monkeypatch.setattr(miniapp_routes.repo, "get_user_by_id", AsyncMock(return_value=user))
    monkeypatch.setattr(miniapp_routes, "_notify_reconciled_video_result_in_bot", notify, raising=False)

    result = await miniapp_routes._reconcile_generation_status(object(), gen)

    assert result is finalized
    finish.assert_awaited_once()
    notify.assert_awaited_once_with(user=user, gen=finalized)


@pytest.mark.asyncio
async def test_reconcile_video_does_not_duplicate_notification_when_already_finalized(monkeypatch):
    gen = _video_generation()
    result_url = "https://cdn.example/video.mp4"
    finalized = _video_generation()
    finalized.status = GenerationStatus.done
    finalized.result_url = result_url

    poll = AsyncMock(return_value=result_url)
    finish = AsyncMock(return_value=None)
    notify = AsyncMock()

    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda provider: poll)
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=finalized))
    monkeypatch.setattr(miniapp_routes, "_notify_reconciled_video_result_in_bot", notify, raising=False)

    result = await miniapp_routes._reconcile_generation_status(object(), gen)

    assert result is finalized
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_web_video_does_not_notify_telegram(monkeypatch):
    gen = _video_generation(task_id="web:neironych:req-123")
    result_url = "https://cdn.example/video.mp4"
    finalized = _video_generation(task_id="web:neironych:req-123")
    finalized.status = GenerationStatus.done
    finalized.result_url = result_url

    poll = AsyncMock(return_value=result_url)
    finish = AsyncMock(return_value=finalized)
    notify = AsyncMock()

    monkeypatch.setattr(miniapp_routes.video_service, "get_poll_fn", lambda provider: poll)
    monkeypatch.setattr(miniapp_routes.repo, "finish_generation", finish)
    monkeypatch.setattr(miniapp_routes.repo, "get_generation_by_id", AsyncMock(return_value=finalized))
    monkeypatch.setattr(miniapp_routes, "_notify_reconciled_video_result_in_bot", notify, raising=False)

    result = await miniapp_routes._reconcile_generation_status(object(), gen)

    assert result is finalized
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconciled_video_delivery_sends_video_with_result_url(monkeypatch):
    gen = _video_generation()
    gen.status = GenerationStatus.done
    gen.result_url = "https://cdn.example/video.mp4"
    user = SimpleNamespace(id=13, tg_id=645180669)

    fake_bot = SimpleNamespace(
        send_video=AsyncMock(return_value=SimpleNamespace(message_id=77)),
        send_message=AsyncMock(),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(miniapp_routes, "Bot", lambda *args, **kwargs: fake_bot)

    await miniapp_routes._notify_reconciled_video_result_in_bot(user=user, gen=gen)

    fake_bot.send_video.assert_awaited_once()
    kwargs = fake_bot.send_video.await_args.kwargs
    assert kwargs["chat_id"] == 645180669
    assert kwargs["video"].url == "https://cdn.example/video.mp4"
    assert "req-123" in kwargs["caption"]
    fake_bot.send_message.assert_not_awaited()
    fake_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconciled_video_delivery_falls_back_to_link(monkeypatch):
    gen = _video_generation()
    gen.status = GenerationStatus.done
    gen.result_url = "https://cdn.example/video.mp4"
    user = SimpleNamespace(id=13, tg_id=645180669)

    fake_bot = SimpleNamespace(
        send_video=AsyncMock(side_effect=RuntimeError("telegram fetch failed")),
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=78)),
        session=SimpleNamespace(close=AsyncMock()),
    )
    monkeypatch.setattr(miniapp_routes, "Bot", lambda *args, **kwargs: fake_bot)

    await miniapp_routes._notify_reconciled_video_result_in_bot(user=user, gen=gen)

    fake_bot.send_video.assert_awaited_once()
    fake_bot.send_message.assert_awaited_once()
    assert "https://cdn.example/video.mp4" in fake_bot.send_message.await_args.kwargs["text"]
    fake_bot.session.close.assert_awaited_once()
