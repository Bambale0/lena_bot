# api/video_service.py
"""Video generation service — KIE.AI/Veo primary with CometAPI fallback."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass

from typing import Any

from api import comet_fallback, kieai_client
from api.kie_model_specs import VIDEO_SPECS, build_kie_input
from api.public_files import ensure_video_reference_aspect_url
from core.gemini_omni import (
    build_gemini_omni_audio_payload,
    build_gemini_omni_character_payload,
)

logger = logging.getLogger(__name__)


class VideoModel(StrEnum):
    # Kling
    KLING_26_T2V    = "kling-2.6/text-to-video"
    KLING_26_I2V    = "kling-2.6/image-to-video"
    KLING_26_MOTION = "kling-2.6/motion-control"
    KLING_30        = "kling-3.0/video"
    KLING_30_MOTION = "kling-3.0/motion-control"
    KLING_V3_TURBO_T2V = "kling/v3-turbo-text-to-video"
    KLING_V3_TURBO_I2V = "kling/v3-turbo-image-to-video"
    # WAN
    WAN_27_T2V      = "wan/2-7-text-to-video"
    WAN_27_I2V      = "wan/2-7-image-to-video"
    # Seedance
    SEEDANCE_2      = "bytedance/seedance-2"
    SEEDANCE_2_FAST = "bytedance/seedance-2-fast"
    SEEDANCE_2_MINI = "bytedance/seedance-2-mini"
    # Grok
    GROK_T2V        = "grok-imagine/text-to-video"
    GROK_I2V        = "grok-imagine/image-to-video"
    # HappyHorse
    HAPPYHORSE_T2V  = "happyhorse/text-to-video"
    HAPPYHORSE_I2V  = "happyhorse/image-to-video"
    # Gemini Omni
    GEMINI_OMNI_VIDEO = "gemini-omni-video"
    # Veo (special endpoint)
    VEO_3           = "veo3"
    VEO_3_FAST      = "veo3_fast"
    VEO_3_LITE      = "veo3_lite"


class MotionDirection(StrEnum):
    PAN_LEFT  = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP   = "tilt_up"
    TILT_DOWN = "tilt_down"
    ZOOM_IN   = "zoom_in"
    ZOOM_OUT  = "zoom_out"
    ORBIT_LEFT = "orbit_left"
    ROLL_CW   = "roll_clockwise"

    def label(self) -> str:
        return {
            "pan_left":       "◄ Pan Left",
            "pan_right":      "► Pan Right",
            "tilt_up":        "▲ Tilt Up",
            "tilt_down":      "▼ Tilt Down",
            "zoom_in":        "🔍 Zoom In",
            "zoom_out":       "🔎 Zoom Out",
            "orbit_left":     "↺ Orbit",
            "roll_clockwise": "↻ Roll",
        }.get(self.value, self.value)


@dataclass
class VideoResult:
    task_id: str
    provider: str  # "kieai" | "veo" | "comet"
    uses_webhook: bool = False


@dataclass
class GeminiOmniAudioResult:
    audio_id: str
    name: str


@dataclass
class GeminiOmniCharacterResult:
    character_id: str
    character_name: str | None
    image_url: str | None


# ── Model sets ────────────────────────────────────────────────────────────────
_VEO_MODELS = {VideoModel.VEO_3, VideoModel.VEO_3_FAST, VideoModel.VEO_3_LITE}
_MOTION_MODELS = {VideoModel.KLING_26_MOTION, VideoModel.KLING_30_MOTION}

SUPPORTS_I2V: set[VideoModel] = {
    VideoModel(spec.model)
    for spec in VIDEO_SPECS.values()
    if "image" in spec.supported_modes and spec.model in set(item.value for item in VideoModel)
}
SUPPORTS_I2V.update({VideoModel.VEO_3_FAST, VideoModel.VEO_3_LITE})  # VEO_3 removed: API says "Reference to video only supports Veo Fast and Veo Lite"


# ── Entry point ───────────────────────────────────────────────────────────────

async def _prepare_video_reference_url(url: str | None) -> str | None:
    if not url:
        return None
    return ensure_video_reference_aspect_url(url) or url


async def _prepare_video_reference_urls(urls: str | list[str] | None) -> str | list[str] | None:
    if not urls:
        return None
    if isinstance(urls, str):
        return await _prepare_video_reference_url(urls)
    prepared = [url for url in [await _prepare_video_reference_url(str(item)) for item in urls if item] if url]
    return prepared or None


def _is_provider_validation_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "422",
            "image aspect ratio",
            "aspect ratio must be",
            "input parameters are not correct",
        )
    )

async def generate_video(
    model: VideoModel,
    prompt: str,
    image_url: str | list[str] | None = None,
    last_frame_url: str | None = None,
    image_bytes: bytes | None = None,   # not used by kie.ai (kept for signature compat)
    motion: MotionDirection | None = None,
    duration: int = 5,
    aspect_ratio: str | None = None,
    resolution: str | None = None,
    # Motion Control specific
    reference_video_url: str | None = None,
    # Grok mode
    grok_mode: str = "normal",
    # Gemini Omni extras
    audio_ids: list[str] | None = None,
    character_ids: list[str] | None = None,
    video_start: float | int | None = None,
    video_end: float | int | None = None,
    seed: int | None = None,
    callback_url: str | None = None,
    enable_fallback: bool = False,
) -> VideoResult:
    image_url = await _prepare_video_reference_urls(image_url)
    last_frame_url = await _prepare_video_reference_url(last_frame_url)

    if model in _VEO_MODELS:
        try:
            return await _veo_generate(
                model,
                prompt,
                image_url,
                aspect_ratio,
                resolution=resolution,
                callback_url=callback_url,
                enable_fallback=enable_fallback,
            )
        except Exception as kie_exc:
            logger.warning("Veo primary create failed for %s; trying CometAPI fallback: %s", model.value, kie_exc)
            if _is_provider_validation_error(kie_exc):
                raise
            return await _comet_fallback_generate(
                kie_exc=kie_exc,
                model=model,
                prompt=prompt,
                image_url=image_url,
                last_frame_url=last_frame_url,
                duration=duration,
                aspect_ratio=aspect_ratio,
                resolution=resolution,
                reference_video_url=reference_video_url,
                grok_mode=grok_mode,
                audio_ids=audio_ids,
                character_ids=character_ids,
                video_start=video_start,
                video_end=video_end,
                seed=seed,
                callback_url=callback_url,
            )

    try:
        return await _kieai_generate(
            model,
            prompt,
            image_url=image_url,
            last_frame_url=last_frame_url,
            motion=motion,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            reference_video_url=reference_video_url,
            grok_mode=grok_mode,
            audio_ids=audio_ids,
            character_ids=character_ids,
            video_start=video_start,
            video_end=video_end,
            seed=seed,
            callback_url=callback_url,
        )
    except Exception as kie_exc:
        logger.warning("KIE.AI video create failed for %s; trying CometAPI fallback: %s", model.value, kie_exc)
        if _is_provider_validation_error(kie_exc):
            raise
        return await _comet_fallback_generate(
            kie_exc=kie_exc,
            model=model,
            prompt=prompt,
            image_url=image_url,
            last_frame_url=last_frame_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            reference_video_url=reference_video_url,
            grok_mode=grok_mode,
            audio_ids=audio_ids,
            character_ids=character_ids,
            video_start=video_start,
            video_end=video_end,
            seed=seed,
            callback_url=callback_url,
        )


# ── Universal KIE.AI generator ────────────────────────────────────────────────

async def _comet_fallback_generate(
    *,
    kie_exc: Exception,
    model: VideoModel,
    prompt: str,
    image_url: str | list[str] | None,
    last_frame_url: str | None,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    reference_video_url: str | None,
    grok_mode: str | None,
    audio_ids: list[str] | None,
    character_ids: list[str] | None,
    video_start: float | int | None,
    video_end: float | int | None,
    seed: int | None,
    callback_url: str | None,
) -> VideoResult:
    try:
        fallback = await comet_fallback.generate_video(
            model_key=model.value,
            prompt=prompt,
            reference_urls=image_url,
            last_frame_url=last_frame_url,
            reference_video_url=reference_video_url,
            duration=duration,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            grok_mode=grok_mode,
            audio_ids=audio_ids,
            character_ids=character_ids,
            video_start=video_start,
            video_end=video_end,
            seed=seed,
            callback_url=callback_url,
        )
    except Exception as comet_exc:
        raise RuntimeError(
            f"Video generation failed via KIE.AI and CometAPI fallback: "
            f"KIE={kie_exc}; CometAPI={comet_exc}"
        ) from comet_exc
    return VideoResult(task_id=fallback.task_id, provider=fallback.provider, uses_webhook=fallback.uses_webhook)

async def _kieai_generate(
    model: VideoModel,
    prompt: str,
    image_url: str | list[str] | None,
    last_frame_url: str | None,
    motion: MotionDirection | None,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    reference_video_url: str | None,
    grok_mode: str,
    audio_ids: list[str] | None,
    character_ids: list[str] | None,
    video_start: float | int | None,
    video_end: float | int | None,
    seed: int | None,
    callback_url: str | None,
) -> VideoResult:
    resolved_model, inp = build_kie_input(
        model=model.value,
        prompt=prompt,
        reference_urls=image_url,
        params={
            "last_frame_url": last_frame_url,
            "duration": duration,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution,
            "reference_video_url": reference_video_url,
            "grok_mode": grok_mode,
            "audio_ids": audio_ids,
            "character_ids": character_ids,
            "video_start": video_start,
            "video_end": video_end,
            "seed": seed,
        },
    )

    resp = await kieai_client.create_task({"model": resolved_model, "input": inp}, callback_url=callback_url)
    if not isinstance(resp, dict):
        raise RuntimeError(f"KIE.AI video: invalid createTask response for {resolved_model}: {resp!r}")

    code = resp.get("code")
    if code not in (None, 200, "200"):
        raise RuntimeError(f"KIE.AI video createTask failed for {resolved_model}: {code} {resp.get('msg')}")

    data = resp.get("data")
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        raise RuntimeError(f"KIE.AI video: invalid createTask data for {resolved_model}: {data!r}")

    task_id = str(data.get("taskId") or resp.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"KIE.AI video: empty taskId for {resolved_model}: {resp!r}")

    logger.info("KIE.AI video task %s: %s", resolved_model, task_id)
    return VideoResult(task_id=task_id, provider="kieai", uses_webhook=bool(callback_url))


def _result_urls_from_dict(value: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("resultUrls", "result_urls", "videoUrls", "video_urls", "urls"):
        items = value.get(key)
        if isinstance(items, list):
            urls.extend(str(item) for item in items if item)
        elif isinstance(items, str) and items:
            urls.append(items)
    for key in ("resultUrl", "result_url", "videoUrl", "video_url", "url"):
        item = value.get(key)
        if isinstance(item, str) and item:
            urls.append(item)
    return list(dict.fromkeys(urls))


def _result_urls_from_value(value: Any) -> list[str]:
    if isinstance(value, dict):
        urls = _result_urls_from_dict(value)
        for nested in value.values():
            urls.extend(_result_urls_from_value(nested))
        return list(dict.fromkeys(urls))
    if isinstance(value, list):
        urls: list[str] = []
        for item in value:
            urls.extend(_result_urls_from_value(item))
        return list(dict.fromkeys(urls))
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("http"):
            return [stripped]
        if stripped.startswith("[") or stripped.startswith("{"):
            try:
                return _result_urls_from_value(json.loads(stripped))
            except json.JSONDecodeError:
                return []
    return []


async def create_gemini_omni_audio(
    *,
    audio_id: str,
    name: str,
    voice_description: str | None = None,
    example_dialogue: str | None = None,
) -> GeminiOmniAudioResult:
    payload = build_gemini_omni_audio_payload(
        audio_id=audio_id,
        name=name,
        voice_description=voice_description,
        example_dialogue=example_dialogue,
    )
    resp = await kieai_client.create_omni_audio(payload)
    if not isinstance(resp, dict):
        raise RuntimeError(f"Gemini Omni audio: invalid response: {resp!r}")
    code = resp.get("code")
    if code not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"Gemini Omni audio failed: {code} {resp.get('msg')}")
    data = resp.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Gemini Omni audio: invalid data: {data!r}")
    result_id = str(data.get("kieAudioId") or data.get("audioId") or "").strip()
    if not result_id:
        raise RuntimeError(f"Gemini Omni audio: empty audio id: {resp!r}")
    return GeminiOmniAudioResult(audio_id=result_id, name=str(data.get("name") or payload["name"]))


async def create_gemini_omni_character(
    *,
    descriptions: str,
    image_urls: str | list[str],
    audio_ids: list[str] | None = None,
    character_name: str | None = None,
) -> GeminiOmniCharacterResult:
    payload = build_gemini_omni_character_payload(
        descriptions=descriptions,
        image_urls=image_urls,
        audio_ids=audio_ids,
        character_name=character_name,
    )
    resp = await kieai_client.create_omni_character(payload)
    if not isinstance(resp, dict):
        raise RuntimeError(f"Gemini Omni character: invalid response: {resp!r}")
    code = resp.get("code")
    if code not in (None, 0, 200, "0", "200"):
        raise RuntimeError(f"Gemini Omni character failed: {code} {resp.get('msg')}")
    data = resp.get("data") or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"Gemini Omni character: invalid data: {data!r}")
    result_id = str(data.get("characterId") or data.get("character_id") or data.get("id") or "").strip()
    if not result_id:
        raise RuntimeError(f"Gemini Omni character: empty characterId: {resp!r}")
    return GeminiOmniCharacterResult(
        character_id=result_id,
        character_name=data.get("characterName"),
        image_url=data.get("imageUrl"),
    )


# ── Veo 3 ─────────────────────────────────────────────────────────────────────

async def _veo_generate(
    model: VideoModel,
    prompt: str,
    image_url: str | list[str] | None,
    aspect_ratio: str | None,
    resolution: str | None = None,
    callback_url: str | None = None,
    enable_fallback: bool = False,
) -> VideoResult:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "model": model.value,
        "aspect_ratio": aspect_ratio or "16:9",
        "enableTranslation": True,
        "enableFallback": enable_fallback,
    }
    if resolution:
        payload["resolution"] = resolution
    if callback_url:
        payload["callBackUrl"] = callback_url
    if image_url:
        payload["imageUrls"] = image_url if isinstance(image_url, list) else [image_url]
        payload["generationType"] = "REFERENCE_2_VIDEO"
    else:
        payload["generationType"] = "TEXT_2_VIDEO"

    resp = await kieai_client.create_veo_task(payload)
    if not isinstance(resp, dict):
        raise RuntimeError(f"Veo3: API returned non-dict response: {type(resp)}")
    code = resp.get("code")
    if code not in (None, 200, "200"):
        raise RuntimeError(f"Veo3 createTask failed: {code} {resp.get('msg')}")
    data = resp.get("data")
    if not isinstance(data, dict):
        data = {}
    # Veo 3.1 returns taskId in data
    task_id = str(data.get("taskId") or resp.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"Veo3: empty taskId in createTask response: {resp!r}")
    logger.info("Veo task taskId: %s", task_id)
    return VideoResult(task_id=task_id, provider="veo", uses_webhook=bool(callback_url))


# ── Poll functions ────────────────────────────────────────────────────────────

async def poll_kieai_status(task_id: str) -> str | None:
    """Universal poller for all non-Veo KIE.AI models."""
    if comet_fallback.is_comet_task_id(task_id):
        return await comet_fallback.poll_status(task_id)

    resp = await kieai_client.get_task_status(task_id)
    data = resp.get("data", {})
    state = str(data.get("state", "")).lower()

    if state == "success":
        result_json_str = data.get("resultJson", "{}")
        try:
            parsed = json.loads(result_json_str)
        except json.JSONDecodeError:
            parsed = {}
        urls = _result_urls_from_dict(parsed) if isinstance(parsed, dict) else []
        if not urls:
            urls = _result_urls_from_dict(data)
        if urls:
            return urls[0]
        raise RuntimeError("KIE.AI: success but no resultUrls in resultJson")

    if state == "fail":
        raise RuntimeError(f"KIE.AI task failed: {data.get('failMsg', 'unknown error')}")

    return None  # waiting / queuing / generating


async def poll_veo_status(video_id: str) -> str | None:
    if comet_fallback.is_comet_task_id(video_id):
        return await comet_fallback.poll_status(video_id)

    resp = await kieai_client.get_veo_status(video_id)
    if not isinstance(resp, dict):
        raise RuntimeError(f"Veo3: invalid status response: {resp!r}")
    data = resp.get("data")
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        raise RuntimeError(f"Veo3: invalid status data: {data!r}")
    success_flag = data.get("successFlag")

    if success_flag is True or success_flag in (1, "1", "true", "success"):
        urls = _result_urls_from_value(data)
        url = urls[0] if urls else None
        if url:
            return url
        raise RuntimeError("Veo3: success but no videoUrl")

    if success_flag is False or success_flag in (2, 3, "2", "3", "fail", "failed", "error"):
        error = data.get("failMsg") or data.get("errorMessage") or data.get("msg") or "unknown error"
        raise RuntimeError(f"Veo3 failed: {error}")

    return None

# ── Veo 3.1 4K enhancement ──────────────────────────────────────────────────

async def generate_video_4k(
    task_id: str,
    index: int = 0,
    callback_url: str | None = None,
) -> VideoResult:
    """Request 4K enhancement for a previously generated Veo video.

    After a Veo video is generated, call this to get a 4K version.
    The result will be delivered via callback or can be polled.
    """
    resp = await kieai_client.create_veo_4k_task(task_id, index=index, callback_url=callback_url)
    if not isinstance(resp, dict):
        resp = {}
    data = resp.get("data")
    if not isinstance(data, dict):
        data = {}
    new_task_id = str(data.get("taskId") or resp.get("taskId") or "")
    logger.info("Veo 4K enhancement taskId: %s", new_task_id)
    return VideoResult(task_id=new_task_id, provider="veo_4k")


async def poll_veo_4k_status(task_id: str) -> str | None:
    """Poll 4K enhancement status. Returns video URL when done."""
    resp = await kieai_client.get_veo_4k_status(task_id)
    if not isinstance(resp, dict):
        raise RuntimeError(f"Veo3 4K: invalid status response: {resp!r}")
    data = resp.get("data")
    if data is None:
        data = {}
    elif not isinstance(data, dict):
        raise RuntimeError(f"Veo3 4K: invalid status data: {data!r}")
    success_flag = data.get("successFlag")

    if success_flag is True or success_flag in (1, "1", "true", "success"):
        urls = _result_urls_from_value(data)
        url = urls[0] if urls else None
        if url:
            return url
        raise RuntimeError("Veo3 4K: success but no videoUrl in response")

    if success_flag is False or success_flag in (2, 3, "2", "3", "fail", "failed", "error"):
        error = data.get("msg") or data.get("errorMessage") or data.get("failMsg") or "unknown error"
        raise RuntimeError(f"Veo3 4K failed: {error}")

    return None


async def poll_comet_status(task_id: str) -> str | None:
    return await comet_fallback.poll_status(task_id)


POLL_FN_MAP: dict[str, Any] = {
    "kieai": poll_kieai_status,
    "veo":   poll_veo_status,
    "veo_4k": poll_veo_4k_status,
    "comet": poll_comet_status,
}


def get_poll_fn(provider: str):
    fn = POLL_FN_MAP.get(provider)
    if fn is None:
        raise ValueError(f"Unknown provider: {provider}")
    return fn
