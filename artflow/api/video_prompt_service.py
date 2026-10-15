"""Video-to-prompt routing through CometAPI/Qwen video understanding."""
from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any

import httpx

from api.neironych_qwen38_service import NeironychQwen38Service, Qwen38ProviderError
from core.config import settings
from core.qwen_routing import get_qwen_route

logger = logging.getLogger(__name__)

VIDEO_PROMPT_MODEL_KEY = "llm.video-prompt"
# A wall-clock budget, unlike HTTPX's per-operation timeout. Canonical ingress
# gives only these synchronous routes 240s, leaving time for refund and cleanup.
VIDEO_PROMPT_TIMEOUT_SECONDS = 180.0

_SUPPORTED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/quicktime",
    "video/webm",
}

_VIDEO_SYSTEM_PROMPT = (
    "Ты эксперт по reverse engineering видеопромптов для современных text-to-video "
    "и image-to-video моделей. Твоя задача — не пересказать видео, а восстановить "
    "точный генерационный промпт, который поможет воспроизвести увиденную сцену. "
    "Анализируй субъект, внешний вид, последовательность действий, motion, движение "
    "камеры, кадрирование, угол, композицию, глубину резкости, свет, окружение, "
    "материалы, цвет, стиль, темп, монтаж, переходы и технические визуальные признаки. "
    "Не додумывай невидимые детали, не называй конкретную камеру или объектив без "
    "визуальных оснований и не выдумывай звук."
)

_VIDEO_PROMPT_REQUEST_TEXT = (
    "Сформируй ответ на русском языке.\n"
    "A. Ready-to-use prompt — один цельный подробный промпт для генерации похожего видео.\n"
    "B. Что я увидел — короткий разбор: субъект, действие/таймлайн, камера, свет, стиль.\n"
    "C. Неоднозначности — только если есть важные сомнения.\n"
    "D. Audio note — обязательно напиши: Аудиодорожка не анализировалась.\n"
    "Не используй markdown-таблицы и не добавляй JSON."
)


@dataclass(frozen=True)
class VideoPromptResult:
    text: str
    provider: str
    model: str


