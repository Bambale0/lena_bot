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
            COMET_VIDEO_PROMPT_FPS=2.0,
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
            COMET_ASSISTANT_MODEL="qwen3.8-max",
            COMET_VIDEO_PROMPT_FPS=2.0,
        ),
    )

    result = await video_prompt_service.generate_prompt_from_video_url("https://cdn.example.test/video.mp4")

    assert result.text == "fallback prompt"
    assert fake_client.calls[0][1]["json"]["model"] == "qwen3.8-max"
    video_part = fake_client.calls[0][1]["json"]["messages"][1]["content"][0]
    assert video_part == {
        "type": "video_url",
        "video_url": {"url": "https://cdn.example.test/video.mp4"},
        "fps": 2.0,
    }


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
    (
        "A. Ready-to-use prompt\n"
        "Невозможно составить точный генерационный промпт, потому что видео или кадры из него "
        "не были прикреплены / не доступны для анализа.\n"
        "B. Что я увидел\nВидеоматериал отсутствует.\n"
        "C. Неоднозначности\nНет исходного видео.\n"
        "D. Audio note\nАудиодорожка не анализировалась."
    ),
    "Видео не видно / файл не прикреплён, поэтому кадры определить невозможно.",
    "I cannot see the video. No video was attached to the request.",
    "A. Ready-to-use prompt\nВидеоматериал отсутствует, пришлите видео.",
    "**A. Ready-to-use prompt**\nНевозможно составить промпт: кадры не доступны.",
    "`A. Ready-to-use prompt`\nВидеоматериал отсутствует, пожалуйста, пришлите видео.",
    "К сожалению, видео не было прикреплено, поэтому я не могу составить промпт.",
    "A. Ready-to-use prompt\nЯ не могу просмотреть видео, потому что оно не было прикреплено.",
    "A. Ready-to-use prompt\nЯ не вижу видео: исходный файл недоступен для анализа.",
    "I cannot analyze the video because the source video was not provided.",
    "I can't see the video; no video was attached to the request.",
])
def test_video_prompt_rejects_missing_video_completion(text):
    with pytest.raises(video_prompt_service.VideoPromptProviderError, match="video input"):
        video_prompt_service._extract_chat_text(
            {"choices": [{"finish_reason": "stop", "message": {"content": text}}]}
        )


@pytest.mark.parametrize("text", [
    'Камера приближается к билборду с надписью «Видеоматериал отсутствует».',
    'В начале видео человек говорит: «Видео не видно», затем поворачивается к окну.',
    "A. Ready-to-use prompt — Покажи постер с текстом 'No video was attached'.",
    "A. Ready-to-use prompt — Невозможно точно определить марку автомобиля в кадре, но камера плавно облетает автомобиль.",
    "Не могу определить высоту здания в видеокадре. Камера медленно приближается.",
    "Я не могу точно назвать год выпуска машины на видео, но её двери открываются.",
    "A. Ready-to-use prompt — Unable to identify the model of the airplane in the video. The camera pans right.",
    "A. Ready-to-use prompt — Невозможно определить предмет в кадре: на столе отсутствует этикетка, камера медленно вращается.",
    "Я не могу прочитать надпись на видео, поскольку номер отсутствует, но ясно видно движение камеры.",
])
def test_video_prompt_does_not_reject_missing_video_quotes_in_real_scene(text):
    assert video_prompt_service._validated_prompt_text(text) == text


def test_video_prompt_native_payload_always_supplies_frame_sampling():
    item = video_prompt_service._video_prompt_chat_messages(
        "https://cdn.example.test/clip.mp4", fps=2,
    )[1]["content"][0]
    assert item == {
        "type": "video_url",
        "video_url": {"url": "https://cdn.example.test/clip.mp4"},
        "fps": 2,
    }



@pytest.mark.parametrize("invalid", [0, 0.09, 10.01, float("nan"), float("inf")])
def test_video_prompt_rejects_invalid_frame_rate(invalid):
    with pytest.raises(ValueError, match="FPS"):
        video_prompt_service._video_prompt_chat_messages(
            "https://cdn.example.test/movie.mp4", fps=invalid,
        )
