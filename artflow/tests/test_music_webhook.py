from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import main
from main import app


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_kie_music_webhook_uses_db_generation_when_in_memory_task_is_missing(monkeypatch) -> None:
    finish_generation = AsyncMock()
    get_generation_by_task_id = AsyncMock(
        return_value=SimpleNamespace(id=77, user_id=42, status=SimpleNamespace(value="processing"))
    )
    get_user_by_id = AsyncMock(return_value=SimpleNamespace(id=42, tg_id=555111))
    get_generation_by_id = AsyncMock(return_value=SimpleNamespace(id=77, user_id=42, credits_spent=20))

    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", get_generation_by_task_id)
    monkeypatch.setattr(main.repo, "get_user_by_id", get_user_by_id)
    monkeypatch.setattr(main.repo, "get_generation_by_id", get_generation_by_id)
    monkeypatch.setattr(main.repo, "finish_generation", finish_generation)
    monkeypatch.setattr(main.repo, "fail_generation", AsyncMock())
    monkeypatch.setattr(main.repo, "add_credits", AsyncMock())
    monkeypatch.setitem(main.kie_music_webhook.__globals__, "extract_music_urls", lambda _payload: ["https://cdn.test/track.mp3"])
    monkeypatch.setitem(main.kie_music_webhook.__globals__, "is_success", lambda _payload: True)
    monkeypatch.setattr(main, "bot", SimpleNamespace(send_audio=AsyncMock()))

    payload = {
        "code": 200,
        "data": {
            "taskId": "music-task-1",
            "status": "SUCCESS",
            "data": [
                {"audio_url": "https://cdn.test/track.mp3"},
            ],
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/kie/music", json=payload)

    assert response.status_code == 200
    get_generation_by_task_id.assert_awaited()
    finish_generation.assert_awaited_once()
    assert finish_generation.await_args.args[1:] == (77, "https://cdn.test/track.mp3")


@pytest.mark.asyncio
async def test_kie_music_webhook_rejects_invalid_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "expected-secret")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/kie/music", json={"data": {"taskId": "music-task-1"}})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_kie_music_webhook_accepts_query_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.repo, "get_generation_by_task_id", AsyncMock(return_value=None))

    payload = {
        "code": 200,
        "data": {"taskId": "music-task-1", "status": "SUCCESS"},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/kie/music?secret=expected-secret", json=payload)

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_kie_music_webhook_fails_closed_in_production_without_secret(monkeypatch) -> None:
    monkeypatch.setattr(main.settings, "ENV", "production")
    monkeypatch.setattr(main.settings, "KIE_WEBHOOK_SECRET", "")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/kie/music", json={"data": {"taskId": "music-task-1"}})

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_kie_suno_voice_webhook_updates_ready_voice(monkeypatch) -> None:
    update_suno_voice = AsyncMock()
    monkeypatch.setattr(main, "AsyncSessionLocal", _FakeSessionContext)
    monkeypatch.setattr(main.repo, "get_suno_voice_by_validate_task_id", AsyncMock(return_value=None))
    monkeypatch.setattr(
        main.repo,
        "get_suno_voice_by_voice_task_id",
        AsyncMock(return_value=SimpleNamespace(id=12, status="generating")),
    )
    monkeypatch.setattr(main.repo, "update_suno_voice", update_suno_voice)

    payload = {
        "code": 200,
        "data": {
            "taskId": "voice-task-1",
            "status": "success",
            "voiceId": "voice_abc",
        },
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/webhook/kie/suno-voice", json=payload)

    assert response.status_code == 200
    update_suno_voice.assert_awaited_once()
    assert update_suno_voice.await_args.args[1:] == (12,)
    assert update_suno_voice.await_args.kwargs == {
        "status": "ready",
        "voice_id": "voice_abc",
        "error_msg": None,
    }
