"""Official multimodal video operations for Seedance, WAN and HappyHorse."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from api import kieai_client
from api.media_gateway import (
    AUDIO_POLICY,
    IMAGE_POLICY,
    VIDEO_POLICY,
    prepare_media_url,
    prepare_media_urls,
)


class SeedanceModel(StrEnum):
    QUALITY = "bytedance/seedance-2"
    FAST = "bytedance/seedance-2-fast"
    MINI = "bytedance/seedance-2-mini"


class WanVideoModel(StrEnum):
    TEXT_TO_VIDEO = "wan/2-7-text-to-video"
    IMAGE_TO_VIDEO = "wan/2-7-image-to-video"
    REFERENCE_TO_VIDEO = "wan/2-7-r2v"
    VIDEO_EDIT = "wan/2-7-videoedit"


class HappyHorseModel(StrEnum):
    TEXT_TO_VIDEO = "happyhorse/text-to-video"
    IMAGE_TO_VIDEO = "happyhorse/image-to-video"
    REFERENCE_TO_VIDEO = "happyhorse/reference-to-video"
    VIDEO_EDIT = "happyhorse/video-edit"
    V11_TEXT_TO_VIDEO = "happyhorse-1-1/text-to-video"
    V11_IMAGE_TO_VIDEO = "happyhorse-1-1/image-to-video"
    V11_REFERENCE_TO_VIDEO = "happyhorse-1-1/reference-to-video"


@dataclass(frozen=True)
class MarketVideoTask:
    task_id: str
    model: str
    uses_webhook: bool = False


_SEEDANCE_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4", "21:9", "adaptive"}
_SEEDANCE_DURATIONS = {3, 5, 8, 10, 15}
_WAN_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4"}
_HAPPYHORSE_RATIOS = {"16:9", "9:16", "1:1", "4:3", "3:4"}
_VIDEO_RESOLUTIONS = {"480p", "720p", "1080p"}


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _choice(value: str, allowed: set[str], name: str) -> str:
    normalized = str(value or "").strip()
    if normalized not in allowed:
        raise ValueError(f"Unsupported {name}={normalized!r}; allowed: {sorted(allowed)}")
    return normalized


def _duration(value: int, allowed: set[int], model: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("duration must be an integer") from exc
    if parsed not in allowed:
        raise ValueError(f"Unsupported duration={parsed} for {model}; allowed: {sorted(allowed)}")
    return parsed


def _seed(value: int | None) -> int:
    if value is None:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("seed must be an integer") from exc
    if parsed < 0 or parsed > 2_147_483_647:
        raise ValueError("seed must be between 0 and 2147483647")
    return parsed


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _clean(item)
            for key, item in value.items()
            if item is not None and item != [] and item != ""
        }
    if isinstance(value, list):
        return [_clean(item) for item in value if item is not None and item != ""]
    return value


async def _create_task(
    model: str,
    input_payload: dict[str, Any],
    *,
    callback_url: str | None,
) -> MarketVideoTask:
    request: dict[str, Any] = {"model": model, "input": _clean(input_payload)}
    response = await kieai_client.create_task(request, callback_url=callback_url)
    if not isinstance(response, dict):
        raise RuntimeError(f"{model}: invalid createTask response: {response!r}")
    code = response.get("code")
    if code not in (None, 200, "200"):
        raise RuntimeError(f"{model}: createTask failed: {code} {response.get('msg')}")
    data = response.get("data")
    if not isinstance(data, dict):
        data = {}
    task_id = str(data.get("taskId") or response.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"{model}: createTask returned no taskId: {response!r}")
    return MarketVideoTask(task_id=task_id, model=model, uses_webhook=bool(callback_url))


async def create_seedance_task(
    model: SeedanceModel,
    prompt: str,
    *,
    first_frame_url: str | None = None,
    last_frame_url: str | None = None,
    reference_image_urls: list[str] | None = None,
    reference_video_urls: list[str] | None = None,
    reference_audio_urls: list[str] | None = None,
    return_last_frame: bool = False,
    generate_audio: bool = False,
    resolution: str = "720p",
    aspect_ratio: str = "16:9",
    duration: int = 5,
    web_search: bool = False,
    callback_url: str | None = None,
) -> MarketVideoTask:
    """Create any official Seedance 2 scenario.

    Frame-to-video and multimodal references are mutually exclusive by provider
    contract. Text-to-video is represented by leaving both groups empty.
    """
    prompt = _required_text(prompt, "prompt")
    resolution = _choice(resolution, _VIDEO_RESOLUTIONS, "resolution")
    if model in {SeedanceModel.FAST, SeedanceModel.MINI} and resolution == "1080p":
        raise ValueError(f"{model.value} does not support 1080p")
    aspect_ratio = _choice(aspect_ratio, _SEEDANCE_RATIOS, "aspect_ratio")
    duration = _duration(duration, _SEEDANCE_DURATIONS, model.value)

    first = await prepare_media_url(first_frame_url, policy=IMAGE_POLICY)
    last = await prepare_media_url(last_frame_url, policy=IMAGE_POLICY)
    ref_images = await prepare_media_urls(reference_image_urls, policy=IMAGE_POLICY)
    ref_videos = await prepare_media_urls(reference_video_urls, policy=VIDEO_POLICY)
    ref_audio = await prepare_media_urls(reference_audio_urls, policy=AUDIO_POLICY)

    uses_frames = bool(first or last)
    uses_multimodal = bool(ref_images or ref_videos or ref_audio)
    if last and not first:
        raise ValueError("Seedance last_frame_url requires first_frame_url")
    if uses_frames and uses_multimodal:
        raise ValueError(
            "Seedance frame-to-video and multimodal references are mutually exclusive"
        )
    if uses_frames and len([item for item in (first, last) if item]) > 2:
        raise ValueError("Seedance supports at most two frame images")

    return await _create_task(
        model.value,
        {
            "prompt": prompt,
            "first_frame_url": first,
            "last_frame_url": last,
            "reference_image_urls": ref_images,
            "reference_video_urls": ref_videos,
            "reference_audio_urls": ref_audio,
            "return_last_frame": bool(return_last_frame),
            "generate_audio": bool(generate_audio),
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "web_search": bool(web_search),
        },
        callback_url=callback_url,
    )


async def create_wan_text_to_video(
    prompt: str,
    *,
    negative_prompt: str = "",
    audio_url: str | None = None,
    resolution: str = "1080p",
    aspect_ratio: str = "16:9",
    duration: int = 5,
    prompt_extend: bool = True,
    watermark: bool = False,
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    prompt = _required_text(prompt, "prompt")
    audio = await prepare_media_url(audio_url, policy=AUDIO_POLICY)
    return await _create_task(
        WanVideoModel.TEXT_TO_VIDEO.value,
        {
            "prompt": prompt,
            "negative_prompt": str(negative_prompt or ""),
            "audio_url": audio,
            "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
            "ratio": _choice(aspect_ratio, _WAN_RATIOS, "ratio"),
            "duration": _duration(duration, {2, 3, 5, 8, 10, 12, 15}, WanVideoModel.TEXT_TO_VIDEO.value),
            "prompt_extend": bool(prompt_extend),
            "watermark": bool(watermark),
            "seed": _seed(seed),
        },
        callback_url=callback_url,
    )


async def create_wan_image_to_video(
    prompt: str,
    *,
    first_frame_url: str | None = None,
    last_frame_url: str | None = None,
    first_clip_url: str | None = None,
    negative_prompt: str = "",
    resolution: str = "1080p",
    duration: int = 5,
    prompt_extend: bool = True,
    watermark: bool = False,
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    prompt = _required_text(prompt, "prompt")
    first = await prepare_media_url(first_frame_url, policy=IMAGE_POLICY)
    last = await prepare_media_url(last_frame_url, policy=IMAGE_POLICY)
    clip = await prepare_media_url(first_clip_url, policy=VIDEO_POLICY)
    if clip and (first or last):
        raise ValueError("WAN video continuation cannot be mixed with frame inputs")
    if not clip and not first:
        raise ValueError("WAN image-to-video requires first_frame_url or first_clip_url")
    if last and not first:
        raise ValueError("WAN last_frame_url requires first_frame_url")

    return await _create_task(
        WanVideoModel.IMAGE_TO_VIDEO.value,
        {
            "prompt": prompt,
            "negative_prompt": str(negative_prompt or ""),
            "first_frame_url": first,
            "last_frame_url": last,
            "first_clip_url": clip,
            "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
            "duration": _duration(duration, {2, 3, 5, 8, 10, 12, 15}, WanVideoModel.IMAGE_TO_VIDEO.value),
            "prompt_extend": bool(prompt_extend),
            "watermark": bool(watermark),
            "seed": _seed(seed),
        },
        callback_url=callback_url,
    )


async def create_wan_reference_to_video(
    prompt: str,
    *,
    reference_image_urls: list[str] | None = None,
    reference_video_urls: list[str] | None = None,
    first_frame_url: str | None = None,
    reference_voice_url: str | None = None,
    negative_prompt: str = "",
    resolution: str = "1080p",
    aspect_ratio: str = "16:9",
    duration: int = 5,
    prompt_extend: bool = True,
    watermark: bool = False,
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    prompt = _required_text(prompt, "prompt")
    images = await prepare_media_urls(reference_image_urls, policy=IMAGE_POLICY)
    videos = await prepare_media_urls(reference_video_urls, policy=VIDEO_POLICY)
    first = await prepare_media_url(first_frame_url, policy=IMAGE_POLICY)
    voice = await prepare_media_url(reference_voice_url, policy=AUDIO_POLICY)
    if not any((images, videos, first, voice)):
        raise ValueError("WAN reference-to-video requires at least one media reference")

    return await _create_task(
        WanVideoModel.REFERENCE_TO_VIDEO.value,
        {
            "prompt": prompt,
            "negative_prompt": str(negative_prompt or ""),
            "reference_image": images,
            "reference_video": videos,
            "first_frame": first,
            "reference_voice": voice,
            "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
            "aspect_ratio": _choice(aspect_ratio, _WAN_RATIOS, "aspect_ratio"),
            "duration": _duration(duration, {2, 3, 5, 8, 10, 12, 15}, WanVideoModel.REFERENCE_TO_VIDEO.value),
            "prompt_extend": bool(prompt_extend),
            "watermark": bool(watermark),
            "seed": _seed(seed),
        },
        callback_url=callback_url,
    )


async def create_wan_video_edit(
    prompt: str,
    *,
    video_url: str,
    reference_image_url: str | None = None,
    negative_prompt: str = "",
    resolution: str = "1080p",
    aspect_ratio: str = "16:9",
    duration: int = 0,
    audio_setting: str = "auto",
    prompt_extend: bool = True,
    watermark: bool = False,
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    prompt = _required_text(prompt, "prompt")
    video = await prepare_media_url(_required_text(video_url, "video_url"), policy=VIDEO_POLICY)
    reference = await prepare_media_url(reference_image_url, policy=IMAGE_POLICY)
    if audio_setting not in {"auto", "keep", "remove", "generate"}:
        raise ValueError("audio_setting must be auto, keep, remove or generate")
    if int(duration) < 0:
        raise ValueError("duration must be zero or positive")

    return await _create_task(
        WanVideoModel.VIDEO_EDIT.value,
        {
            "prompt": prompt,
            "negative_prompt": str(negative_prompt or ""),
            "video_url": video,
            "reference_image": reference,
            "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
            "aspect_ratio": _choice(aspect_ratio, _WAN_RATIOS, "aspect_ratio"),
            "duration": int(duration),
            "audio_setting": audio_setting,
            "prompt_extend": bool(prompt_extend),
            "watermark": bool(watermark),
            "seed": _seed(seed),
        },
        callback_url=callback_url,
    )


async def create_happyhorse_text_to_video(
    prompt: str,
    *,
    version_11: bool = False,
    resolution: str = "1080p",
    aspect_ratio: str = "16:9",
    duration: int = 5,
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    model = HappyHorseModel.V11_TEXT_TO_VIDEO if version_11 else HappyHorseModel.TEXT_TO_VIDEO
    payload: dict[str, Any] = {
        "prompt": _required_text(prompt, "prompt"),
        "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
        "aspect_ratio": _choice(aspect_ratio, _HAPPYHORSE_RATIOS, "aspect_ratio"),
        "duration": _duration(duration, {3, 5, 8, 10, 12, 15}, model.value),
    }
    if not version_11 or seed is not None:
        payload["seed"] = _seed(seed)
    return await _create_task(model.value, payload, callback_url=callback_url)


async def create_happyhorse_image_to_video(
    prompt: str,
    *,
    image_urls: list[str],
    version_11: bool = False,
    resolution: str = "1080p",
    duration: int = 5,
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    model = HappyHorseModel.V11_IMAGE_TO_VIDEO if version_11 else HappyHorseModel.IMAGE_TO_VIDEO
    images = await prepare_media_urls(image_urls, policy=IMAGE_POLICY)
    if not images:
        raise ValueError("HappyHorse image-to-video requires image_urls")
    payload: dict[str, Any] = {
        "prompt": _required_text(prompt, "prompt"),
        "image_urls": images,
        "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
        "duration": _duration(duration, {3, 5, 8, 10, 12, 15}, model.value),
    }
    if not version_11 or seed is not None:
        payload["seed"] = _seed(seed)
    return await _create_task(model.value, payload, callback_url=callback_url)


async def create_happyhorse_reference_to_video(
    prompt: str,
    *,
    reference_image_urls: list[str],
    version_11: bool = False,
    resolution: str = "1080p",
    aspect_ratio: str = "16:9",
    duration: int = 5,
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    model = (
        HappyHorseModel.V11_REFERENCE_TO_VIDEO
        if version_11
        else HappyHorseModel.REFERENCE_TO_VIDEO
    )
    images = await prepare_media_urls(reference_image_urls, policy=IMAGE_POLICY)
    if not images:
        raise ValueError("HappyHorse reference-to-video requires reference images")
    payload: dict[str, Any] = {
        "prompt": _required_text(prompt, "prompt"),
        "reference_image": images,
        "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
        "aspect_ratio": _choice(aspect_ratio, _HAPPYHORSE_RATIOS, "aspect_ratio"),
        "duration": _duration(duration, {3, 5, 8, 10, 12, 15}, model.value),
    }
    if not version_11 or seed is not None:
        payload["seed"] = _seed(seed)
    return await _create_task(model.value, payload, callback_url=callback_url)


async def create_happyhorse_video_edit(
    prompt: str,
    *,
    video_url: str,
    reference_image_urls: list[str] | None = None,
    resolution: str = "1080p",
    audio_setting: str = "auto",
    seed: int | None = None,
    callback_url: str | None = None,
) -> MarketVideoTask:
    video = await prepare_media_url(_required_text(video_url, "video_url"), policy=VIDEO_POLICY)
    images = await prepare_media_urls(reference_image_urls, policy=IMAGE_POLICY)
    if audio_setting not in {"auto", "keep", "remove", "generate"}:
        raise ValueError("audio_setting must be auto, keep, remove or generate")
    return await _create_task(
        HappyHorseModel.VIDEO_EDIT.value,
        {
            "prompt": _required_text(prompt, "prompt"),
            "video_url": video,
            "reference_image": images,
            "resolution": _choice(resolution, {"720p", "1080p"}, "resolution"),
            "audio_setting": audio_setting,
            "seed": _seed(seed),
        },
        callback_url=callback_url,
    )
