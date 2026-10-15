from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from api import photo_prompt_service


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")
        return None

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


def test_photo_prompt_instructions_request_russian_output() -> None:
    assert "русском языке" in photo_prompt_service._SYSTEM_PROMPT
    assert "финальный русский промпт" in photo_prompt_service._SYSTEM_PROMPT
    assert "Не используй английский язык" in photo_prompt_service._PHOTO_PROMPT_REQUEST_TEXT
    assert "English prompt" not in photo_prompt_service._SYSTEM_PROMPT
    assert "English prompt" not in photo_prompt_service._PHOTO_PROMPT_REQUEST_TEXT


@pytest.mark.asyncio
async def test_generate_prompt_from_photo_uses_neironych_first(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from core.qwen_routing import QwenRoute

    monkeypatch.setattr(photo_prompt_service, "get_qwen_route", AsyncMock(return_value=QwenRoute("image", "neironych", "kie", "test")))
    qwen = SimpleNamespace(analyze_image=AsyncMock(return_value="Подробный русский промпт: красный квадрат на белом фоне."))
    monkeypatch.setattr(photo_prompt_service, "NeironychQwen38Service", lambda: qwen)
    kie = AsyncMock()
    monkeypatch.setattr(photo_prompt_service, "_call_kie_chat", kie)

    result = await photo_prompt_service.generate_prompt_from_photo_result(b"image", "image/jpeg")

    assert result.provider == "neironych"
    assert result.model == photo_prompt_service.settings.NEIRONYCH_QWEN38_MODEL
    assert "красный квадрат" in result.text
    qwen.analyze_image.assert_awaited_once()
    kie.assert_not_awaited()


@pytest.mark.asyncio
async def test_photo_definite_neironych_rejection_uses_one_kie_fallback(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from api.neironych_qwen38_service import Qwen38ProviderError
    from core.qwen_routing import QwenRoute

    monkeypatch.setattr(photo_prompt_service, "get_qwen_route", AsyncMock(return_value=QwenRoute("image", "neironych", "kie", "test")))
    qwen = SimpleNamespace(analyze_image=AsyncMock(side_effect=Qwen38ProviderError("http_error", ambiguous=False, status=422)))
    monkeypatch.setattr(photo_prompt_service, "NeironychQwen38Service", lambda: qwen)
    kie = AsyncMock(return_value=photo_prompt_service.PhotoPromptResult("Детальный русский промпт", "kie_chat", "gpt-5-2"))
    monkeypatch.setattr(photo_prompt_service, "_call_kie_chat", kie)

    result = await photo_prompt_service.generate_prompt_from_photo_result(b"image", "image/jpeg")

    assert result.provider == "kie_chat"
    kie.assert_awaited_once()


@pytest.mark.asyncio
async def test_photo_ambiguous_neironych_failure_never_starts_second_paid_request(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from api.neironych_qwen38_service import Qwen38ProviderError
    from core.qwen_routing import QwenRoute

    monkeypatch.setattr(photo_prompt_service, "get_qwen_route", AsyncMock(return_value=QwenRoute("image", "neironych", "kie", "test")))
    qwen = SimpleNamespace(analyze_image=AsyncMock(side_effect=Qwen38ProviderError("transport_error", ambiguous=True)))
    monkeypatch.setattr(photo_prompt_service, "NeironychQwen38Service", lambda: qwen)
    kie = AsyncMock()
    monkeypatch.setattr(photo_prompt_service, "_call_kie_chat", kie)

    with pytest.raises(RuntimeError, match="неопределённым исходом"):
        await photo_prompt_service.generate_prompt_from_photo_result(b"image", "image/jpeg")
    kie.assert_not_awaited()


@pytest.mark.asyncio
async def test_kie_primary_definitive_rejection_uses_neironych_backup(monkeypatch) -> None:
    from unittest.mock import AsyncMock

    from core.qwen_routing import QwenRoute

    monkeypatch.setattr(photo_prompt_service, "get_qwen_route", AsyncMock(
        return_value=QwenRoute("image", "kie", "neironych", "test"),
    ))
    request = httpx.Request("POST", "https://kie.test/chat")
    response = httpx.Response(422, request=request)
    kie = AsyncMock(side_effect=httpx.HTTPStatusError("unsupported", request=request, response=response))
    monkeypatch.setattr(photo_prompt_service, "_call_kie_chat", kie)
    qwen = SimpleNamespace(analyze_image=AsyncMock(return_value="Подробный русский промпт: красный квадрат на белом фоне."))
    monkeypatch.setattr(photo_prompt_service, "NeironychQwen38Service", lambda: qwen)

    result = await photo_prompt_service.generate_prompt_from_photo_result(b"image", "image/jpeg")
    assert result.provider == "neironych"
    kie.assert_awaited_once()
    qwen.analyze_image.assert_awaited_once()
