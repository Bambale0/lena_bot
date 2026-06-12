from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import assistant_service


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
async def test_generate_assistant_reply_uses_kie_then_comet_fallback(monkeypatch) -> None:
    fake_client = _FakeClient(
        [
            _FakeResponse({"code": 500, "msg": "Server exception, please try again later"}),
            _FakeResponse({"choices": [{"message": {"content": "Привет! Чем помочь?"}}]}),
        ]
    )
    monkeypatch.setattr(assistant_service.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        assistant_service,
        "settings",
        SimpleNamespace(
            KIE_AI_KEY="test-key",
            KIE_ASSISTANT_MODEL="gpt-5-4",
            KIE_ASSISTANT_FALLBACK="gpt-5-4",
            COMET_API_KEY="test-comet-key",
            COMET_BASE_URL="https://api.cometapi.com",
            COMET_ASSISTANT_MODEL="gpt-5.4",
            COMET_ASSISTANT_FALLBACK="gpt-5.4-mini",
        ),
    )

    reply = await assistant_service.generate_assistant_reply([{"role": "user", "content": "Привет"}])

    assert reply == "Привет! Чем помочь?"
    args, kwargs = fake_client.calls[0]
    assert args[0] == "https://api.kie.ai/codex/v1/responses"
    assert kwargs["json"]["model"] == "gpt-5-4"
    args, _kwargs = fake_client.calls[1]
    assert args[0] == "https://api.cometapi.com/v1/chat/completions"


@pytest.mark.asyncio
async def test_generate_assistant_reply_uses_comet_after_kie_errors(monkeypatch) -> None:
    fake_client = _FakeClient(
        [
            _FakeResponse({"error": "missing"}, status_code=404),
            _FakeResponse({"choices": [{"message": {"content": "Comet OK"}}]}),
        ]
    )
    monkeypatch.setattr(assistant_service.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        assistant_service,
        "settings",
        SimpleNamespace(
            KIE_AI_KEY="test-key",
            KIE_ASSISTANT_MODEL="gpt-5-4",
            KIE_ASSISTANT_FALLBACK="",
            COMET_API_KEY="test-comet-key",
            COMET_BASE_URL="https://api.cometapi.com",
            COMET_ASSISTANT_MODEL="gpt-5.4",
            COMET_ASSISTANT_FALLBACK="gpt-5.4-mini",
        ),
    )

    reply = await assistant_service.generate_assistant_reply([{"role": "user", "content": "Ping"}])

    assert reply == "Comet OK"
    comet_args, comet_kwargs = fake_client.calls[-1]
    assert comet_args[0] == "https://api.cometapi.com/v1/chat/completions"
    assert comet_kwargs["json"]["model"] == "gpt-5.4"
    assert comet_kwargs["json"]["messages"][-1] == {"role": "user", "content": "Ping"}


def test_extract_chat_output_text_supports_list_content() -> None:
    payload = {
        "choices": [
            {
                "message": {
                    "content": [
                        {"type": "text", "text": "Первая строка"},
                        {"type": "text", "text": "Вторая строка"},
                    ]
                }
            }
        ]
    }
    assert assistant_service._extract_chat_output_text(payload) == "Первая строка\nВторая строка"


def test_sanitize_assistant_reply_hides_raw_context_dump() -> None:
    raw = "\n".join(
        [
            "КОНТЕКСТ",
            "role: user",
            'content: [{"type":"input_text","text":"осьминоги"}]',
            "role: assistant",
            "content: служебный ответ",
        ]
    )

    assert assistant_service.sanitize_assistant_reply(raw) == "Готово. Чем ещё помочь?"
    assert assistant_service.sanitize_assistant_reply("Обычный ответ") == "Обычный ответ"
