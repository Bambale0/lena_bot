from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

# Kept as a module attribute for backward-compatible tests and monkeypatches.
import httpx

from api import llm_provider_service as llm
from core.config import settings

logger = logging.getLogger(__name__)

_COMET_DEFAULT_ASSISTANT_MODEL = "gpt-5.4"
_COMET_DEFAULT_ASSISTANT_FALLBACK = "gpt-5.4-mini"

_SYSTEM_PROMPT = (
    "Ты — AI-ассистент внутри Telegram-бота APIX. "
    "Помогай кратко, по делу и дружелюбно. "
    "Ты хорошо разбираешься в генерации изображений, видео, музыки, Midjourney, "
    "промптах, оплатах, референсах и сценариях использования APIX. "
    "Если вопрос не про APIX, всё равно старайся помочь как обычный полезный ассистент. "
    "Не придумывай факты о состоянии аккаунта пользователя, если их нет в сообщениях. "
    "Отвечай на языке пользователя. Обычно это русский. "
    "Держи ответы компактными, но полезными."
)

_ADMIN_SYSTEM_PROMPT = (
    "Пользователь может быть администратором APIX. "
    "Если он спрашивает про модерацию, жалобы, баны, выплаты, промпты на проверке "
    "или админские сценарии, отвечай как опытный модератор и операционный помощник. "
    "Не обещай, что уже выполнил действие, если из контекста не видно результата."
)

_PROMPT_MODERATION_SYSTEM_PROMPT = (
    "Ты — AI-модератор Telegram-бота APIX и витрины пользовательских промптов. "
    "Оцени текст на спам, мошенничество, агрессию, незаконный или опасный контент, "
    "явно сексуальный контент, шок-контент, бессмысленный мусор и попытки обмана. "
    "Если данных недостаточно или случай спорный, выбирай ручную проверку."
)

_MODERATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["approve", "reject", "manual_review"],
        },
        "risk": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "reason": {"type": "string"},
        "recommendation": {"type": "string"},
    },
    "required": ["decision", "risk", "reason", "recommendation"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class PromptModerationDecision:
    decision: str
    risk: str
    reason: str
    recommendation: str
    raw: str
    provider: str = ""
    model: str = ""


@dataclass(frozen=True)
class AssistantReply:
    text: str
    provider: str
    model: str
    usage: dict[str, Any]
    tool_calls: tuple[dict[str, Any], ...] = ()


def _normalize_comet_text_model(model: str | None) -> str | None:
    value = str(model or "").strip()
    if not value:
        return None
    parts = value.split("-")
    if len(parts) >= 3 and parts[0] == "gpt" and parts[1].isdigit() and parts[2].isdigit():
        return f"gpt-{parts[1]}.{parts[2]}" + (
            "-" + "-".join(parts[3:]) if len(parts) > 3 else ""
        )
    return value


def _kie_route(model: str) -> llm.LLMRoute:
    provider = (
        llm.LLMProvider.KIE_CLAUDE
        if str(model).startswith("claude-")
        else llm.LLMProvider.KIE_RESPONSES
    )
    return llm.LLMRoute(provider=provider, model=str(model))


def _assistant_routes(*, web_search: bool = False) -> list[llm.LLMRoute]:
    routes: list[llm.LLMRoute] = []
    seen: set[tuple[str, str]] = set()

    for model in (
        getattr(settings, "KIE_ASSISTANT_MODEL", ""),
        getattr(settings, "KIE_ASSISTANT_FALLBACK", ""),
    ):
        value = str(model or "").strip()
        if not value:
            continue
        route = _kie_route(value)
        # Claude does not expose built-in web search through this KIE route.
        if web_search and route.provider == llm.LLMProvider.KIE_CLAUDE:
            continue
        key = (route.provider.value, route.model)
        if key not in seen:
            seen.add(key)
            routes.append(route)

    if web_search:
        return routes

    for model in (
        getattr(settings, "COMET_ASSISTANT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_FALLBACK", None),
        _normalize_comet_text_model(getattr(settings, "KIE_ASSISTANT_MODEL", None)),
        _normalize_comet_text_model(getattr(settings, "KIE_ASSISTANT_FALLBACK", None)),
        _COMET_DEFAULT_ASSISTANT_MODEL,
        _COMET_DEFAULT_ASSISTANT_FALLBACK,
    ):
        value = _normalize_comet_text_model(model)
        if not value:
            continue
        route = llm.LLMRoute(llm.LLMProvider.COMET_CHAT, value)
        key = (route.provider.value, route.model)
        if key not in seen:
            seen.add(key)
            routes.append(route)
    return routes


def _moderation_routes() -> list[llm.LLMRoute]:
    models = [
        getattr(settings, "COMET_ASSISTANT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_FALLBACK", None),
        _COMET_DEFAULT_ASSISTANT_MODEL,
        _COMET_DEFAULT_ASSISTANT_FALLBACK,
    ]
    result: list[llm.LLMRoute] = []
    seen: set[str] = set()
    for model in models:
        value = _normalize_comet_text_model(model)
        if value and value not in seen:
            seen.add(value)
            result.append(llm.LLMRoute(llm.LLMProvider.COMET_CHAT, value))
    return result


def _request_messages(messages: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    normalized: list[dict[str, Any]] = []
    for item in messages[-12:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")
        if role not in {"user", "assistant", "system"}:
            role = "user"
        normalized.append({"role": role, "content": item.get("content", "")})
    if not normalized:
        raise ValueError("At least one assistant message is required")
    return tuple(normalized)


async def generate_assistant_result(
    messages: list[dict[str, Any]],
    *,
    admin_mode: bool = False,
    web_search: bool = False,
    function_tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    reasoning_effort: llm.ReasoningEffort = llm.ReasoningEffort.MEDIUM,
) -> AssistantReply:
    system_prompt = _SYSTEM_PROMPT
    if admin_mode:
        system_prompt = f"{system_prompt} {_ADMIN_SYSTEM_PROMPT}"

    request = llm.LLMRequest(
        messages=_request_messages(messages),
        system_prompt=system_prompt,
        reasoning_effort=reasoning_effort,
        web_search=bool(web_search),
        function_tools=tuple(function_tools or ()),
        tool_choice=tool_choice,
    )
    result = await llm.call_with_fallbacks(
        _assistant_routes(web_search=web_search),
        request,
        kie_api_key=str(getattr(settings, "KIE_AI_KEY", "")),
        comet_api_key=str(getattr(settings, "COMET_API_KEY", "")),
        comet_base_url=str(
            getattr(settings, "COMET_BASE_URL", "https://api.cometapi.com")
        ),
    )
    text = sanitize_assistant_reply(result.text)
    logger.info(
        "assistant generated via provider=%s model=%s",
        result.provider.value,
        result.model,
    )
    return AssistantReply(
        text=text,
        provider=result.provider.value,
        model=result.model,
        usage=dict(result.usage),
        tool_calls=result.tool_calls,
    )


async def generate_assistant_reply(
    messages: list[dict[str, Any]],
    *,
    admin_mode: bool = False,
) -> str:
    return (await generate_assistant_result(messages, admin_mode=admin_mode)).text


def sanitize_assistant_reply(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "Готово. Чем ещё помочь?"
    text = text.removeprefix("КОНТЕКСТ").removeprefix("CONTEXT").strip()
    lines = text.splitlines()
    has_debug_shape = any(
        line.strip().lower().startswith(("role:", "content:")) for line in lines
    )
    if has_debug_shape:
        lines = [
            line.strip()
            for line in lines
            if line.strip()
            and not line.strip().lower().startswith(("role:", "content:"))
            and not line.strip().startswith('[{"type":"input_text"')
        ]
        text = "\n".join(lines).strip()
    return text or "Готово. Чем ещё помочь?"


def _moderation_details(
    *,
    prompt_id: int | None,
    title: str,
    description: str,
    prompt_text: str,
    tags: list[str] | None,
    model: str | None,
    extra_context: str | None = None,
) -> str:
    return "\n".join(
        [
            f"ID: {prompt_id if prompt_id is not None else '—'}",
            f"Название: {title or '—'}",
            f"Описание: {description or '—'}",
            f"Модель: {model or '—'}",
            f"Теги: {', '.join(tags or []) or '—'}",
            f"Контекст: {extra_context or '—'}",
            "Текст промпта:",
            prompt_text or "—",
        ]
    )


async def generate_prompt_moderation_review(
    *,
    prompt_id: int,
    title: str,
    description: str,
    prompt_text: str,
    tags: list[str] | None,
    model: str | None,
) -> str:
    details = _moderation_details(
        prompt_id=prompt_id,
        title=title,
        description=description,
        prompt_text=prompt_text,
        tags=tags,
        model=model,
    )
    reply = await generate_assistant_result(
        [{"role": "user", "content": details}],
        reasoning_effort=llm.ReasoningEffort.MEDIUM,
    )
    return reply.text


async def generate_freeform_prompt_moderation_review(
    *,
    prompt_text: str,
    model: str | None = None,
    extra_context: str | None = None,
) -> str:
    details = _moderation_details(
        prompt_id=None,
        title="",
        description="",
        prompt_text=prompt_text,
        tags=None,
        model=model,
        extra_context=extra_context,
    )
    reply = await generate_assistant_result(
        [{"role": "user", "content": details}],
        reasoning_effort=llm.ReasoningEffort.MEDIUM,
    )
    return reply.text


async def generate_prompt_moderation_decision(
    *,
    prompt_id: int | None = None,
    title: str = "",
    description: str = "",
    prompt_text: str,
    tags: list[str] | None = None,
    model: str | None = None,
) -> PromptModerationDecision:
    details = _moderation_details(
        prompt_id=prompt_id,
        title=title,
        description=description,
        prompt_text=prompt_text,
        tags=tags,
        model=model,
    )
    request = llm.LLMRequest(
        messages=({"role": "user", "content": details},),
        system_prompt=_PROMPT_MODERATION_SYSTEM_PROMPT,
        reasoning_effort=llm.ReasoningEffort.MEDIUM,
        response_format=llm.strict_json_schema("prompt_moderation", _MODERATION_SCHEMA),
    )
    try:
        result = await llm.call_with_fallbacks(
            _moderation_routes(),
            request,
            kie_api_key=str(getattr(settings, "KIE_AI_KEY", "")),
            comet_api_key=str(getattr(settings, "COMET_API_KEY", "")),
            comet_base_url=str(
                getattr(settings, "COMET_BASE_URL", "https://api.cometapi.com")
            ),
        )
        payload = llm.parse_strict_json(result)
        return PromptModerationDecision(
            decision=str(payload["decision"]),
            risk=str(payload["risk"]),
            reason=str(payload["reason"]).strip(),
            recommendation=str(payload["recommendation"]).strip(),
            raw=result.text,
            provider=result.provider.value,
            model=result.model,
        )
    except Exception as exc:
        logger.exception("Strict prompt moderation failed; forcing manual review")
        return PromptModerationDecision(
            decision="manual_review",
            risk="medium",
            reason="Автоматическая проверка не завершилась надёжно.",
            recommendation="Отправить промпт на ручную проверку.",
            raw=str(exc),
        )


def _parse_prompt_moderation_json(raw: str) -> dict[str, Any]:
    """Backward-compatible strict parser used by older callers/tests."""
    try:
        parsed = json.loads(str(raw or "").strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Prompt moderation decision parse failed: {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Prompt moderation decision must be a JSON object")
    return parsed


def _extract_chat_output_text(data: dict[str, Any]) -> str:
    route = llm.LLMRoute(llm.LLMProvider.COMET_CHAT, "compat")
    return llm._extract_chat_result(data, route).text


async def _generate_text_reply(
    messages: list[dict[str, Any]],
    *,
    system_prompt: str,
) -> str:
    request = llm.LLMRequest(
        messages=_request_messages(messages),
        system_prompt=system_prompt,
    )
    result = await llm.call_with_fallbacks(
        _assistant_routes(),
        request,
        kie_api_key=str(getattr(settings, "KIE_AI_KEY", "")),
        comet_api_key=str(getattr(settings, "COMET_API_KEY", "")),
        comet_base_url=str(
            getattr(settings, "COMET_BASE_URL", "https://api.cometapi.com")
        ),
    )
    return result.text
