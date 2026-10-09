from __future__ import annotations

import asyncio
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


@pytest.mark.asyncio
async def test_video_prompt_overall_deadline_stops_a_provider_that_keeps_reading(monkeypatch) -> None:
    """The overall budget must end even when HTTPX's per-read timer would reset."""
    deadlines = []

    def immediate_timeout(seconds):
        deadlines.append(seconds)
        return asyncio.timeout(0)

    class YieldingClient(_FakeClient):
        async def post(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            await asyncio.sleep(0)
            return _FakeResponse({"choices": [{"message": {"content": "late prompt"}}]})

    client = YieldingClient([])
    monkeypatch.setattr(video_prompt_service.httpx, "AsyncClient", lambda **kwargs: client)
    monkeypatch.setattr(video_prompt_service, "asyncio", SimpleNamespace(timeout=immediate_timeout), raising=False)

    with pytest.raises(video_prompt_service.VideoPromptProviderError, match="timed out"):
        await video_prompt_service.generate_prompt_from_video_url("https://example.test/clip.mp4")

    assert deadlines == [180.0]
    assert len(client.calls) == 1  # A timed-out paid analysis is never retried.


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
    assert content[0]["video_url"] == {"url": "https://cdn.example.test/video.mp4"}
    assert content[0]["fps"] == 3
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
            COMET_VIDEO_PROMPT_FPS=2.0,
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


def test_video_prompt_telegram_instruction_is_short_creator_copy() -> None:
    handler = Path("bot/handlers/video_prompt.py").read_text(encoding="utf-8")

    assert "Отправь видео — я сделаю подробный промпт для похожего ролика." in handler
    assert "Стоимость: <b>{float(model_cost.credits):g} 💋</b>." in handler
    assert "Отправь короткое видео MP4, MOV или WebM до 20 МБ." not in handler
    assert "Я разберу сцену, движение, камеру, свет и стиль" not in handler
    assert "Стоимость анализа:" not in handler


def test_video_prompt_frontend_copy_is_short_on_all_surfaces() -> None:
    legacy = Path("webapp/src/main.jsx").read_text(encoding="utf-8")
    services = Path("webapp/src/features/services-screen.tsx").read_text(encoding="utf-8")

    assert "Отправь видео — я сделаю подробный промпт для похожего ролика." in legacy
    assert "Загрузи MP4, MOV или WebM до 100 МБ" not in legacy
    assert "я разберу сцену, движение, камеру, свет и стиль" not in legacy
    assert "Видео → промпт" in services
    assert "Сделаю подробный промпт для похожего ролика" in services
    assert "MP4, MOV, WebM · стоимость по тарифу" not in services


_PROVIDER_FAILURE = (
    "The request could not be completed. Please retry later, "
    "or reduce the request parameters/content."
)


@pytest.mark.parametrize("payload", [
    {"choices": [{"message": {"content": _PROVIDER_FAILURE}}]},
    {"choices": [{"message": {"content": [{"type": "text", "text": _PROVIDER_FAILURE}]}}]},
    *[{key: _PROVIDER_FAILURE} for key in ("output_text", "text", "answer", "response")],
    {"choices": [{"message": {"content": "  " + _PROVIDER_FAILURE.upper().replace(". ", ".\n") + "  "}}]},
    {"error": {"message": "private upstream details"}, "text": "otherwise usable text"},
    {"choices": [{"message": {"refusal": "blocked", "content": "otherwise usable text"}}]},
    {"choices": [{"finish_reason": "content_filter", "message": {"content": "partial text"}}]},
    {"choices": [{"message": {"content": [{"type": "refusal", "refusal": "blocked"}, {"type": "text", "text": "partial text"}]}}]},
])
def test_video_prompt_rejects_provider_failure_completions(payload) -> None:
    with pytest.raises(video_prompt_service.VideoPromptProviderError, match="Video prompt") as error:
        video_prompt_service._extract_chat_text(payload)
    assert "private upstream details" not in str(error.value)


@pytest.mark.parametrize("text", [
    "A. Ready-to-use prompt — камера плавно движется вдоль берега.",
    'Покажи экран с надписью: "' + _PROVIDER_FAILURE + '". Камера отъезжает назад.',
    "The request could not be completed appears on a sign in the scene.",
])
def test_video_prompt_preserves_valid_prompts_and_quoted_errors(text) -> None:
    assert video_prompt_service._extract_chat_text({
        "error": None,
        "choices": [{"finish_reason": "stop", "message": {"refusal": None, "content": text}}],
    }) == text


@pytest.mark.parametrize("text", [
    {"error": "private upstream details"},
    ["private upstream details"],
    500,
    True,
])
def test_video_prompt_does_not_turn_non_text_content_into_a_prompt(text) -> None:
    payload = {"choices": [{"message": {"content": [{"type": "text", "text": text}]}}]}

    with pytest.raises(video_prompt_service.VideoPromptProviderError, match="Video prompt") as error:
        video_prompt_service._extract_chat_text(payload)

    assert "private upstream details" not in str(error.value)


@pytest.mark.parametrize("choices", [{}, {"message": {}}, "invalid", 1, [None], ["invalid"]])
def test_video_prompt_rejects_malformed_choices_even_with_fallback_text(choices) -> None:
    with pytest.raises(video_prompt_service.VideoPromptProviderError, match="Video prompt"):
        video_prompt_service._extract_chat_text({"choices": choices, "text": "private upstream details"})


def test_video_prompt_extracts_only_text_from_content_blocks() -> None:
    payload = {"choices": [{"message": {"content": [
        {"type": "text", "text": "  Камера движется.  "},
        {"type": "text", "text": {"error": "private upstream details"}},
        {"type": "text", "text": ""},
        {"type": "text", "text": "  Мягкий свет.  "},
    ]}}]}

    assert video_prompt_service._extract_chat_text(payload) == "Камера движется.\nМягкий свет."


@pytest.mark.parametrize("choices", [None, []])
@pytest.mark.parametrize("key", ["output_text", "text", "answer", "response"])
def test_video_prompt_preserves_text_fallback_without_choices(choices, key) -> None:
    assert video_prompt_service._extract_chat_text({
        "choices": choices,
        key: "  Камера движется.  ",
    }) == "Камера движется."
