"""Contract and failure tests for the Neironych Qwen chat boundary."""
from __future__ import annotations

import httpx
import pytest

from api.neironych_qwen38_service import (
    NeironychQwen38Service,
    Qwen38ProviderError,
)


def _service(handler):
    transport = httpx.MockTransport(handler)
    return NeironychQwen38Service(
        api_key="test-secret", base_url="https://provider.test", model="qwen3.8-max",
        transport=transport,
    )


@pytest.mark.asyncio
async def test_text_uses_exact_chat_contract_and_extracts_blocks() -> None:
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json={"choices": [{"message": {"content": [
            {"type": "text", "text": "Первый"}, {"type": "text", "text": "Второй"},
        ]}}]})

    answer = await _service(handler).analyze_text(user_instruction="Привет", system_prompt="Системный")
    request = seen["request"]
    assert request.url.path == "/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-secret"
    assert request.headers["idempotency-key"] == request.headers["x-client-request-id"]
    body = __import__("json").loads(request.content)
    assert body == {"model": "qwen3.8-max", "stream": False, "messages": [
        {"role": "system", "content": "Системный"}, {"role": "user", "content": "Привет"},
    ]}
    assert answer == "Первый\nВторой"


@pytest.mark.asyncio
async def test_image_and_video_have_distinct_media_contracts_without_unverified_options() -> None:
    seen = []

    def handler(request):
        seen.append(__import__("json").loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "готово"}}]})

    service = _service(handler)
    await service.analyze_image(image_url="data:image/png;base64,YQ==", user_instruction="Фото", system_prompt="S")
    await service.analyze_video(video_url="https://example.test/v.mp4", user_instruction="Видео", fps=2)
    assert seen[0]["messages"][1]["content"] == [
        {"type": "text", "text": "Фото"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,YQ=="}},
    ]
    assert seen[1]["messages"][0]["content"] == [
        {"type": "text", "text": "Видео"},
        {"type": "video_url", "video_url": {"url": "https://example.test/v.mp4"}, "fps": 2.0},
    ]
    assert all("response_format" not in item and "reasoning" not in item for item in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"choices": []}),
    httpx.Response(200, json={"choices": [{"message": {"content": " "}}]}),
    httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "partial"}}]}),
    httpx.Response(200, text="not-json"),
])
async def test_empty_or_invalid_response_is_never_success(response) -> None:
    with pytest.raises(Qwen38ProviderError) as caught:
        await _service(lambda _request: response).analyze_text(user_instruction="тест")
    assert caught.value.ambiguous is True


@pytest.mark.asyncio
async def test_http_4xx_is_definite_but_timeout_is_ambiguous() -> None:
    with pytest.raises(Qwen38ProviderError) as caught:
        await _service(lambda _request: httpx.Response(400, json={"error": "unsupported"})).analyze_text(
            user_instruction="тест",
        )
    assert caught.value.ambiguous is False

    def timeout(_request):
        raise httpx.ReadTimeout("timeout")

    with pytest.raises(Qwen38ProviderError) as caught:
        await _service(timeout).analyze_text(user_instruction="тест")
    assert caught.value.ambiguous is True


@pytest.mark.asyncio
async def test_provider_log_has_correlation_without_prompt_or_secret(caplog) -> None:
    import logging

    caplog.set_level(logging.INFO, logger="api.neironych_qwen38_service")
    service = _service(lambda _request: httpx.Response(200, json={
        "choices": [{"message": {"content": "Безопасный ответ"}}],
    }))
    await service.analyze_text(user_instruction="личный запрос 123")
    log = caplog.text
    for field in ("provider=neironych", "model=qwen3.8-max", "mode=text", "request_id=", "result=success"):
        assert field in log
    assert "test-secret" not in log
    assert "личный запрос 123" not in log
