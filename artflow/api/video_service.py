# api/video_service.py
"""
Video generation service — единый провайдер KIE.AI.

Все модели кроме Veo:
  POST /api/v1/jobs/createTask   →  VideoResult(task_id, provider="kieai")
  GET  /api/v1/jobs/recordInfo   →  poll_kieai_status

Veo 3:
  POST /api/v1/veo/generate      →  VideoResult(task_id=videoId, provider="veo")
  GET  /api/v1/veo/record-info   →  poll_veo_status
  GET  /api/v1/veo/4k/record-info →  poll_veo_4k_status
"""
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

from api import kieai_client
from api.kie_model_specs import VIDEO_SPECS, build_kie_input

logger = logging.getLogger(__name__)


class VideoModel(StrEnum):
    # Kling
    KLING_26_T2V    = "kling-2.6/text-to-video"
    KLING_26_I2V    = "kling-2.6/image-to-video"
    KLING_26_MOTION = "kling-2.6/motion-control"
    KLING_30        = "kling-3.0/video"
    KLING_30_MOTION = "kling-3.0/motion-control"
    # WAN
    WAN_27_T2V      = "wan/2-7-text-to-video"
    WAN_27_I2V      = "wan/2-7-image-to-video"
    # Seedance
    SEEDANCE_2      = "bytedance/seedance-2"
    SEEDANCE_2_FAST = "bytedance/seedance-2-fast"
    # Grok
    GROK_T2V        = "grok-imagine/text-to-video"
    GROK_I2V        = "grok-imagine/image-to-video"
    # HappyHorse
    HAPPYHORSE_T2V  = "happyhorse/text-to-video"
    HAPPYHORSE_I2V  = "happyhorse/image-to-video"
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
    provider: str  # "kieai" | "veo"


# ── Model sets ────────────────────────────────────────────────────────────────
_VEO_MODELS = {VideoModel.VEO_3, VideoModel.VEO_3_FAST, VideoModel.VEO_3_LITE}
_MOTION_MODELS = {VideoModel.KLING_26_MOTION, VideoModel.KLING_30_MOTION}

SUPPORTS_I2V: set[VideoModel] = {
    VideoModel(spec.model)
    for spec in VIDEO_SPECS.values()
    if "image" in spec.supported_modes and spec.model in set(item.value for item in VideoModel)
}
SUPPORTS_I2V.update({VideoModel.VEO_3, VideoModel.VEO_3_FAST, VideoModel.VEO_3_LITE})


# ── Entry point ───────────────────────────────────────────────────────────────

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
    callback_url: str | None = None,
    enable_fallback: bool = False,
) -> VideoResult:
    if model in _VEO_MODELS:
        return await _veo_generate(model, prompt, image_url, aspect_ratio,
                                       resolution=resolution,
                                       callback_url=callback_url,
                                       enable_fallback=enable_fallback)
    return await _kieai_generate(
        model, prompt,
        image_url=image_url,
        last_frame_url=last_frame_url,
        motion=motion,
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        reference_video_url=reference_video_url,
        grok_mode=grok_mode,
        callback_url=callback_url,
    )


# ── Universal KIE.AI generator ────────────────────────────────────────────────

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
    return VideoResult(task_id=task_id, provider="kieai")


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
    data = resp.get("data")
    if not isinstance(data, dict):
        data = {}
    # Veo 3.1 returns taskId in data
    task_id = str(data.get("taskId") or resp.get("taskId") or "")
    logger.info("Veo task taskId: %s", task_id)
    return VideoResult(task_id=task_id, provider="veo")


# ── Poll functions ────────────────────────────────────────────────────────────

async def poll_kieai_status(task_id: str) -> str | None:
    """Universal poller for all non-Veo KIE.AI models."""
    resp = await kieai_client.get_task_status(task_id)
    data = resp.get("data", {})
    state = str(data.get("state", "")).lower()

    if state == "success":
        result_json_str = data.get("resultJson", "{}")
        try:
            parsed = json.loads(result_json_str)
        except json.JSONDecodeError:
            parsed = {}
        urls = parsed.get("resultUrls", [])
        if urls:
            return urls[0]
        raise RuntimeError("KIE.AI: success but no resultUrls in resultJson")

    if state == "fail":
        raise RuntimeError(f"KIE.AI task failed: {data.get('failMsg', 'unknown error')}")

    return None  # waiting / queuing / generating


async def poll_veo_status(video_id: str) -> str | None:
    resp = await kieai_client.get_veo_status(video_id)
    data = resp.get("data", {})
    success_flag = data.get("successFlag")

    if success_flag is True or success_flag in (1, "1", "true", "success"):
        url = data.get("videoUrl")
        if not url:
            result_urls = data.get("resultUrls", [])
            url = result_urls[0] if result_urls else None
        if url:
            return url
        raise RuntimeError("Veo3: success but no videoUrl")

    if success_flag is False or success_flag in ("fail", "failed", "error"):
        raise RuntimeError(f"Veo3 failed: {data.get('failMsg', 'unknown error')}")

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
    data = resp.get("data", {})
    success_flag = data.get("successFlag")

    if success_flag is True or success_flag in (1, "1", "true", "success"):
        info = data.get("info") or {}
        result_urls = info.get("resultUrls") or data.get("resultUrls") or []
        if result_urls:
            return result_urls[0]
        url = data.get("videoUrl") or info.get("videoUrl")
        if url:
            return url
        raise RuntimeError("Veo3 4K: success but no videoUrl in response")

    if success_flag is False or success_flag in ("fail", "failed", "error"):
        raise RuntimeError(f"Veo3 4K failed: {data.get('msg', data.get('errorMessage', 'unknown error'))}")

    return None


POLL_FN_MAP: dict[str, Any] = {
    "kieai": poll_kieai_status,
    "veo":   poll_veo_status,
    "veo_4k": poll_veo_4k_status,
}


def get_poll_fn(provider: str):
    fn = POLL_FN_MAP.get(provider)
    if fn is None:
        raise ValueError(f"Unknown provider: {provider}")
    return fn
