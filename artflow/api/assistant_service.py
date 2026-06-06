from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from api import openrouter_client
from core.config import settings

logger = logging.getLogger(__name__)

_KIE_BASE = "https://api.kie.ai"
_COMET_DEFAULT_ASSISTANT_MODEL = "gpt-5.4"
_COMET_DEFAULT_ASSISTANT_FALLBACK = "gpt-5.4-mini"

_SYSTEM_PROMPT = (
    "Ты — AI-ассистент внутри Telegram-бота APIX. "
    "Помогай кратко, по делу и дружелюбно. "
    "Ты хорошо разбираешься в генерации изображений, видео, музыки, Midjourney, промптах, оплатах, референсах и сценариях использования APIX. "
    "Если вопрос не про APIX, всё равно старайся помочь как обычный полезный ассистент. "
    "Не придумывай факты о состоянии аккаунта пользователя, если их нет в сообщениях. "
    "Отвечай на языке пользователя. Обычно это русский. "
    "Держи ответы компактными, но полезными."
)

_ADMIN_SYSTEM_PROMPT = (
    "Пользователь может быть администратором APIX. "
    "Если он спрашивает про модерацию, жалобы, баны, выплаты, промпты на проверке или админские сценарии, "
    "отвечай как опытный модератор и операционный помощник. "
    "Не обещай, что уже выполнил действие, если из контекста не видно результата."
)

_PROMPT_MODERATION_SYSTEM_PROMPT = (
    "Ты — AI-модератор Telegram-бота APIX и витрины пользовательских промптов. "
    "Твоя задача — дать рекомендацию модератору по конкретному промпту. "
    "Оцени текст на предмет спама, мошенничества, агрессии, незаконного или опасного контента, "
    "явно сексуального контента, бессмысленного мусора, очень низкого качества и попыток обмана пользователей. "
    "Если данных недостаточно или случай спорный, выбирай ручную проверку, а не категоричный отказ. "
    "Ответ верни на русском, компактно, в формате:\n"
    "Вердикт: ...\n"
    "Причины: ...\n"
    "Риск: низкий/средний/высокий\n"
    "Рекомендация: ..."
)


_PROMPT_MODERATION_DECISION_SYSTEM_PROMPT = (
    "Ты — автоматический AI-модератор Telegram-бота APIX. "
    "Тебе нужно принять решение по пользовательскому промпту для публикации в витрине. "
    "Проверяй спам, мошенничество, манипуляции, незаконный и опасный контент, явную сексуализацию, "
    "шок-контент, бессмысленный мусор, токсичный abuse-контент и попытки обмануть пользователей. "
    "Если промпт нормальный, полезный и безопасный — approve. "
    "Если промпт явно плохой или нарушает правила — reject. "
    "Если случай спорный или контекста мало — manual_review. "
    "Верни СТРОГО JSON без markdown и без пояснений вокруг, формат: "
    '{"decision":"approve|reject|manual_review","risk":"low|medium|high","reason":"...","recommendation":"..."}'
)


@dataclass(frozen=True)
class PromptModerationDecision:
    decision: str
    risk: str
    reason: str
    recommendation: str
    raw: str


async def generate_assistant_reply(messages: list[dict[str, str]], *, admin_mode: bool = False) -> str:
    system_prompt = _SYSTEM_PROMPT
    if admin_mode:
        system_prompt = f"{system_prompt} {_ADMIN_SYSTEM_PROMPT}"
    return await _generate_text_reply(messages, system_prompt=system_prompt)


async def generate_prompt_moderation_review(
    *,
    prompt_id: int,
    title: str,
    description: str,
    prompt_text: str,
    tags: list[str] | None,
    model: str | None,
) -> str:
    details = [
        f"ID: {prompt_id}",
        f"Название: {title or '—'}",
        f"Описание: {description or '—'}",
        f"Модель: {model or '—'}",
        f"Теги: {', '.join(tags or []) or '—'}",
        "Текст промпта:",
        prompt_text or "—",
    ]
    return await _generate_text_reply(
        [{"role": "user", "content": "\n".join(details)}],
        system_prompt=_PROMPT_MODERATION_SYSTEM_PROMPT,
    )


async def generate_freeform_prompt_moderation_review(
    *,
    prompt_text: str,
    model: str | None = None,
    extra_context: str | None = None,
) -> str:
    details = [
        "Режим: проверка произвольного промпта перед генерацией",
        f"Модель: {model or '—'}",
        f"Контекст: {extra_context or '—'}",
        "Текст промпта:",
        prompt_text or "—",
    ]
    return await _generate_text_reply(
        [{"role": "user", "content": "\n".join(details)}],
        system_prompt=_PROMPT_MODERATION_SYSTEM_PROMPT,
    )


