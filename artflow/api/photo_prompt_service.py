"""Photo-to-prompt vision routing with exact KIE/Comet model contracts."""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

_KIE_BASE = "https://api.kie.ai"
_PHOTO_PROMPT_REQUEST_TEXT = (
    "Analyze this image and write one detailed English prompt that can recreate it as accurately as possible. "
    "Return only the final generation prompt, without explanations, headings, markdown, or quotation marks."
)
_SYSTEM_PROMPT = (
    "You are an expert prompt engineer for AI image generation. Analyze the provided image and produce "
    "one precise, richly detailed prompt in English. Describe the main subject and important elements, visual "
    "style and medium, composition, lighting, color palette, mood, textures, materials, camera angle, lens, "
    "perspective, depth of field, and relevant fine details. Preserve visible relationships and spatial layout. "
    "Output only the final English prompt with no commentary, headings, markdown, or quotation marks."
)
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@dataclass(frozen=True)
class PhotoPromptResult:
    text: str
    provider: str
    model: str


def _validate_image(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    if not image_bytes:
        raise ValueError("Image is empty")
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 20 MB")
    normalized_mime = str(mime_type or "image/jpeg").split(";", 1)[0].lower().strip()
    if normalized_mime not in _ALLOWED_MIME_TYPES:
        raise ValueError(f"Unsupported image MIME type: {normalized_mime}")
    return image_bytes, normalized_mime


def _image_data_url(image_bytes: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"


def _photo_prompt_chat_messages(image_data_url: str) -> list[dict[str, Any]]:
    return [
        {"role": "system", "content": [{"type": "text", "text": _SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_url, "detail": "high"},
                },
                {"type": "text", "text": _PHOTO_PROMPT_REQUEST_TEXT},
            ],
        },
    ]


def _photo_prompt_responses_input(image_data_url: str) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": _SYSTEM_PROMPT}],
        },
        {
            "role": "user",
            "content": [
                {"type": "input_image", "image_url": image_data_url},
                {"type": "input_text", "text": _PHOTO_PROMPT_REQUEST_TEXT},
            ],
        },
    ]


def _extract_chat_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Vision response is not an object")
    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            text = "\n".join(
                str(item.get("text") or "").strip()
                for item in content
                if isinstance(item, dict) and item.get("text")
            ).strip()
            if text:
                return text
    for key in ("output_text", "text", "answer", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise RuntimeError(f"Vision chat response did not contain text: {payload!r}")


def _extract_responses_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Responses payload is not an object")
    if payload.get("code") not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"Responses provider error: {payload!r}")
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = str(content.get("text") or "").strip()
                if text:
                    return text
    raise RuntimeError(f"Responses payload did not contain output_text: {payload!r}")


def _kie_prefers_responses(model: str) -> bool:
    value = str(model or "").strip().lower()
    return value in {"gpt-5-4", "gpt-5-5", "gpt-codex"} or "codex" in value


def _normalize_comet_model(model: str | None) -> str | None:
    value = str(model or "").strip()
    if not value:
        return None
    parts = value.split("-")
    if len(parts) >= 3 and parts[0] == "gpt" and parts[1].isdigit() and parts[2].isdigit():
        return f"gpt-{parts[1]}.{parts[2]}" + (
            "-" + "-".join(parts[3:]) if len(parts) > 3 else ""
        )
    return value


async def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Vision provider returned non-object JSON: {data!r}")
    return data


async def _call_kie_chat(model: str, image_data_url: str) -> PhotoPromptResult:
    payload = {
        "messages": _photo_prompt_chat_messages(image_data_url),
        "reasoning_effort": "high",
    }
    data = await _post_json(
        f"{_KIE_BASE}/{model}/v1/chat/completions",
        {
            "Authorization": f"Bearer {settings.KIE_AI_KEY}",
            "Content-Type": "application/json",
        },
        payload,
    )
    return PhotoPromptResult(_extract_chat_text(data), "kie_chat", model)


