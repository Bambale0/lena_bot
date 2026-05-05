# api/video_service.py
"""
Video generation service — единый провайдер KIE.AI.

Все модели кроме Veo:
  POST /api/v1/jobs/createTask   →  VideoResult(task_id, provider="kieai")
  GET  /api/v1/jobs/recordInfo   →  poll_kieai_status

Veo 3:
  POST /api/v1/veo/generate      →  VideoResult(task_id=videoId, provider="veo")
  GET  /api/v1/veo/video/{id}    →  poll_veo_status
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from api import kieai_client

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
    VideoModel.KLING_26_I2V,
    VideoModel.KLING_30,
    VideoModel.WAN_27_I2V,
    VideoModel.SEEDANCE_2,
    VideoModel.SEEDANCE_2_FAST,
    VideoModel.GROK_I2V,
    VideoModel.HAPPYHORSE_I2V,
    VideoModel.VEO_3,
    VideoModel.VEO_3_FAST,
    VideoModel.VEO_3_LITE,
}


# ── Entry point ───────────────────────────────────────────────────────────────

async def generate_video(
    model: VideoModel,
    prompt: str,
    image_url: str | None = None,
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
) -> VideoResult:
    if model in _VEO_MODELS:
        return await _veo_generate(model, prompt, image_url, aspect_ratio)
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
    image_url: str | None,
    last_frame_url: str | None,
    motion: MotionDirection | None,
    duration: int,
    aspect_ratio: str | None,
    resolution: str | None,
    reference_video_url: str | None,
    grok_mode: str,
    callback_url: str | None,
) -> VideoResult:
    inp: dict[str, Any] = {}
    m = model.value

    # ── Kling 2.6 T2V ────────────────────────────────────────────────────────
    if m == VideoModel.KLING_26_T2V:
        inp = {
            "prompt": prompt,
            "sound": False,
            "aspect_ratio": aspect_ratio or "16:9",
            "duration": str(duration),
        }

    # ── Kling 2.6 I2V ────────────────────────────────────────────────────────
    elif m == VideoModel.KLING_26_I2V:
        inp = {
            "prompt": prompt,
            "image_urls": [image_url] if image_url else [],
            "sound": False,
            "duration": str(duration),
        }

    # ── Kling 2.6 Motion Control ──────────────────────────────────────────────
    elif m == VideoModel.KLING_26_MOTION:
        inp = {
            "input_urls": [image_url] if image_url else [],
            "video_urls": [reference_video_url] if reference_video_url else [],
            "character_orientation": "video",
            "mode": resolution or "720p",
        }
        if prompt:
            inp["prompt"] = prompt

    # ── Kling 3.0 ─────────────────────────────────────────────────────────────
    elif m == VideoModel.KLING_30:
        inp = {
            "prompt": prompt,
            "mode": "pro",
            "sound": False,
            "duration": duration,
        }
        image_urls: list[str] = []
        if image_url:
            image_urls.append(image_url)
        if last_frame_url:
            image_urls.append(last_frame_url)
        if image_urls:
            inp["image_urls"] = image_urls

    # ── Kling 3.0 Motion Control ──────────────────────────────────────────────
    elif m == VideoModel.KLING_30_MOTION:
        inp = {
            "input_urls": [image_url] if image_url else [],
            "video_urls": [reference_video_url] if reference_video_url else [],
            "mode": "pro" if resolution == "1080p" else "std",
        }
        if prompt:
            inp["prompt"] = prompt

    # ── WAN 2.7 T2V ──────────────────────────────────────────────────────────
    elif m == VideoModel.WAN_27_T2V:
        inp = {
            "prompt": prompt,
            "resolution": resolution or "1080p",
            "ratio": aspect_ratio or "16:9",
            "duration": duration,
            "prompt_extend": True,
            "watermark": False,
        }

    # ── WAN 2.7 I2V ──────────────────────────────────────────────────────────
    elif m == VideoModel.WAN_27_I2V:
        inp = {
            "prompt": prompt,
            "first_frame_url": image_url or "",
            "duration": duration,
            "resolution": resolution or "1080p",
            "prompt_extend": True,
            "watermark": False,
        }
        if last_frame_url:
            inp["last_frame_url"] = last_frame_url

    # ── Seedance 2 / 2 Fast ───────────────────────────────────────────────────
    elif m in (VideoModel.SEEDANCE_2, VideoModel.SEEDANCE_2_FAST):
        inp = {
            "prompt": prompt,
            "resolution": resolution or "720p",
            "aspect_ratio": aspect_ratio or "16:9",
            "duration": duration,
            "generate_audio": False,
        }
        if image_url:
            inp["first_frame_url"] = image_url
        if last_frame_url:
            inp["last_frame_url"] = last_frame_url

    # ── Grok T2V ─────────────────────────────────────────────────────────────
    elif m == VideoModel.GROK_T2V:
        inp = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio or "16:9",
            "mode": grok_mode,
            "duration": str(duration),
            "resolution": resolution or "720p",
        }

    # ── Grok I2V ─────────────────────────────────────────────────────────────
    elif m == VideoModel.GROK_I2V:
        inp = {
            "prompt": prompt,
            "image_url": image_url or "",
            "mode": grok_mode,
        }
        if aspect_ratio:
            inp["aspect_ratio"] = aspect_ratio

    # ── HappyHorse T2V ────────────────────────────────────────────────────────
    elif m == VideoModel.HAPPYHORSE_T2V:
        inp = {
            "prompt": prompt,
            "resolution": resolution or "1080p",
            "aspect_ratio": aspect_ratio or "16:9",
            "duration": max(3, min(15, duration)),
        }

    # ── HappyHorse I2V ────────────────────────────────────────────────────────
    elif m == VideoModel.HAPPYHORSE_I2V:
        inp = {
            "image_urls": [image_url] if image_url else [],
            "resolution": resolution or "1080p",
            "duration": max(3, min(15, duration)),
        }
        if prompt:
            inp["prompt"] = prompt

    else:
        raise ValueError(f"Unknown video model: {model}")

    resp = await kieai_client.create_task({"model": m, "input": inp}, callback_url=callback_url)
    task_id = str(resp.get("data", {}).get("taskId") or resp.get("taskId"))
    logger.info("KIE.AI video task %s: %s", m, task_id)
    return VideoResult(task_id=task_id, provider="kieai")


# ── Veo 3 ─────────────────────────────────────────────────────────────────────

async def _veo_generate(
    model: VideoModel,
    prompt: str,
    image_url: str | None,
    aspect_ratio: str | None,
) -> VideoResult:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "model": model.value,
        "aspect_ratio": aspect_ratio or "16:9",
        "enableTranslation": True,
    }
    if image_url:
        payload["imageUrls"] = [image_url]
        payload["generationType"] = "REFERENCE_2_VIDEO"
    else:
        payload["generationType"] = "TEXT_2_VIDEO"

    resp = await kieai_client.create_veo_task(payload)
    video_id = str(resp.get("data", {}).get("videoId") or resp.get("videoId"))
    logger.info("Veo task videoId: %s", video_id)
    return VideoResult(task_id=video_id, provider="veo")


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
    state = str(data.get("state", "")).lower()

    if state == "success":
        url = data.get("videoUrl")
        if not url:
            result_urls = data.get("resultUrls", [])
            url = result_urls[0] if result_urls else None
        if url:
            return url
        raise RuntimeError("Veo3: success but no videoUrl")

    if state == "fail":
        raise RuntimeError(f"Veo3 failed: {data.get('failMsg', 'unknown error')}")

    return None


POLL_FN_MAP: dict[str, Any] = {
    "kieai": poll_kieai_status,
    "veo":   poll_veo_status,
}


def get_poll_fn(provider: str):
    fn = POLL_FN_MAP.get(provider)
    if fn is None:
        raise ValueError(f"Unknown provider: {provider}")
    return fn
