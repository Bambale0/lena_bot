from __future__ import annotations

import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_KIE_BASE = "https://api.kie.ai"

_SYSTEM_PROMPT = (
    "Ты — AI-ассистент внутри Telegram-бота APIX. "
    "Помогай кратко, по делу и дружелюбно. "
    "Ты хорошо разбираешься в генерации изображений, видео, музыки, Midjourney, промптах, оплатах, референсах и сценариях использования APIX. "
    "Если вопрос не про APIX, всё равно старайся помочь как обычный полезный ассистент. "
    "Не придумывай факты о состоянии аккаунта пользователя, если их нет в сообщениях. "
    "Отвечай на языке пользователя. Обычно это русский. "
    "Держи ответы компактными, но полезными."
)


async def generate_assistant_reply(messages: list[dict[str, str]]) -> str:
    seen: set[str] = set()
    models: list[str] = []
    for model in (settings.KIE_ASSISTANT_MODEL, settings.KIE_ASSISTANT_FALLBACK, "gpt-5-5"):
        if model and model not in seen:
            seen.add(model)
            models.append(model)

    for model in models:
        try:
            return await _call_kie_responses(model, messages)
        except Exception as exc:
            logger.warning("assistant: %s responses failed — %s", model, exc)
        try:
            return await _call_kie_chat(model, messages)
        except Exception as exc:
            logger.warning("assistant: %s chat fallback failed — %s", model, exc)
    raise RuntimeError("Assistant models are unavailable right now.")


def _to_input_messages(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    input_messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": _SYSTEM_PROMPT}],
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


async def _call_kie_responses(model: str, messages: list[dict[str, str]]) -> str:
    url = f"{_KIE_BASE}/codex/v1/responses"
    payload = {
        "model": model,
        "stream": False,
        "input": _to_input_messages(messages),
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


async def _call_kie_chat(model: str, messages: list[dict[str, str]]) -> str:
    url = f"{_KIE_BASE}/{model}/v1/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            *[
                {
                    "role": (item.get("role") or "user") if (item.get("role") or "user") in {"user", "assistant", "system"} else "user",
                    "content": item.get("content", ""),
                }
                for item in messages[-12:]
            ],
        ],
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
