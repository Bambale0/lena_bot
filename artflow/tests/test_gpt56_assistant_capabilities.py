from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import assistant_service, llm_provider_service as llm


def test_gpt56_kie_payload_supports_max_reasoning_and_files() -> None:
    request = llm.LLMRequest(
        messages=(
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Compare these inputs"},
                    {"type": "input_image", "image_url": "https://example.test/photo.png"},
                    {"type": "input_file", "file_url": "https://example.test/report.pdf"},
                ],
            },
        ),
        reasoning_effort=llm.ReasoningEffort.MAX,
        web_search=True,
        max_output_tokens=8192,
    )

    payload = llm.build_kie_responses_payload("gpt-5-6-sol", request)

    assert payload["model"] == "gpt-5-6-sol"
    assert payload["reasoning"] == {"effort": "max"}
    assert payload["tools"] == [{"type": "web_search"}]
    assert payload["tool_choice"] == "auto"
    assert payload["input"][0]["content"] == [
        {"type": "input_text", "text": "Compare these inputs"},
        {"type": "input_image", "image_url": "https://example.test/photo.png"},
        {"type": "input_file", "file_url": "https://example.test/report.pdf"},
    ]


def test_assistant_directives_work_for_text_and_multimodal() -> None:
    text_messages, web_search, effort = assistant_service._apply_assistant_directives(
        [{"role": "user", "content": "/noweb /max Проведи глубокий анализ"}],
        web_search=True,
        reasoning_effort=llm.ReasoningEffort.MEDIUM,
    )
    assert web_search is False
    assert effort == llm.ReasoningEffort.MAX
    assert text_messages[-1]["content"] == "Проведи глубокий анализ"

    multi_messages, web_search, effort = assistant_service._apply_assistant_directives(
        [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "/web /deep Что на фото?"},
                    {"type": "input_image", "image_url": "https://example.test/photo.png"},
                ],
            }
        ],
        web_search=False,
        reasoning_effort=llm.ReasoningEffort.LOW,
    )
    assert web_search is True
    assert effort == llm.ReasoningEffort.HIGH
    assert multi_messages[-1]["content"][0]["text"] == "Что на фото?"


@pytest.mark.asyncio
async def test_unified_assistant_uses_gpt56_sol_with_web_search(monkeypatch) -> None:
    captured: list[tuple[list[llm.LLMRoute], llm.LLMRequest]] = []

    async def fake_call(routes, request, **kwargs):
        captured.append((list(routes), request))
        return llm.LLMResult(
            text="Актуальный ответ",
            provider=llm.LLMProvider.KIE_RESPONSES,
            model="gpt-5-6-sol",
        )

    monkeypatch.setattr(assistant_service.llm, "call_with_fallbacks", fake_call)
    monkeypatch.setattr(
        assistant_service,
        "settings",
        SimpleNamespace(
            KIE_AI_KEY="kie",
            COMET_API_KEY="comet",
            COMET_BASE_URL="https://api.cometapi.com",
            KIE_ASSISTANT_MODEL="gpt-5-6-sol",
            KIE_ASSISTANT_FALLBACK="gpt-5-6-terra",
            COMET_ASSISTANT_MODEL="gpt-5.4",
            COMET_ASSISTANT_FALLBACK="gpt-5.4-mini",
            ASSISTANT_WEB_SEARCH_ENABLED=True,
            ASSISTANT_DEFAULT_REASONING="medium",
            ASSISTANT_MAX_OUTPUT_TOKENS=8192,
        ),
    )

    result = await assistant_service.generate_assistant_result(
        [{"role": "user", "content": "Что нового сегодня?"}]
    )

    assert result.model == "gpt-5-6-sol"
    routes, request = captured[0]
    assert routes[0].model == "gpt-5-6-sol"
    assert routes[1].model == "gpt-5-6-terra"
    assert request.web_search is True
    assert request.reasoning_effort == llm.ReasoningEffort.MEDIUM
    assert request.max_output_tokens == 8192
