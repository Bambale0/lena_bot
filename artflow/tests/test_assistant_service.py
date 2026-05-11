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

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, *args, **kwargs):
        if not self._responses:
            raise RuntimeError("no more fake responses")
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_generate_assistant_reply_falls_back_to_chat(monkeypatch) -> None:
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
        SimpleNamespace(KIE_AI_KEY="test-key", KIE_ASSISTANT_MODEL="gpt-5-4", KIE_ASSISTANT_FALLBACK="gpt-5-4"),
    )

    reply = await assistant_service.generate_assistant_reply([{"role": "user", "content": "Привет"}])

    assert reply == "Привет! Чем помочь?"


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