async def _call_kie_responses(model: str, image_data_url: str) -> PhotoPromptResult:
    payload = {
        "model": model,
        "stream": False,
        "input": _photo_prompt_responses_input(image_data_url),
        "reasoning": {"effort": "high"},
    }
    data = await _post_json(
        f"{_KIE_BASE}/codex/v1/responses",
        {
            "Authorization": f"Bearer {settings.KIE_AI_KEY}",
            "Content-Type": "application/json",
        },
        payload,
    )
    return PhotoPromptResult(_extract_responses_text(data), "kie_responses", model)


async def _call_kie_model(model: str, image_data_url: str) -> PhotoPromptResult:
    if _kie_prefers_responses(model):
        try:
            return await _call_kie_responses(model, image_data_url)
        except Exception as exc:
            logger.warning("photo_prompt: KIE Responses %s failed: %s", model, exc)
            # Compatibility fallback documented by older KIE model pages.
            return await _call_kie_chat(model, image_data_url)
    return await _call_kie_chat(model, image_data_url)


async def _call_comet(model: str, image_data_url: str) -> PhotoPromptResult:
    payload = {
        "model": model,
        "messages": _photo_prompt_chat_messages(image_data_url),
        "reasoning_effort": "high",
        "max_completion_tokens": 4096,
        "stream": False,
    }
    data = await _post_json(
        f"{str(settings.COMET_BASE_URL).rstrip('/')}/v1/chat/completions",
        {
            "Authorization": f"Bearer {settings.COMET_API_KEY}",
            "Content-Type": "application/json",
        },
        payload,
    )
    return PhotoPromptResult(_extract_chat_text(data), "comet_chat", model)


def _comet_models() -> list[str]:
    candidates = [
        _normalize_comet_model(getattr(settings, "KIE_PHOTO_PROMPT_MODEL", None)),
        _normalize_comet_model(getattr(settings, "KIE_PHOTO_PROMPT_FALLBACK", None)),
        getattr(settings, "COMET_ASSISTANT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_FALLBACK", None),
    ]
    result: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value not in result:
            result.append(value)
    return result


async def generate_prompt_from_photo_result(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> PhotoPromptResult:
    image_bytes, mime_type = _validate_image(image_bytes, mime_type)
    image_data_url = _image_data_url(image_bytes, mime_type)
    errors: list[str] = []

    for model in (
        getattr(settings, "KIE_PHOTO_PROMPT_MODEL", ""),
        getattr(settings, "KIE_PHOTO_PROMPT_FALLBACK", ""),
    ):
        model_name = str(model or "").strip()
        if not model_name:
            continue
        try:
            result = await _call_kie_model(model_name, image_data_url)
            logger.info(
                "photo_prompt generated via provider=%s model=%s",
                result.provider,
                result.model,
            )
            return result
        except Exception as exc:
            errors.append(f"kie/{model_name}: {exc}")

    for model in _comet_models():
        try:
            result = await _call_comet(model, image_data_url)
            logger.info(
                "photo_prompt generated via provider=%s model=%s",
                result.provider,
                result.model,
            )
            return result
        except Exception as exc:
            errors.append(f"comet/{model}: {exc}")

    raise RuntimeError("Photo prompt models failed: " + " | ".join(errors))


async def generate_prompt_from_photo(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> str:
    return (await generate_prompt_from_photo_result(image_bytes, mime_type)).text


# Compatibility helpers retained for existing tests and imports.
def _extract_kie_text(data: Any) -> str:
    return _extract_chat_text(data)


def _extract_kie_responses_text(data: Any) -> str:
    return _extract_responses_text(data)


async def _call_kie_gpt_chat(model: str, image_data_url: str) -> str:
    return (await _call_kie_chat(model, image_data_url)).text


async def _call_kie_gpt_responses(model: str, image_data_url: str) -> str:
    return (await _call_kie_responses(model, image_data_url)).text


async def _call_comet_gpt(model: str, image_data_url: str) -> str:
    return (await _call_comet(model, image_data_url)).text