async def generate_prompt_moderation_decision(
    *,
    prompt_id: int | None = None,
    title: str = "",
    description: str = "",
    prompt_text: str,
    tags: list[str] | None = None,
    model: str | None = None,
) -> PromptModerationDecision:
    details = [
        f"ID: {prompt_id if prompt_id is not None else '—'}",
        f"Название: {title or '—'}",
        f"Описание: {description or '—'}",
        f"Модель: {model or '—'}",
        f"Теги: {', '.join(tags or []) or '—'}",
        "Текст промпта:",
        prompt_text or "—",
    ]
    raw = await _generate_text_reply(
        [{"role": "user", "content": "\n".join(details)}],
        system_prompt=_PROMPT_MODERATION_DECISION_SYSTEM_PROMPT,
    )
    payload = _parse_prompt_moderation_json(raw)
    decision = str(payload.get("decision") or "manual_review").strip().lower()
    if decision not in {"approve", "reject", "manual_review"}:
        decision = "manual_review"
    risk = str(payload.get("risk") or "medium").strip().lower()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"
    reason = str(payload.get("reason") or "Недостаточно уверенный ответ модели.").strip()
    recommendation = str(payload.get("recommendation") or "Отправить на ручную проверку.").strip()
    return PromptModerationDecision(
        decision=decision,
        risk=risk,
        reason=reason,
        recommendation=recommendation,
        raw=raw,
    )


def _parse_prompt_moderation_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start:end + 1]
        parsed = json.loads(snippet)
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError(f"Prompt moderation decision parse failed: {raw!r}")


async def _generate_text_reply(messages: list[dict[str, str]], *, system_prompt: str) -> str:
    """Try the fastest known-good providers first.

    KIE currently serves the Responses API for GPT-style assistant models, but its
    chat-completions fallback for the same model family returns 422 unsupported,
    and the KIE Claude endpoint has been intermittently failing with 404/500.
    To keep assistant replies fast and reliable in production, we only use the
    KIE Responses path here and fall back directly to CometAPI text models.
    """
    if openrouter_client.force_migrated_models() and not openrouter_client.configured():
        raise RuntimeError("OpenRouter is forced for assistant replies, but OPENROUTER_API_KEY is not configured")

    if openrouter_client.configured():
        openrouter_errors: list[str] = []
        for model in _openrouter_assistant_models():
            try:
                reply = await _call_openrouter_chat(model, messages, system_prompt=system_prompt)
                logger.info("assistant: generated via OpenRouter %s", model)
                return reply
            except Exception as exc:
                openrouter_errors.append(f"{model}: {exc}")
                logger.warning("assistant: OpenRouter %s failed — %s", model, exc)
        if openrouter_client.force_migrated_models():
            raise RuntimeError(
                "Assistant OpenRouter models are unavailable: "
                + ("; ".join(openrouter_errors) if openrouter_errors else "no OpenRouter models configured")
            )

    seen: set[str] = set()
    kie_models: list[str] = []
    for model in (settings.KIE_ASSISTANT_MODEL, settings.KIE_ASSISTANT_FALLBACK):
        if not model or model in seen:
            continue
        seen.add(model)
        if str(model).startswith("claude-"):
            logger.info("assistant: skipping KIE Claude fallback for %s; using Comet fallback instead", model)
            continue
        kie_models.append(model)

    for model in kie_models:
        try:
            return await _call_kie_responses(model, messages, system_prompt=system_prompt)
        except Exception as exc:
            logger.warning("assistant: %s responses failed — %s", model, exc)

    for model in _comet_assistant_models():
        try:
            reply = await _call_comet_chat(model, messages, system_prompt=system_prompt)
            logger.info("assistant: generated via CometAPI %s", model)
            return reply
        except Exception as exc:
            logger.warning("assistant: CometAPI %s fallback failed — %s", model, exc)

    raise RuntimeError("Assistant models are unavailable right now.")


def _normalize_comet_text_model(model: str | None) -> str | None:
    value = str(model or "").strip()
    if not value:
        return None
    parts = value.split("-")
    if len(parts) >= 3 and parts[0] == "gpt" and parts[1].isdigit() and parts[2].isdigit():
        return f"gpt-{parts[1]}.{parts[2]}" + ("-" + "-".join(parts[3:]) if len(parts) > 3 else "")
    return value


def _comet_assistant_models() -> list[str]:
    candidates = [
        getattr(settings, "COMET_ASSISTANT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_FALLBACK", None),
        _normalize_comet_text_model(getattr(settings, "KIE_ASSISTANT_MODEL", None)),
        _normalize_comet_text_model(getattr(settings, "KIE_ASSISTANT_FALLBACK", None)),
        _COMET_DEFAULT_ASSISTANT_MODEL,
        _COMET_DEFAULT_ASSISTANT_FALLBACK,
    ]
    models: list[str] = []
    seen: set[str] = set()
    for model in candidates:
        normalized = _normalize_comet_text_model(model)
        if normalized and normalized not in seen:
            seen.add(normalized)
            models.append(normalized)
    return models


