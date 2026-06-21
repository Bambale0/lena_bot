from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from api import kieai_client


@pytest.mark.asyncio
async def test_upload_file_stream_uses_upload_path_form_field(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": {"downloadUrl": "https://cdn.example.test/ref.png"}}

    class FakeClient:
        async def post(self, path: str, *, data: dict, files: dict) -> FakeResponse:
            calls.append({"path": path, "data": data, "files": files})
            return FakeResponse()

    monkeypatch.setattr(kieai_client, "get_upload_client", lambda: FakeClient())

    url = await kieai_client.upload_file_stream(
        b"\x89PNG\r\n\x1a\npayload",
        filename="ref.png",
        content_type="image/png",
        upload_path="images/custom",
    )

    assert url == "https://cdn.example.test/ref.png"
    assert calls[0]["path"] == "/api/file-stream-upload"
    assert calls[0]["data"] == {"uploadPath": "images/custom"}


@pytest.mark.asyncio
async def test_create_omni_audio_uses_documented_endpoint(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 0, "data": {"kieAudioId": "audio_123"}}

    monkeypatch.setattr(kieai_client, "_retry_post", fake_post)

    payload = {"audio_id": "achernar", "name": "Narrator"}
    response = await kieai_client.create_omni_audio(payload)

    assert response["data"]["kieAudioId"] == "audio_123"
    assert calls == [("/api/v1/omni/audio/create", payload)]


@pytest.mark.asyncio
async def test_create_omni_character_uses_documented_endpoint(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"code": 200, "data": {"characterId": "character_123"}}

    monkeypatch.setattr(kieai_client, "_retry_post", fake_post)

    payload = {"descriptions": "hero", "image_urls": ["https://example.test/hero.png"]}
    response = await kieai_client.create_omni_character(payload)

    assert response["data"]["characterId"] == "character_123"
    assert calls == [("/api/v1/omni/character/create", payload)]


@pytest.mark.asyncio
async def test_suno_voice_helpers_use_documented_endpoints(monkeypatch) -> None:
    posts: list[tuple[str, dict]] = []
    gets: list[tuple[str, dict | None]] = []

    async def fake_post(path: str, payload: dict) -> dict:
        posts.append((path, payload))
        return {"code": 200, "data": {"taskId": "task_123"}}

    async def fake_get(path: str, params: dict | None = None) -> dict:
        gets.append((path, params))
        return {"code": 200, "data": {"taskId": params["taskId"] if params else ""}}

    monkeypatch.setattr(kieai_client, "_retry_post", fake_post)
    monkeypatch.setattr(kieai_client, "_retry_get", fake_get)

    await kieai_client.create_suno_voice_validation({"voiceUrl": "https://cdn.test/v.mp3"})
    await kieai_client.get_suno_voice_validation("validate_task")
    await kieai_client.create_suno_voice({"taskId": "validate_task", "verifyUrl": "https://cdn.test/r.mp3"})
    await kieai_client.get_suno_voice_record("voice_task")
    await kieai_client.check_suno_voice({"task_id": "voice_task"})

    assert posts == [
        ("/api/v1/voice/validate", {"voiceUrl": "https://cdn.test/v.mp3"}),
        ("/api/v1/voice/generate", {"taskId": "validate_task", "verifyUrl": "https://cdn.test/r.mp3"}),
        ("/api/v1/voice/check-voice", {"task_id": "voice_task"}),
    ]
    assert gets == [
        ("/api/v1/voice/validate-info", {"taskId": "validate_task"}),
        ("/api/v1/voice/record-info", {"taskId": "voice_task"}),
    ]



def test_looks_like_insufficient_credits_matches_provider_messages() -> None:
    assert kieai_client._looks_like_insufficient_credits({"message": "Credits insufficient. Please top up."}) is True
    assert kieai_client._looks_like_insufficient_credits("Current balance isn't enough for this task") is True
    assert kieai_client._looks_like_insufficient_credits({"message": "temporary provider timeout"}) is False


@pytest.mark.asyncio
async def test_maybe_alert_credit_issue_calls_admin_alert_once(monkeypatch) -> None:
    alert = AsyncMock()
    monkeypatch.setattr(kieai_client, "send_admin_alert_once", alert)

    await kieai_client._maybe_alert_credit_issue(
        "kie.ai POST /api/v1/jobs/createTask",
        {"message": "insufficient credits, please top up"},
    )

    alert.assert_awaited_once()
    kwargs = alert.await_args.kwargs
    assert kwargs["alert_key"] == "provider-credits:kie.ai POST /api/v1/jobs/createTask"
    assert "закончились кредиты" in kwargs["title"].lower()
    assert "insufficient credits" in kwargs["message"].lower()
