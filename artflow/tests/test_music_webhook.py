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
