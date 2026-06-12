from __future__ import annotations

from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_generate_prompt_from_photo_uses_kie_first(monkeypatch) -> None:
    fake_client = _FakeClient([_FakeResponse({"choices": [{"message": {"content": "детальный промпт"}}]})])
    monkeypatch.setattr(photo_prompt_service.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        photo_prompt_service,
        "settings",
        SimpleNamespace(
            COMET_API_KEY="test-comet",
            COMET_BASE_URL="https://api.cometapi.com",
            COMET_ASSISTANT_MODEL="gpt-5.4",
            COMET_ASSISTANT_FALLBACK="gpt-5.4-mini",
            KIE_AI_KEY="test-kie",
            KIE_PHOTO_PROMPT_MODEL="gpt-5-2",
            KIE_PHOTO_PROMPT_FALLBACK="gpt-5-5",
        ),
    )

    result = await photo_prompt_service.generate_prompt_from_photo(b"image", "image/jpeg")

    assert result == "детальный промпт"
    args, kwargs = fake_client.calls[0]
    assert args[0] == "https://api.kie.ai/gpt-5-2/v1/chat/completions"
    assert "model" not in kwargs["json"]


@pytest.mark.asyncio
async def test_generate_prompt_from_photo_uses_kie_responses_for_gpt_5_5(monkeypatch) -> None:
    fake_client = _FakeClient(
        [
            _FakeResponse({"error": "missing"}, status_code=404),
            _FakeResponse(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": "kie prompt from responses"}],
                        }
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(photo_prompt_service.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        photo_prompt_service,
        "settings",
        SimpleNamespace(
            COMET_API_KEY="test-comet",
            COMET_BASE_URL="https://api.cometapi.com",
            COMET_ASSISTANT_MODEL="gpt-5.4",
            COMET_ASSISTANT_FALLBACK="gpt-5.4-mini",
            KIE_AI_KEY="test-kie",
            KIE_PHOTO_PROMPT_MODEL="gpt-5-2",
            KIE_PHOTO_PROMPT_FALLBACK="gpt-5-5",
        ),
    )

    result = await photo_prompt_service.generate_prompt_from_photo(b"image", "image/jpeg")

    assert result == "kie prompt from responses"
    args, kwargs = fake_client.calls[-1]
    assert args[0] == "https://api.kie.ai/codex/v1/responses"
    assert kwargs["json"]["model"] == "gpt-5-5"


@pytest.mark.asyncio
async def test_generate_prompt_from_photo_uses_comet_after_kie_errors(monkeypatch) -> None:
    fake_client = _FakeClient([
        _FakeResponse({"error": "missing"}, status_code=404),
        _FakeResponse({"error": "missing"}, status_code=404),
        _FakeResponse({"error": "missing"}, status_code=404),
        _FakeResponse({"choices": [{"message": {"content": "comet prompt"}}]}),
    ])
    monkeypatch.setattr(photo_prompt_service.httpx, "AsyncClient", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        photo_prompt_service,
        "settings",
        SimpleNamespace(
            COMET_API_KEY="test-comet",
            COMET_BASE_URL="https://api.cometapi.com",
            COMET_ASSISTANT_MODEL="gpt-5.4",
            COMET_ASSISTANT_FALLBACK="gpt-5.4-mini",
            KIE_AI_KEY="test-kie",
            KIE_PHOTO_PROMPT_MODEL="gpt-5-2",
            KIE_PHOTO_PROMPT_FALLBACK="gpt-5-5",
        ),
    )

    result = await photo_prompt_service.generate_prompt_from_photo(b"image", "image/jpeg")

    assert result == "comet prompt"
    args, kwargs = fake_client.calls[-1]
    assert args[0] == "https://api.cometapi.com/v1/chat/completions"
    assert kwargs["json"]["model"] == "gpt-5.2"
