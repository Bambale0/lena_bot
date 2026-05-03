# api/video_service.py
"""
Video generation service.

Models and providers:
  kling-3.0            -> CometAPI  /kling/v1/  (provider: kling)
  kling-2.6-motion     -> CometAPI  /kling/v1/  (provider: kling)
  grok-video           -> CometAPI  /v1/video/  (provider: grok)
  grok-imagine-video   -> CometAPI  /grok/v1/   (provider: grok2)
  doubao-seedance-2-0  -> CometAPI  /v1/videos  multipart (provider: seedance)
  veo3.1-pro           -> CometAPI  /v1/videos  multipart+file (provider: veo)
  happyhorse-1.0-*     -> aivideoapi.ai          (provider: happyhorse)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from api import comet_client

logger = logging.getLogger(__name__)


class VideoModel(StrEnum):
    KLING_30 = "kling-3.0"
    KLING_26_MOTION = "kling-2.6-motion"
    GROK_VIDEO = "grok-video"
    GROK_IMAGINE = "grok-imagine-video"
    SEEDANCE_20 = "doubao-seedance-2-0"
    VEO_31_PRO = "veo3.1-pro"
    HAPPYHORSE_T2V = "happyhorse-1.0-text-to-video"
    HAPPYHORSE_I2V = "happyhorse-1.0-image-to-video"


class MotionDirection(StrEnum):
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    TILT_UP = "tilt_up"
    TILT_DOWN = "tilt_down"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    ORBIT_LEFT = "orbit_left"
    ROLL_CW = "roll_clockwise"

    def label(self) -> str:
        _labels = {
            "pan_left": "◄ Pan Left",
            "pan_right": "► Pan Right",
            "tilt_up": "▲ Tilt Up",
            "tilt_down": "▼ Tilt Down",
            "zoom_in": "🔍 Zoom In",
            "zoom_out": "🔎 Zoom Out",
            "orbit_left": "↺ Orbit",
            "roll_clockwise": "↻ Roll",
        }
        return _labels.get(self.value, self.value)


@dataclass
class VideoResult:
    task_id: str
    provider: str  # kling | grok | grok2 | seedance | veo | happyhorse


# ── Models that need image bytes (not URL) for i2v ────────────────────────────
NEEDS_IMAGE_BYTES: set[VideoModel] = {VideoModel.VEO_31_PRO}
# Models that support i2v at all
SUPPORTS_I2V: set[VideoModel] = {
    VideoModel.KLING_30,
    VideoModel.KLING_26_MOTION,
    VideoModel.GROK_VIDEO,
    VideoModel.HAPPYHORSE_I2V,
    VideoModel.SEEDANCE_20,
    VideoModel.VEO_31_PRO,
}


async def generate_video(
    model: VideoModel,
    prompt: str,
    image_url: str | None = None,
    image_bytes: bytes | None = None,
    motion: MotionDirection | None = None,
    duration: int = 5,
) -> VideoResult:
    if model in (VideoModel.KLING_30,):
        return await _kling_generate(model, prompt, image_url, duration)
    elif model == VideoModel.KLING_26_MOTION:
        return await _kling_motion_generate(prompt, image_url, motion)
    elif model == VideoModel.GROK_VIDEO:
        return await _grok_generate(prompt)
    elif model == VideoModel.GROK_IMAGINE:
        return await _grok_imagine_generate(prompt, duration)
    elif model == VideoModel.SEEDANCE_20:
        return await _seedance_generate(prompt, image_url, duration)
    elif model == VideoModel.VEO_31_PRO:
        return await _veo_generate(prompt, image_url, image_bytes)
    elif model in (VideoModel.HAPPYHORSE_T2V, VideoModel.HAPPYHORSE_I2V):
        return await _happyhorse_generate(model, prompt, image_url, duration)
    else:
        raise ValueError(f"Unknown video model: {model}")


# ── Kling ─────────────────────────────────────────────────────────────────────

async def _kling_generate(
    model: VideoModel, prompt: str, image_url: str | None, duration: int
) -> VideoResult:
    version_map = {VideoModel.KLING_30: "2.0"}
    version = version_map.get(model, "1.6")
    if image_url:
        path = "/kling/v1/videos/image2video"
        payload: dict[str, Any] = {
            "model_name": f"kling-v{version}",
            "image_url": image_url,
            "prompt": prompt,
            "duration": str(duration),
            "mode": "pro",
        }
    else:
        path = "/kling/v1/videos/text2video"
        payload = {
            "model_name": f"kling-v{version}",
            "prompt": prompt,
            "duration": str(duration),
            "mode": "pro",
        }
    resp = await comet_client.post(path, payload)
    task_id = resp["data"]["task_id"]
    logger.info("Kling task: %s", task_id)
    return VideoResult(task_id=task_id, provider="kling")


async def _kling_motion_generate(
    prompt: str, image_url: str | None, motion: MotionDirection | None
) -> VideoResult:
    payload: dict[str, Any] = {
        "model_name": "kling-v1.6",
        "prompt": prompt,
        "duration": "5",
        "mode": "pro",
    }
    if image_url:
        payload["image_url"] = image_url
    if motion:
        cfg: dict[str, int] = {"horizontal": 0, "vertical": 0, "zoom": 0, "tilt": 0, "pan": 0, "roll": 0}
        if motion == MotionDirection.PAN_LEFT:      cfg["pan"] = -10
        elif motion == MotionDirection.PAN_RIGHT:   cfg["pan"] = 10
        elif motion == MotionDirection.TILT_UP:     cfg["tilt"] = 10
        elif motion == MotionDirection.TILT_DOWN:   cfg["tilt"] = -10
        elif motion == MotionDirection.ZOOM_IN:     cfg["zoom"] = 10
        elif motion == MotionDirection.ZOOM_OUT:    cfg["zoom"] = -10
        elif motion == MotionDirection.ORBIT_LEFT:  cfg["horizontal"] = -10
        elif motion == MotionDirection.ROLL_CW:     cfg["roll"] = 10
        payload["camera_control"] = {"type": "preset_motion", "config": cfg}
    path = "/kling/v1/videos/image2video" if image_url else "/kling/v1/videos/text2video"
    resp = await comet_client.post(path, payload)
    task_id = resp["data"]["task_id"]
    logger.info("Kling motion task: %s", task_id)
    return VideoResult(task_id=task_id, provider="kling")


async def poll_kling_status(task_id: str) -> str | None:
    resp = await comet_client.get(f"/kling/v1/videos/text2video/{task_id}")
    status = resp.get("data", {}).get("task_status")
    if status == "succeed":
        videos = resp["data"].get("task_result", {}).get("videos", [])
        if videos:
            return videos[0].get("url")
    if status == "failed":
        raise RuntimeError(resp.get("data", {}).get("task_status_msg", "Kling failed"))
    return None


# ── Grok (old endpoint) ───────────────────────────────────────────────────────

async def _grok_generate(prompt: str) -> VideoResult:
    resp = await comet_client.post(
        "/v1/video/generate",
        {"model": "grok-2-vision", "prompt": prompt},
    )
    task_id = str(resp.get("task_id") or resp.get("id"))
    logger.info("Grok video task: %s", task_id)
    return VideoResult(task_id=task_id, provider="grok")


async def poll_grok_status(task_id: str) -> str | None:
    resp = await comet_client.get(f"/v1/video/generate/{task_id}")
    status = resp.get("status")
    if status == "succeeded":
        return resp.get("video_url") or resp.get("url")
    if status in ("failed", "error"):
        raise RuntimeError(f"Grok video failed: {resp.get('message', 'error')}")
    return None


# ── Grok Imagine (new endpoint /grok/v1/) ─────────────────────────────────────

async def _grok_imagine_generate(prompt: str, duration: int = 10) -> VideoResult:
    resp = await comet_client.post(
        "/grok/v1/videos/generations",
        {
            "model": "grok-imagine-video",
            "prompt": prompt,
            "duration": duration,
            "aspect_ratio": "16:9",
            "resolution": "720p",
        },
    )
    task_id = str(resp.get("request_id") or resp.get("id") or resp.get("data", {}).get("taskId"))
    logger.info("Grok Imagine task: %s", task_id)
    return VideoResult(task_id=task_id, provider="grok2")


async def poll_grok2_status(task_id: str) -> str | None:
    resp = await comet_client.get(f"/grok/v1/videos/{task_id}")
    data = resp.get("data", resp)
    status = str(data.get("status", "")).upper()
    if status == "SUCCESS":
        return data.get("data", {}).get("video", {}).get("url") or data.get("video_url")
    if status in ("FAILURE", "FAILED", "failed"):
        raise RuntimeError(f"Grok Imagine failed: {data.get('fail_reason', 'error')}")
    return None


# ── Seedance 2.0 (CometAPI /v1/videos multipart) ─────────────────────────────

async def _seedance_generate(
    prompt: str, image_url: str | None, duration: int = 5
) -> VideoResult:
    fields: dict[str, Any] = {
        "prompt": prompt,
        "model": "doubao-seedance-2-0",
        "seconds": str(duration),
        "size": "16:9",
    }
    # Seedance accepts image_url as a form field for i2v
    if image_url:
        fields["image_url"] = image_url

    # Send as multipart via files-tuple format
    files = {k: (None, v) for k, v in fields.items()}
    resp = await comet_client.post_multipart("/v1/videos", data={}, files=files)
    task_id = str(resp.get("id") or resp.get("task_id") or resp.get("data", {}).get("taskId"))
    logger.info("Seedance task: %s", task_id)
    return VideoResult(task_id=task_id, provider="seedance")


async def poll_seedance_status(task_id: str) -> str | None:
    resp = await comet_client.get(f"/v1/videos/{task_id}")
    status = str(resp.get("status", "")).lower()
    if status in ("success", "completed"):
        return resp.get("video_url") or resp.get("url") or f"https://api.cometapi.com/v1/videos/{task_id}/content"
    if status in ("failed", "error"):
        raise RuntimeError(f"Seedance failed: {resp.get('error', 'unknown error')}")
    return None


# ── Veo 3.1 Pro (CometAPI /v1/videos multipart+file) ─────────────────────────

async def _veo_generate(
    prompt: str,
    image_url: str | None = None,
    image_bytes: bytes | None = None,
) -> VideoResult:
    if image_bytes:
        # i2v: upload image as multipart file
        files: dict[str, Any] = {
            "prompt": (None, prompt),
            "model": (None, "veo3.1-pro"),
            "size": (None, "16x9"),
            "input_reference": ("reference.jpg", image_bytes, "image/jpeg"),
        }
        resp = await comet_client.post_multipart("/v1/videos", data={}, files=files)
    else:
        # t2v: plain JSON also accepted by CometAPI for Veo
        files = {
            "prompt": (None, prompt),
            "model": (None, "veo3.1-pro"),
            "size": (None, "16x9"),
        }
        resp = await comet_client.post_multipart("/v1/videos", data={}, files=files)

    task_id = str(resp.get("id") or resp.get("task_id") or resp.get("data", {}).get("taskId"))
    logger.info("Veo task: %s", task_id)
    return VideoResult(task_id=task_id, provider="veo")


async def poll_veo_status(task_id: str) -> str | None:
    resp = await comet_client.get(f"/v1/videos/{task_id}")
    data = resp.get("data", resp)
    status = str(data.get("status", "")).lower()
    if status in ("success", "completed"):
        return data.get("video_url") or data.get("url") or f"https://api.cometapi.com/v1/videos/{task_id}/content"
    if status in ("failed", "error"):
        raise RuntimeError(f"Veo failed: {data.get('error', 'unknown')}")
    return None


# ── HappyHorse (aivideoapi.ai) ────────────────────────────────────────────────

async def _happyhorse_generate(
    model: VideoModel,
    prompt: str,
    image_url: str | None,
    duration: int,
) -> VideoResult:
    from api import aivideoapi_client as hh
    payload: dict[str, Any] = {
        "model": model.value,
        "input": {
            "prompt": prompt,
            "resolution": "720p",
            "duration": max(3, min(15, duration)),
        },
    }
    if model == VideoModel.HAPPYHORSE_I2V and image_url:
        payload["input"]["image_urls"] = [image_url]
    elif model == VideoModel.HAPPYHORSE_T2V:
        payload["input"]["aspect_ratio"] = "16:9"

    resp = await hh.post("/v1/videos/generations", payload)
    task_id = str(resp.get("data", {}).get("taskId") or resp.get("taskId"))
    logger.info("HappyHorse task: %s", task_id)
    return VideoResult(task_id=task_id, provider="happyhorse")


async def poll_happyhorse_status(task_id: str) -> str | None:
    from api import aivideoapi_client as hh
    resp = await hh.get(f"/v1/tasks/{task_id}")
    status = resp.get("status", "")
    if status == "completed":
        urls = resp.get("output", {}).get("urls", [])
        if urls:
            return urls[0]
        raise RuntimeError("HappyHorse: completed but no URL in response")
    if status == "failed":
        err = resp.get("error", {}).get("message", "unknown error")
        raise RuntimeError(f"HappyHorse failed: {err}")
    return None


# ── Dispatch map: provider -> poll function ───────────────────────────────────

POLL_FN_MAP = {
    "kling":       poll_kling_status,
    "grok":        poll_grok_status,
    "grok2":       poll_grok2_status,
    "seedance":    poll_seedance_status,
    "veo":         poll_veo_status,
    "happyhorse":  poll_happyhorse_status,
}


def get_poll_fn(provider: str):
    fn = POLL_FN_MAP.get(provider)
    if fn is None:
        raise ValueError(f"Unknown provider: {provider}")
    return fn
