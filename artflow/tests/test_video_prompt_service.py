from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from api import video_prompt_service
from bot.utils.telegram_ui import split_text_chunks


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.calls: list[tuple[tuple, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if not self._responses:
            raise RuntimeError("no more fake responses")
        return self._responses.pop(0)


def test_video_prompt_instructions_are_reverse_prompt_focused() -> None:
    assert "reverse engineering видеопромптов" in video_prompt_service._VIDEO_SYSTEM_PROMPT
    assert "Аудиодорожка не анализировалась" in video_prompt_service._VIDEO_PROMPT_REQUEST_TEXT
    assert "не пересказать видео" in video_prompt_service._VIDEO_SYSTEM_PROMPT


def test_video_prompt_video_validation_checks_mime_and_magic_bytes() -> None:
    assert video_prompt_service.is_supported_video_prompt_video(
        b"\x00\x00\x00\x18ftypmp42payload",
        "video/mp4",
    )
    assert video_prompt_service.is_supported_video_prompt_video(
        b"\x1a\x45\xdf\xa3webm-payload",
        "video/webm; codecs=vp9",
    )
    assert not video_prompt_service.is_supported_video_prompt_video(b"RIFFfake-wave", "video/webm")
    assert not video_prompt_service.is_supported_video_prompt_video(
        b"\x00\x00\x00\x18ftypmp42payload",
        "application/octet-stream",
    )


@pytest.mark.asyncio
async def test_generate_prompt_from_video_url_calls_comet_with_video_url(monkeypatch) -> None:
    fake_client = _FakeClient(
        [_FakeResponse({"choices": [{"message": {"content": "готовый видеопромпт"}}]})]
    )
    monkeypatch.setattr(video_prompt_service.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        video_prompt_service,
        "settings",
        SimpleNamespace(
            COMET_API_KEY="test-comet",
            COMET_BASE_URL="https://api.cometapi.com",
            COMET_VIDEO_PROMPT_MODEL="qwen3.8-max",
        ),
    )

    result = await video_prompt_service.generate_prompt_from_video_url(
        "https://cdn.example.test/video.mp4",
        fps=3,
    )

    assert result.text == "готовый видеопромпт"
    assert result.provider == "comet_chat"
    assert result.model == "qwen3.8-max"
    args, kwargs = fake_client.calls[0]
    assert args[0] == "https://api.cometapi.com/v1/chat/completions"
    payload = kwargs["json"]
    assert payload["model"] == "qwen3.8-max"
    content = payload["messages"][1]["content"]
    assert content[0]["type"] == "video_url"
    assert content[0]["video_url"] == {"url": "https://cdn.example.test/video.mp4", "fps": 3}
    assert content[1]["type"] == "text"


@pytest.mark.asyncio
async def test_generate_prompt_from_video_url_uses_assistant_fallback_model(monkeypatch) -> None:
    fake_client = _FakeClient(
        [_FakeResponse({"choices": [{"message": {"content": "fallback prompt"}}]})]
    )
    monkeypatch.setattr(video_prompt_service.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        video_prompt_service,
        "settings",
        SimpleNamespace(
            COMET_API_KEY="test-comet",
            COMET_BASE_URL="https://api.cometapi.com/",
            COMET_VIDEO_PROMPT_MODEL="",
            COMET_ASSISTANT_MODEL="qwen3.8-max",
        ),
    )

    result = await video_prompt_service.generate_prompt_from_video_url("https://cdn.example.test/video.mp4")

    assert result.text == "fallback prompt"
    assert fake_client.calls[0][1]["json"]["model"] == "qwen3.8-max"


def test_video_prompt_telegram_chunks_preserve_full_text() -> None:
    prompt = ("Первый блок с деталями камеры и движения. " * 180) + "\n\n" + (
        "Второй блок со светом, стилем и таймлайном. " * 180
    )
    clean = prompt.strip()

    chunks = split_text_chunks(prompt, max_chars=3000)

    assert len(chunks) > 1
    assert "".join(chunks) == clean
    assert all(0 < len(chunk) <= 3000 for chunk in chunks)

    handler = Path("bot/handlers/video_prompt.py").read_text(encoding="utf-8")
    assert "_MAX_PROMPT_MESSAGE_CHARS" not in handler
    assert "сокращённая версия" not in handler
    assert "split_text_chunks(prompt, max_chars=_MAX_PROMPT_CHUNK_CHARS)" in handler
    assert "for result_message in _result_messages(prompt, credits=credits):" in handler
    assert "await message.answer(result_message)" in handler
    assert "Часть {index}/{total}" in handler
