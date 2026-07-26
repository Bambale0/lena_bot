"""Official Kling and Grok video operations.

The functions in this module map one-to-one to documented KIE models. They do
not fall back to a different model and validate provider constraints before a
credit-consuming createTask request is sent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from api import kieai_client
from api.media_gateway import (
    AUDIO_POLICY,
    IMAGE_POLICY,
    KLING_ELEMENT_IMAGE_POLICY,
    KLING_MOTION_26_IMAGE_POLICY,
    KLING_MOTION_26_VIDEO_POLICY,
    KLING_MOTION_30_IMAGE_POLICY,
    KLING_MOTION_30_VIDEO_POLICY,
    MediaKind,
    MediaPolicy,
    prepare_media_url,
    prepare_media_urls,
)


class KlingModel(StrEnum):
    V26_TEXT = "kling-2.6/text-to-video"
    V26_IMAGE = "kling-2.6/image-to-video"
    V26_MOTION = "kling-2.6/motion-control"
    V30_VIDEO = "kling-3.0/video"
    V30_MOTION = "kling-3.0/motion-control"
    V3_TURBO_TEXT = "kling/v3-turbo-text-to-video"
    V3_TURBO_IMAGE = "kling/v3-turbo-image-to-video"


class GrokVideoModel(StrEnum):
    UPSCALE = "grok-imagine/upscale"
    EXTEND = "grok-imagine/extend"
    PREVIEW_15 = "grok-imagine-video-1-5-preview"


class KlingElementKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class KlingShot:
    prompt: str
    duration: int


@dataclass(frozen=True)
class KlingElement:
    name: str
    description: str
    kind: KlingElementKind
    media_urls: tuple[str, ...]
    audio_urls: tuple[str, ...] = ()
    start_time_ms: int | None = None
    end_time_ms: int | None = None


@dataclass(frozen=True)
class ProviderVideoTask:
    task_id: str
    model: str
    uses_webhook: bool = False


_KLING_RATIOS = {"16:9", "9:16", "1:1"}
_KLING_30_MODES = {"std", "pro", "4K"}
_KLING_MOTION_MODES = {"720p", "1080p", "4K"}
_TURBO_RESOLUTIONS = {"720p", "1080p"}
_GROK_RATIOS = {"16:9", "9:16", "1:1", "2:3", "3:2"}
_GROK_RESOLUTIONS = {"480p", "720p"}
_ELEMENT_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")

_KLING_ELEMENT_VIDEO_POLICY = MediaPolicy(
    kind=MediaKind.VIDEO,
    max_bytes=100 * 1024 * 1024,
    max_items=1,
    upload_path="videos/apix-kling-elements",
    allowed_mime_types=frozenset({"video/mp4", "video/quicktime"}),
    min_duration_seconds=3,
)
_KLING_ELEMENT_AUDIO_POLICY = MediaPolicy(
    kind=MediaKind.AUDIO,
    max_items=1,
    upload_path="audio/apix-kling-elements",
    allowed_mime_types=AUDIO_POLICY.allowed_mime_types,
    min_duration_seconds=5,
    max_duration_seconds=30,
)


def _required(value: str, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _choice(value: str, allowed: set[str], field: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in allowed:
        raise ValueError(f"Unsupported {field}={normalized!r}; allowed: {sorted(allowed)}")
    return normalized


def _integer_range(value: Any, field: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if parsed < minimum or parsed > maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return parsed


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean(item)
            for key, item in value.items()
            if item is not None and item != "" and item != []
        }
    if isinstance(value, list):
        return [_clean(item) for item in value if item is not None and item != ""]
    return value


async def _create(
    model: str,
    payload: dict[str, Any],
    *,
    callback_url: str | None = None,
) -> ProviderVideoTask:
    response = await kieai_client.create_task(
        {"model": model, "input": _clean(payload)},
        callback_url=callback_url,
    )
    if not isinstance(response, dict):
        raise RuntimeError(f"{model}: invalid createTask response: {response!r}")
    code = response.get("code")
    if code not in (None, 200, "200"):
        raise RuntimeError(f"{model}: createTask failed: {code} {response.get('msg')}")
    data = response.get("data") if isinstance(response.get("data"), dict) else {}
    task_id = str(data.get("taskId") or response.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"{model}: createTask returned no taskId: {response!r}")
    return ProviderVideoTask(task_id=task_id, model=model, uses_webhook=bool(callback_url))


async def create_kling_26_text_to_video(
    prompt: str,
    *,
    sound: bool = True,
    aspect_ratio: str = "16:9",
    duration: int = 5,
    callback_url: str | None = None,
) -> ProviderVideoTask:
    return await _create(
        KlingModel.V26_TEXT.value,
        {
            "prompt": _required(prompt, "prompt"),
            "sound": bool(sound),
            "aspect_ratio": _choice(aspect_ratio, _KLING_RATIOS, "aspect_ratio"),
            "duration": str(_integer_range(duration, "duration", 5, 10)),
        },
        callback_url=callback_url,
    )


async def create_kling_26_image_to_video(
    prompt: str,
    *,
    image_urls: list[str],
    sound: bool = True,
    duration: int = 5,
    callback_url: str | None = None,
) -> ProviderVideoTask:
    images = await prepare_media_urls(image_urls, policy=IMAGE_POLICY)
    if not images:
        raise ValueError("Kling 2.6 image-to-video requires image_urls")
    if len(images) > 2:
        raise ValueError("Kling 2.6 image-to-video supports at most first and last frame")
    return await _create(
        KlingModel.V26_IMAGE.value,
        {
            "prompt": _required(prompt, "prompt"),
            "image_urls": images,
            "sound": bool(sound),
            "duration": str(_integer_range(duration, "duration", 5, 10)),
        },
        callback_url=callback_url,
    )


async def _prepare_kling_element(element: KlingElement) -> dict[str, Any]:
    name = _required(element.name, "element.name")
    if not _ELEMENT_NAME_RE.fullmatch(name):
        raise ValueError(
            "Kling element name must start with a letter and contain only letters, digits and underscores"
        )
    description = _required(element.description, f"{name}.description")

    if element.kind == KlingElementKind.IMAGE:
        if not 2 <= len(element.media_urls) <= 4:
            raise ValueError(f"Image element {name} requires 2-4 images")
        media = await prepare_media_urls(
            list(element.media_urls),
            policy=KLING_ELEMENT_IMAGE_POLICY,
        )
    else:
        if len(element.media_urls) != 1:
            raise ValueError(f"Video element {name} requires exactly one video")
        media = await prepare_media_urls(
            list(element.media_urls),
            policy=_KLING_ELEMENT_VIDEO_POLICY,
        )

    audio = await prepare_media_urls(
        list(element.audio_urls),
        policy=_KLING_ELEMENT_AUDIO_POLICY,
    )
    payload: dict[str, Any] = {
        "name": name,
        "description": description,
        "element_input_urls": media,
        "element_input_audio_urls": audio,
    }
    if element.kind == KlingElementKind.VIDEO:
        start = 0 if element.start_time_ms is None else _integer_range(
            element.start_time_ms,
            f"{name}.start_time_ms",
            0,
            30000,
        )
        end = 8000 if element.end_time_ms is None else _integer_range(
            element.end_time_ms,
            f"{name}.end_time_ms",
            0,
            30000,
        )
        if end <= start:
            raise ValueError(f"{name}.end_time_ms must be greater than start_time_ms")
        if end - start < 3000 or end - start > 8000:
            raise ValueError(f"{name} effective video segment must be 3-8 seconds")
        payload["start_time"] = start
        payload["end_time"] = end
    return _clean(payload)


def _referenced_element_names(prompt: str, shots: list[KlingShot]) -> set[str]:
    combined = "\n".join([prompt, *(shot.prompt for shot in shots)])
    return set(re.findall(r"@([A-Za-z][A-Za-z0-9_]*)", combined))


async def create_kling_30_video(
    prompt: str = "",
    *,
    image_urls: list[str] | None = None,
    sound: bool = True,
    duration: int = 5,
    aspect_ratio: str | None = "16:9",
    mode: str = "pro",
    shots: list[KlingShot] | None = None,
    elements: list[KlingElement] | None = None,
    callback_url: str | None = None,
) -> ProviderVideoTask:
    images = await prepare_media_urls(image_urls, policy=IMAGE_POLICY)
    shots = list(shots or [])
    elements = list(elements or [])
    multi_shots = bool(shots)

    duration_value = _integer_range(duration, "duration", 3, 15)
    mode_value = _choice(mode, _KLING_30_MODES, "mode")
    ratio_value = None if images and not aspect_ratio else (
        _choice(str(aspect_ratio or "16:9"), _KLING_RATIOS, "aspect_ratio")
    )

    if multi_shots:
        if len(images) > 1:
            raise ValueError("Kling 3.0 multi-shot supports only a first-frame image")
        if not shots:
            raise ValueError("Kling 3.0 multi-shot requires multi_prompt")
        total_shot_duration = 0
        multi_prompt: list[dict[str, Any]] = []
        for index, shot in enumerate(shots, start=1):
            shot_prompt = _required(shot.prompt, f"shot {index} prompt")
            if len(shot_prompt) > 500:
                raise ValueError(f"shot {index} prompt exceeds 500 characters")
            shot_duration = _integer_range(shot.duration, f"shot {index} duration", 1, 12)
            total_shot_duration += shot_duration
            multi_prompt.append({"prompt": shot_prompt, "duration": shot_duration})
        if total_shot_duration != duration_value:
            raise ValueError("Kling multi_prompt durations must equal total duration")
    else:
        if len(images) > 2:
            raise ValueError("Kling 3.0 single-shot supports first and last frame only")
        prompt = _required(prompt, "prompt")
        multi_prompt = []

    if len(elements) > 3:
        raise ValueError("Kling 3.0 supports at most 3 elements")
    prepared_elements = [await _prepare_kling_element(element) for element in elements]
    element_names = {str(item["name"]) for item in prepared_elements}
    referenced = _referenced_element_names(prompt, shots)
    missing = referenced - element_names
    if missing:
        raise ValueError(f"Prompt references undefined Kling elements: {sorted(missing)}")

    return await _create(
        KlingModel.V30_VIDEO.value,
        {
            "prompt": prompt if not multi_shots else None,
            "image_urls": images,
            "sound": bool(sound),
            "duration": str(duration_value),
            "aspect_ratio": ratio_value,
            "mode": mode_value,
            "multi_shots": multi_shots,
            "multi_prompt": multi_prompt,
            "kling_elements": prepared_elements,
        },
        callback_url=callback_url,
    )


async def create_kling_motion_control(
    prompt: str,
    *,
    image_url: str,
    video_url: str,
    version: str = "3.0",
    mode: str = "720p",
    character_orientation: str = "image",
    background_source: str = "input_video",
    callback_url: str | None = None,
) -> ProviderVideoTask:
    if version not in {"2.6", "3.0"}:
        raise ValueError("Kling motion-control version must be 2.6 or 3.0")
    if character_orientation not in {"image", "video"}:
        raise ValueError("character_orientation must be image or video")
    if background_source not in {"input_video", "input_image"}:
        raise ValueError("background_source must be input_video or input_image")

    if version == "2.6":
        model = KlingModel.V26_MOTION
        image_policy = KLING_MOTION_26_IMAGE_POLICY
        video_policy = KLING_MOTION_26_VIDEO_POLICY
        allowed_modes = {"720p", "1080p"}
    else:
        model = KlingModel.V30_MOTION
        image_policy = KLING_MOTION_30_IMAGE_POLICY
        video_policy = KLING_MOTION_30_VIDEO_POLICY
        allowed_modes = _KLING_MOTION_MODES

    image = await prepare_media_url(_required(image_url, "image_url"), policy=image_policy)
    video = await prepare_media_url(_required(video_url, "video_url"), policy=video_policy)
    payload: dict[str, Any] = {
        "prompt": _required(prompt, "prompt"),
        "input_urls": [image],
        "video_urls": [video],
        "mode": _choice(mode, allowed_modes, "mode"),
        "character_orientation": character_orientation,
    }
    if version == "3.0":
        payload["background_source"] = background_source
    return await _create(model.value, payload, callback_url=callback_url)


async def create_kling_v3_turbo_text(
    prompt: str,
    *,
    duration: int = 5,
    aspect_ratio: str = "16:9",
    resolution: str = "720p",
    callback_url: str | None = None,
) -> ProviderVideoTask:
    return await _create(
        KlingModel.V3_TURBO_TEXT.value,
        {
            "prompt": _required(prompt, "prompt"),
            "duration": str(_integer_range(duration, "duration", 3, 15)),
            "aspect_ratio": _choice(aspect_ratio, _KLING_RATIOS, "aspect_ratio"),
            "resolution": _choice(resolution, _TURBO_RESOLUTIONS, "resolution"),
        },
        callback_url=callback_url,
    )


async def create_kling_v3_turbo_image(
    prompt: str,
    *,
    image_urls: list[str],
    duration: int = 5,
    resolution: str = "720p",
    callback_url: str | None = None,
) -> ProviderVideoTask:
    images = await prepare_media_urls(image_urls, policy=IMAGE_POLICY)
    if not images:
        raise ValueError("Kling V3 Turbo image-to-video requires an image")
    if len(images) > 2:
        raise ValueError("Kling V3 Turbo supports at most first and last frame")
    return await _create(
        KlingModel.V3_TURBO_IMAGE.value,
        {
            "prompt": _required(prompt, "prompt"),
            "image_urls": images,
            "duration": str(_integer_range(duration, "duration", 3, 15)),
            "resolution": _choice(resolution, _TURBO_RESOLUTIONS, "resolution"),
        },
        callback_url=callback_url,
    )


async def create_grok_upscale(
    task_id: str,
    *,
    callback_url: str | None = None,
) -> ProviderVideoTask:
    return await _create(
        GrokVideoModel.UPSCALE.value,
        {"task_id": _required(task_id, "task_id")},
        callback_url=callback_url,
    )


async def create_grok_extend(
    task_id: str,
    *,
    prompt: str = "",
    extend_at: int = 2,
    extend_times: int = 6,
    callback_url: str | None = None,
) -> ProviderVideoTask:
    return await _create(
        GrokVideoModel.EXTEND.value,
        {
            "task_id": _required(task_id, "task_id"),
            "prompt": str(prompt or ""),
            "extend_at": _integer_range(extend_at, "extend_at", 0, 30),
            "extend_times": str(_integer_range(extend_times, "extend_times", 1, 30)),
        },
        callback_url=callback_url,
    )


async def create_grok_preview_15(
    prompt: str,
    *,
    image_urls: list[str] | None = None,
    aspect_ratio: str = "16:9",
    resolution: str = "480p",
    duration: int = 8,
    callback_url: str | None = None,
) -> ProviderVideoTask:
    images = await prepare_media_urls(image_urls, policy=IMAGE_POLICY)
    return await _create(
        GrokVideoModel.PREVIEW_15.value,
        {
            "prompt": _required(prompt, "prompt"),
            "image_urls": images,
            "aspect_ratio": _choice(aspect_ratio, _GROK_RATIOS, "aspect_ratio"),
            "resolution": _choice(resolution, _GROK_RESOLUTIONS, "resolution"),
            "duration": _integer_range(duration, "duration", 1, 30),
        },
        callback_url=callback_url,
    )
