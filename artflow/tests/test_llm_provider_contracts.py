from __future__ import annotations

from types import SimpleNamespace

import pytest

from api import assistant_service, llm_provider_service as llm, photo_prompt_service


def test_kie_responses_multimodal_web_search_payload() -> None:
    request = llm.LLMRequest(
        messages=(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in the image?"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://example.test/image.png"},
                    },
                ],
            },
        ),
        system_prompt="Be precise",
        reasoning_effort=llm.ReasoningEffort.HIGH,
        web_search=True,
    )

    payload = llm.build_kie_responses_payload("gpt-5-5", request)

    assert payload == {
        "model": "gpt-5-5",
        "stream": False,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": "Be precise"}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "What is in the image?"},
                    {
                        "type": "input_image",
                        "image_url": "https://example.test/image.png",
                    },
                ],
            },
        ],
        "reasoning": {"effort": "high"},
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
    }


def test_kie_rejects_web_search_and_functions_together() -> None:
    request = llm.LLMRequest(
        messages=({"role": "user", "content": "Hi"},),
        web_search=True,
        function_tools=(
            {
                "type": "function",
                "name": "lookup",
                "description": "Lookup",
                "parameters": {"type": "object"},
            },
        ),
    )

    with pytest.raises(ValueError, match="mutually exclusive"):
        llm.build_kie_responses_payload("gpt-5-5", request)


def test_comet_chat_strict_schema_and_function_tools() -> None:
    schema = llm.strict_json_schema(
        "answer",
        {
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        },
    )
    tool = {
        "type": "function",
        "function": {
            "name": "lookup",
            "description": "Lookup data",
            "parameters": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
            },
        },
    }
    payload = llm.build_comet_chat_payload(
        "gpt-5.4",
        llm.LLMRequest(
            messages=({"role": "user", "content": "Find it"},),
            system_prompt="Use the tool",
            function_tools=(tool,),
            response_format=schema,
        ),
    )

    assert payload["messages"][0] == {"role": "developer", "content": "Use the tool"}
    assert payload["tools"] == [tool]
    assert payload["tool_choice"] == "auto"
    assert payload["response_format"] == schema
    assert payload["max_completion_tokens"] == 4096


def test_claude_route_converts_openai_function_schema() -> None:
    payload = llm.build_kie_claude_payload(
        "claude-sonnet-4-5",
        llm.LLMRequest(
            messages=({"role": "user", "content": "Weather?"},),
            system_prompt="Answer accurately",
            reasoning_effort=llm.ReasoningEffort.HIGH,
            function_tools=(
                {
                    "type": "function",
                    "function": {
                        "name": "weather",
                        "description": "Get weather",
                        "parameters": {
                            "type": "object",
                            "properties": {"city": {"type": "string"}},
                            "required": ["city"],
                        },
                    },
                },
            ),
        ),
    )

    assert payload["system"] == "Answer accurately"
    assert payload["thinkingFlag"] is True
    assert payload["tools"] == [
        {
            "name": "weather",
            "description": "Get weather",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }
    ]


def test_response_extractors_preserve_provider_and_tool_calls() -> None:
    route = llm.LLMRoute(llm.LLMProvider.KIE_RESPONSES, "gpt-5-5")
    result = llm._extract_responses_result(
        {
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Answer"}],
                },
                {
                    "type": "function_call",
                    "name": "lookup",
                    "arguments": "{}",
                },
            ],
            "usage": {"total_tokens": 10},
        },
        route,
    )

    assert result.text == "Answer"
    assert result.provider == llm.LLMProvider.KIE_RESPONSES
    assert result.model == "gpt-5-5"
    assert result.usage == {"total_tokens": 10}
    assert result.tool_calls[0]["name"] == "lookup"


@pytest.mark.asyncio
async def test_assistant_routes_real_claude_fallback(monkeypatch) -> None:
    captured: list[list[llm.LLMRoute]] = []

    async def fake_call(routes, request, **kwargs):
        captured.append(list(routes))
        return llm.LLMResult(
            text="Claude answered",
            provider=llm.LLMProvider.KIE_CLAUDE,
            model="claude-sonnet-4-5",
        )

    monkeypatch.setattr(assistant_service.llm, "call_with_fallbacks", fake_call)
    monkeypatch.setattr(
        assistant_service,
        "settings",
        SimpleNamespace(
            KIE_AI_KEY="kie",
            COMET_API_KEY="comet",
            COMET_BASE_URL="https://api.cometapi.com",
            KIE_ASSISTANT_MODEL="gpt-5-4",
            KIE_ASSISTANT_FALLBACK="claude-sonnet-4-5",
            COMET_ASSISTANT_MODEL="gpt-5.4",
            COMET_ASSISTANT_FALLBACK="gpt-5.4-mini",
        ),
    )

    result = await assistant_service.generate_assistant_result(
        [{"role": "user", "content": "Hello"}]
    )

    assert result.text == "Claude answered"
    assert any(route.provider == llm.LLMProvider.KIE_CLAUDE for route in captured[0])


@pytest.mark.asyncio
async def test_strict_moderation_uses_json_schema(monkeypatch) -> None:
    captured: list[llm.LLMRequest] = []

    async def fake_call(routes, request, **kwargs):
        captured.append(request)
        return llm.LLMResult(
            text=(
                '{"decision":"manual_review","risk":"medium",'
                '"reason":"Ambiguous","recommendation":"Review"}'
            ),
            provider=llm.LLMProvider.COMET_CHAT,
            model="gpt-5.4",
        )

    monkeypatch.setattr(assistant_service.llm, "call_with_fallbacks", fake_call)

    decision = await assistant_service.generate_prompt_moderation_decision(
        prompt_text="Ambiguous prompt"
    )

    assert decision.decision == "manual_review"
    assert decision.provider == "comet_chat"
    assert captured[0].response_format["type"] == "json_schema"
    assert captured[0].response_format["json_schema"]["strict"] is True


@pytest.mark.asyncio
async def test_moderation_failure_forces_manual_review(monkeypatch) -> None:
    async def fail_call(routes, request, **kwargs):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(assistant_service.llm, "call_with_fallbacks", fail_call)

    decision = await assistant_service.generate_prompt_moderation_decision(
        prompt_text="Any prompt"
    )

    assert decision.decision == "manual_review"
    assert decision.risk == "medium"
    assert "provider failed" in decision.raw


def test_photo_prompt_rejects_unsupported_or_large_input() -> None:
    with pytest.raises(ValueError, match="Unsupported image MIME"):
        photo_prompt_service._validate_image(b"image", "application/pdf")
    with pytest.raises(ValueError, match="20 MB"):
        photo_prompt_service._validate_image(b"x" * (20 * 1024 * 1024 + 1), "image/png")


def test_photo_prompt_chat_uses_high_detail_image() -> None:
    messages = photo_prompt_service._photo_prompt_chat_messages(
        "data:image/png;base64,AAAA"
    )
    image_part = messages[1]["content"][0]
    assert image_part == {
        "type": "image_url",
        "image_url": {
            "url": "data:image/png;base64,AAAA",
            "detail": "high",
        },
    }
