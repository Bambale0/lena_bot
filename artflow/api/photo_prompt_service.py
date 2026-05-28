"""Generate a detailed image recreation prompt from a photo via KIE.AI, with CometAPI fallback."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_KIE_BASE = "https://api.kie.ai"

_SYSTEM_PROMPT = (
    "Ты — эксперт по промптам для AI-генерации изображений. "
    "Проанализируй предоставленное изображение и создай единственный, детальный промпт, "
    "который позволит AI-генератору воссоздать его максимально точно. "
    "Опиши: главный объект и элементы, художественный стиль и технику, "
    "композицию и кадрирование, освещение и тени, цветовую палитру, "
    "настроение и атмосферу, текстуры, детали, угол камеры и перспективу. "
    "Выведи ТОЛЬКО текст промпта на русском языке, без пояснений и лишних слов."
)


async def generate_prompt_from_photo(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Call KIE.AI vision models first, then CometAPI fallback."""
    b64 = base64.b64encode(image_bytes).decode()
    image_data_url = f"data:{mime_type};base64,{b64}"

    for model in (settings.KIE_PHOTO_PROMPT_MODEL, settings.KIE_PHOTO_PROMPT_FALLBACK):
        try:
            result = await _call_kie_gpt(model, image_data_url)
            logger.info("photo_prompt: generated via %s (%d chars)", model, len(result))
            return result
        except Exception as exc:
            logger.warning("photo_prompt: %s failed — %s", model, exc)

    for model in _comet_photo_prompt_models():
        try:
            result = await _call_comet_gpt(model, image_data_url)
            logger.info("photo_prompt: generated via CometAPI %s (%d chars)", model, len(result))
            return result
        except Exception as exc:
            logger.warning("photo_prompt: CometAPI %s fallback failed — %s", model, exc)

    raise RuntimeError("Photo prompt models failed to generate a prompt.")


def _normalize_comet_model(model: str | None) -> str | None:
    value = str(model or "").strip()
    if not value:
        return None
    parts = value.split("-")
    if len(parts) >= 3 and parts[0] == "gpt" and parts[1].isdigit() and parts[2].isdigit():
        return f"gpt-{parts[1]}.{parts[2]}" + ("-" + "-".join(parts[3:]) if len(parts) > 3 else "")
    return value


def _comet_photo_prompt_models() -> list[str]:
    candidates = [
        _normalize_comet_model(getattr(settings, "KIE_PHOTO_PROMPT_MODEL", None)),
        _normalize_comet_model(getattr(settings, "KIE_PHOTO_PROMPT_FALLBACK", None)),
        getattr(settings, "COMET_ASSISTANT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_FALLBACK", None),
    ]
    models: list[str] = []
    seen: set[str] = set()
    for model in candidates:
        value = str(model or "").strip()
        if value and value not in seen:
            seen.add(value)
            models.append(value)
    return models


def _extract_kie_text(data: Any) -> str:
    if not isinstance(data, dict):
        raise KeyError("response is not a JSON object")

    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
                    elif isinstance(item, str) and item.strip():
                        parts.append(item.strip())
                if parts:
                    return "\n".join(parts).strip()

    for key in ("output_text", "text", "answer", "response"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    result = data.get("data")
    if isinstance(result, dict):
        for key in ("output_text", "text", "answer", "response"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    raise KeyError("choices")


async def _call_kie_gpt(model: str, image_data_url: str) -> str:
    # KIE endpoint: POST https://api.kie.ai/{model}/v1/chat/completions
    url = f"{_KIE_BASE}/{model}/v1/chat/completions"

    payload = {
        "messages": [
            {
                "role": "system",
                "content": [{"type": "text", "text": _SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Проанализируй это изображение и создай детальный промпт "
                            "на русском языке, который позволит воссоздать изображение максимально точно."
                        ),
                    },
                ],
            },
        ],
        "reasoning_effort": "high",
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
        data = resp.json()
        try:
            return _extract_kie_text(data)
        except Exception:
            logger.warning(
                "photo_prompt: unexpected %s response: %s",
                model,
                json.dumps(data, ensure_ascii=False)[:1200],
            )
            raise


async def _call_comet_gpt(model: str, image_data_url: str) -> str:
    url = f"{settings.COMET_BASE_URL.rstrip('/')}/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": [{"type": "text", "text": _SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            "Проанализируй это изображение и создай детальный промпт "
                            "на русском языке, который позволит воссоздать изображение максимально точно."
                        ),
                    },
                ],
            },
        ],
        "reasoning_effort": "high",
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.COMET_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        try:
            return _extract_kie_text(data)
        except Exception:
            logger.warning(
                "photo_prompt: unexpected CometAPI %s response: %s",
                model,
                json.dumps(data, ensure_ascii=False)[:1200],
            )
            raise
