"""Video-to-prompt routing through CometAPI/Qwen video understanding."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

VIDEO_PROMPT_MODEL_KEY = "llm.video-prompt"

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
    video_payload: dict[str, Any] = {"url": video_url}
    if fps is not None:
        video_payload["fps"] = fps
    return [
        {"role": "system", "content": [{"type": "text", "text": _VIDEO_SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "video_url", "video_url": video_payload},
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


def _extract_chat_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Video prompt response is not an object")
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
    raise RuntimeError(f"Video prompt response did not contain text: {payload!r}")


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
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError(f"Video prompt provider returned non-object JSON: {data!r}")
    return data


async def generate_prompt_from_video_url(
    video_url: str,
    *,
    fps: float | int | None = None,
) -> VideoPromptResult:
    clean_url = str(video_url or "").strip()
    if not clean_url:
        raise ValueError("Video URL is empty")
    model = _comet_video_prompt_model()
    payload = {
        "model": model,
        "messages": _video_prompt_chat_messages(clean_url, fps=fps),
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
    result = VideoPromptResult(_extract_chat_text(data), "comet_chat", model)
    logger.info("video_prompt generated via provider=%s model=%s", result.provider, result.model)
    return result
