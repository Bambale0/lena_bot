"""Video-to-prompt routing through CometAPI/Qwen video understanding."""
from __future__ import annotations

import logging
import math
import re
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
    # The Comet/Qwen gateway ignores video unless fps is a sibling of
    # video_url, not nested inside video_url. Always send an explicit fps:
    # the no-fps request returned HTTP 200 but the model saw no frames.
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


def _missing_video_completion(text: str) -> bool:
    """Reject provider statements about a missing *source*, not missing scene details.

    The reply can begin with a section-A label or a first-person refusal.
    Quotes and descriptions of empty screens inside an actual video must stay
    valid prompts; their absence is an in-scene fact, not an upload failure.
    """
    # Build a validation-only view. Markdown is presentation, not evidence
    # of success; preserve the original text when returning a valid prompt.
    plain = text.casefold().translate(str.maketrans("", "", "`*_#"))
    opening = " ".join(plain.split())
    opening = re.sub(
        r"^a\s*[.)]\s*ready-to-use prompt[\s:—–-]*", "", opening,
    )
    # A quoted caption describes text inside the visible scene. Do not let
    # it override source-absence checks, but retain every assertion outside
    # the quote so a genuine missing-input refusal cannot hide behind one.
    opening = re.sub(
        r"(\b(?:надпись\w*|текст\w*|табличк\w*|caption|label|sign|inscription|text)"
        r"(?:\s+(?:says|reads|reading))?\s*[:—–-]?\s*)"
        r"(?:«[^»]*»|“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*')",
        r"\1[scene-caption]", opening,
    )
    # After explicitly labeled captions have been masked, keep an unlabelled
    # quoted source name as an antecedent for "it/оно was not provided".
    # The order matters: a caption named "the source video" is scene content.
    opening = re.sub(
        r"[\"'«“‘]((?:the\s+)?(?:(?:source|input|uploaded|provided)\s+)?"
        r"(?:video|footage|file)|(?:исходн\w*|входн\w*|загруженн\w*|"
        r"прикрепл[её]нн\w*)\s+(?:видео|кадры|файл))[\"'»”’]",
        r"\1", opening,
    )
    # The scene label may follow its quoted content instead of preceding it.
    opening = re.sub(
        r"(?:«[^»]*»|“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*')"
        r"(\s+(?:на|в|on|in)\s+(?:(?:a|the)\s+)?"
        r"(?:табличк\w*|плакат\w*|экране|мониторе|"
        r"sign|label|caption|screen|monitor|billboard)\b)",
        r"[scene-caption]\1", opening,
    )
    # Normalize apostrophes in contractions, after preserving paired quotes.
    opening = re.sub(r"(?<=\w)[’‘ʼ](?=\w)", "'", opening)[:420]

    if opening.startswith((
        "нет исходного видео",
        "please upload a video",
        "no video was attached",
        "no video was provided",
        "no video is available",
    )):
        return True

    # Absence *on a TV/monitor in the recorded scene* is valid visual
    # content. Explicit "source/uploaded/input video" must override this
    # exception: those qualifiers refer to the file supplied for inference.
    refusal_opening = opening.startswith((
        "невозможно ", "не могу ", "я не могу ", "я не вижу ",
        "к сожалению,", "извините,", "sorry,",
        "i cannot ", "i can't ", "cannot ", "can't ", "unable to ",
    ))
    explicit_source_opening = opening.startswith((
        "исходное видео ", "входное видео ", "загруженное видео ",
        "исходные кадры ", "прикреплённое видео ", "исходный файл ",
        "source video ", "the source video ", "uploaded video ",
        "input video ", "source footage ", "the source footage ",
    ))
    if refusal_opening and re.search(
        r"(?:source|uploaded|input|provided)\s+(?:video|footage|file)|"
        r"(?:исходн\w*|входн\w*|загруженн\w*|прикрепл[её]нн\w*)"
        r"\s+(?:видео|кадры|файл)",
        opening,
    ):
        explicit_source_opening = True
    if not explicit_source_opening and re.search(
        r"(?:видео\s+(?:отсутству\w*|недоступ\w*)\s+"
        r"(?:на|в)\s+(?:экране|мониторе|телевизоре)|"
        r"video\s+(?:is\s+)?(?:missing|unavailable|not visible)\s+"
        r"on\s+(?:the\s+)?(?:television|tv|monitor|screen))",
        opening,
    ):
        return False

    # If a scene contains "Видеоматериал отсутствует" as a sign or caption,
    # it is not a statement about the input. Recognize these phrases only
    # when the provider's *answer* opens with an input noun or a refusal.
    source_opening = opening.startswith((
        "видео ", "видеоматериал ", "кадры ", "исходный файл ",
        "исходное видео ", "входное видео ", "загруженное видео ",
        "исходные кадры ", "прикреплённое видео ",
        "video ", "source video ", "the video ", "the source video ",
        "source footage ", "the source footage ", "uploaded video ",
        "footage ", "frames ", "source file ", "no video ",
    ))
    if not (refusal_opening or source_opening):
        return False

    # A missing/blocked INPUT is different from an unidentified car model,
    # absent label, or invisible video *on a screen in the recorded scene*.
    source_missing_ru = re.search(
        r"(?:видео|видеоматериал|кадры|исходный файл|"
        r"(?:исходн\w+|входн\w+|загруженн\w+|прикреплённ\w+)"
        r"\s+(?:видео|кадры))"
        r"(?:\s+или\s+кадры\s+из\s+него)?\s+"
        r"(?:не\s+(?:(?:был[ои]|были)\s+)?"
        r"(?:прикреплен\w*|прикреплён\w*|загружен\w*|"
        r"предоставлен\w*|доступн\w*|поступил\w*)|"
        r"недоступ\w*|отсутству\w*)",
        opening,
    )
    source_missing_en = re.search(
        r"(?:source video|the video|video|footage|frames?|source file)\s+"
        r"(?:(?:was|were|is|are)\s+)?"
        r"(?:not\s+(?:provided|attached|available|accessible|received)|"
        r"missing|unavailable)",
        opening,
    )
    if source_missing_ru or source_missing_en:
        return True

    # Some gateway refusals name the uploaded video first, then refer to
    # that *source* as "it"/"оно" when explaining why it was unavailable.
    # Require a failed video analysis/prompt action: an unidentified object
    # whose properties were absent from scene metadata is not missing input.
    analyzing_source = refusal_opening and any(
        action in opening for action in (
            "проанализир", "анализировать видео", "просмотреть видео",
            "описать видео", "увидеть видео", "рассмотреть видео",
            "составить промпт", "восстановить промпт",
            "analyze", "analyse", "describe the video", "see the video",
            "view the video", "generate a video prompt",
            "generate a prompt from the video",
        )
    )
    if analyzing_source and re.search(
        r"(?:видео|видеоматериал|video|footage).{0,90}?"
        r"(?:потому что|так как|because|since)\s+"
        r"(?:оно|it)\s+"
        r"(?:(?:не\s+(?:(?:был[ои]|были)\s+)?"
        r"(?:прикреплен\w*|прикреплён\w*|предоставлен\w*|"
        r"загружен\w*)|недоступ\w*)|"
        r"(?:(?:was|is)\s+)?not\s+"
        r"(?:provided|attached|available|accessible|uploaded)|"
        r"unavailable)",
        opening,
    ):
        return True

    # Handle pronoun references to the uploaded file and messages containing
    # an explicit instruction to re-upload rather than source-adjacent nouns.
    if refusal_opening and any(phrase in opening for phrase in (
        "не могу просмотреть видео", "не могу увидеть видео",
        "i cannot access the video", "i can't access the video",
        "i cannot see the video", "i can't see the video",
    )):
        return any(phrase in opening for phrase in (
            "не было прикреплено", "не было загружено",
            "не предоставлено", "файл не прикреплен", "файл не прикреплён",
            "was not attached", "wasn't attached", "was not provided",
            "not provided", "no video", "not uploaded",
        ))

    if opening.startswith("видео не видно"):
        return any(phrase in opening for phrase in (
            "файл не прикреплен", "файл не прикреплён",
            "загрузите видео", "пришлите видео",
        ))
    return False


def _validated_prompt_text(text: str) -> str:
    clean = text.strip()
    if " ".join(clean.split()).casefold() == _PROVIDER_FAILURE_TEXT:
        raise VideoPromptProviderError("Video prompt provider returned a failure message")
    if _missing_video_completion(clean):
        raise VideoPromptProviderError("Video prompt provider could not access video input")
    return clean


def _extract_chat_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise VideoPromptProviderError("Video prompt response is not an object")
    if payload.get("error"):
        raise VideoPromptProviderError("Video prompt provider returned an error")
    choices = payload.get("choices") or []
    if choices and isinstance(choices[0], dict):
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
                str(item.get("text") or "").strip()
                for item in content
                if isinstance(item, dict) and item.get("text")
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
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
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