def _video_prompt_chat_messages(video_url: str, *, fps: float | int | None = None) -> list[dict[str, Any]]:
    # Qwen OpenAI-compatible video inputs use fps beside video_url.
    # See Model Studio vision/video documentation; adapted from PR205.
    sample_fps = float(settings.COMET_VIDEO_PROMPT_FPS if fps is None else fps)
    if not math.isfinite(sample_fps) or not 0.1 <= sample_fps <= 10:
        raise ValueError("Video prompt FPS must be between 0.1 and 10")
    video_payload: dict[str, Any] = {"url": video_url}
    return [
        {"role": "system", "content": [{"type": "text", "text": _VIDEO_SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": video_payload, "fps": sample_fps},
                {"type": "text", "text": _VIDEO_PROMPT_REQUEST_TEXT},
            ],
        },
    ]


def is_supported_video_prompt_video(data: bytes, content_type: str | None) -> bool:
    content = str(content_type or "").split(";", 1)[0].strip().lower()
    if content and content not in _SUPPORTED_VIDEO_MIME_TYPES:
        return False
    return (
        (len(data) > 12 and data[4:8] == b"ftyp")
        or data.startswith(b"\x1a\x45\xdf\xa3")
    )


class VideoPromptProviderError(RuntimeError):
    """Provider completion is not a usable video prompt (safe to log)."""


# Exact failure-only provider output, not substring matching: a valid creative
# prompt can quote the same message as text visible in the requested scene.
_PROVIDER_FAILURE_TEXT = (
    "The request could not be completed. Please retry later, "
    "or reduce the request parameters/content."
).casefold()


def _validated_prompt_text(text: str) -> str:
    clean = text.strip()
    if " ".join(clean.split()).casefold() == _PROVIDER_FAILURE_TEXT:
        raise VideoPromptProviderError("Video prompt provider returned a failure message")
    return clean


def _extract_chat_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise VideoPromptProviderError("Video prompt response is not an object")
    if payload.get("error"):
        raise VideoPromptProviderError("Video prompt provider returned an error")
    choices = payload.get("choices")
    if choices is None:
        choices = []
    if not isinstance(choices, list) or (choices and not isinstance(choices[0], dict)):
        raise VideoPromptProviderError("Video prompt response contained invalid choices")
    if choices:
        if choices[0].get("finish_reason") == "content_filter":
            raise VideoPromptProviderError("Video prompt provider filtered the response")
        message = choices[0].get("message") if isinstance(choices[0].get("message"), dict) else {}
        if message.get("refusal"):
            raise VideoPromptProviderError("Video prompt provider refused the request")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return _validated_prompt_text(content)
        if isinstance(content, list):
            if any(isinstance(item, dict) and item.get("type") == "refusal" for item in content):
                raise VideoPromptProviderError("Video prompt provider refused the request")
            text = "\n".join(
                item["text"].strip()
                for item in content
                if isinstance(item, dict) and item.get("type") in {"text", "output_text"}
                and isinstance(item.get("text"), str) and item["text"]
            ).strip()
            if text:
                return _validated_prompt_text(text)
    for key in ("output_text", "text", "answer", "response"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _validated_prompt_text(value)
    raise VideoPromptProviderError("Video prompt response did not contain text")


def _comet_video_prompt_model() -> str:
    for candidate in (
        getattr(settings, "COMET_VIDEO_PROMPT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_MODEL", None),
        getattr(settings, "COMET_ASSISTANT_FALLBACK", None),
    ):
        value = str(candidate or "").strip()
        if value:
            return value
    return "qwen3.8-max"


async def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        async with asyncio.timeout(VIDEO_PROMPT_TIMEOUT_SECONDS):
            async with httpx.AsyncClient(timeout=VIDEO_PROMPT_TIMEOUT_SECONDS) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
    except (TimeoutError, httpx.TimeoutException) as exc:
        # Convert our own deadline into an ordinary failure so both API and bot
        # handlers run their existing once-only refund and temporary-file cleanup.
        raise VideoPromptProviderError("Video prompt analysis timed out") from exc
    if not isinstance(data, dict):
        raise VideoPromptProviderError("Video prompt provider returned non-object JSON")
    return data


async def generate_prompt_from_video_url(
    video_url: str,
    *,
    fps: float | int | None = None,
) -> VideoPromptResult:
    clean_url = str(video_url or "").strip()
    if not clean_url:
        raise ValueError("Video URL is empty")
    route = await get_qwen_route("video")
    providers = [route.primary_provider]
    if route.backup_provider:
        providers.append(route.backup_provider)
    last_error: Exception | None = None
    for provider in providers:
        try:
            if provider == "neironych":
                text = await NeironychQwen38Service().analyze_video(
                    video_url=clean_url, user_instruction=_VIDEO_PROMPT_REQUEST_TEXT,
                    system_prompt=_VIDEO_SYSTEM_PROMPT, fps=fps,
                )
                if len(text.strip()) < 100:
                    raise Qwen38ProviderError("unusable_video_prompt", ambiguous=True)
                result = VideoPromptResult(text, "neironych", settings.NEIRONYCH_QWEN38_MODEL)
            else:
                model = str(settings.KIE_VIDEO_PROMPT_MODEL).strip()
                if model != "gemini-3.1-pro":
                    raise VideoPromptProviderError("Unverified KIE video model")
                payload = {"messages": [{"role": "user", "content": [
                    {"type": "text", "text": _VIDEO_SYSTEM_PROMPT + "\n\n" + _VIDEO_PROMPT_REQUEST_TEXT},
                    {"type": "image_url", "image_url": {"url": clean_url}},
                ]}], "stream": False, "include_thoughts": False, "reasoning_effort": "high"}
                data = await _post_json(
                    "https://api.kie.ai/gemini-3.1-pro/v1/chat/completions",
                    {"Authorization": f"Bearer {settings.KIE_AI_KEY}"}, payload,
                )
                result = VideoPromptResult(_extract_chat_text(data), "kie_chat", model)
                if len(result.text.strip()) < 100:
                    raise VideoPromptProviderError("Video provider returned no usable scene analysis")
            logger.info("video_prompt generated via provider=%s model=%s", result.provider, result.model)
            return result
        except Qwen38ProviderError as exc:
            last_error = exc
            if exc.ambiguous:
                raise VideoPromptProviderError("Video provider outcome is uncertain; no automatic paid retry") from exc
        except VideoPromptProviderError:
            raise
        except Exception as exc:
            last_error = exc
            break
    raise VideoPromptProviderError("Video analysis unavailable") from last_error
