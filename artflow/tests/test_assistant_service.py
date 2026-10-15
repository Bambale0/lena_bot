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
async def test_generate_assistant_reply_uses_neironych_qwen_first(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from core.qwen_routing import QwenRoute

    monkeypatch.setattr(assistant_service, "get_qwen_route", AsyncMock(return_value=QwenRoute("text", "neironych", "kie", "test")))
    qwen = SimpleNamespace(analyze_text=AsyncMock(return_value="Привет! Чем помочь?"))
    monkeypatch.setattr(assistant_service, "NeironychQwen38Service", lambda: qwen)
    kie = AsyncMock()
    monkeypatch.setattr(assistant_service.llm, "call_route", kie)

    reply = await assistant_service.generate_assistant_reply([{"role": "user", "content": "Привет"}])

    assert reply == "Привет! Чем помочь?"
    qwen.analyze_text.assert_awaited_once()
    kie.assert_not_awaited()


@pytest.mark.asyncio
async def test_assistant_definite_qwen_rejection_uses_one_kie_backup(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from api import llm_provider_service as llm
    from api.neironych_qwen38_service import Qwen38ProviderError
    from core.qwen_routing import QwenRoute

    monkeypatch.setattr(assistant_service, "get_qwen_route", AsyncMock(return_value=QwenRoute("text", "neironych", "kie", "test")))
    qwen = SimpleNamespace(analyze_text=AsyncMock(side_effect=Qwen38ProviderError("http_error", ambiguous=False, status=422)))
    monkeypatch.setattr(assistant_service, "NeironychQwen38Service", lambda: qwen)
    kie = AsyncMock(return_value=llm.LLMResult(text="KIE ответ", provider=llm.LLMProvider.KIE_RESPONSES, model="gpt-5-4"))
    monkeypatch.setattr(assistant_service.llm, "call_route", kie)

    reply = await assistant_service.generate_assistant_reply([{"role": "user", "content": "Привет"}])

    assert reply == "KIE ответ"
    kie.assert_awaited_once()


@pytest.mark.asyncio
async def test_assistant_timeout_never_starts_second_paid_request(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from api.neironych_qwen38_service import Qwen38ProviderError
    from core.qwen_routing import QwenRoute

    monkeypatch.setattr(assistant_service, "get_qwen_route", AsyncMock(return_value=QwenRoute("text", "neironych", "kie", "test")))
    qwen = SimpleNamespace(analyze_text=AsyncMock(side_effect=Qwen38ProviderError("transport_error", ambiguous=True)))
    monkeypatch.setattr(assistant_service, "NeironychQwen38Service", lambda: qwen)
    kie = AsyncMock()
    monkeypatch.setattr(assistant_service.llm, "call_route", kie)

    with pytest.raises(RuntimeError, match="повторная платная отправка остановлена"):
        await assistant_service.generate_assistant_reply([{"role": "user", "content": "Привет"}])
    kie.assert_not_awaited()


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
