"""Exact KIE/Comet LLM provider contracts for assistant, vision and tools."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import httpx


class LLMProvider(StrEnum):
    KIE_RESPONSES = "kie_responses"
    KIE_CLAUDE = "kie_claude"
    COMET_CHAT = "comet_chat"


class ReasoningEffort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"
    MAX = "max"


@dataclass(frozen=True)
class LLMRoute:
    provider: LLMProvider
    model: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: LLMProvider
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    tool_calls: tuple[dict[str, Any], ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMRequest:
    messages: tuple[dict[str, Any], ...]
    system_prompt: str = ""
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    web_search: bool = False
    function_tools: tuple[dict[str, Any], ...] = ()
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    max_output_tokens: int = 4096


def _required(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _validate_request(request: LLMRequest) -> None:
    if not request.messages:
        raise ValueError("messages are required")
    if request.web_search and request.function_tools:
        raise ValueError("KIE web_search and function calling are mutually exclusive")
    if request.max_output_tokens < 1 or request.max_output_tokens > 128_000:
        raise ValueError("max_output_tokens must be between 1 and 128000")
    for tool in request.function_tools:
        if not isinstance(tool, dict):
            raise TypeError("function tool must be an object")


def _normalize_role(value: Any, *, allow_system: bool = True) -> str:
    role = str(value or "user")
    allowed = {"user", "assistant", "system"} if allow_system else {"user", "assistant"}
    return role if role in allowed else "user"


def _responses_content(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        return [{"type": "input_text", "text": value}]
    if not isinstance(value, list):
        return [{"type": "input_text", "text": str(value or "")}]

    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            result.append({"type": "input_text", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "")
        if item_type in {"input_text", "text"}:
            result.append({"type": "input_text", "text": str(item.get("text") or "")})
        elif item_type in {"input_image", "image_url"}:
            image_value = item.get("image_url")
            if isinstance(image_value, dict):
                image_value = image_value.get("url")
            result.append(
                {
                    "type": "input_image",
                    "image_url": _required(str(image_value or ""), "image_url"),
                }
            )
        elif item_type in {"input_file", "file_url"}:
            file_value = item.get("file_url") or item.get("file_id")
            result.append(
                {
                    "type": "input_file",
                    "file_url": _required(str(file_value or ""), "file_url"),
                }
            )
        else:
            raise ValueError(f"Unsupported Responses content type: {item_type}")
    return result


def build_kie_responses_payload(model: str, request: LLMRequest) -> dict[str, Any]:
    _validate_request(request)
    input_messages: list[dict[str, Any]] = []
    if request.system_prompt:
        input_messages.append(
            {
                "role": "system",
                "content": [{"type": "input_text", "text": request.system_prompt}],
            }
        )
    for message in request.messages:
        input_messages.append(
            {
                "role": _normalize_role(message.get("role")),
                "content": _responses_content(message.get("content")),
            }
        )

    payload: dict[str, Any] = {
        "model": _required(model, "model"),
        "stream": False,
        "input": input_messages,
        "reasoning": {"effort": request.reasoning_effort.value},
    }
    if request.web_search:
        payload["tools"] = [{"type": "web_search"}]
        payload["tool_choice"] = request.tool_choice or "auto"
    elif request.function_tools:
        payload["tools"] = list(request.function_tools)
        payload["tool_choice"] = request.tool_choice or "auto"
    return payload


def _chat_content(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return str(value or "")
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            result.append({"type": "text", "text": item})
        elif isinstance(item, dict):
            item_type = str(item.get("type") or "")
            if item_type in {"text", "input_text"}:
                result.append({"type": "text", "text": str(item.get("text") or "")})
            elif item_type in {"image_url", "input_image"}:
                image_value = item.get("image_url")
                if isinstance(image_value, str):
                    image_value = {"url": image_value, "detail": item.get("detail") or "auto"}
                elif isinstance(image_value, dict):
                    image_value = dict(image_value)
                    image_value.setdefault("detail", item.get("detail") or "auto")
                else:
                    raise ValueError("image_url content requires a URL")
                result.append({"type": "image_url", "image_url": image_value})
            else:
                raise ValueError(f"Unsupported Chat content type: {item_type}")
    return result


def build_comet_chat_payload(model: str, request: LLMRequest) -> dict[str, Any]:
    _validate_request(request)
    messages: list[dict[str, Any]] = []
    if request.system_prompt:
        messages.append({"role": "developer", "content": request.system_prompt})
    for message in request.messages:
        messages.append(
            {
                "role": _normalize_role(message.get("role")),
                "content": _chat_content(message.get("content")),
            }
        )
    payload: dict[str, Any] = {
        "model": _required(model, "model"),
        "messages": messages,
        "stream": False,
        "max_completion_tokens": request.max_output_tokens,
        "reasoning_effort": (
            request.reasoning_effort.value
            if request.reasoning_effort not in {ReasoningEffort.XHIGH, ReasoningEffort.MAX}
            else ReasoningEffort.HIGH.value
        ),
    }
    if request.function_tools:
        payload["tools"] = list(request.function_tools)
        payload["tool_choice"] = request.tool_choice or "auto"
    elif request.web_search:
        # OpenAI-compatible Chat does not have a universal built-in web-search
        # tool contract. Callers should route web search to KIE Responses.
        raise ValueError("web_search requires a KIE Responses route")
    if request.response_format:
        payload["response_format"] = request.response_format
    return payload


def _claude_content(value: Any) -> Any:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return str(value or "")
    blocks: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            blocks.append({"type": "text", "text": item})
        elif isinstance(item, dict) and item.get("type") in {"text", "input_text"}:
            blocks.append({"type": "text", "text": str(item.get("text") or "")})
        else:
            raise ValueError("Claude fallback currently accepts text message blocks only")
    return blocks


def build_kie_claude_payload(model: str, request: LLMRequest) -> dict[str, Any]:
    _validate_request(request)
    if request.web_search:
        raise ValueError("KIE Claude route does not expose a built-in web_search tool")
    messages = [
        {
            "role": _normalize_role(message.get("role"), allow_system=False),
            "content": _claude_content(message.get("content")),
        }
        for message in request.messages
    ]
    payload: dict[str, Any] = {
        "model": _required(model, "model"),
        "messages": messages,
        "stream": False,
        "max_tokens": request.max_output_tokens,
        "thinkingFlag": request.reasoning_effort in {
            ReasoningEffort.HIGH,
            ReasoningEffort.XHIGH,
            ReasoningEffort.MAX,
        },
    }
    if request.system_prompt:
        payload["system"] = request.system_prompt
    if request.function_tools:
        tools: list[dict[str, Any]] = []
        for tool in request.function_tools:
            if tool.get("type") == "function" and isinstance(tool.get("function"), dict):
                function = tool["function"]
                tools.append(
                    {
                        "name": _required(function.get("name"), "tool name"),
                        "description": str(function.get("description") or ""),
                        "input_schema": function.get("parameters") or {"type": "object"},
                    }
                )
            else:
                tools.append(dict(tool))
        payload["tools"] = tools
    return payload


def _extract_responses_result(payload: dict[str, Any], route: LLMRoute) -> LLMResult:
    if payload.get("code") not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"KIE Responses error: {payload!r}")
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "message":
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("type") == "output_text":
                    if content.get("text"):
                        text_parts.append(str(content["text"]))
        elif item.get("type") in {"function_call", "tool_call"}:
            tool_calls.append(dict(item))
    text = "\n".join(part.strip() for part in text_parts if part.strip()).strip()
    if not text and not tool_calls:
        raise RuntimeError(f"KIE Responses returned neither text nor tool calls: {payload!r}")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return LLMResult(text=text, provider=route.provider, model=route.model, usage=usage, tool_calls=tuple(tool_calls), raw=payload)


def _extract_chat_result(payload: dict[str, Any], route: LLMRoute) -> LLMResult:
    if payload.get("code") not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"Comet Chat error: {payload!r}")
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise RuntimeError(f"Comet Chat response has no choices: {payload!r}")
    message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "\n".join(
            str(item.get("text") or "").strip()
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ).strip()
    else:
        text = ""
    tool_calls = tuple(
        dict(item) for item in (message.get("tool_calls") or []) if isinstance(item, dict)
    )
    if not text and not tool_calls:
        raise RuntimeError(f"Comet Chat returned neither text nor tool calls: {payload!r}")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return LLMResult(text=text, provider=route.provider, model=route.model, usage=usage, tool_calls=tool_calls, raw=payload)


def _extract_claude_result(payload: dict[str, Any], route: LLMRoute) -> LLMResult:
    if payload.get("error"):
        raise RuntimeError(f"KIE Claude error: {payload!r}")
    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in payload.get("content") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and item.get("text"):
            text_parts.append(str(item["text"]))
        elif item.get("type") == "tool_use":
            tool_calls.append(dict(item))
    text = "\n".join(part.strip() for part in text_parts if part.strip()).strip()
    if not text and not tool_calls:
        raise RuntimeError(f"KIE Claude returned neither text nor tool calls: {payload!r}")
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    return LLMResult(text=text, provider=route.provider, model=route.model, usage=usage, tool_calls=tuple(tool_calls), raw=payload)


async def call_route(
    route: LLMRoute,
    request: LLMRequest,
    *,
    kie_api_key: str,
    comet_api_key: str,
    comet_base_url: str = "https://api.cometapi.com",
    timeout_seconds: float = 90,
) -> LLMResult:
    headers = {"Content-Type": "application/json"}
    if route.provider == LLMProvider.KIE_RESPONSES:
        url = "https://api.kie.ai/codex/v1/responses"
        headers["Authorization"] = f"Bearer {kie_api_key}"
        payload = build_kie_responses_payload(route.model, request)
        extractor = _extract_responses_result
    elif route.provider == LLMProvider.KIE_CLAUDE:
        url = "https://api.kie.ai/claude/v1/messages"
        headers["Authorization"] = f"Bearer {kie_api_key}"
        payload = build_kie_claude_payload(route.model, request)
        extractor = _extract_claude_result
    elif route.provider == LLMProvider.COMET_CHAT:
        url = f"{comet_base_url.rstrip('/')}/v1/chat/completions"
        headers["Authorization"] = f"Bearer {comet_api_key}"
        payload = build_comet_chat_payload(route.model, request)
        extractor = _extract_chat_result
    else:
        raise ValueError(f"Unsupported LLM provider: {route.provider}")

    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"{route.provider} returned non-object JSON: {data!r}")
    return extractor(data, route)


async def call_with_fallbacks(
    routes: list[LLMRoute] | tuple[LLMRoute, ...],
    request: LLMRequest,
    *,
    kie_api_key: str,
    comet_api_key: str,
    comet_base_url: str = "https://api.cometapi.com",
) -> LLMResult:
    errors: list[str] = []
    for route in routes:
        try:
            return await call_route(
                route,
                request,
                kie_api_key=kie_api_key,
                comet_api_key=comet_api_key,
                comet_base_url=comet_base_url,
            )
        except Exception as exc:
            errors.append(f"{route.provider.value}/{route.model}: {exc}")
    raise RuntimeError("All LLM routes failed: " + " | ".join(errors))


def strict_json_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _required(name, "schema name"),
            "strict": True,
            "schema": schema,
        },
    }


def parse_strict_json(result: LLMResult) -> dict[str, Any]:
    try:
        parsed = json.loads(result.text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Structured LLM output is not valid JSON: {result.text!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Structured LLM output must be a JSON object")
    return parsed