def _openrouter_assistant_models() -> list[str]:
    candidates = [
        getattr(settings, "KIE_ASSISTANT_MODEL", None),
        getattr(settings, "KIE_ASSISTANT_FALLBACK", None),
        getattr(settings, "COMET_ASSISTANT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_FALLBACK", None),
        _COMET_DEFAULT_ASSISTANT_MODEL,
        _COMET_DEFAULT_ASSISTANT_FALLBACK,
    ]
    models: list[str] = []
    seen: set[str] = set()
    for model in candidates:
        normalized = openrouter_client.text_model_for_source(model)
        if normalized and normalized not in seen:
            seen.add(normalized)
            models.append(normalized)
    return models


def _to_input_messages(messages: list[dict[str, str]], *, system_prompt: str) -> list[dict[str, Any]]:
    input_messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        }
    ]
    for item in messages[-12:]:
        role = item.get("role") or "user"
        if role not in {"user", "assistant", "system"}:
            role = "user"
        input_messages.append(
            {
                "role": role,
                "content": [{"type": "input_text", "text": item.get("content", "")}],
            }
        )
    return input_messages


def _extract_output_text(data: dict[str, Any]) -> str:
    if data.get("code") and data.get("code") != 200:
        raise RuntimeError(f"{data!r}")
    output = data.get("output") or []
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                return str(content["text"]).strip()
    raise RuntimeError(f"Assistant response did not contain output_text: {data!r}")


def _extract_chat_output_text(data: dict[str, Any]) -> str:
    if data.get("code") and data.get("code") != 200:
        raise RuntimeError(f"{data!r}")

    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError(f"Assistant chat response did not contain choices: {data!r}")

    content = ((choices[0] or {}).get("message") or {}).get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]).strip())
        text = "\n".join(part for part in parts if part).strip()
        if text:
            return text
    raise RuntimeError(f"Assistant chat response did not contain text: {data!r}")


def _to_chat_messages(messages: list[dict[str, str]], *, system_prompt: str) -> list[dict[str, str]]:
    chat_messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for item in messages[-12:]:
        role = item.get("role") or "user"
        if role not in {"user", "assistant", "system"}:
            role = "user"
        chat_messages.append({"role": role, "content": item.get("content", "")})
    return chat_messages


async def _call_kie_responses(model: str, messages: list[dict[str, str]], *, system_prompt: str) -> str:
    url = f"{_KIE_BASE}/codex/v1/responses"
    payload = {
        "model": model,
        "stream": False,
        "input": _to_input_messages(messages, system_prompt=system_prompt),
        "reasoning": {"effort": "medium"},
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.KIE_AI_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return _extract_output_text(resp.json())


async def _call_kie_claude(model: str, messages: list[dict[str, str]], *, system_prompt: str) -> str:
    url = f"{_KIE_BASE}/claude/v1/messages"
    payload = {
        "model": model,
        "messages": [
            *[
                {
                    "role": (item.get("role") or "user") if (item.get("role") or "user") in {"user", "assistant"} else "user",
                    "content": item.get("content", ""),
                }
                for item in messages[-12:]
            ]
        ],
        "thinkingFlag": True,
        "stream": False,
        "max_tokens": 4096,
    }
    if system_prompt:
        payload["messages"] = [{"role": "user", "content": system_prompt}, *payload["messages"]]

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.KIE_AI_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"{data!r}")
        content = data.get("content") or []
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]).strip())
        text_out = "\n".join(part for part in parts if part).strip()
        if text_out:
            return text_out
        raise RuntimeError(f"Assistant claude response did not contain text: {data!r}")


async def _call_kie_chat(model: str, messages: list[dict[str, str]], *, system_prompt: str) -> str:
    url = f"{_KIE_BASE}/{model}/v1/chat/completions"
    payload = {
        "messages": _to_chat_messages(messages, system_prompt=system_prompt),
        "reasoning_effort": "medium",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.KIE_AI_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return _extract_chat_output_text(resp.json())


async def _call_comet_chat(model: str, messages: list[dict[str, str]], *, system_prompt: str) -> str:
    url = f"{str(getattr(settings, 'COMET_BASE_URL', 'https://api.cometapi.com')).rstrip('/')}/v1/chat/completions"
    payload: dict[str, Any] = {
        "model": model,
        "messages": _to_chat_messages(messages, system_prompt=system_prompt),
        "stream": False,
        "max_completion_tokens": 4096,
    }
    if model.startswith("gpt-"):
        payload["reasoning_effort"] = "medium"

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {getattr(settings, 'COMET_API_KEY', '')}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return _extract_chat_output_text(resp.json())


async def _call_openrouter_chat(model: str, messages: list[dict[str, str]], *, system_prompt: str) -> str:
    payload = await openrouter_client.chat_completion(
        model=model,
        messages=_to_chat_messages(messages, system_prompt=system_prompt),
        max_completion_tokens=4096,
        reasoning_effort="medium",
    )
    return _extract_chat_output_text(payload)
